"""Bounded, model-based public AQI report for Biên Hòa (not station readings)."""
from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

from core import constants as policy

AQI_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
PLACE = "Biên Hòa, Đồng Nai"
LAT, LON = 10.95738, 106.84268
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class AirQualityFacts:
    status: str
    place: str = PLACE
    model_time: str = ""
    aqi: int | None = None
    pm25: float | None = None
    timeline: tuple[tuple[str, int], ...] = ()
    source_url: str = AQI_API
    elapsed_ms: float = 0


def aqi_label(value: int) -> str:
    if value <= 50:
        return "Tốt"
    if value <= 100:
        return "Trung bình"
    if value <= 150:
        return "Không tốt cho nhóm nhạy cảm"
    if value <= 200:
        return "Có hại cho sức khỏe"
    if value <= 300:
        return "Rất có hại"
    return "Nguy hiểm"


def _number(value, *, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= maximum:
        return None
    return number


def parse_aqi_response(payload: dict, now: datetime | None = None) -> AirQualityFacts:
    if not isinstance(payload, dict):
        return AirQualityFacts(status="unavailable")
    current, hourly = payload.get("current"), payload.get("hourly")
    if not isinstance(current, dict) or not isinstance(hourly, dict):
        return AirQualityFacts(status="unavailable")
    raw_stamp = current.get("time")
    aqi = _number(current.get("us_aqi"), maximum=500)
    pm25 = _number(current.get("pm2_5"), maximum=2000)
    if not isinstance(raw_stamp, str) or aqi is None or pm25 is None:
        return AirQualityFacts(status="unavailable")
    try:
        stamp = datetime.fromisoformat(raw_stamp)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=VN_TZ)
        stamp = stamp.astimezone(VN_TZ)
        real_now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    except (ValueError, TypeError):
        return AirQualityFacts(status="unavailable")
    if abs((real_now - stamp).total_seconds()) > 3 * 3600:
        return AirQualityFacts(status="stale")

    times, values = hourly.get("time"), hourly.get("us_aqi")
    if not isinstance(times, list) or not isinstance(values, list):
        return AirQualityFacts(status="unavailable")
    timeline = []
    for raw_time, raw_aqi in zip(times[:72], values[:72]):
        valid = _number(raw_aqi, maximum=500)
        if not isinstance(raw_time, str) or valid is None:
            continue
        try:
            moment = datetime.fromisoformat(raw_time)
            moment = moment.replace(tzinfo=VN_TZ) if moment.tzinfo is None else moment.astimezone(VN_TZ)
        except ValueError:
            continue
        # Forecast points only, never present them as sensor observations.
        if moment >= stamp and moment <= stamp.replace(hour=23, minute=0, second=0):
            timeline.append((moment.strftime("%Hh"), int(round(valid))))
    # Drawing requires two distinct future points; short data is still valid.
    return AirQualityFacts(
        status="ok", model_time=stamp.strftime("%H:%M %d/%m/%Y"),
        aqi=int(round(aqi)), pm25=round(pm25, 1),
        timeline=tuple(timeline[:16]),
    )


class OpenMeteoAirQuality:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._cache: tuple[float, AirQualityFacts] | None = None

    async def fetch(self) -> AirQualityFacts:
        if not policy.ASUMI_AQI_ENABLED:
            return AirQualityFacts(status="disabled")
        async with self._lock:
            if self._cache and self._cache[0] > time.monotonic():
                return self._cache[1]
            started = time.perf_counter()
            try:
                timeout = aiohttp.ClientTimeout(total=policy.ASUMI_AQI_TIMEOUT_SECONDS)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        AQI_API, params={
                            "latitude": LAT, "longitude": LON,
                            "current": "us_aqi,pm2_5",
                            "hourly": "us_aqi", "forecast_days": 1,
                            "timezone": "Asia/Ho_Chi_Minh",
                        },
                        allow_redirects=False,
                    ) as response:
                        if response.status != 200:
                            return AirQualityFacts(status="unavailable")
                        if response.content_length and response.content_length > 192 * 1024:
                            return AirQualityFacts(status="unavailable")
                        raw = await response.content.read(192 * 1024 + 1)
                        if len(raw) > 192 * 1024:
                            return AirQualityFacts(status="unavailable")
                facts = parse_aqi_response(json.loads(raw))
                if facts.status == "ok":
                    facts = AirQualityFacts(
                        **{**facts.__dict__, "elapsed_ms": (time.perf_counter() - started) * 1000}
                    )
                    self._cache = (time.monotonic() + policy.ASUMI_AQI_CACHE_SECONDS, facts)
                return facts
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
                return AirQualityFacts(status="unavailable")


aqi_provider = OpenMeteoAirQuality()
