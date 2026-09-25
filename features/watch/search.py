"""
features/watch/search.py - Search provider interface, Brave Search integration,
URL normalization, fingerprinting, search cache, and query budget gate.
"""

import asyncio
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import aiohttp
import config
from features.watch.models import SearchResult, SearchUsage


# Common tracking parameters to strip during canonicalization
TRACKING_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "gclsrc",
    "msclkid",
    "yclid",
    "mc_eid",
    "_hsenc",
    "_hsmi",
    "igshid",
    "si",
    "ref",
    "ref_src",
}


def canonicalize_url(url: str) -> str:
    """
    Safely normalizes a URL by stripping tracking parameters, lowercasing scheme/host,
    removing empty query strings, removing fragments, and trimming trailing slashes.
    Preserves meaningful query parameters (like v=, id=, article=).
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        if not scheme:
            scheme = "https"
        netloc = parsed.netloc.lower()
        # Remove standard ports
        if scheme == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        elif scheme == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]

        # Strip tracking query parameters
        clean_query_pairs = []
        if parsed.query:
            for k, v in parse_qsl(parsed.query, keep_blank_values=True):
                if k.lower() not in TRACKING_PARAMS:
                    clean_query_pairs.append((k, v))
        clean_query_pairs.sort(key=lambda x: x[0])
        new_query = urlencode(clean_query_pairs)

        # Normalize path
        path = parsed.path
        if path.endswith("/") and len(path) > 1:
            path = path[:-1]

        # Omit fragment
        return urlunparse((scheme, netloc, path, "", new_query, ""))
    except Exception:
        return url.strip()


def compute_fingerprint(canonical_url: str, title: str = "", domain: str = "") -> str:
    """
    Computes a stable hash fingerprint for deduplication.
    Prefers canonical URL. Fallback: domain + title.
    """
    clean_url = canonical_url.strip()
    if clean_url:
        return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()[:32]
    fallback_data = f"{domain.strip().lower()}|{title.strip().lower()}"
    return hashlib.sha256(fallback_data.encode("utf-8")).hexdigest()[:32]


class SearchCache:
    """In-memory bounded TTL cache for SearchResult lists."""

    def __init__(self, ttl_hours: float = 6.0):
        self._ttl_seconds = ttl_hours * 3600
        self._cache: Dict[str, Tuple[float, List[SearchResult]]] = {}
        self._lock = asyncio.Lock()

    def _normalize_key(self, query: str, provider: str = "brave") -> str:
        clean = " ".join(query.strip().lower().split())
        return f"{provider}:{clean}"

    async def get(self, query: str, provider: str = "brave") -> Optional[List[SearchResult]]:
        key = self._normalize_key(query, provider)
        now = time.monotonic()
        async with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            cached_at, results = entry
            if now - cached_at > self._ttl_seconds:
                self._cache.pop(key, None)
                return None
            return results

    async def set(self, query: str, results: List[SearchResult], provider: str = "brave") -> None:
        key = self._normalize_key(query, provider)
        now = time.monotonic()
        async with self._lock:
            # Simple eviction if cache grows beyond 500 keys
            if len(self._cache) > 500:
                expired = [k for k, (t, _) in self._cache.items() if now - t > self._ttl_seconds]
                for k in expired:
                    self._cache.pop(k, None)
                if len(self._cache) > 500:
                    # Evict oldest 100 entries
                    oldest = sorted(self._cache.items(), key=lambda x: x[1][0])[:100]
                    for k, _ in oldest:
                        self._cache.pop(k, None)
            self._cache[key] = (now, results)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()


class SearchError(Exception):
    """Base exception for search operations."""
    pass


class BraveNotConfiguredError(SearchError):
    """Raised when Brave API key is not configured."""
    pass


class BudgetExhaustedError(SearchError):
    """Raised when monthly search budget is exhausted."""
    pass


class SearchProvider:
    """Abstract interface for Web search providers."""

    async def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        raise NotImplementedError


class BraveSearchProvider(SearchProvider):
    """
    Async search provider for Brave Search Web API.
    Handles auth, timeouts, 429 backoff, transient 5xx retry, and normalization.
    """

    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None):
        self.api_key = api_key or getattr(config, "BRAVE_SEARCH_API_KEY", "")
        self.session = session
        self._own_session: Optional[aiohttp.ClientSession] = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session and not self.session.closed:
            return self.session
        if self._own_session and not self._own_session.closed:
            return self._own_session
        self._own_session = aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (compatible; AsumiBot/2.9; +https://discord.app)"}
        )
        return self._own_session

    async def close(self) -> None:
        if self._own_session and not self._own_session.closed:
            await self._own_session.close()
            self._own_session = None

    async def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """
        Executes a web search query via Brave Search API.
        Returns a list of normalized SearchResult objects.
        """
        if not self.is_configured():
            raise BraveNotConfiguredError(
                "🔭 Watch chưa thể tìm kiếm Web vì Brave Search chưa được cấu hình."
            )

        session = await self._get_session()
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key.strip(),
        }
        params = {
            "q": query.strip(),
            "count": min(max(1, limit), 20),
            "text_decorations": "0",
            "spellcheck": "0",
        }

        # Bounded request: initial + at most 1 retry for transient failure
        last_error = None
        for attempt in range(1, 3):
            try:
                async with session.get(
                    self.ENDPOINT,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10.0),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        return self._parse_brave_response(data)
                    elif resp.status in (401, 403):
                        text = await resp.text()
                        raise SearchError(f"Brave Search xác thực thất bại (HTTP {resp.status}): {text[:100]}")
                    elif resp.status == 429:
                        raise SearchError("Brave Search bị giới hạn tần suất (HTTP 429 Too Many Requests).")
                    elif resp.status >= 500:
                        last_error = SearchError(f"Brave Search máy chủ lỗi (HTTP {resp.status})")
                        if attempt < 2:
                            await asyncio.sleep(1.5)
                            continue
                        raise last_error
                    else:
                        text = await resp.text()
                        raise SearchError(f"Brave Search phản hồi bất thường (HTTP {resp.status}): {text[:100]}")
            except (asyncio.TimeoutError, aiohttp.ClientError) as err:
                last_error = err
                if attempt < 2:
                    await asyncio.sleep(1.5)
                    continue
                raise SearchError(f"Lỗi mạng khi kết nối Brave Search: {err}") from err

        raise SearchError(f"Tìm kiếm Brave thất bại sau các lần thử: {last_error}")

    def _parse_brave_response(self, data: Dict[str, Any]) -> List[SearchResult]:
        results: List[SearchResult] = []
        if not isinstance(data, dict):
            return results

        web_block = data.get("web") or {}
        raw_items = web_block.get("results") or []

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            raw_url = (item.get("url") or "").strip()
            if not title or not raw_url:
                continue

            snippet = (item.get("description") or "").strip()
            canonical_url = canonicalize_url(raw_url)
            parsed_host = urlparse(canonical_url).netloc

            # Extract source domain or fallback
            profile = item.get("profile") or {}
            domain = profile.get("name") or parsed_host or "Web"

            published_at = item.get("page_age") or item.get("age") or None
            fp = compute_fingerprint(canonical_url, title, domain)

            results.append(
                SearchResult(
                    title=title,
                    url=raw_url,
                    canonical_url=canonical_url,
                    snippet=snippet,
                    source_domain=domain,
                    published_at=str(published_at) if published_at else None,
                    fingerprint=fp,
                    metadata={"extra_snippets": item.get("extra_snippets") or []},
                )
            )

        return results


def get_current_month_key(dt: Optional[datetime] = None) -> str:
    """Returns the current month key e.g. '2026-09'."""
    now = dt or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def get_remaining_days_in_month(dt: Optional[datetime] = None) -> int:
    """Calculates remaining calendar days in current month including today."""
    now = dt or datetime.now(timezone.utc)
    # Next month first day minus 1 day gives days in month
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    last_day_of_month = (next_month - timedelta(days=1)).day
    return max(1, last_day_of_month - now.day + 1)


def calculate_daily_allowance(limit: int, used: int, dt: Optional[datetime] = None) -> float:
    """Calculates suggested soft daily search allowance based on days left in month."""
    remaining = max(0, limit - used)
    days_left = get_remaining_days_in_month(dt)
    return round(remaining / days_left, 1)

