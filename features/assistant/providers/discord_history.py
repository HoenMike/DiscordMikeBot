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
    channel_name: str = ""


@dataclass(frozen=True)
class HistorySearchResult:
    status: str
    hits: tuple[HistoryHit, ...] = ()
    sort_mode: str = "relevance"
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


def _temporal_request(query: str) -> tuple[str, int] | None:
    """Recognize author-first chronological requests, never approximate 'đầu năm'."""
    folded = _fold(query)
    oldest = (
        r"\b(?:tin nhan|doan chat)(?:\s+\w+){0,2}\s+(?:dau tien|cu nhat|som nhat)\b",
        r"\blan dau(?: tien)?\b",
    )
    newest = (
        r"\b(?:tin nhan|doan chat)(?:\s+\w+){0,2}\s+(?:gan nhat|moi nhat|cuoi cung)\b",
        r"\blan cuoi(?: cung)?\b",
    )
    mode = (
        "oldest" if any(re.search(p, folded) for p in oldest)
        else "newest" if any(re.search(p, folded) for p in newest)
        else ""
    )
    if not mode:
        return None
    count = re.search(r"\b([1-5])\s+(?:tin nhan|doan chat|message)\b", folded)
    return mode, int(count.group(1)) if count else 1


def _temporal_terms(query: str) -> tuple[str, ...]:
    """An author-only first/last request must not search the words 'đầu tiên'."""
    if any(s in _fold(query) for s in ("mua xe", "doi xe", "tau xe", "xe moi")):
        return _terms(query)
    folded = _fold(re.sub(r"<@!?\d+>", " ", query))
    topic = re.search(
        r"\b(?:nhac (?:toi|den)|noi ve|de cap (?:toi|den)|ve)\s+(.+)$",
        folded,
    )
    if not topic:
        return ("",)
    value = re.split(
        r"\b(?:trong server|tren discord|trong discord|la khi nao|luc nao|khong)\b",
        topic.group(1),
        maxsplit=1,
    )[0].strip(" ?.,!").strip()
    return (value[:100],) if value else ("",)


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
        from core import constants as policy
        return cls(
            bot,
            enabled=policy.ASUMI_DISCORD_HISTORY_ENABLED,
            timeout_seconds=policy.ASUMI_DISCORD_HISTORY_TIMEOUT_SECONDS,
            max_calls=policy.ASUMI_DISCORD_HISTORY_MAX_CALLS,
            max_results=policy.ASUMI_DISCORD_HISTORY_MAX_RESULTS,
            cooldown_seconds=policy.ASUMI_DISCORD_HISTORY_COOLDOWN_SECONDS,
        )

    @staticmethod
    def _author_ids(message, query: str = "") -> list[int]:
        bot_id = getattr(getattr(message, "guild", None), "me", None)
        bot_id = getattr(bot_id, "id", None)
        authors = list(dict.fromkeys(
            int(user.id)
            for user in (getattr(message, "mentions", None) or [])
            if getattr(user, "id", None) is not None and user.id != bot_id
        ))
        # Explicit people always win. In Discord a mention of Asumi itself is
        # NOT the person being searched. Vietnamese self-references such as
        # "của t", "của tôi" and "mình đã nhắn" resolve to the requester.
        if authors:
            return authors
        folded = _fold(query).replace("đ", "d")
        own_message = (
            re.search(r"\bcua\s+(?:t|toi|tui|minh|em|tao|ban than)\b", folded)
            or re.search(
                r"\b(?:t|toi|tui|minh|em|tao)\s+(?:da\s+)?(?:nhan|gui|viet|noi)\b",
                folded,
            )
            or re.search(r"\b(?:my messages|my first message|my last message)\b", folded)
        )
        if own_message:
            requester_id = getattr(getattr(message, "author", None), "id", None)
            if requester_id is not None:
                return [int(requester_id)]
        return []

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
        author_ids = self._author_ids(message, query)
        if len(author_ids) > 1:
            return HistorySearchResult(status="multiple_authors")
        temporal = _temporal_request(query)
        sort_mode, requested_count = temporal if temporal else ("relevance", self.max_results)
        if temporal and not author_ids:
            return HistorySearchResult(status="missing_author", sort_mode=sort_mode)
        terms = (
            _temporal_terms(query) if temporal else _terms(query)
        )[: self.max_calls]
        if not terms:
            return HistorySearchResult(status="missing_topic")
        result_limit = min(self.max_results, requested_count)

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
        live_verifications = 0
        max_live_verifications = min(12, max(2, self.max_results * 2))
        per_term_verifications = (
            max(1, max_live_verifications // len(terms)) if temporal else max_live_verifications
        )

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds * self.max_calls)
            headers = {"Authorization": f"Bot {token}"}
            url = f"https://discord.com/api/v10/guilds/{int(guild.id)}/messages/search"
            # One total deadline for all search variants AND live re-fetches.
            async with asyncio.timeout(
                max(2.0, min(self.timeout_seconds * self.max_calls, 12.0))
            ):
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    for term in terms:
                        if live_verifications >= max_live_verifications:
                            break
                        checked_this_term = 0
                        params = {
                            "limit": 25,
                            "sort_by": "timestamp" if temporal else "relevance",
                        }
                        if temporal:
                            params["sort_order"] = "asc" if sort_mode == "oldest" else "desc"
                        if term:
                            params["content"] = term
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
                                # Discord search index can lag behind edits/deletes.
                                # Re-fetch the live message (bounded by max_results)
                                # after requester + bot ACL checks, then use its text.
                                if (
                                    live_verifications >= max_live_verifications
                                    or (temporal and checked_this_term >= per_term_verifications)
                                ):
                                    break
                                live_verifications += 1
                                checked_this_term += 1
                                channel = (
                                    guild.get_channel_or_thread(channel_id)
                                    if hasattr(guild, "get_channel_or_thread")
                                    else guild.get_channel(channel_id)
                                )
                                fetch_message = getattr(channel, "fetch_message", None)
                                if fetch_message is None:
                                    continue
                                try:
                                    live = await asyncio.wait_for(
                                        fetch_message(msg_id), timeout=2.0,
                                    )
                                except Exception:
                                    continue
                                live_author = getattr(getattr(live, "author", None), "id", None)
                                if live_author != user_id or getattr(live, "id", None) != msg_id:
                                    continue
                                content = (getattr(live, "content", "") or "").strip()
                                if not content:
                                    continue

                                seen.add(msg_id)
                                hits.append(HistoryHit(
                                    message_id=msg_id,
                                    channel_id=channel_id,
                                    author_id=user_id,
                                    author_name=str(
                                        getattr(live.author, "display_name", None)
                                        or author.get("global_name")
                                        or author.get("username")
                                        or "Unknown"
                                    )[:80],
                                    content=content[:600],
                                    date=str(item.get("timestamp") or "")[:10],
                                    channel_name=str(getattr(channel, "name", "") or "")[:80],
                                    jump_url=(
                                        f"https://discord.com/channels/{guild.id}/{channel_id}/{msg_id}"
                                    ),
                                ))
                                if len(hits) >= result_limit and not temporal:
                                    break
                            if (
                                (len(hits) >= result_limit and not temporal)
                                or live_verifications >= max_live_verifications
                                or (temporal and checked_this_term >= per_term_verifications)
                            ):
                                break
                        if (
                            (len(hits) >= result_limit and not temporal)
                            or live_verifications >= max_live_verifications
                        ):
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

        if temporal:
            hits.sort(key=lambda hit: hit.message_id, reverse=(sort_mode == "newest"))
        return HistorySearchResult(
            status="ok" if hits else "no_results",
            hits=tuple(hits[:result_limit]),
            sort_mode=sort_mode,
            start_date=start_date,
            end_date=end_date,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            api_calls=api_calls,
            rejected_for_permissions=rejected,
        )
