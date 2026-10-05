import unittest
from unittest.mock import patch

from PIL import Image
from datetime import datetime, timezone, timedelta

from features.tarot.deck import DrawnCard, TAROT_DECK
from features.tarot.reading.recap import build_recap_state
from features.tarot.reading.schema import TarotKeyCard, TarotReadingResult
from features.tarot.renderer import render_recap_card_to_bytes
from features.tarot.tarot_view import TarotResultActionView


def drawn(card_id: str, index: int) -> DrawnCard:
    return DrawnCard(
        card=TAROT_DECK[card_id],
        is_reversed=(index % 2 == 0),
        position_index=index,
        position_title=f"LÁ {index}: VỊ TRÍ {index}",
        position_description="Mô tả vị trí",
    )


class FakeManager:
    pass


class TarotRecapTests(unittest.TestCase):
    def setUp(self):
        self.asset_patch = patch("features.tarot.renderer.ensure_card_asset", return_value=None)
        self.asset_patch.start()
        self.cards = [
            drawn("major_01", 1),
            drawn("major_09", 2),
            drawn("cups_02", 3),
        ]

    def tearDown(self):
        self.asset_patch.stop()

    def test_prefers_structured_key_card_and_takeaway(self):
        result = TarotReadingResult(
            headline="Một quyết định cần đủ dữ kiện",
            dominant_theme="Từ quan sát sang hành động",
            key_card=TarotKeyCard(
                card_id="major_09",
                card_name="Ẩn Sĩ",
                reason="Điểm neo",
            ),
            practical_takeaway=["Chốt tiêu chí trước khi chọn hướng."],
        )
        now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone(timedelta(hours=7)))
        state = build_recap_state(
            spread_title="Bản đồ quyết định",
            user_name="Mai",
            drawn_cards=self.cards,
            reading_result=result,
            ai_reading="Bài đọc dài không nên bị nhét vào recap.",
            now=now,
        )
        self.assertEqual(state.hero_card.card.id, "major_09")
        self.assertEqual(state.headline, "Một quyết định cần đủ dữ kiện")
        self.assertEqual(state.takeaway, "Chốt tiêu chí trước khi chọn hướng.")
        self.assertEqual(state.date_label, "05/10/2026")

    def test_fallback_does_not_need_extra_ai(self):
        state = build_recap_state(
            spread_title="Single Card",
            user_name="Mai",
            drawn_cards=[self.cards[0]],
            reading_result=None,
            ai_reading="Đối chiếu điều đang thấy với dữ kiện thật trước khi quyết định.",
        )
        self.assertEqual(state.hero_card.card.id, "major_01")
        self.assertTrue(state.headline)
        self.assertTrue(state.takeaway)

    def test_renderer_returns_portrait_png(self):
        result = TarotReadingResult(
            headline="Giữ nhịp trước khi tăng tốc",
            practical_takeaway=["Ưu tiên một bước kiểm chứng nhỏ."],
        )
        state = build_recap_state(
            spread_title="Past · Present · Future",
            user_name="Mai",
            drawn_cards=self.cards,
            reading_result=result,
            ai_reading="Reading",
        )
        buffer = render_recap_card_to_bytes(state)
        self.assertLess(len(buffer.getvalue()), 8 * 1024 * 1024)
        self.assertEqual(buffer.read(8), b"\x89PNG\r\n\x1a\n")
        buffer.seek(0)
        with Image.open(buffer) as image:
            self.assertEqual(image.size, (1200, 1500))
            self.assertEqual(image.mode, "RGB")

    def test_result_view_exposes_recap_on_second_row(self):
        view = TarotResultActionView(
            author_id=1,
            author_name="Mai",
            drawn_cards=self.cards,
            question="Tôi nên ưu tiên gì?",
            ai_reading="Reading",
            reader_style="auto",
            spread_key="ppf",
            tarot_manager=FakeManager(),
            reading_result=TarotReadingResult(
                headline="Headline",
                practical_takeaway=["Takeaway"],
            ),
            spread_title="Past · Present · Future",
        )
        recap = next(
            item for item in view.children
            if getattr(item, "custom_id", "") == "tarot_recap"
        )
        self.assertEqual(recap.row, 1)
        followup = next(item for item in view.children if getattr(item, "custom_id", "") == "tarot_followup")
        positive = next(item for item in view.children if getattr(item, "custom_id", "") == "tarot_rate_pos")
        negative = next(item for item in view.children if getattr(item, "custom_id", "") == "tarot_rate_neg")
        self.assertEqual(followup.row, 0)
        self.assertEqual(followup.label, "❓ Hỏi thêm (0/3)")
        self.assertEqual(positive.row, 1)
        self.assertEqual(negative.row, 1)
        view.stop()

    def test_fallback_text_strips_markdown_for_image(self):
        state = build_recap_state(
            spread_title="**Single Card**",
            user_name="Mai",
            drawn_cards=[self.cards[0]],
            reading_result=None,
            ai_reading="**Điều đáng làm:** kiểm tra lại dữ kiện trước khi quyết định.",
        )
        self.assertNotIn("**", state.spread_title)
        self.assertNotIn("**", state.takeaway)


class TarotRecapTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_visually_disables_every_result_button(self):
        view = TarotResultActionView(
            author_id=1,
            author_name="Mai",
            drawn_cards=[drawn("major_01", 1)],
            question="Test",
            ai_reading="Reading",
            reader_style="auto",
            spread_key="single",
            tarot_manager=FakeManager(),
            reading_result=TarotReadingResult(
                headline="Headline",
                practical_takeaway=["Takeaway"],
            ),
            spread_title="Single Card",
        )
        await view.on_timeout()
        self.assertTrue(all(item.disabled for item in view.children))
        view.stop()


if __name__ == "__main__":
    unittest.main()
