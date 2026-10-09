"""T25 Discord in-message Tarot rich UI pilot."""
import unittest
from PIL import Image
from features.tarot.deck import DrawnCard, TAROT_DECK
from features.tarot.inline_ui import render_inline_tarot_to_bytes
from features.tarot.reading.recap import build_recap_state
from features.tarot.reading.schema import TarotReadingResult


class InlineTarotUiTests(unittest.TestCase):
    def make_state(self):
        card = DrawnCard(
            card=TAROT_DECK["major_02"],
            is_reversed=False,
            position_index=0,
            position_title="Năng lượng ngày",
            position_description="Năng lượng ngày",
        )
        reading = TarotReadingResult(
            full_reading="Luận giải đầy đủ sẽ nằm trong Discord button.",
            headline="Đừng vội quyết định trước khi đủ thông tin.",
            core_message="Nên quan sát trước.",
            practical_takeaway=["Hãy ghi lại một điều bạn học được hôm nay."],
        )
        return build_recap_state(
            spread_title="Daily hôm nay",
            user_name="Tester",
            drawn_cards=[card],
            reading_result=reading,
            ai_reading=reading.full_reading,
        )

    def test_rich_inline_image_is_real_compact_png(self):
        state = self.make_state()
        data = render_inline_tarot_to_bytes(state)
        self.assertTrue(data.getvalue().startswith(b"\\x89PNG\\r\\n\\x1a\\n"))
        with Image.open(data) as image:
            self.assertEqual(image.size, (1200, 760))
            self.assertEqual(image.mode, "RGB")
        self.assertIn("thông tin", state.headline)
        self.assertIn("ghi lại", state.takeaway)

    def test_long_reading_does_not_enter_visual_layout(self):
        state = self.make_state()
        self.assertLessEqual(len(state.headline), 110)
        self.assertLessEqual(len(state.takeaway), 190)


if __name__ == "__main__":
    unittest.main()
