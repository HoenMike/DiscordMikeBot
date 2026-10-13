"""Opt-in Codex reset alerts. No role ping until the guild admin enables it."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from html import unescape
import re
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from core import constants as policy
from features.codex_watch.signals import (
    extract_signals, extract_backup_signals, merge_signals,
    format_alert, forecast_warning,
    format_forecast_alert, parse_time,
)
from features.codex_watch.store import codex_watch_store, WatchStorageError

FEED = "https://codex-reset.com/api/feed"
BACKUP = "https://didcodexreset.com/openapi/v1/records?page=1&pageSize=10"
FORECAST = "https://codex-reset.com/api/forecast"
OBSERVATORY = "https://codex.gussuriworks.com/en"
TOKYO = ZoneInfo("Asia/Tokyo")
LA = ZoneInfo("America/Los_Angeles")


async def read_public(session: aiohttp.ClientSession, url: str, *, json_mode: bool):
    """Only hardcoded public HTTPS endpoints, strict redirects/size/time limits."""
    async with session.get(url, allow_redirects=False) as response:
        if response.status != 200:
            raise ValueError("Public source unavailable")
        content = await response.content.read(256 * 1024 + 1)
        if len(content) > 256 * 1024:
            raise ValueError("Public source too large")
        if json_mode:
            import json
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError("Invalid JSON root")
            return value
        return content.decode("utf-8")


def parse_independent_forecast(markup: str, now: datetime) -> tuple[int, int] | None:
    """A second UNOFFICIAL forecast; not a completion confirmation."""
    markup = re.sub(r"(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", markup)
    clean = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", markup)))
    age = re.search(r"Last updated:\s*([A-Z][a-z]+ \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M JST)", clean)
    if age is None:
        return None
    try:
        try:
            updated = datetime.strptime(age.group(1), "%b %d, %Y, %I:%M %p JST").replace(tzinfo=TOKYO)
        except ValueError:
            updated = datetime.strptime(age.group(1), "%B %d, %Y, %I:%M %p JST").replace(tzinfo=TOKYO)
        if not timedelta(0) <= now.astimezone(timezone.utc) - updated.astimezone(timezone.utc) <= timedelta(hours=12):
            return None
        h24 = re.search(r"Within 24h\s*(\d{1,3})%", clean)
        h48 = re.search(r"Within 48h\s*(\d{1,3})%", clean)
        if h24 is None or h48 is None:
            return None
        values = (int(h24.group(1)), int(h48.group(1)))
        return values if all(0 <= v <= 100 for v in values) else None
    except ValueError:
        return None


class CodexWatch(commands.GroupCog, group_name="codex-watch",
                 group_description="Codex global reset alerts"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        try:
            await codex_watch_store.initialize()
        except WatchStorageError as exc:
            print(f"[CodexWatch] safe idle, no Turso: {exc}", flush=True)
        self.poll.start()

    async def cog_unload(self):
        self.poll.cancel()

    def _permitted(self, channel: discord.TextChannel, role: discord.Role) -> bool:
        member = channel.guild.me
        if member is None:
            return False
        perms = channel.permissions_for(member)
        return (
            perms.view_channel and perms.send_messages
            and (role.mentionable or perms.mention_everyone)
            and role.guild.id == channel.guild.id
        )

    @app_commands.command(name="setup", description="Lưu kênh và role; mặc định tắt cảnh báo")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel,
                    role: discord.Role):
        if interaction.guild is None or channel.guild.id != interaction.guild.id or role.guild.id != interaction.guild.id:
            await interaction.response.send_message("Channel/role phải cùng server.", ephemeral=True)
            return
        if role.is_default() or role.managed:
            await interaction.response.send_message("Chọn role thường, không phải @everyone/bot role.", ephemeral=True)
            return
        if not self._permitted(channel, role):
            await interaction.response.send_message(
                "Asumi cần View Channel, Send Messages và quyền mention role (role mentionable hoặc bot được Mention All Roles).",
                ephemeral=True,
            )
            return
        try:
            await codex_watch_store.setup(interaction.guild.id, channel.id, role.id)
        except WatchStorageError as exc:
            await interaction.response.send_message(f"Không lưu được: {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ Đã lưu {channel.mention} và role {discord.utils.escape_mentions(role.name)}.\n"
            "Watch đang TẮT, chưa gửi ping. Dùng lệnh /codex-watch preview để xem thử, "
            "sau đó /codex-watch enable để bật.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="preview", description="Xem thử cảnh báo; KHÔNG ping role")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def preview(self, interaction: discord.Interaction):
        try:
            cfg = await codex_watch_store.get(interaction.guild_id)
        except WatchStorageError:
            cfg = None
        if cfg is None:
            await interaction.response.send_message("Chưa setup Watch.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        content = "Chưa tìm được tín hiệu mới phù hợp."
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                feed = await read_public(session, FEED, json_mode=True)
                items = extract_signals(feed, datetime.now(timezone.utc))
                if items:
                    content = format_alert(items[-1])
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            content = (
                "🟠 **CODEX GLOBAL RESET — ĐÃ CÔNG BỐ**\n"
                "⚠️ Đây chỉ là mẫu, chưa xác nhận có reset thực tế."
            )
        await interaction.followup.send(
            "**Preview — không tag bất kỳ role nào**\n" + content,
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            suppress_embeds=True,
        )

    @app_commands.command(name="enable", description="Bật thông báo và ping role cho tin MỚI")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enable(self, interaction: discord.Interaction):
        try:
            cfg = await codex_watch_store.get(interaction.guild_id)
            if cfg is None:
                await interaction.response.send_message("Hãy setup trước.", ephemeral=True)
                return
            channel = interaction.guild.get_channel(cfg.channel_id)
            role = interaction.guild.get_role(cfg.role_id)
            if not isinstance(channel, discord.TextChannel) or role is None or not self._permitted(channel, role):
                await interaction.response.send_message("Channel/role/quyền ping không hợp lệ. Setup lại.", ephemeral=True)
                return
            await codex_watch_store.set_enabled(interaction.guild_id, True)
        except WatchStorageError as exc:
            await interaction.response.send_message(f"Không bật được: {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            "✅ Watch đã bật. Kiểm tra 5 phút/lần, chỉ tin MỚI kể từ bây giờ. "
            "Mọi cảnh báo kể cả banked đều tag role được chọn.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="disable", description="Tắt toàn bộ thông báo Codex")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction):
        try:
            found = await codex_watch_store.set_enabled(interaction.guild_id, False)
        except WatchStorageError as exc:
            await interaction.response.send_message(f"Không lưu được: {exc}", ephemeral=True)
            return
        await interaction.response.send_message("✅ Đã tắt Watch." if found else "Chưa setup.", ephemeral=True)

    @app_commands.command(name="status", description="Xem trạng thái Watch")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction):
        try:
            cfg = await codex_watch_store.get(interaction.guild_id)
        except WatchStorageError:
            await interaction.response.send_message("Turso không khả dụng; Watch fail-closed.", ephemeral=True)
            return
        if cfg is None:
            await interaction.response.send_message("Watch chưa setup.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Codex Watch **{'ON' if cfg.enabled else 'OFF'}**\n"
            f"Channel <#{cfg.channel_id}> · Role <@&{cfg.role_id}>\n"
            "Chu kỳ 5 phút, chống trùng bằng Turso, link preview bị tắt. "
            "Mọi cảnh báo bao gồm banked đều ping role khi bật.",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _send(self, cfg, event_key: str, source: str, body: str):
        guild = self.bot.get_guild(cfg.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(cfg.channel_id)
        role = guild.get_role(cfg.role_id)
        if not isinstance(channel, discord.TextChannel) or role is None or not self._permitted(channel, role):
            return
        latest = await codex_watch_store.get(cfg.guild_id)
        if latest != cfg or not latest.enabled:
            return
        if not await codex_watch_store.claim(cfg.guild_id, event_key, source):
            return
        try:
            msg = await channel.send(
                f"<@&{role.id}>\n{body}",
                allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role], replied_user=False),
                suppress_embeds=True,  # no X unfurl / URL onebox
            )
        except (discord.Forbidden, discord.HTTPException):
            await codex_watch_store.failed(cfg.guild_id, event_key)
            return
        await codex_watch_store.complete(cfg.guild_id, event_key, msg.id)

    async def _cycle(self):
        configs = await codex_watch_store.enabled_configs()
        if not configs:
            return
        now = datetime.now(timezone.utc)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            # One tracker being unavailable must not disable the other.
            primary, secondary = [], []
            try:
                feed = await read_public(session, FEED, json_mode=True)
                primary = extract_signals(feed, now)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            try:
                mirror = await read_public(session, BACKUP, json_mode=True)
                secondary = extract_backup_signals(mirror, now)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            events = merge_signals(primary, secondary)
            for cfg in configs:
                for event in events:
                    if event.posted_at <= cfg.active_after:
                        continue
                    day = event.posted_at.astimezone(LA).date()
                    event_key = f"tibo:{day}:{event.stage}"
                    await self._send(cfg, event_key, event.url, format_alert(event))
            if any(event.stage == "announced" for event in events):
                return
            forecast = await read_public(session, FORECAST, json_mode=True)
            try:
                updated = parse_time(forecast["updated_at"])
                if not timedelta(0) <= now - updated <= timedelta(hours=12):
                    return
                p = forecast["probabilities"]
                p24, p48 = int(p["model_24h"]), int(p["model_48h"])
                if max(p24, p48) <= 75:
                    return
            except (KeyError, TypeError, ValueError):
                return
            html = await read_public(session, OBSERVATORY, json_mode=False)
            second = parse_independent_forecast(html, now)
            if not forecast_warning(forecast, second):
                return
            for cfg in configs:
                if now <= cfg.active_after:
                    continue
                key = "forecast:" + now.astimezone(LA).strftime("%Y-%m-%d")
                body = format_forecast_alert("https://codex-reset.com/", p24, p48, *second)
                await self._send(cfg, key, "https://codex-reset.com/", body)

    @tasks.loop(minutes=policy.ASUMI_CODEX_WATCH_INTERVAL_MINUTES)
    async def poll(self):
        try:
            await self._cycle()
        except (WatchStorageError, ValueError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            print(f"[CodexWatch] skipped: {type(exc).__name__}: {exc}", flush=True)
        except Exception as exc:
            print(f"[CodexWatch] unexpected: {type(exc).__name__}", flush=True)

    @poll.before_loop
    async def ready(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(CodexWatch(bot))
