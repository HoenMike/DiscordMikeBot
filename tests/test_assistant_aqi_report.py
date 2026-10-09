"""T25.2 AQI report: strictly model-labelled data + rendered in-chat card."""
import io
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from PIL import Image

from features.assistant.air_quality_renderer import render_air_quality_png
from features.assistant.providers.air_quality import (
    AirQualityFacts, aqi_label, parse_aqi_response,
)
from features.assistant.router import route_message
from features.assistant.tools import CommandToolRegistry

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 9, 10, tzinfo=TZ)


def payload():
    return {
        "current": {"time": "2026-10-09T10:00", "us_aqi": 124, "pm2_5": 45.0},
        "hourly": {
            "time": ["2026-10-09T09:00", "2026-10-09T10:00",
                     "2026-10-09T11:00", "2026-10-09T12:00"],
            "us_aqi": [135, 124, 118, 110],
        },
    }


class AirQualityTypedTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_route_no_brave_or_clef(self):
        decision = await route_message(
            "chất lượng không khí Biên Hòa hôm nay",
            cloudflare_router=SimpleNamespace(enabled=False),
        )
        self.assertEqual(decision.tool, "air_quality.report")
        self.assertEqual(decision.source, "local_aqi_model")
        decision = await route_message(
            "AQI Biên Hòa trong server hôm qua",
            cloudflare_router=SimpleNamespace(enabled=False),
        )
        self.assertNotEqual(decision.tool, "air_quality.report")

    async def test_parser_models_not_station_and_guards_bad_values(self):
        facts = parse_aqi_response(payload(), now=NOW)
        self.assertEqual(facts.status, "ok")
        self.assertEqual(facts.aqi, 124)
        self.assertEqual(facts.pm25, 45)
        self.assertEqual(facts.timeline, (("10h", 124), ("11h", 118), ("12h", 110)))
        self.assertEqual(aqi_label(124), "Không tốt cho nhóm nhạy cảm")
        stale = parse_aqi_response(payload(), now=NOW + timedelta(hours=4))
        self.assertEqual(stale.status, "stale")
        altered = payload()
        altered["current"]["pm2_5"] = float("nan")
        self.assertEqual(parse_aqi_response(altered, now=NOW).status, "unavailable")
        altered = payload()
        altered["current"]["us_aqi"] = None
        self.assertEqual(parse_aqi_response(altered, now=NOW).status, "unavailable")

    async def test_render_png_with_typed_facts(self):
        facts = parse_aqi_response(payload(), now=NOW)
        data = render_air_quality_png(facts)
        self.assertTrue(data.getvalue().startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(io.BytesIO(data.getvalue())) as img:
            self.assertEqual(img.size, (1120, 800))
            self.assertEqual(img.format, "PNG")
        with self.assertRaises(ValueError):
            render_air_quality_png(AirQualityFacts(status="unavailable"))

    async def test_discord_reply_png_and_source_with_model_warning(self):
        facts = parse_aqi_response(payload(), now=NOW)
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=8),
            reply=AsyncMock(return_value=SimpleNamespace(id=900)),
        )
        decision = await route_message("AQI Biên Hòa hôm nay")
        with patch(
            "features.assistant.tools.aqi_provider.fetch",
            new=AsyncMock(return_value=facts),
        ):
            result = await registry.execute(decision, msg)
        self.assertEqual(result.details["aqi_provider"], "open_meteo_model")
        self.assertEqual(result.details["aqi_visual"], "png")
        text = msg.reply.await_args.args[0]
        self.assertIn("**Biên Hòa · US AQI mô hình: 124", text)
        self.assertIn("không phải số đo trực tiếp", text)
        self.assertIn("[1](https://open-meteo.com/", text)
        attachment = msg.reply.await_args.kwargs["file"]
        self.assertEqual(attachment.filename, "aqi_bien_hoa.png")
        self.assertEqual(result.response_message_ids, (900,))

    async def test_renderer_failure_falls_back_without_inventing_data(self):
        facts = parse_aqi_response(payload(), now=NOW)
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=8),
            reply=AsyncMock(return_value=SimpleNamespace(id=901)),
        )
        decision = await route_message("AQI Biên Hòa hôm nay")
        with patch(
            "features.assistant.tools.aqi_provider.fetch",
            new=AsyncMock(return_value=facts),
        ), patch(
            "features.assistant.tools.render_air_quality_png",
            side_effect=RuntimeError("No font"),
        ):
            result = await registry.execute(decision, msg)
        self.assertEqual(result.details["aqi_visual"], "text_fallback")
        self.assertNotIn("file", msg.reply.await_args.kwargs)
        self.assertIn("Chưa thể tạo biểu đồ", msg.reply.await_args.args[0])

    async def test_unavailable_or_stale_never_displays_guess(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=8),
            reply=AsyncMock(return_value=SimpleNamespace(id=902)),
        )
        decision = await route_message("PM2.5 Biên Hòa hôm nay")
        with patch(
            "features.assistant.tools.aqi_provider.fetch",
            new=AsyncMock(return_value=AirQualityFacts(status="stale")),
        ):
            result = await registry.execute(decision, msg)
        self.assertEqual(result.details["aqi_status"], "stale")
        self.assertNotIn("file", msg.reply.await_args.kwargs)
        self.assertIn("quá cũ", msg.reply.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
