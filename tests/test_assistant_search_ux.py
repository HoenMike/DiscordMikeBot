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

    def test_compact_sources_and_answer_bolding(self):
        embed = build_search_embed(
            "giá xăng hôm nay như nào",
            self.sample(),
            "Chưa xác minh giá chính xác [1], [2] tại thời điểm này. "
            "Nguồn công khai chưa cung cấp bảng giá hợp lệ.",
        )
        self.assertIn("🔎", embed.title)
        self.assertTrue(embed.description.startswith(
            "**Chưa xác minh giá chính xác"
        ))
        lead, detail = embed.description.split("\n\n", 1)
        self.assertNotIn("[1]", lead)
        self.assertIn("Nguồn công khai", detail)
        self.assertIn("[1](https://pvoil.com.vn/gia-ban-le)", detail)
        self.assertIn("[2](https://petrolimex.com.vn/gia-xang-dau)", detail)
        self.assertEqual(embed.fields, [])
        self.assertFalse(embed.footer.text)
        self.assertNotIn("pricedancing.com", embed.description)

    def test_cktg_response_highlights_takeaway_with_minimal_citations(self):
        hits = [
            BraveHit(
                title="Lịch thi đấu giải đấu chính thức",
                description="Một đoạn trích dài không nên xuất hiện trong lời đáp.",
                url="https://example.org/worlds",
            )
        ]
        embed = build_search_embed(
            "Khi nào CKTG bắt đầu?", hits,
            "CKTG LMHT 2026 bắt đầu ngày 15/10/2026. "
            "Giải đấu dự kiến kéo dài đến 14/11.",
        )
        self.assertTrue(embed.description.startswith(
            "**CKTG LMHT 2026 bắt đầu ngày 15/10/2026.**"
        ))
        self.assertIn("\n\nGiải đấu dự kiến", embed.description)
        self.assertTrue(embed.description.endswith(
            "[1](https://example.org/worlds)"
        ))
        self.assertNotIn("Kiểm chứng", str(embed.to_dict()))
        self.assertNotIn("Một đoạn trích dài", str(embed.to_dict()))
        self.assertEqual(embed.fields, [])

    def test_no_summary_does_not_invent_price(self):
        embed = build_search_embed("giá xăng hôm nay", self.sample())
        self.assertIn("chưa thể xác minh", embed.description)
        self.assertNotIn("đ/lít", embed.description)
        self.assertEqual(embed.description.count("https://"), 2)

    def test_mass_mentions_are_escaped(self):
        bad = BraveHit(
            title="Thông báo @everyone",
            description="<strong>@here</strong> giá xăng",
            url="https://example.org/price",
        )
        embed = build_search_embed(
            "giá xăng hôm nay", [bad],
            "Đừng tag @everyone. Không nhắc @here trong kênh.",
        )
        self.assertNotIn("@everyone", embed.description)
        self.assertNotIn("@here", embed.description)
        self.assertNotIn("Thông báo", embed.description)

    def test_source_count_link_bounds_and_unsafe_urls(self):
        hits = [
            BraveHit(title="X" * 500, description="<b>Y</b>" * 400,
                     url=f"https://example.org/results/{i}")
            for i in range(7)
        ]
        hits.insert(0, BraveHit("Bad", "javascript:alert(1)", "unsafe"))
        embed = build_search_embed("test", hits)
        self.assertLessEqual(len(embed), 6000)
        self.assertEqual(embed.description.count("https://"), 1)
        self.assertNotIn("javascript:", embed.description)
        self.assertEqual(len(embed.fields), 0)

    def test_source_link_parentheses_are_safe(self):
        embed = build_search_embed(
            "câu hỏi", [BraveHit("news", "https://example.org/news_(2026)", "")],
            "Kết quả đúng theo trang vừa tìm.",
        )
        self.assertIn("[1](https://example.org/news_%282026%29)", embed.description)

    def test_empty_and_long_answers_have_bounded_emphasis(self):
        embed = build_search_embed("hỏi", [], "")
        self.assertIn("**Mình chưa thể xác minh", embed.description)
        long = "Thông tin " + ("rất dài " * 70) + ". Nội dung sau."
        embed = build_search_embed("hỏi", [], long)
        self.assertTrue(embed.description.startswith("**"))
        self.assertLess(embed.description.index("**", 2), 220)
        self.assertIn("Nội dung sau.", embed.description)


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
