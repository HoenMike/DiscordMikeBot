"""Brave fact grounding may read select public HTML pages, never private URLs."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from features.assistant.providers.public_pages import (
    fetch_public_page_evidence, safe_public_url, relevant_page_excerpt,
)


class PublicPageSafetyTests(unittest.TestCase):
    def test_allowlisted_https_only(self):
        self.assertTrue(safe_public_url("https://www.vnexpress.net/kinh-doanh/tin.html"))
        self.assertTrue(safe_public_url("https://www.pvoil.com.vn/tin-tuc"))
        for url in (
            "http://www.vnexpress.net/",
            "https://discord.com/channels/1/2/3",
            "https://169.254.169.254/latest/meta-data",
            "https://localhost/",
            "https://www.vnexpress.net.evil.com/",
            "https://user:pass@vnexpress.net/news",
            "https://vnexpress.net:8080/news",
        ):
            with self.subTest(url=url):
                self.assertFalse(safe_public_url(url))

    def test_html_cleaning_and_query_relevance(self):
        raw = """<html><nav>Link link menu</nav><script>IGNORE=1</script>
        <article><p>Giá dầu hôm nay có thể thay đổi theo kỳ điều hành mới.</p>
        <p>Giá nhiên liệu công bố cần kiểm chứng nguồn chính.</p></article></html>"""
        snippet = relevant_page_excerpt(raw, "giá dầu hôm nay")
        self.assertIn("Giá dầu hôm nay", snippet)
        self.assertNotIn("IGNORE", snippet)
        self.assertNotIn("menu", snippet)


class PublicPageFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_only_allowed_sources_without_redirects(self):
        requested = []
        class Resp:
            status = 200
            headers = {"Content-Type": "text/html"}
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            class content:
                @staticmethod
                async def read(max_bytes):
                    return (
                        "<html><article><p>Giá dầu được điều chỉnh theo kỳ "
                        "mới nhất; bảng dữ liệu chi tiết theo ngày hiệu lực.</p>"
                        "<p>" + "Nguồn dữ liệu chính thức. " * 20 + "</p></article></html>"
                    ).encode()
        class Session:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            def get(self, url, **kwargs):
                requested.append((url, kwargs))
                return Resp()
        hits = [
            SimpleNamespace(url="https://vnexpress.net/test", title="News", description="snippet"),
            SimpleNamespace(url="https://discord.com/channels/1/2/3", title="private", description="private"),
            SimpleNamespace(url="https://pvoil.com.vn/tin-tuc", title="PVOIL", description="snippet"),
        ]
        with patch("features.assistant.providers.public_pages.aiohttp.ClientSession", Session):
            evidence = await fetch_public_page_evidence("giá dầu hôm nay", hits)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(len(requested), 2)
        self.assertTrue(all(not item[1]["allow_redirects"] for item in requested))
        self.assertNotIn("discord.com", str(requested))

if __name__ == "__main__":
    unittest.main()
