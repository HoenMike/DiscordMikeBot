"""Non-official structured fallback for Vietnamese retail fuel prices.

Used only after the original publisher cannot be read (HTTP 403/HTML mismatch).
VietFuelAPI is community-maintained, not PVOIL or a government source. Dates,
indicated source count, declared units and plausible values must validate.
Never silently label these figures as verified first-party PVOIL.
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from core import constants as policy

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
API_URL = "https://vietfuel-api.tranqui.workers.dev/api/fuel-prices"

@dataclass(frozen=True)
class FuelAggregate:
    status: str
    effective_date: str = ""
    provider: str = "VietFuelAPI"
    rows: tuple[tuple[str, int], ...] = ()
    source_url: str = API_URL
    elapsed_ms: float = 0.0

def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFD", (text or "").casefold())
    return "".join(ch for ch in norm if unicodedata.category(ch) != "Mn").replace("đ", "d")

def _classify(name: str) -> tuple[str, str] | None:
    text = _fold(name).replace(" ", "")
    if "e10" in text and "ron95" in text and ("iii" in text or "-3" in text):
        return "e10", "E10 RON95-III"
    if "e5" in text and "ron92" in text:
        return "e5", "E5 RON92-II"
    if ("diesel" in text or "diezen" in text or "dau" in text or text.startswith("do")) and "0,05" in text or (
        ("diesel" in text or "diezen" in text or text.startswith("do")) and "0.05" in text
    ):
        return "do_005", "Dầu DO 0,05S"
    return None

def _fresh_timestamp(value: str, *, now: datetime) -> bool:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        age = now - stamp.astimezone(VN_TZ)
        return timedelta(seconds=-300) <= age <= timedelta(hours=policy.ASUMI_FUEL_AGGREGATE_MAX_SCRAPE_AGE_HOURS)
    except (ValueError, TypeError):
        return False

def parse_fuel_aggregate(data: object, *, now: datetime | None = None) -> FuelAggregate:
    now = now or datetime.now(VN_TZ)
    if not isinstance(data, dict) or data.get("success") is not True or data.get("status") != "ok":
        return FuelAggregate(status="invalid_response")
    meta, items = data.get("meta"), data.get("data")
    if not isinstance(meta, dict) or not isinstance(items, list) or len(items) > 120:
        return FuelAggregate(status="invalid_response")
    raw_date = meta.get("priceDate")
    try:
        effective = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return FuelAggregate(status="missing_price_date")
    days = (now.date() - effective).days
    if not 0 <= days <= policy.ASUMI_FUEL_AGGREGATE_MAX_PRICE_AGE_DAYS:
        return FuelAggregate(status="stale_price_date")
    if not _fresh_timestamp(meta.get("scrapedAt"), now=now):
        return FuelAggregate(status="stale_cache")
    if not isinstance(meta.get("sourceCount"), int) or meta["sourceCount"] < 1:
        return FuelAggregate(status="missing_source")
    found: dict[str, tuple[str, int]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        classified = _classify(str(item.get("name") or ""))
        if not classified:
            continue
        key, label = classified
        if key in found:
            continue
        unit = _fold(str(item.get("unit") or "")).replace(" ", "")
        if unit and not any(x in unit for x in ("vnd/lit", "vnd/l", "dong/lit", "đ/lit")):
            continue
        value = item.get("region1")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 10_000 <= value <= 80_000:
            continue
        if float(value) != int(value):
            continue
        found[key] = (label, int(value))
    rows = tuple(found[key] for key in ("e10", "e5", "do_005") if key in found)
    if len(rows) < 2:
        return FuelAggregate(status="missing_prices")
    return FuelAggregate(status="ok", effective_date=effective.isoformat(), rows=rows)

class VietFuelReader:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._cache: FuelAggregate | None = None
        self._cache_until = 0.0

    async def fetch(self) -> FuelAggregate:
        if not policy.ASUMI_FUEL_AGGREGATE_ENABLED:
            return FuelAggregate(status="disabled")
        async with self._lock:
            if self._cache is not None and time.monotonic() < self._cache_until:
                return self._cache
            started = time.perf_counter()
            result = FuelAggregate(status="unavailable")
            timeout = aiohttp.ClientTimeout(total=policy.ASUMI_FUEL_AGGREGATE_TIMEOUT_SECONDS)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        API_URL,
                        headers={"Accept": "application/json", "User-Agent": "Asumi/3.7.7"},
                        allow_redirects=False,
                    ) as response:
                        if response.status != 200:
                            result = FuelAggregate(status=f"http_{response.status}")
                        elif "application/json" not in response.headers.get("Content-Type", "").lower():
                            result = FuelAggregate(status="invalid_content_type")
                        else:
                            body = await response.content.read(131073)
                            if len(body) > 131072:
                                result = FuelAggregate(status="too_large")
                            else:
                                import json
                                result = parse_fuel_aggregate(json.loads(body))
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
                result = FuelAggregate(status=type(exc).__name__)
            result = FuelAggregate(
                status=result.status, effective_date=result.effective_date,
                rows=result.rows, elapsed_ms=(time.perf_counter()-started)*1000,
            )
            self._cache = result
            self._cache_until = time.monotonic() + (
                policy.ASUMI_FUEL_AGGREGATE_CACHE_SECONDS if result.status == "ok" else 45
            )
            return result

vietfuel_reader = VietFuelReader()
