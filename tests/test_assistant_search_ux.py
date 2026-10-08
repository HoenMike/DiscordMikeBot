"""Regression for the source-first, compact Brave Search Discord UX."""
import unittest
from types import SimpleNamespace

from features.assistant.providers.brave import BraveHit, BraveSearchAdapter
from features.assistant.search_presenter import (
    _plain, build_search_embed, prioritize_sources,
)


class BraveSearchUXTests(unittest.TestCase):
    def sample(self):
        return (
            BraveHit(
                title="Lịch sử giá xăng <strong>RON 95</strong>",
                url="https://pricedancing.com/vi/petrol-price",
                description="Từ năm ngoái <strong>chưa cập nhật</strong>.",
            ),
            BraveHit(
                title="Bài tổng hợp giá xăng",
                url="https://baomoi.com/tong-hop",
                description="Tin tháng trước...",
            ),
            BraveHit(
                title="Giá xăng dầu <strong>hôm nay</strong>",
                url="https://pvoil.com.vn/gia-ban-le",
                description="Dữ liệu theo kỳ điều hành mới nhất.",
            ),
            BraveHit(
                title="Bảng giá bán lẻ",
                url="https://petrolimex.com.vn/gia-xang-dau",
                description="Công bố giá xăng trên trang gốc.",
            ),
        )

    def test_html_cleaning(self):
        self.assertEqual(
            _plain("Dưới đây là bảng <strong>giá xăng</strong> &amp; dầu", 120),
            "Dưới đây là bảng giá xăng & dầu",
        )

    def test_gas_prefers_official_sources(self):
        ranked = prioritize_sources("giá xăng hôm nay", self.sample())
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0].url, "https://pvoil.com.vn/gia-ban-le")
        self.assertEqual(ranked[1].url, "https://petrolimex.com.vn/gia-xang-dau")
        self.assertNotIn("pricedancing.com", [x.url for x in ranked])

    def test_other_topics_preserve_brave_order(self):
        ranked = prioritize_sources("tình hình game hôm nay", self.sample())
        self.assertEqual(ranked[0], self.sample()[0])

    def test_compact_embed_sources_and_unlinked_citations(self):
        embed = build_search_embed(
            "giá xăng hôm nay như nào",
            self.sample(),
            "Chưa xác minh giá chính xác [1], [2] tại thời điểm này.",
        )
        self.assertIn("🔎", embed.title)
        self.assertIn("Chưa xác minh", embed.description)
        self.assertNotIn("[1]", embed.description)
        self.assertEqual(len(embed.fields), 1)
        sources = embed.fields[0].value
        self.assertIn("https://pvoil.com.vn/gia-ban-le", sources)
        self.assertIn("https://petrolimex.com.vn/gia-xang-dau", sources)
        self.assertNotIn("<strong>", sources)
        self.assertLessEqual(len(sources), 1024)
        self.assertIn("Brave Search", embed.footer.text)

    def test_no_summary_does_not_invent_price(self):
        embed = build_search_embed("giá xăng hôm nay", self.sample())
        self.assertIn("chưa đủ để xác minh", embed.description)
        self.assertNotIn("đ/lít", embed.description)

    def test_mass_mentions_are_escaped(self):
        bad = BraveHit(
            title="Thông báo @everyone",
            description="<strong>@here</strong> giá xăng",
            url="https://example.org/price",
        )
        embed = build_search_embed("giá xăng hôm nay", [bad], "Đừng tag @everyone")
        self.assertNotIn("@everyone", embed.description)
        self.assertNotIn("@here", embed.fields[0].value)

    def test_source_count_and_message_bounds(self):
        long = [BraveHit(
            title="X" * 500,
            description="<b>Y</b>" * 400,
            url=f"https://example.org/results/{i}",
        ) for i in range(7)]
        embed = build_search_embed("test", long)
        self.assertLessEqual(embed.length, 6000)
        self.assertLessEqual(len(embed.fields[0].value), 1024)
        self.assertLessEqual(embed.fields[0].value.count("https://"), 3)


class BraveSearchQueryTests(unittest.TestCase):
    def test_fuel_today_expands_one_query(self):
        query = BraveSearchAdapter._public_search_query("giá xăng hôm nay như nào")
        self.assertIn("RON95", query)
        self.assertIn("PVOIL", query)
        self.assertIn("Việt Nam", query)

    def test_other_search_queries_unchanged(self):
        query = "Giá dầu Brent mới nhất?"
        self.assertEqual(BraveSearchAdapter._public_search_query(query), query)


if __name__ == "__main__":
    unittest.main()
