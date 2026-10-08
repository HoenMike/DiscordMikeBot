"""PVOIL HTTP diagnostics and strict source-labeled fuel fallback."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from features.assistant.providers.pvoil_prices import VerifiedFuelReport
from features.assistant.providers.vietfuel import (
    parse_fuel_aggregate, FuelAggregate, VietFuelReader, API_URL,
)
from features.assistant.providers.brave import BraveSearchResult, BraveHit
from features.assistant.router import route_message
from features.assistant.search_presenter import build_aggregated_fuel_embed
from features.assistant.tools import CommandToolRegistry

NOW = datetime(2026, 10, 8, 11, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
def response(*, price_date="2026-10-01", scraped_at=None, source_count=4):
    return {
        "success": True, "status": "ok",
        "meta": {
            "priceDate": price_date, "sourceCount": source_count,
            "scrapedAt": scraped_at or NOW.isoformat(),
            "primarySource": "Petrolimex",
        },
        "data": [
            {"name": "Xăng E10 RON 95-III", "region1": 27180, "region2": 27710, "unit": "VND/lít"},
            {"name": "Xăng E5 RON 92-II", "region1": 26560, "region2": 27090, "unit": "VND/lít"},
            {"name": "Dầu DO 0,05S-II", "region1": 29710, "region2": 30290, "unit": "VND/lít"},
        ],
    }

class AggregateParserTests(unittest.TestCase):
    def test_valid_date_prices_and_provenance(self):
        r = parse_fuel_aggregate(response(), now=NOW)
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.effective_date, "2026-10-01")
        self.assertEqual(len(r.rows), 3)
        self.assertEqual(r.rows[0], ("E10 RON95-III", 27180))

    def test_stale_and_future_price_period_rejected(self):
        self.assertEqual(parse_fuel_aggregate(response(price_date="2026-09-01"), now=NOW).status, "stale_price_date")
        self.assertEqual(parse_fuel_aggregate(response(price_date="2026-10-10"), now=NOW).status, "stale_price_date")

    def test_old_scrape_and_untrusted_source_rejected(self):
        old = (NOW - timedelta(hours=72)).isoformat()
        self.assertEqual(parse_fuel_aggregate(response(scraped_at=old), now=NOW).status, "stale_cache")
        self.assertEqual(parse_fuel_aggregate(response(source_count=0), now=NOW).status, "missing_source")

    def test_wrong_units_absurd_prices_rejected(self):
        data = response()
        data["data"][0]["unit"] = "USD/gallon"
        data["data"][1]["region1"] = 42
        self.assertEqual(parse_fuel_aggregate(data, now=NOW).status, "missing_prices")

    def test_provider_label_explicitly_non_official(self):
        result = parse_fuel_aggregate(response(), now=NOW)
        embed = build_aggregated_fuel_embed("giá xăng hôm nay", result)
        self.assertIn("27.180 đ/lít", embed.description)
        self.assertIn("01/10/2026", embed.description)
        self.assertIn("VietFuelAPI", embed.fields[0].value)
        self.assertIn("chưa kiểm chứng trực tiếp", embed.footer.text)
        self.assertNotIn("PVOIL — Bảng giá", embed.fields[0].value)

class AggregateTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_fixed_json_url_and_no_redirect(self):
        import json
        requests = []
        class Resp:
            status = 200
            headers = {"Content-Type": "application/json"}
            class content:
                @staticmethod
                async def read(maxbytes):
                    return json.dumps(response(scraped_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
                                               price_date=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat())).encode()
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
        class Session:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def get(self, url, **kwargs):
                requests.append((url, kwargs))
                return Resp()
        with patch("features.assistant.providers.vietfuel.aiohttp.ClientSession", Session):
            result = await VietFuelReader().fetch()
        self.assertEqual(result.status, "ok")
        self.assertEqual(requests[0][0], API_URL)
        self.assertFalse(requests[0][1]["allow_redirects"])

class FuelFallbackFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_pvoil_unavailable_aggregate_answer_no_brave_charge(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=4), reply=AsyncMock(return_value=SimpleNamespace(id=101)))
        agg = parse_fuel_aggregate(response(), now=NOW)
        with patch("features.assistant.tools.pvoil_reader.fetch", new=AsyncMock(
            return_value=VerifiedFuelReport(status="unavailable", attempts=("pvoil_1:http_403",))
        )), patch("features.assistant.tools.vietfuel_reader.fetch",
                  new=AsyncMock(return_value=agg)), patch(
            "features.assistant.tools.brave_search.search", new=AsyncMock()
        ) as brave:
            result = await registry.execute(
                await route_message("giá xăng hôm nay như nào"), msg
            )
        brave.assert_not_awaited()
        self.assertEqual(result.details["aggregate_status"], "ok")
        self.assertEqual(result.details["first_party_reason"], "pvoil_1:http_403")
        self.assertEqual(result.details["web_provider"], "vietfuel")
        embed = msg.reply.await_args.kwargs["embed"]
        self.assertIn("27.180", embed.description)

    async def test_both_sources_bad_fallback_honestly_to_brave(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=4), reply=AsyncMock(return_value=SimpleNamespace(id=102)))
        with patch("features.assistant.tools.pvoil_reader.fetch", new=AsyncMock(
            return_value=VerifiedFuelReport(status="unavailable", attempts=("pvoil_1:http_403",))
        )), patch("features.assistant.tools.vietfuel_reader.fetch", new=AsyncMock(
            return_value=FuelAggregate(status="stale_price_date")
        )), patch("features.assistant.tools.brave_search.search", new=AsyncMock(
            return_value=BraveSearchResult(status="ok", hits=(
                BraveHit("Nguồn", "https://example.org/energy", "Thông báo điều hành."),
            ))
        )) as brave, patch.object(registry, "_summarize_public_search", new=AsyncMock()) as model:
            result = await registry.execute(
                await route_message("giá xăng hôm nay như nào"), msg
            )
        brave.assert_awaited_once()
        model.assert_not_awaited()
        self.assertEqual(result.details["aggregate_status"], "stale_price_date")
        self.assertIn("chưa truy xuất được", msg.reply.await_args.kwargs["embed"].description)

if __name__ == "__main__":
    unittest.main()
