"""Restore bounded @Asumi conversational requests lost during a Render redeploy.

Discord gateway events are NOT persisted while a bot is disconnected. A
durable Turso timestamp plus Discord channel history is our source of truth.
Only explicit human mentions are eligible; never replay slash/prefix/admin,
Feedback, or state-changing assistant tools. No message content is stored.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import discord

from core.db import db_client
from features.assistant.trigger import has_explicit_mention, strip_bot_mention

# Keep all non-secret knobs in source, not Render Environment.
LOOKBACK_SECONDS = 15 * 60
FIRST_BOOT_LOOKBACK_SECONDS = 2 * 60
HEARTBEAT_SECONDS = 60
CLAIM_LEASE_SECONDS = 90
MAX_RETRIES = 2
MAX_CHANNELS = 80
MAX_MESSAGES_PER_CHANNEL = 100
MAX_PENDING = 60

RECOVERY_ACK = "⏳ **Asumi vừa kết nối lại** — mình đã tìm được lời nhắn lúc cập nhật và đang xử lý."


def eligible_replay(message, bot_user_id: int | None) -> bool:
    """A deliberately strict gate before automatically doing anything."""
    if (getattr(message.author, "bot", False)
            or not getattr(message, "guild", None)
            or not has_explicit_mention(message, bot_user_id)):
        return False
    query = strip_bot_mention(message.content or "", bot_user_id).strip()
    if not query or query.startswith((".m", ".M", "/", "!", ".")):
        return False
    from features.feedback.intent import detect_feedback
    if detect_feedback(query):
        return False
    return True


def already_answered(message, channel_messages, bot_user_id: int) -> bool:
    """Skip delivered responses; a recovery progress note is not an answer."""
    for candidate in channel_messages:
        if getattr(getattr(candidate, "author", None), "id", None) != bot_user_id:
            continue
        ref = getattr(candidate, "reference", None)
        if (getattr(ref, "message_id", None) == message.id
                and not (getattr(candidate, "content", "") or "").startswith(RECOVERY_ACK)):
            return True
    return False


class DeployRecovery:
    def __init__(self, store=None):
        self.store = store or db_client
        self._schema_ready = False
        self._recovery_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None

    async def _ready_store(self) -> bool:
        await self.store.connect()
        if not self.store.is_cloud:
            # Never promise durability on Render's ephemeral local SQLite.
            return False
        if not self._schema_ready:
            await self.store.execute(
                """CREATE TABLE IF NOT EXISTS asumi_deploy_gateway (
                    key TEXT PRIMARY KEY, last_seen REAL NOT NULL
                )"""
            )
            await self.store.execute(
                """CREATE TABLE IF NOT EXISTS asumi_deploy_queue (
                    message_id TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )"""
            )
            await self.store.commit()
            self._schema_ready = True
        return True

    async def register(self, message) -> bool:
        """Persist an incoming mention before starting an assistant response."""
        try:
            if not await self._ready_store():
                return False
            now = time.time()
            await self.store.execute(
                """INSERT OR IGNORE INTO asumi_deploy_queue
                   (message_id,guild_id,channel_id,author_id,created_at,status,attempts,updated_at)
                   VALUES (?,?,?,?,?,'pending',0,?)""",
                (str(message.id), str(message.guild.id), str(message.channel.id),
                 str(message.author.id), message.created_at.timestamp(), now),
            )
            await self.store.commit()
            return True
        except Exception as exc:
            print(f"[Asumi Recovery] durable register failed: {type(exc).__name__}", flush=True)
            return False

    async def claim(self, message_id: int) -> bool:
        """CAS claim: even overlapping old/new instances cannot both execute."""
        now = time.time()
        result = await self.store.execute(
            """UPDATE asumi_deploy_queue
               SET status='processing', attempts=attempts+1, updated_at=?
               WHERE message_id=? AND attempts<?
                 AND (status='pending' OR
                      (status='processing' AND updated_at<?))""",
            (now, str(message_id), MAX_RETRIES, now - CLAIM_LEASE_SECONDS),
        )
        await self.store.commit()
        return int(result.rowcount or 0) == 1

    async def finish(self, message_id: int, *, done: bool) -> None:
        await self.store.execute(
            """UPDATE asumi_deploy_queue SET status=?, updated_at=?
               WHERE message_id=?""",
            ("done" if done else "pending", time.time(), str(message_id)),
        )
        await self.store.commit()

    async def heartbeat(self) -> None:
        if not await self._ready_store():
            return
        await self.store.execute(
            """INSERT INTO asumi_deploy_gateway(key,last_seen)
               VALUES('discord',?)
               ON CONFLICT(key) DO UPDATE SET last_seen=excluded.last_seen""",
            (time.time(),),
        )
        await self.store.commit()

    async def _last_seen(self) -> float | None:
        if not await self._ready_store():
            return None
        async with self.store.execute(
            "SELECT last_seen FROM asumi_deploy_gateway WHERE key='discord'"
        ) as cur:
            row = await cur.fetchone()
        return float(row[0]) if row else None

    async def _heartbeat_loop(self, bot) -> None:
        while not bot.is_closed():
            await asyncio.sleep(HEARTBEAT_SECONDS)
            if bot.is_ready():
                try:
                    await self.heartbeat()
                except Exception as exc:
                    print(f"[Asumi Recovery] heartbeat unavailable: {type(exc).__name__}", flush=True)

    async def on_ready(self, bot) -> None:
        """Run after Discord gateway becomes ready; don't block other events."""
        async with self._recovery_lock:
            try:
                if not await self._ready_store():
                    print("[Asumi Recovery] Turso unavailable: startup recovery disabled", flush=True)
                    return
                previous = await self._last_seen()
                now = time.time()
                # A never-before-seen deployment gets only a tiny bootstrap
                # window; no full guild crawl or historical command replay.
                seconds = (FIRST_BOOT_LOOKBACK_SECONDS if previous is None
                           else min(LOOKBACK_SECONDS, max(90, now - previous + 70)))
                cutoff = now - seconds
                await self.recover(bot, cutoff=cutoff)
                await self.heartbeat()
                if self._heartbeat_task is None or self._heartbeat_task.done():
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(bot))
            except Exception as exc:
                print(f"[Asumi Recovery] startup recovery error: {type(exc).__name__}: {exc}", flush=True)

    @staticmethod
    def _can_read(bot, channel) -> bool:
        guild = getattr(channel, "guild", None)
        me = getattr(guild, "me", None)
        if not me:
            return False
        try:
            p = channel.permissions_for(me)
            return bool(p.view_channel and p.read_message_history and p.send_messages)
        except Exception:
            return False

    async def _replay(self, bot, message, known_messages) -> None:
        bot_id = bot.user.id
        if not eligible_replay(message, bot_id):
            return
        if not self._can_read(bot, message.channel):
            return
        if not isinstance(message.author, discord.Member):
            # A departed user must not have private requests retried.
            return
        if not message.channel.permissions_for(message.author).view_channel:
            return
        if already_answered(message, known_messages, bot_id):
            await self.register(message)
            await self.finish(message.id, done=True)
            return
        if not await self.register(message) or not await self.claim(message.id):
            return
        ack = None
        done = False
        try:
            ack = await message.reply(
                RECOVERY_ACK, mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            assistant = bot.get_cog("AssistantCog")
            if assistant is None:
                raise RuntimeError("AssistantCog not available")
            done = bool(await assistant.handle_conversation_message(
                message, recovery_mode=True,
            ))
        except (discord.Forbidden, discord.NotFound):
            # Missing permissions/deleted messages must not create retries.
            done = True
        except Exception as exc:
            print(f"[Asumi Recovery] replay {message.id} failed: {type(exc).__name__}", flush=True)
            if ack is not None:
                try:
                    await ack.edit(content="⚠️ Asumi đã nhận lại lời nhắn nhưng xử lý chưa xong. Bạn có thể thử nhắc lại.")
                except Exception:
                    pass
        finally:
            try:
                await self.finish(message.id, done=done)
            except Exception:
                pass
            if done and ack is not None:
                try:
                    await ack.delete()
                except Exception:
                    pass

    async def recover(self, bot, *, cutoff: float) -> int:
        """Bounded channel-history reconciliation, oldest messages first."""
        total = 0
        channels = []
        for guild in bot.guilds:
            channels.extend(
                channel for channel in [*guild.text_channels, *guild.threads]
                if self._can_read(bot, channel)
            )
            if len(channels) >= MAX_CHANNELS:
                break
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        for channel in channels[:MAX_CHANNELS]:
            try:
                messages = [
                    m async for m in channel.history(
                        limit=MAX_MESSAGES_PER_CHANNEL,
                        after=cutoff_dt, oldest_first=True,
                    )
                ]
            except (discord.Forbidden, discord.HTTPException):
                continue
            except Exception as exc:
                print(f"[Asumi Recovery] channel scan failed: {type(exc).__name__}", flush=True)
                continue
            for message in messages:
                if eligible_replay(message, bot.user.id):
                    await self._replay(bot, message, messages)
                    total += 1
                    if total >= MAX_PENDING:
                        print("[Asumi Recovery] bounded recovery limit reached", flush=True)
                        return total
        if total:
            print(f"[Asumi Recovery] inspected {total} missed-mention candidates", flush=True)
        return total


deploy_recovery = DeployRecovery()
