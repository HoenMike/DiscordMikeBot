"""Dated Vùng 1 fuel prices from a public third-party price history page.

Unlike PVOIL, WebGia.TV's HTML page is reachable from GitHub CI runners.
This is a public, non-official aggregator: never present it as PVOIL-verified.
Only extract figures from table rows containing a matching product, the Vùng 1
column and a plausible, recent effective date. No user URL or query is fetched.
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
WEBGIA_URL = "https://webgia.tv/xang-dau/petrolimex"
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d{3})+|\d{5,6})(?!\d)")

@dataclass(frozen=True)
class FuelAggregate:
    status: str
    effective_date: str = ""
    rows: tuple[tuple[str, int], ...] = ()
    provider: str = "WebGia.TV"
    source_url: str = WEBGIA_URL
    elapsed_ms: float = 0.0

def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value).casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").replace("đ", "d")

def _type(text: str) -> tuple[str, str] | None:
    s = _fold(text).replace(" ", "")
    if "e10" in s and "ron95" in s and "iii" in s:
        return "e10", "Xăng E10 RON95-III"
    if "e5" in s and "ron92" in s:
        return "e5", "Xăng E5 RON92-II"
    if any(x in s for x in ("diesel", "dau", "do0")) and any(x in s for x in ("0,05", "0.05")):
        return "diesel", "Dầu diesel 0,05S-II"
    return None

def _amount(text: str) -> int | None:
    m = PRICE_RE.search(str(text))
    if not m:
        return None
    value = int(m.group(1).replace(".", ""))
    return value if 10_000 <= value <= 80_000 else None

class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.skip: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "noscript"):
            self.skip.append(tag)
        if self.skip:
            return
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in ("td", "th") and self.cell is not None:
            if self.row is not None:
                self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.skip or not data.strip():
            return
        if self.cell is not None:
            self.cell.append(data.strip())

def parse_webgia_fuel(html: str, *, now: datetime | None = None) -> FuelAggregate:
    now = now or datetime.now(VN_TZ)
    parser = _TableRows()
    try:
        parser.feed(html[:policy.ASUMI_FUEL_AGGREGATE_MAX_BYTES])
    except Exception:
        return FuelAggregate(status="invalid_html")
    # Require a table declaring Vùng 1; never guess column offsets from a
    # random page or price chart.
    if not any(
        any(_fold(c).strip() == "vung 1" for c in row)
        and any("mat hang" in _fold(c) for c in row)
        for row in parser.rows
    ):
        return FuelAggregate(status="missing_table_header")

    entries: dict[str, dict[str, tuple[str, int]]] = {}
    for row in parser.rows:
        if len(row) < 5:
            continue
        product = _type(row[0])
        if product is None:
            continue
        amount = _amount(row[1])
        if amount is None:
            continue
        effective_date = None
        for cell in reversed(row[2:]):
            m = DATE_RE.search(cell)
            if m:
                try:
                    stamp = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
                    if 0 <= (now.date() - stamp).days <= policy.ASUMI_FUEL_AGGREGATE_MAX_PRICE_AGE_DAYS:
                        effective_date = stamp.isoformat()
                except ValueError:
                    pass
                break
        if effective_date:
            key, label = product
            entries.setdefault(effective_date, {})[key] = (label, amount)

    if not entries:
        return FuelAggregate(status="missing_recent_period")
    latest = max(entries)
    found = entries[latest]
    rows = tuple(found[k] for k in ("e10", "e5", "diesel") if k in found)
    if len(rows) < 2:
        return FuelAggregate(status="missing_prices")
    return FuelAggregate(status="ok", effective_date=latest, rows=rows)

class WebGiaReader:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._cache: FuelAggregate | None = None
        self._until = 0.0

    async def fetch(self) -> FuelAggregate:
        if not policy.ASUMI_FUEL_AGGREGATE_ENABLED:
            return FuelAggregate(status="disabled")
        async with self._lock:
            if self._cache and time.monotonic() < self._until:
                return self._cache
            started = time.perf_counter()
            report = FuelAggregate(status="unavailable")
            timeout = aiohttp.ClientTimeout(total=policy.ASUMI_FUEL_AGGREGATE_TIMEOUT_SECONDS)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        WEBGIA_URL,
                        headers={"Accept": "text/html", "User-Agent": "AsumiBot/3.7.7"},
                        allow_redirects=False,
                    ) as response:
                        if response.status != 200:
                            report = FuelAggregate(status=f"http_{response.status}")
                        elif "text/html" not in response.headers.get("Content-Type", "").lower():
                            report = FuelAggregate(status="invalid_content_type")
                        else:
                            body = await response.content.read(policy.ASUMI_FUEL_AGGREGATE_MAX_BYTES + 1)
                            if len(body) > policy.ASUMI_FUEL_AGGREGATE_MAX_BYTES:
                                report = FuelAggregate(status="too_large")
                            else:
                                report = parse_webgia_fuel(body.decode("utf-8", "replace"))
            except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError, ValueError) as exc:
                report = FuelAggregate(status=type(exc).__name__)
            report = FuelAggregate(
                status=report.status, effective_date=report.effective_date,
                rows=report.rows, elapsed_ms=(time.perf_counter()-started)*1000,
            )
            if report.status != "ok":
                print("[Asumi Fuel] WebGia unavailable: "+report.status, flush=True)
            self._cache = report
            self._until = time.monotonic() + (
                policy.ASUMI_FUEL_AGGREGATE_CACHE_SECONDS if report.status=="ok" else 45
            )
            return report

webgia_reader = WebGiaReader()
