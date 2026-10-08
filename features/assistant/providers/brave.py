"""Bounded Brave Search API adapter for explicit Asumi web search.

Only the Search endpoint is used. Quota reservations persist in the existing
Turso/SQLite adapter and happen BEFORE outbound calls, including failures.
Never pass private Discord context to this provider.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import aiohttp

import config
from core.db import db_client


BRAVE_WEB_URL = "https://api.search.brave.com/res/v1/web/search"


@dataclass(frozen=True)
class BraveHit:
    title: str
    url: str
    description: str


@dataclass(frozen=True)
class BraveSearchResult:
    status: str
    hits: tuple[BraveHit, ...] = ()
    elapsed_ms: float = 0.0
    remaining: int | None = None
    cache_hit: bool = False


class BraveSearchAdapter:
    """Fail-closed external search with a durable account-wide monthly cap."""

    def __init__(
        self,
        *,
        api_key: str = "",
        enabled: bool = False,
        monthly_cap: int = 500,
        max_results: int = 5,
        timeout_seconds: float = 5.0,
        cooldown_seconds: float = 15.0,
        cache_ttl_seconds: float = 180.0,
    ):
        self.api_key = api_key.strip()
        self.enabled = bool(enabled and self.api_key)
        # Search is currently $5 / 1000 requests with $5 monthly credit.
        # Never allow a configuration typo to exceed the credit envelope.
        self.monthly_cap = max(1, min(int(monthly_cap), 900))
        self.max_results = max(1, min(int(max_results), 8))
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 10.0))
        self.cooldown_seconds = max(1.0, float(cooldown_seconds))
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._lock = asyncio.Lock()
        self._last_request_by_user: dict[int, float] = {}
        self._cache: dict[str, tuple[float, tuple[BraveHit, ...]]] = {}
        self._schema_ready = False

    @classmethod
    def from_env(cls) -> "BraveSearchAdapter":
        enabled = os.getenv("ASUMI_WEB_SEARCH_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on",
        }
        return cls(
            api_key=os.getenv("BRAVE_SEARCH_API_KEY", ""),
            enabled=enabled,
            monthly_cap=int(os.getenv("ASUMI_WEB_SEARCH_MONTHLY_REQUEST_CAP", "500")),
            max_results=int(os.getenv("ASUMI_WEB_SEARCH_MAX_RESULTS", "5")),
            timeout_seconds=float(os.getenv("ASUMI_WEB_SEARCH_TIMEOUT_SECONDS", "5")),
            cooldown_seconds=float(os.getenv("ASUMI_WEB_SEARCH_USER_COOLDOWN_SECONDS", "15")),
            cache_ttl_seconds=float(os.getenv("ASUMI_WEB_SEARCH_CACHE_TTL_SECONDS", "180")),
        )

    @staticmethod
    def _period() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    async def _reserve_request(self) -> int | None:
        """Atomically consume one request from durable quota or reject."""
        await db_client.connect()
        # Render's local SQLite fallback is not durable on ephemeral disks.
        # If Turso is configured but unreachable, refuse chargeable calls.
        if config.TURSO_AUTH_TOKEN and config.TURSO_DATABASE_URL and not db_client.is_cloud:
            raise RuntimeError("Durable quota database unavailable")

        if not self._schema_ready:
            await db_client.execute(
                """CREATE TABLE IF NOT EXISTS asumi_brave_usage (
                    period TEXT PRIMARY KEY,
                    requests INTEGER NOT NULL DEFAULT 0
                )"""
            )
            await db_client.commit()
            self._schema_ready = True

        period = self._period()
        await db_client.execute(
            "INSERT OR IGNORE INTO asumi_brave_usage (period, requests) VALUES (?, 0)",
            (period,),
        )
        cursor = await db_client.execute(
            """UPDATE asumi_brave_usage SET requests = requests + 1
               WHERE period = ? AND requests < ?""",
            (period, self.monthly_cap),
        )
        await db_client.commit()
        if int(cursor.rowcount or 0) != 1:
            return None

        async with db_client.execute(
            "SELECT requests FROM asumi_brave_usage WHERE period = ?",
            (period,),
        ) as result:
            row = await result.fetchone()
        return max(0, self.monthly_cap - int(row[0])) if row else 0

    @staticmethod
    def _parse_hits(data: Any, maximum: int) -> tuple[BraveHit, ...]:
        results = (
            data.get("web", {}).get("results", [])
            if isinstance(data, dict) and isinstance(data.get("web"), dict)
            else []
        )
        output: list[BraveHit] = []
        seen: set[str] = set()
        for raw in results if isinstance(results, list) else []:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen:
                continue
            title = " ".join(str(raw.get("title") or "").split())[:160]
            description = " ".join(str(raw.get("description") or "").split())[:360]
            seen.add(url)
            output.append(BraveHit(title=title or parsed.netloc, url=url, description=description))
            if len(output) >= maximum:
                break
        return tuple(output)

    async def search(self, query: str, user_id: int) -> BraveSearchResult:
        if not self.enabled:
            return BraveSearchResult(status="disabled")

        clean_query = " ".join((query or "").split())[:350]
        if not clean_query:
            return BraveSearchResult(status="empty_query")

        started = time.perf_counter()
        cache_key = clean_query.casefold()
        now = time.monotonic()

        async with self._lock:
            entry = self._cache.get(cache_key)
            if entry and entry[0] > now:
                return BraveSearchResult(
                    status="ok", hits=entry[1], cache_hit=True,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )
            last = self._last_request_by_user.get(int(user_id), -1e12)
            if now - last < self.cooldown_seconds:
                return BraveSearchResult(status="cooldown")

            try:
                remaining = await self._reserve_request()
            except Exception as exc:
                print(
                    f"⚠️ [Asumi Brave] quota DB failed closed: {type(exc).__name__}",
                    flush=True,
                )
                return BraveSearchResult(status="quota_unavailable")
            if remaining is None:
                return BraveSearchResult(status="quota_exhausted", remaining=0)

            # Reservation is conservative even if the HTTP call later fails.
            self._last_request_by_user[int(user_id)] = now

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            headers = {
                "X-Subscription-Token": self.api_key,
                "Accept": "application/json",
            }
            params = {
                "q": clean_query,
                "count": self.max_results,
                "safesearch": "moderate",
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    BRAVE_WEB_URL, headers=headers, params=params,
                ) as response:
                    if response.status in (401, 403):
                        return BraveSearchResult(status="unauthorized", remaining=remaining)
                    if response.status in (402, 429):
                        return BraveSearchResult(status="rate_limited", remaining=remaining)
                    if response.status != 200:
                        return BraveSearchResult(status="provider_error", remaining=remaining)
                    body = await response.json()
            hits = self._parse_hits(body, self.max_results)
            if self.cache_ttl_seconds > 0 and hits:
                async with self._lock:
                    if len(self._cache) >= 128:
                        self._cache.clear()
                    self._cache[cache_key] = (
                        time.monotonic() + self.cache_ttl_seconds, hits,
                    )
            return BraveSearchResult(
                status="ok" if hits else "no_results",
                hits=hits,
                remaining=remaining,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            print(
                f"⚠️ [Asumi Brave] request failed: {type(exc).__name__}",
                flush=True,
            )
            return BraveSearchResult(
                status="timeout" if isinstance(exc, asyncio.TimeoutError) else "provider_error",
                remaining=remaining,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )


brave_search = BraveSearchAdapter.from_env()
