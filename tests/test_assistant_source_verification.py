"""Live first-party price extraction: dated facts, bounded HTTP, safe fallback."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.providers.brave import BraveHit, BraveSearchResult
from features.assistant.providers.pvoil_prices import (
    VN_TZ, OFFICIAL_PVOIL_URLS, PVOILPriceReader, VerifiedFuelPrice,
    VerifiedFuelReport, parse_pvoil_prices,
)
from features.assistant.router import route_locally
from features.assistant.tools import CommandToolRegistry

TABLE = """<!doctype html><html><body>
<h1>Bảng giá xăng dầu</h1>
<table><thead><tr>
<th>TT</th><th>Mặt hàng</th>
<th>Giá điều chỉnh lúc 15:00 ngày 01/10/2026 (Đồng/lít thực tế)</th>
<th>Chênh lệch tăng/giảm</th></tr></thead>
<tbody>
<tr><td>1</td><td>Xăng E10 RON 95-III</td><td>27.180 đ</td><td>+100</td></tr>
<tr><td>2</td><td>Xăng E5 RON 92-II</td><td>26.560 đ</td><td>+170</td></tr>
<tr><td>3</td><td>Dầu DO 0,05S-II</td><td>29.710 đ</td><td>-780</td></tr>
<tr><td>4</td><td>Dầu DO 0,001S-V</td><td>31.110 đ</td><td>-980</td></tr>
</tbody></table></body></html>"""

HOME = """<html><body>
<h2>Bảng giá bán lẻ xăng dầu (Đồng/lít)</h2>
<h4>Giá điều chỉnh từ 15:00 ngày 01/10/2026</h4>
<div>Xăng E10 RON 95-III 27.180 đ Xăng E5 RON 92-II 26.560 đ
Dầu DO 0,05S-II 29.710 đ Dầu DO 0,001S-V 31.110 đ</div>
</body></html>"""

AT = datetime(2026, 10, 8, 10, 20, tzinfo=VN_TZ)


class PVOILParserTests(unittest.TestCase):
    def test_dated_table_extracts_four_prices_not_delta(self):
        report = parse_pvoil_prices(TABLE, now=AT)
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.effective_at.isoformat(), "2026-10-01T15:00:00+07:00")
        self.assertEqual([x.vnd_per_liter for x in report.rows],
                         [27180, 26560, 29710, 31110])

    def test_homepage_compact_text_without_rows(self):
        report = parse_pvoil_prices(HOME, now=AT)
        self.assertEqual(report.status, "ok")
        self.assertEqual(len(report.rows), 4)
        self.assertEqual(report.rows[0].label, "Xăng E10 RON95-III")

    def test_missing_date_fails_without_made_up_effective_time(self):
        data = TABLE.replace("Giá điều chỉnh lúc 15:00 ngày 01/10/2026", "Bảng giá hôm nay")
        self.assertEqual(parse_pvoil_prices(data, now=AT).status,
                         "missing_effective_date")

    def test_future_date_is_rejected(self):
        data = TABLE.replace("01/10/2026", "10/10/2026")
        self.assertEqual(parse_pvoil_prices(data, now=AT).status,
                         "missing_effective_date")

    def test_html_script_data_not_treated_as_a_price(self):
        injected = TABLE.replace("<tbody>", "<script>Giá điều chỉnh lúc 00:00 ngày 08/10/2026 Xăng E10 RON 95-III 19.999 đ</script><tbody>")
        report = parse_pvoil_prices(injected, now=AT)
        self.assertEqual(report.effective_at.day, 1)
        self.assertEqual(report.rows[0].vnd_per_liter, 27180)

    def test_screenshot_delta_is_not_confused_with_price(self):
        report = parse_pvoil_prices(TABLE.replace("27.180 đ", "").replace("26.560 đ", ""), now=AT)
        self.assertEqual(report.status, "ok")
        self.assertEqual([x.vnd_per_liter for x in report.rows], [29710, 31110])


class OfficialSourceTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_https_only_and_redirects_disabled(self):
        urls = []
        class Content:
            async def read(self, amount):
                self.amount = amount
                return TABLE.encode()
        class Response:
            def __init__(self, status):
                self.status = status
                self.headers = {"Content-Type": "text/html; charset=utf-8"}
                self.content = Content()
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
        class Session:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            def get(self, url, **kwargs):
                urls.append((url, kwargs))
                return Response(200)
        with patch("features.assistant.providers.pvoil_prices.aiohttp.ClientSession", Session):
            report = await PVOILPriceReader().fetch()
        self.assertEqual(report.status, "ok")
        self.assertEqual(urls[0][0], OFFICIAL_PVOIL_URLS[0])
        self.assertFalse(urls[0][1]["allow_redirects"])
        self.assertEqual(report.source_url, OFFICIAL_PVOIL_URLS[0])

    async def test_unavailable_does_not_fabricate_price(self):
        class Response:
            status = 403
            headers = {}
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
        class Session:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            def get(self, url, **kwargs): return Response()
        with patch("features.assistant.providers.pvoil_prices.aiohttp.ClientSession", Session):
            report = await PVOILPriceReader().fetch()
        self.assertEqual(report.status, "unavailable")
        self.assertFalse(report.rows)


class VerifiedFuelToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_table_is_answered_directly_and_model_skipped(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=42),
            reply=AsyncMock(return_value=SimpleNamespace(id=125)),
        )
        report = VerifiedFuelReport(
            status="ok", effective_at=datetime(2026, 10, 1, 15, 0, tzinfo=VN_TZ),
            rows=(VerifiedFuelPrice("Xăng E10 RON95-III", 27180),
                  VerifiedFuelPrice("Xăng E5 RON92-II", 26560)),
            source_url=OFFICIAL_PVOIL_URLS[0], elapsed_ms=29,
        )
        bravo = BraveSearchResult(status="ok", hits=(
            BraveHit("Brave search snippet", "https://example.org/1", "no number"),
        ), remaining=499)
        with patch("features.assistant.tools.brave_search.search",
                   new=AsyncMock(return_value=bravo)), patch(
            "features.assistant.tools.pvoil_reader.fetch",
            new=AsyncMock(return_value=report),
        ), patch.object(registry, "_summarize_public_search", new=AsyncMock()) as ai:
            response = await registry.execute(route_locally("tìm trên web giá xăng hôm nay"), msg)
        embed = msg.reply.await_args.kwargs["embed"]
        self.assertIn("27.180 đ/lít", embed.description)
        self.assertIn("01/10/2026", embed.description)
        self.assertIn("pvoil.com.vn/tin-gia-xang-dau", embed.fields[0].value)
        self.assertTrue(response.handled)
        self.assertEqual(response.details["first_party_rows"], 2)
        self.assertIn("27180", response.response_context)
        ai.assert_not_awaited()

    async def test_failed_source_gracefully_returns_existing_brave_sources(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=42),
            reply=AsyncMock(return_value=SimpleNamespace(id=126)),
        )
        bravo = BraveSearchResult(status="ok", hits=(
            BraveHit("Tin giá xăng", "https://example.org/gas", "Giá xăng dầu"),
        ))
        with patch("features.assistant.tools.brave_search.search",
                   new=AsyncMock(return_value=bravo)), patch(
            "features.assistant.tools.pvoil_reader.fetch",
            new=AsyncMock(return_value=VerifiedFuelReport(status="unavailable")),
        ), patch(
            "features.assistant.tools.webgia_reader.fetch",
            new=AsyncMock(return_value=SimpleNamespace(status="unavailable", rows=(), elapsed_ms=0)),
        ), patch.object(registry, "_summarize_public_search",
                        new=AsyncMock(return_value="Chưa xác minh được giá.")):
            result = await registry.execute(route_locally("tìm trên web giá xăng hôm nay"), msg)
        embed = msg.reply.await_args.kwargs["embed"]
        self.assertIn("chưa đủ để xác nhận", embed.description)
        self.assertIn("[1](https://example.org/gas)", embed.description)
        self.assertEqual(result.details["first_party_status"], "unavailable")
        self.assertNotIn("query", result.details)


if __name__ == "__main__":
    unittest.main()
