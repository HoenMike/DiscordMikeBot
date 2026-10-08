"""On-demand Discord guild message search; no passive archive or indexing."""
from __future__ import annotations

import asyncio
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import aiohttp


DISCORD_EPOCH_MS = 1420070400000
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class HistoryHit:
    message_id: int
    channel_id: int
    author_id: int
    author_name: str
    content: str
    date: str
    jump_url: str


@dataclass(frozen=True)
class HistorySearchResult:
    status: str
    hits: tuple[HistoryHit, ...] = ()
    start_date: str = ""
    end_date: str = ""
    elapsed_ms: float = 0.0
    api_calls: int = 0
    rejected_for_permissions: int = 0


def _fold(value: str) -> str:
    s = unicodedata.normalize("NFD", (value or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")


def _snowflake(dt: datetime) -> int:
    ms = int(dt.astimezone(timezone.utc).timestamp() * 1000)
    return max(0, ms - DISCORD_EPOCH_MS) << 22


def _date_filter(query: str, now: datetime | None = None):
    """Bound common Vietnamese dates; None is a bounded query without date."""
    now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    text = _fold(query)
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else now.year
    if "nam ngoai" in text:
        year = now.year - 1

    month_match = re.search(r"\bthang\s+(1[0-2]|0?[1-9])\b", text)
    if month_match:
        month = int(month_match.group(1))
        start = datetime(year, month, 1, tzinfo=VN_TZ)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=VN_TZ)
        else:
            end = datetime(year, month + 1, 1, tzinfo=VN_TZ)
        return start, end

    if any(signal in text for signal in ("dau nam", "hoi dau nam", "dip dau nam")):
        return (
            datetime(year, 1, 1, tzinfo=VN_TZ),
            datetime(year, 4, 1, tzinfo=VN_TZ),
        )
    if year_match or "nam ngoai" in text:
        return (
            datetime(year, 1, 1, tzinfo=VN_TZ),
            datetime(year + 1, 1, 1, tzinfo=VN_TZ),
        )
    return None, None


def _terms(query: str) -> tuple[str, ...]:
    """Small bounded synonym expansions; not semantic full-server indexing."""
    folded = _fold(query)
    if any(s in folded for s in ("mua xe", "doi xe", "tau xe", "xe moi")):
        return ("mua xe", "đổi xe", "xe mới")
    if "laptop" in folded or "may tinh" in folded:
        return ("laptop", "máy tính")
    # Choose meaningful words rather than send the whole conversational question
    stops = {
        "tim", "kiem", "lai", "xem", "doan", "tin", "nhan", "chat",
        "hinh", "nhu", "the", "nao", "khong", "nho", "ve", "gi", "roi",
        "hoi", "dau", "nam", "nay", "thang", "co", "noi", "cua", "ban",
        "nguoi", "do", "truoc", "truong", "hop", "tren", "discord", "giup", "toi",
    }
    tokens = [
        token for token in re.findall(r"[a-z0-9]{2,}", folded)
        if token not in stops and not token.isdigit() and len(token) >= 3
    ]
    return (" ".join(tokens[-3:])[:100],) if tokens else ()


class DiscordHistorySearcher:
    """Bot-token REST search, with requester-specific channel checks."""

    def __init__(
        self, bot,
        *,
        enabled: bool = False,
        timeout_seconds: float = 5.0,
        max_calls: int = 3,
        max_results: int = 5,
        cooldown_seconds: float = 20.0,
    ):
        self.bot = bot
        self.enabled = bool(enabled)
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 8.0))
        self.max_calls = max(1, min(int(max_calls), 3))
        self.max_results = max(1, min(int(max_results), 5))
        self.cooldown_seconds = max(1.0, float(cooldown_seconds))
        self._last_call: dict[int, float] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_env(cls, bot):
        return cls(
            bot,
            enabled=os.getenv("ASUMI_DISCORD_HISTORY_ENABLED", "false").lower() in {
                "1", "true", "yes", "on",
            },
            timeout_seconds=float(os.getenv("ASUMI_DISCORD_HISTORY_TIMEOUT_SECONDS", "5")),
            max_calls=int(os.getenv("ASUMI_DISCORD_HISTORY_MAX_CALLS", "3")),
            max_results=int(os.getenv("ASUMI_DISCORD_HISTORY_MAX_RESULTS", "5")),
            cooldown_seconds=float(os.getenv("ASUMI_DISCORD_HISTORY_COOLDOWN_SECONDS", "20")),
        )

    @staticmethod
    def _author_ids(message) -> list[int]:
        bot_id = getattr(getattr(message, "guild", None), "me", None)
        bot_id = getattr(bot_id, "id", None)
        return list(dict.fromkeys(
            int(user.id)
            for user in (getattr(message, "mentions", None) or [])
            if getattr(user, "id", None) is not None and user.id != bot_id
        ))

    @staticmethod
    def _can_show(guild, requester, channel_id: int) -> bool:
        # Fail closed for unknown/uncached channels; exclude private threads.
        channel = None
        if hasattr(guild, "get_channel_or_thread"):
            channel = guild.get_channel_or_thread(channel_id)
        elif hasattr(guild, "get_channel"):
            channel = guild.get_channel(channel_id)
        if channel is None or getattr(channel, "type", None) is None:
            return False
        if str(getattr(channel, "type", "")).lower() == "private_thread":
            return False
        bot_member = getattr(guild, "me", None)
        if requester is None or bot_member is None:
            return False
        try:
            user_perms = channel.permissions_for(requester)
            bot_perms = channel.permissions_for(bot_member)
            if not all((
                user_perms.view_channel,
                user_perms.read_message_history,
                bot_perms.view_channel,
                bot_perms.read_message_history,
            )):
                return False
            parent = getattr(channel, "parent", None)
            if parent is not None:
                parent_perms = parent.permissions_for(requester)
                if not (parent_perms.view_channel and parent_perms.read_message_history):
                    return False
        except Exception:
            return False
        return True

    async def search(self, message, query: str) -> HistorySearchResult:
        if not self.enabled:
            return HistorySearchResult(status="disabled")
        guild = getattr(message, "guild", None)
        if guild is None:
            return HistorySearchResult(status="guild_only")
        author_ids = self._author_ids(message)
        if len(author_ids) > 1:
            return HistorySearchResult(status="multiple_authors")
        terms = _terms(query)[: self.max_calls]
        if not terms:
            return HistorySearchResult(status="missing_topic")

        token = (
            getattr(getattr(self.bot, "http", None), "token", None)
            or os.getenv("DISCORD_TOKEN", "")
        )
        if not token:
            return HistorySearchResult(status="no_bot_token")

        start, end = _date_filter(query)
        start_date = start.date().isoformat() if start else ""
        end_date = (end - timedelta(days=1)).date().isoformat() if end else ""
        started = time.perf_counter()
        async with self._lock:
            now = time.monotonic()
            owner_id = int(message.author.id)
            if now - self._last_call.get(owner_id, -1e12) < self.cooldown_seconds:
                return HistorySearchResult(status="cooldown")
            self._last_call[owner_id] = now

        requester = getattr(message, "author", None)
        if hasattr(guild, "get_member"):
            requester = guild.get_member(int(message.author.id)) or requester
        hits: list[HistoryHit] = []
        seen: set[int] = set()
        rejected = 0
        api_calls = 0

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds * self.max_calls)
            headers = {"Authorization": f"Bot {token}"}
            url = f"https://discord.com/api/v10/guilds/{int(guild.id)}/messages/search"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for term in terms:
                    params = {"content": term, "limit": 25, "sort_by": "relevance"}
                    if author_ids:
                        params["author_id"] = str(author_ids[0])
                    if start:
                        params["min_id"] = str(max(0, _snowflake(start) - 1))
                    if end:
                        params["max_id"] = str(_snowflake(end))
                    async with session.get(url, headers=headers, params=params) as response:
                        api_calls += 1
                        if response.status == 202:
                            return HistorySearchResult(
                                status="indexing", start_date=start_date,
                                end_date=end_date, api_calls=api_calls,
                            )
                        if response.status in (401, 403):
                            return HistorySearchResult(status="permission_error", api_calls=api_calls)
                        if response.status == 429:
                            return HistorySearchResult(status="rate_limited", api_calls=api_calls)
                        if response.status != 200:
                            return HistorySearchResult(status="api_error", api_calls=api_calls)
                        data = await response.json()

                    groups = data.get("messages", []) if isinstance(data, dict) else []
                    for group in groups if isinstance(groups, list) else []:
                        for item in group if isinstance(group, list) else []:
                            if not isinstance(item, dict):
                                continue
                            try:
                                msg_id = int(item["id"])
                                channel_id = int(item["channel_id"])
                                author = item["author"]
                                user_id = int(author["id"])
                            except (KeyError, ValueError, TypeError):
                                continue
                            if msg_id in seen:
                                continue
                            if author_ids and user_id != author_ids[0]:
                                continue
                            if not self._can_show(guild, requester, channel_id):
                                rejected += 1
                                continue
                            content = str(item.get("content") or "").strip()
                            if not content:
                                continue
                            # Discord search can provide approximate hits; let
                            # user verify via original source, never invent text.
                            seen.add(msg_id)
                            hits.append(HistoryHit(
                                message_id=msg_id,
                                channel_id=channel_id,
                                author_id=user_id,
                                author_name=str(author.get("global_name") or author.get("username") or "Unknown")[:80],
                                content=content[:600],
                                date=str(item.get("timestamp") or "")[:10],
                                jump_url=(
                                    f"https://discord.com/channels/{guild.id}/{channel_id}/{msg_id}"
                                ),
                            ))
                            if len(hits) >= self.max_results:
                                break
                        if len(hits) >= self.max_results:
                            break
                    if len(hits) >= self.max_results:
                        break

        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
            print(
                f"⚠️ [Asumi History] API error: {type(exc).__name__}",
                flush=True,
            )
            return HistorySearchResult(
                status="timeout" if isinstance(exc, asyncio.TimeoutError) else "api_error",
                start_date=start_date, end_date=end_date, api_calls=api_calls,
            )

        return HistorySearchResult(
            status="ok" if hits else "no_results",
            hits=tuple(hits),
            start_date=start_date,
            end_date=end_date,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            api_calls=api_calls,
            rejected_for_permissions=rejected,
        )
