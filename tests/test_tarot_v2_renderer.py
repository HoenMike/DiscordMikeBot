import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from features.tarot.deck import DrawnCard, TAROT_DECK
from features.tarot.renderer import (
    _fit_header_title,
    _safe_title,
    render_reading_board_to_bytes,
    render_spread_to_bytes,
)
from features.tarot.rendering.state import ReadingBoardState


def drawn(card_id: str, position_index: int, title: str, reversed_: bool = False) -> DrawnCard:
    return DrawnCard(
        card=TAROT_DECK[card_id],
        is_reversed=reversed_,
        position_index=position_index,
        position_title=title,
        position_description=title,
    )


def cards(count: int):
    ids = [
        "major_00", "major_02", "major_18", "major_19", "wands_01",
        "cups_02", "swords_03", "pentacles_04", "major_09", "major_10",
    ]
    return [
        drawn(ids[idx], idx + 1, f"LÁ {idx + 1}: VỊ TRÍ {idx + 1}", reversed_=(idx % 3 == 1))
        for idx in range(count)
    ]


def image_from_buffer(buffer: io.BytesIO) -> Image.Image:
    buffer.seek(0)
    with Image.open(buffer) as raw:
        return raw.copy()


class TarotReadingBoardStateTests(unittest.TestCase):
    def test_legacy_state_normalizes_indices_and_emphasis(self):
        spread_cards = cards(3)
        state = ReadingBoardState.from_legacy(
            "ppf",
            spread_cards,
            {0, 2, 99},
            just_revealed_indices={2, 8},
            key_card_id=spread_cards[2].card.id,
            target_position_index=1,
            final=True,
        )
        self.assertEqual(state.revealed_indices, frozenset({0, 2}))
        self.assertEqual(state.just_revealed_indices, frozenset({2}))
        self.assertTrue(state.is_key_card(2))
        self.assertTrue(state.is_target(1))
        self.assertTrue(state.final)


class TarotReadingBoardRendererTests(unittest.TestCase):
    def setUp(self):
        self.asset_patch = patch("features.tarot.renderer.ensure_card_asset", return_value=None)
        self.asset_patch.start()

    def tearDown(self):
        self.asset_patch.stop()

    def assert_board(self, spread_key, spread_cards, expected_size, revealed=None, **kwargs):
        buffer = render_spread_to_bytes(
            spread_key,
            spread_cards,
            revealed_indices=(set(range(len(spread_cards))) if revealed is None else revealed),
            **kwargs,
        )
        self.assertLess(len(buffer.getvalue()), 8 * 1024 * 1024)
        image = image_from_buffer(buffer)
        self.assertEqual(image.size, expected_size)
        self.assertEqual(image.mode, "RGB")
        return image

    def test_one_card_portrait_board(self):
        self.assert_board("single", cards(1), (1080, 1350), revealed={0})

    def test_long_bilingual_spread_title_is_not_truncated(self):
        full_title = "Mind - Body - Spirit (Tâm Trí - Thể Chất - Trực Giác)"
        safe = _safe_title("mbs", full_title)
        self.assertEqual(safe, full_title)
        self.assertNotIn("...", safe)

        canvas = Image.new("RGB", (1400, 900))
        draw = ImageDraw.Draw(canvas)
        font, lines = _fit_header_title(draw, safe.upper(), 1400)

        self.assertLessEqual(len(lines), 2)
        self.assertEqual(" ".join(lines), safe.upper())
        max_width = 1400 - max(120, 1400 // 10)
        for line in lines:
            box = draw.textbbox((0, 0), line, font=font)
            self.assertLessEqual(box[2] - box[0], max_width)

    def test_custom_title_up_to_schema_limit_keeps_full_text(self):
        full_title = (
            "Bản Đồ Quyết Định Giữa Hai Hướng Đi Và Những Điều Cần Cân Nhắc Kỹ"
        )
        safe = _safe_title("custom", full_title)
        self.assertEqual(safe, full_title)
        self.assertNotIn("...", safe)

        canvas = Image.new("RGB", (1500, 1150))
        draw = ImageDraw.Draw(canvas)
        font, lines = _fit_header_title(draw, safe.upper(), 1500)

        self.assertLessEqual(len(lines), 2)
        self.assertEqual(" ".join(lines), safe.upper())

    def test_three_card_partial_board(self):
        self.assert_board(
            "ppf",
            cards(3),
            (1400, 900),
            revealed={0, 2},
            just_revealed_indices={2},
        )

    def test_five_card_known_layouts(self):
        self.assert_board("two_paths", cards(5), (1400, 1100))
        self.assert_board("horseshoe", cards(5), (1500, 1100))

    def test_celtic_mobile_readable_canvas_target(self):
        self.assert_board(
            "celtic",
            cards(10),
            (1600, 1350),
            revealed=set(range(10)),
            key_card_id="major_18",
            final=True,
        )

    def test_dynamic_four_five_six_seven_layouts(self):
        self.assert_board("custom_four", cards(4), (1300, 1100), spread_title="Custom 4")
        self.assert_board("custom_five", cards(5), (1300, 1150), spread_title="Custom 5")
        self.assert_board("custom_six", cards(6), (1500, 1150), spread_title="Custom 6")
        self.assert_board("custom_seven", cards(7), (1500, 1150), spread_title="Custom 7")

    def test_reversed_key_new_and_target_states_render_without_mutating_cards(self):
        spread_cards = cards(3)
        original_reversed = [card.is_reversed for card in spread_cards]
        self.assert_board(
            "ppf",
            spread_cards,
            (1400, 900),
            revealed={0, 1, 2},
            just_revealed_indices={1},
            key_card_id=spread_cards[2].card.id,
            target_position_index=0,
            final=True,
        )
        self.assertEqual([card.is_reversed for card in spread_cards], original_reversed)

    def test_renderer_failure_falls_back_to_text_board(self):
        state = ReadingBoardState.from_legacy("ppf", cards(3), {0, 1})
        with patch("features.tarot.renderer.render_reading_board", side_effect=RuntimeError("boom")):
            buffer = render_reading_board_to_bytes(state)
        image = image_from_buffer(buffer)
        self.assertEqual(image.size[0], 1200)
        self.assertGreaterEqual(image.size[1], 760)


if __name__ == "__main__":
    unittest.main()
