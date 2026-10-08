"""Bounded first-party source reading for Vietnam retail fuel prices.

Do NOT use this as an arbitrary URL fetcher. The only URLs that can be requested
are the two hardcoded PVOIL public HTTPS pages. Redirects (including cross-host)
are blocked and response bodies are capped. This is intentionally independent
of private Discord session data.
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import aiohttp

from core import constants as policy

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
OFFICIAL_PVOIL_URLS = (
    "https://www.pvoil.com.vn/tin-gia-xang-dau",
    "https://www.pvoil.com.vn/",
    "https://www.pvoil.com.vn/tin-tuc",
)

_PRODUCTS = (
    ("e10", "Xăng E10 RON95-III"),
    ("e5", "Xăng E5 RON92-II"),
    ("diesel_005", "Dầu DO 0,05S-II"),
    ("diesel_0001", "Dầu DO 0,001S-V"),
)
_DATE = re.compile(
    r"(?:Giá\s+điều\s+chỉnh\s+(?:lúc|từ)|Price\s+adjusted\s+from)"
    r"\s*(\d{1,2})\s*[:h]\s*(\d{2})\s*(?:ngày|date)?\s*"
    r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})",
    re.IGNORECASE,
)
_AMOUNT = re.compile(r"(?<!\d)(\d{1,3}[.,]\d{3}|\d{5,6})(?!\d)")


@dataclass(frozen=True)
class VerifiedFuelPrice:
    label: str
    vnd_per_liter: int


@dataclass(frozen=True)
class VerifiedFuelReport:
    status: str
    effective_at: datetime | None = None
    rows: tuple[VerifiedFuelPrice, ...] = ()
    source_url: str = ""
    elapsed_ms: float = 0.0


class _OfficialPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in {"td", "th"} and self.current_cell is not None:
            if self.current_row is not None:
                self.current_row.append(" ".join(" ".join(self.current_cell).split()))
            self.current_cell = None
        if tag == "tr" and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None

    def handle_data(self, data):
        if self.skip_depth or not data.strip():
            return
        self.text.append(data.strip())
        if self.current_cell is not None:
            self.current_cell.append(data.strip())


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value).casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").replace("đ", "d")


def _product_key(text: str) -> str | None:
    folded = _fold(text)
    if re.search(r"\bE10\s*RON\s*95\b", folded, re.I):
        return "e10"
    if re.search(r"\bE5\s*RON\s*92\b", folded, re.I):
        return "e5"
    if "DO" in text.upper() or "diesel" in folded:
        if re.search(r"0[,.]001\s*S", text, re.I):
            return "diesel_0001"
        if re.search(r"0[,.]05\s*S", text, re.I):
            return "diesel_005"
    return None


def _vnd(value: str) -> int | None:
    match = _AMOUNT.search(value)
    if not match:
        return None
    number = int(match.group(1).replace(".", "").replace(",", ""))
    return number if 10_000 <= number <= 90_000 else None


def parse_pvoil_prices(html: str, *, now: datetime | None = None) -> VerifiedFuelReport:
    """Extract price only when an official effective date and product agree."""
    now = now or datetime.now(VN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    parser = _OfficialPage()
    try:
        parser.feed(html[: policy.ASUMI_FUEL_SOURCE_MAX_RESPONSE_BYTES])
    except Exception:
        return VerifiedFuelReport(status="unreadable")
    flat = " ".join(parser.text)
    dates: list[datetime] = []
    for m in _DATE.finditer(flat):
        try:
            value = datetime(
                int(m.group(5)), int(m.group(4)), int(m.group(3)),
                int(m.group(1)), int(m.group(2)), tzinfo=VN_TZ,
            )
            if datetime(2020, 1, 1, tzinfo=VN_TZ) <= value <= now:
                dates.append(value)
        except ValueError:
            continue
    if not dates:
        return VerifiedFuelReport(status="missing_effective_date")
    # PVOIL's current page has one published effective date. Ignore dates
    # later than now and never silently label a future schedule "current".
    effective = max(dates)
    found: dict[str, int] = {}
    for cells in parser.rows:
        for i, cell in enumerate(cells):
            key = _product_key(cell)
            if key is None or key in found:
                continue
            for candidate in cells[i + 1 : i + 3]:
                value = _vnd(candidate)
                if value is not None:
                    found[key] = value
                    break
    # The homepage also contains a compact price block instead of table rows.
    # Search each product name only in a small local window, never globally
    # pairing an unrelated date/price from the rest of the website.
    patterns = {
        "e10": r"Xăng\s+E10\s+RON\s*95(?:[-\s]*III)?",
        "e5": r"Xăng\s+E5\s+RON\s*92(?:[-\s]*II)?",
        "diesel_005": r"Dầu\s+DO\s+0[,.]05\s*S(?:[-\s]*II)?",
        "diesel_0001": r"Dầu\s+DO\s+0[,.]001\s*S(?:[-\s]*V)?",
    }
    for key, pattern in patterns.items():
        if key in found:
            continue
        match = re.search(pattern, flat, re.IGNORECASE)
        if match:
            nearby = flat[match.end(): match.end() + 65]
            price_match = _AMOUNT.search(nearby)
            if price_match:
                prefix = nearby[:price_match.start()]
                suffix = nearby[price_match.end(): price_match.end() + 8]
                # Never steal a later product's price if this one is missing.
                # Official PVOIL page formats every valid price with currency.
                crossed_product = re.search(r"\b(?:Xăng|Dầu|Diesel)\b", prefix, re.I)
                if not crossed_product and re.match(r"\s*(?:đ|₫|VND)", suffix, re.I):
                    found_value = _vnd(price_match.group(1))
                    if found_value is not None:
                        found[key] = found_value

    if len(found) < 2:
        return VerifiedFuelReport(status="missing_prices")
    rows = tuple(
        VerifiedFuelPrice(label=label, vnd_per_liter=found[key])
        for key, label in _PRODUCTS if key in found
    )
    return VerifiedFuelReport(status="ok", effective_at=effective, rows=rows)


class PVOILPriceReader:
    """One bounded attempt across two known first-party pages, with TTL."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._cached_until = 0.0
        self._cached: VerifiedFuelReport | None = None

    async def fetch(self) -> VerifiedFuelReport:
        if not policy.ASUMI_FUEL_SOURCE_ENABLED:
            return VerifiedFuelReport(status="disabled")
        async with self._lock:
            if self._cached and time.monotonic() < self._cached_until:
                return self._cached
            started = time.perf_counter()
            selected = VerifiedFuelReport(status="unavailable")
            timeout = aiohttp.ClientTimeout(total=policy.ASUMI_FUEL_SOURCE_TIMEOUT_SECONDS)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    for url in OFFICIAL_PVOIL_URLS:
                        try:
                            async with session.get(
                                url,
                                headers={"Accept": "text/html", "User-Agent": "AsumiBot/3.7 (+public-source-verification)"},
                                allow_redirects=False,
                            ) as response:
                                if response.status != 200:
                                    continue
                                if "text/html" not in response.headers.get("Content-Type", ""):
                                    continue
                                body = await response.content.read(
                                    policy.ASUMI_FUEL_SOURCE_MAX_RESPONSE_BYTES + 1
                                )
                                if len(body) > policy.ASUMI_FUEL_SOURCE_MAX_RESPONSE_BYTES:
                                    continue
                                candidate = parse_pvoil_prices(body.decode("utf-8", "replace"))
                                if candidate.status == "ok" and (
                                    selected.effective_at is None
                                    or candidate.effective_at > selected.effective_at
                                    or (candidate.effective_at == selected.effective_at
                                        and len(candidate.rows) > len(selected.rows))
                                ):
                                    selected = VerifiedFuelReport(
                                        status="ok", effective_at=candidate.effective_at,
                                        rows=candidate.rows, source_url=url,
                                        elapsed_ms=(time.perf_counter() - started) * 1000,
                                    )
                        except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError):
                            continue
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            if selected.status != "ok":
                selected = VerifiedFuelReport(
                    status="unavailable",
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )
            self._cached = selected
            self._cached_until = time.monotonic() + (
                policy.ASUMI_FUEL_SOURCE_CACHE_SECONDS
                if selected.status == "ok" else 45
            )
            return selected


pvoil_reader = PVOILPriceReader()
