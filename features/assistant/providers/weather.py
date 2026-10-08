"""Structured public forecast facts for Asumi.

Never synthesize weather from unrelated AQI/search snippets. Uses the Open-Meteo
public forecast API (key-free for eligible noncommercial use), with public
place-name geocoding only when the city is not in the preverified shortlist.
No private Discord context, arbitrary URLs, or generated "current" figures.
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

from core import constants as policy


FORECAST_API = "https://api.open-meteo.com/v1/forecast"
GEOCODE_API = "https://geocoding-api.open-meteo.com/v1/search"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Geographic coordinates are static public place data, not user's location.
KNOWN_PLACES = (
    ("biên hòa", "Biên Hòa, Đồng Nai", 10.95738, 106.84268),
    ("bien hoa", "Biên Hòa, Đồng Nai", 10.95738, 106.84268),
    ("hồ chí minh", "TP. Hồ Chí Minh", 10.8231, 106.6297),
    ("sài gòn", "TP. Hồ Chí Minh", 10.8231, 106.6297),
    ("hà nội", "Hà Nội", 21.0285, 105.8542),
    ("đà nẵng", "Đà Nẵng", 16.0544, 108.2022),
    ("cần thơ", "Cần Thơ", 10.0452, 105.7469),
)

WEATHER_DESCRIPTIONS = {
    0: "Trời quang",
    1: "Ít mây",
    2: "Có mây",
    3: "Nhiều mây",
    45: "Có sương mù",
    48: "Sương mù đóng băng",
    51: "Mưa phùn nhẹ", 53: "Mưa phùn", 55: "Mưa phùn dày",
    61: "Mưa nhẹ", 63: "Mưa", 65: "Mưa lớn",
    71: "Tuyết nhẹ", 73: "Có tuyết", 75: "Tuyết dày",
    80: "Mưa rào nhẹ", 81: "Mưa rào", 82: "Mưa rào mạnh",
    95: "Giông", 96: "Giông có mưa đá", 99: "Giông mạnh có mưa đá",
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").replace("đ", "d")


def parse_weather_place(query: str) -> tuple[str, float, float] | str | None:
    """A stated city is required; unknown cities go through VN geocoding."""
    folded = _fold(query)
    for key, display, lat, lon in KNOWN_PLACES:
        if _fold(key) in folded:
            return display, lat, lon

    candidate = re.sub(
        r"(?i)^(?:cho mình (?:xem|biết)\s+|xem\s+|dự báo\s+)*"
        r"(?:thời tiết|nhiệt độ)\s+(?:ở\s+|tại\s+|khu vực\s+)?",
        "", query.strip(),
    )
    candidate = re.split(
        r"(?i)\b(?:hôm nay|ngày mai|bây giờ|hiện tại|tối nay|sáng nay|"
        r"thế nào|như nào|ra sao|bao nhiêu|có mưa|không|được không)\b",
        candidate, maxsplit=1,
    )[0].strip(" ?,!.")
    candidate = re.sub(r"(?i)^(?:ở|tại)\s+", "", candidate).strip()
    # "thời tiết hôm nay" has no declared city. Do not infer the user location.
    if not candidate or candidate == query or len(candidate) > 60:
        return None
    return candidate


@dataclass(frozen=True)
class WeatherFacts:
    status: str
    place: str = ""
    measured_at: str = ""
    temp_c: float | None = None
    feels_c: float | None = None
    humidity_pct: int | None = None
    condition: str = ""
    low_c: float | None = None
    high_c: float | None = None
    rain_probability_pct: int | None = None
    rain_mm: float | None = None
    source_url: str = FORECAST_API
    elapsed_ms: float = 0.0


class OpenMeteoWeather:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, WeatherFacts]] = {}

    async def _lookup(self, session, place: str) -> tuple[str, float, float] | None:
        async with session.get(GEOCODE_API, params={
            "name": place, "count": 5, "format": "json", "language": "vi",
            "countryCode": "VN",
        }, allow_redirects=False) as response:
            if response.status != 200:
                return None
            data = await response.json(content_type=None)
        if not isinstance(data, dict):
            return None
        for item in data.get("results", [])[:5]:
            if not isinstance(item, dict) or item.get("country_code") != "VN":
                continue
            try:
                lat, lon = float(item["latitude"]), float(item["longitude"])
            except (TypeError, ValueError, KeyError):
                continue
            if 8 <= lat <= 24 and 102 <= lon <= 110:
                name = str(item.get("name") or place)[:65]
                admin = str(item.get("admin1") or "")[:50]
                return f"{name}, {admin}" if admin and admin != name else name, lat, lon
        return None

    async def fetch(self, query: str) -> WeatherFacts:
        if not policy.ASUMI_WEATHER_ENABLED:
            return WeatherFacts(status="disabled")
        place = parse_weather_place(query)
        if place is None:
            return WeatherFacts(status="missing_location")
        started = time.perf_counter()
        key = _fold(str(place))
        async with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            timeout = aiohttp.ClientTimeout(total=policy.ASUMI_WEATHER_TIMEOUT_SECONDS)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    chosen = place if isinstance(place, tuple) else await self._lookup(session, place)
                    if chosen is None:
                        return WeatherFacts(status="unknown_location", place=str(place))
                    name, lat, lon = chosen
                    params = {
                        "latitude": lat, "longitude": lon,
                        "timezone": "Asia/Ho_Chi_Minh", "forecast_days": 1,
                        "current": (
                            "temperature_2m,apparent_temperature,"
                            "relative_humidity_2m,weather_code,precipitation"
                        ),
                        "daily": (
                            "temperature_2m_min,temperature_2m_max,"
                            "precipitation_probability_max,precipitation_sum"
                        ),
                    }
                    async with session.get(
                        FORECAST_API, params=params, allow_redirects=False
                    ) as response:
                        if response.status != 200:
                            return WeatherFacts(status="unavailable", place=name)
                        data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    return WeatherFacts(status="unavailable", place=name)
                current = data.get("current") or {}
                daily = data.get("daily") or {}
                if not isinstance(current, dict) or not isinstance(daily, dict):
                    return WeatherFacts(status="unavailable", place=name)
                def first(field):
                    value = daily.get(field)
                    return value[0] if isinstance(value, list) and value else None
                temp, stamp = current.get("temperature_2m"), current.get("time")
                if not isinstance(temp, (int, float)) or not isinstance(stamp, str):
                    return WeatherFacts(status="unavailable", place=name)
                # Timestamp is supplied in requested time zone by Open-Meteo.
                measured = datetime.fromisoformat(stamp)
                now = datetime.now(VN_TZ)
                if abs((now.replace(tzinfo=None) - measured).total_seconds()) > 7200:
                    return WeatherFacts(status="stale", place=name)
                def numeric(value):
                    return float(value) if isinstance(value, (int, float)) else None
                def whole(value):
                    return int(round(value)) if isinstance(value, (int, float)) else None
                facts = WeatherFacts(
                    status="ok", place=name, measured_at=stamp,
                    temp_c=numeric(temp),
                    feels_c=numeric(current.get("apparent_temperature")),
                    humidity_pct=whole(current.get("relative_humidity_2m")),
                    condition=WEATHER_DESCRIPTIONS.get(current.get("weather_code"), "Chưa rõ"),
                    low_c=numeric(first("temperature_2m_min")),
                    high_c=numeric(first("temperature_2m_max")),
                    rain_probability_pct=whole(first("precipitation_probability_max")),
                    rain_mm=numeric(first("precipitation_sum")),
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )
                self._cache[key] = (
                    time.monotonic() + policy.ASUMI_WEATHER_CACHE_SECONDS,
                    facts,
                )
                if len(self._cache) > 40:
                    self._cache = {key: self._cache[key]}
                return facts
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
                return WeatherFacts(status="unavailable", place=str(place))


weather_provider = OpenMeteoWeather()
