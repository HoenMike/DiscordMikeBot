"""Asumi must answer the user's weather/fuel question, not dump search links."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from features.assistant.providers.weather import (
    OpenMeteoWeather, WeatherFacts, FORECAST_API, parse_weather_place,
)
from features.assistant.providers.pvoil_prices import VerifiedFuelReport, VerifiedFuelPrice
from features.assistant.providers.brave import BraveSearchResult, BraveHit
from features.assistant.router import route_message
from features.assistant.tools import CommandToolRegistry

VN = ZoneInfo("Asia/Ho_Chi_Minh")


class FactRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_route_without_brave_or_clef(self):
        result = await route_message("thời tiết biên hòa hôm nay như nào")
        self.assertEqual(result.tool, "weather.forecast")
        self.assertEqual(result.source, "local_weather_facts")

    async def test_weather_private_chat_does_not_leave_discord(self):
        result = await route_message("thời tiết trong tin nhắn <@123456789012345678> hôm nay")
        self.assertIsNone(result.tool)

    def test_named_weather_location_not_inferred_from_user(self):
        self.assertIsNone(parse_weather_place("thời tiết hôm nay như nào"))
        place = parse_weather_place("thời tiết biên hòa hôm nay")
        self.assertEqual(place[0], "Biên Hòa, Đồng Nai")


class StructuredWeatherTests(unittest.IsolatedAsyncioTestCase):
    async def test_openmeteo_answer_has_real_temperature_rain_and_timestamp(self):
        calls = []
        timestamp = datetime.now(VN).strftime("%Y-%m-%dT%H:%M")
        class Reply:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def json(self, **kwargs):
                return {
                    "current": {
                        "time": timestamp, "temperature_2m": 30.2,
                        "apparent_temperature": 34.5,
                        "relative_humidity_2m": 78,
                        "weather_code": 3,
                    },
                    "daily": {
                        "temperature_2m_min": [26.0],
                        "temperature_2m_max": [33.0],
                        "precipitation_probability_max": [80],
                        "precipitation_sum": [6.2],
                    },
                }
        class Session:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            def get(self, url, **kwargs):
                calls.append((url, kwargs))
                return Reply()
        with patch("features.assistant.providers.weather.aiohttp.ClientSession", Session):
            facts = await OpenMeteoWeather().fetch("thời tiết biên hòa hôm nay")
        self.assertEqual(facts.status, "ok")
        self.assertEqual(facts.temp_c, 30.2)
        self.assertEqual(facts.rain_probability_pct, 80)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], FORECAST_API)
        self.assertFalse(calls[0][1]["allow_redirects"])
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=10), reply=AsyncMock(return_value=SimpleNamespace(id=1)))
        with patch("features.assistant.tools.weather_provider.fetch", new=AsyncMock(return_value=facts)), patch(
            "features.assistant.tools.brave_search.search", new=AsyncMock()
        ) as brave:
            result = await registry.execute(
                await route_message("thời tiết biên hòa hôm nay như nào"), msg
            )
        embed = msg.reply.await_args.kwargs["embed"]
        self.assertIn("30°C", embed.description)
        self.assertIn("34°C", embed.description)
        self.assertIn("80%", embed.fields[1].value)
        self.assertIn("33°C", embed.fields[0].value)
        self.assertNotIn("AQI", embed.description)
        self.assertEqual(result.details["weather_status"], "ok")
        brave.assert_not_awaited()

    async def test_missing_city_asks_question_instead_of_guessing(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=10), reply=AsyncMock(return_value=SimpleNamespace(id=2)))
        with patch("features.assistant.tools.weather_provider.fetch", new=AsyncMock(
            return_value=WeatherFacts(status="missing_location")
        )):
            result = await registry.execute(
                await route_message("thời tiết hôm nay như nào"), msg,
            )
        self.assertIn("ở đâu", msg.reply.await_args.args[0])
        self.assertEqual(result.details["weather_status"], "missing_location")

    async def test_weather_api_failure_does_not_hallucinate_aqi(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=10), reply=AsyncMock(return_value=SimpleNamespace(id=3)))
        with patch("features.assistant.tools.weather_provider.fetch", new=AsyncMock(
            return_value=WeatherFacts(status="unavailable")
        )):
            await registry.execute(
                await route_message("thời tiết biên hòa hôm nay"), msg,
            )
        answer = msg.reply.await_args.args[0]
        self.assertIn("Chưa lấy được dữ liệu dự báo", answer)
        self.assertNotIn("ô nhiễm", answer)


class FuelFactsFirstTests(unittest.IsolatedAsyncioTestCase):
    async def test_fuel_facts_skip_brave_and_answer_exact_price(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=77), reply=AsyncMock(return_value=SimpleNamespace(id=200)))
        official = VerifiedFuelReport(
            status="ok",
            effective_at=datetime(2026, 10, 1, 15, tzinfo=VN),
            rows=(VerifiedFuelPrice("Xăng E10 RON95-III", 27180),),
            source_url="https://www.pvoil.com.vn/tin-gia-xang-dau",
        )
        with patch("features.assistant.tools.pvoil_reader.fetch",
                   new=AsyncMock(return_value=official)), patch(
            "features.assistant.tools.brave_search.search",
            new=AsyncMock(),
        ) as brave:
            result = await registry.execute(
                await route_message("giá xăng hôm nay như nào"), msg,
            )
        brave.assert_not_awaited()
        self.assertIn("27.180", msg.reply.await_args.kwargs["embed"].description)
        self.assertEqual(result.details["web_provider"], "pvoil")

    async def test_fuel_failure_falls_back_to_brave_with_reason(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=77), reply=AsyncMock(return_value=SimpleNamespace(id=201)))
        with patch("features.assistant.tools.pvoil_reader.fetch", new=AsyncMock(
            return_value=VerifiedFuelReport(status="unavailable")
        )), patch("features.assistant.tools.webgia_reader.fetch", new=AsyncMock(
            return_value=SimpleNamespace(status="unavailable", rows=(), elapsed_ms=0),
        )), patch("features.assistant.tools.brave_search.search", new=AsyncMock(
            return_value=BraveSearchResult(status="ok", hits=(
                BraveHit(title="Bảng giá", url="https://example.org/prices",
                         description="Thông tin chưa đủ về giá bán lẻ"),
            ))
        )), patch.object(registry, "_summarize_public_search", new=AsyncMock(return_value="")):
            result = await registry.execute(
                await route_message("giá xăng hôm nay như nào"), msg,
            )
        self.assertEqual(result.details["first_party_status"], "unavailable")
        self.assertIn("chưa truy xuất được bảng giá", msg.reply.await_args.kwargs["embed"].description)


if __name__ == "__main__":
    unittest.main()
