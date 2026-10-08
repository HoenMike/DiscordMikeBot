"""Live-source-shaped dated WebGia Vùng 1 price data after PVOIL 403."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from features.assistant.providers.pvoil_prices import VerifiedFuelReport
from features.assistant.providers.webgia_prices import (
    WEBGIA_URL, FuelAggregate, WebGiaReader, parse_webgia_fuel,
)
from features.assistant.providers.brave import BraveSearchResult, BraveHit
from features.assistant.router import route_message
from features.assistant.search_presenter import build_aggregated_fuel_embed
from features.assistant.tools import CommandToolRegistry

NOW = datetime(2026, 10, 8, 11, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

def page(date="01/10/2026"):
    return f"""<!doctype html><html><body>
    <h2>Bảng giá Petrolimex</h2><table>
    <thead><tr><th>Mặt hàng</th><th>Vùng 1</th><th>+/- Vùng 1</th>
    <th>Vùng 2</th><th>+/- Vùng 2</th><th>Hiệu lực từ</th></tr></thead>
    <tbody><tr><td>Xăng E10 RON 95-III</td><td>27.180</td><td>▲ 100</td>
    <td>27.720</td><td>▲ 100</td><td>{date}</td></tr>
    <tr><td>Xăng E5 RON 92-II</td><td>26.560</td><td>▲ 170</td>
    <td>27.090</td><td>▲ 180</td><td>{date}</td></tr>
    <tr><td>Dầu diesel 0,05S-II</td><td>29.710</td><td>▼ 780</td>
    <td>30.300</td><td>▼ 790</td><td>{date}</td></tr>
    </tbody></table><script>fake table Xăng E10 RON 95-III 19.000</script></body></html>"""

class ParserTests(unittest.TestCase):
    def test_realistic_price_table(self):
        report = parse_webgia_fuel(page(), now=NOW)
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.effective_date, "2026-10-01")
        self.assertEqual(report.rows, (
            ("Xăng E10 RON95-III", 27180),
            ("Xăng E5 RON92-II", 26560),
            ("Dầu diesel 0,05S-II", 29710),
        ))

    def test_old_or_future_price_date_rejected(self):
        self.assertEqual(parse_webgia_fuel(page("01/09/2026"), now=NOW).status, "missing_recent_period")
        self.assertEqual(parse_webgia_fuel(page("10/10/2026"), now=NOW).status, "missing_recent_period")

    def test_missing_date_or_table_header_rejected(self):
        self.assertEqual(parse_webgia_fuel(page("Không rõ ngày"), now=NOW).status, "missing_recent_period")
        self.assertEqual(parse_webgia_fuel(page().replace("<th>Vùng 1</th>", "<th>Giá</th>"), now=NOW).status, "missing_table_header")

    def test_rejects_absurd_price_or_false_price_deltas(self):
        data = page().replace("<td>27.180</td>", "<td>100</td>")
        self.assertEqual(parse_webgia_fuel(data, now=NOW).rows[0][0], "Xăng E5 RON92-II")

    def test_non_official_labels_not_misrepresented(self):
        report = parse_webgia_fuel(page(), now=NOW)
        embed = build_aggregated_fuel_embed("giá xăng hôm nay", report)
        self.assertIn("27.180 đ/lít", embed.description)
        self.assertIn("01/10/2026", embed.description)
        self.assertIn("WebGia.TV", embed.fields[0].value)
        self.assertIn("chưa kiểm chứng trực tiếp", embed.footer.text)
        self.assertNotIn("PVOIL — Bảng giá", embed.fields[0].value)

class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_webgia_fixed_https_and_no_redirect(self):
        calls = []
        class Resp:
            status = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}
            class content:
                @staticmethod
                async def read(n):
                    date = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%d/%m/%Y")
                    return page(date).encode()
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
        class Session:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            def get(self, url, **kwargs):
                calls.append((url, kwargs)); return Resp()
        with patch("features.assistant.providers.webgia_prices.aiohttp.ClientSession", Session):
            report = await WebGiaReader().fetch()
        self.assertEqual(report.status, "ok")
        self.assertEqual(calls[0][0], WEBGIA_URL)
        self.assertFalse(calls[0][1]["allow_redirects"])

class FuelFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_403_to_webgia_without_brave(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=4), reply=AsyncMock(return_value=SimpleNamespace(id=101)))
        report = parse_webgia_fuel(page(), now=NOW)
        with patch("features.assistant.tools.pvoil_reader.fetch", new=AsyncMock(
            return_value=VerifiedFuelReport(status="unavailable", attempts=("pvoil_1:http_403",))
        )), patch("features.assistant.tools.webgia_reader.fetch",
                  new=AsyncMock(return_value=report)), patch(
            "features.assistant.tools.brave_search.search", new=AsyncMock()
        ) as brave:
            result = await registry.execute(await route_message("giá xăng hôm nay như nào"), msg)
        brave.assert_not_awaited()
        self.assertEqual(result.details["aggregate_status"], "ok")
        self.assertEqual(result.details["first_party_reason"], "pvoil_1:http_403")
        self.assertEqual(result.details["web_provider"], "webgia")
        self.assertIn("27.180", msg.reply.await_args.kwargs["embed"].description)

    async def test_both_structured_sources_fail_then_honest_brave(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(author=SimpleNamespace(id=4), reply=AsyncMock(return_value=SimpleNamespace(id=102)))
        with patch("features.assistant.tools.pvoil_reader.fetch", new=AsyncMock(
            return_value=VerifiedFuelReport(status="unavailable", attempts=("pvoil_1:http_403",))
        )), patch("features.assistant.tools.webgia_reader.fetch", new=AsyncMock(
            return_value=FuelAggregate(status="missing_recent_period")
        )), patch("features.assistant.tools.brave_search.search", new=AsyncMock(
            return_value=BraveSearchResult(status="ok", hits=(
                BraveHit("Nguồn", "https://example.org/energy", "Thông báo điều hành."),
            ))
        )) as brave, patch.object(registry, "_summarize_public_search", new=AsyncMock()) as model:
            result = await registry.execute(await route_message("giá xăng hôm nay như nào"), msg)
        brave.assert_awaited_once()
        model.assert_not_awaited()
        self.assertEqual(result.details["aggregate_status"], "missing_recent_period")
        self.assertIn("chưa truy xuất được", msg.reply.await_args.kwargs["embed"].description)

if __name__ == "__main__":
    unittest.main()
