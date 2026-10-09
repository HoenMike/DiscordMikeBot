"""Legacy Tarot UI: full reading stays inside Discord, never in TXT files."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from features.tarot.deck import DrawnCard, TAROT_DECK
from features.tarot.reading.pagination import TarotReadingPagesView, split_reading_pages
from features.tarot.tarot_view import TarotResultActionView


def make_result(reading="Bình tĩnh trước mỗi quyết định.", *, cards=1):
    card = DrawnCard(
        card=TAROT_DECK["major_02"], is_reversed=False,
        position_index=0, position_title="Lời khuyên",
        position_description="Lời khuyên",
    )
    return TarotResultActionView(
        author_id=7, author_name="Test", drawn_cards=[card] * cards,
        question="Hôm nay?", context=None, ai_reading=reading,
        reader_style="auto", spread_key="single", tarot_manager=None,
    )


def read_button(view):
    return next(x for x in view.children if x.custom_id == "tarot_read_full")


class TarotReadingPagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_reading_preserves_full_text_and_sanitizes_mentions(self):
        original = ("Lời khuyên @everyone. Đọc kỹ.\n\n" * 330).strip()
        pages = split_reading_pages(original)
        self.assertGreater(len(pages), 1)
        self.assertEqual("".join(pages), discord.utils.escape_mentions(original))
        self.assertTrue(all(len(page) <= 3400 for page in pages))
        self.assertNotIn("@everyone", "".join(pages))

    async def test_button_uses_ephemeral_embed_only_without_any_txt_file(self):
        view = make_result("Dòng thông điệp dài. " * 420)
        response = SimpleNamespace(send_message=AsyncMock())
        interaction = SimpleNamespace(user=SimpleNamespace(id=14), response=response)
        await read_button(view).callback(interaction)
        kwargs = response.send_message.await_args.kwargs
        self.assertTrue(kwargs["ephemeral"])
        self.assertFalse(kwargs["allowed_mentions"].everyone)
        self.assertIn("LUẬN GIẢI TAROT", kwargs["embed"].title)
        self.assertIsInstance(kwargs["view"], TarotReadingPagesView)
        self.assertNotIn("file", kwargs)
        self.assertNotIn("files", kwargs)
        self.assertNotIn("content", kwargs)
        view.stop()

    async def test_short_reading_has_no_page_controls_and_no_attachment(self):
        view = make_result("Ngắn, rõ, đủ.")
        response = SimpleNamespace(send_message=AsyncMock())
        interaction = SimpleNamespace(user=SimpleNamespace(id=14), response=response)
        await read_button(view).callback(interaction)
        kwargs = response.send_message.await_args.kwargs
        self.assertIsNone(kwargs["view"])
        self.assertIn("Ngắn, rõ, đủ.", kwargs["embed"].description)
        self.assertNotIn("file", kwargs)
        view.stop()

    async def test_page_navigation_never_draws_new_cards_and_is_viewer_scoped(self):
        pages = TarotReadingPagesView("Từ khóa màu sắc và cảm xúc.\n" * 600, viewer_id=14)
        self.assertTrue(pages.previous_button.disabled)
        self.assertFalse(pages.next_button.disabled)
        response = SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock())
        interaction = SimpleNamespace(user=SimpleNamespace(id=14), response=response)
        await pages.next_button.callback(interaction)
        self.assertEqual(pages.page_index, 1)
        self.assertIn("Trang 2/", pages.build_embed().footer.text)
        self.assertFalse(pages.previous_button.disabled)
        response.edit_message.assert_awaited_once()
        denied_response = SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock())
        denied = SimpleNamespace(user=SimpleNamespace(id=99), response=denied_response)
        await pages.previous_button.callback(denied)
        denied_response.send_message.assert_awaited_once()
        denied_response.edit_message.assert_not_awaited()
        self.assertEqual(pages.page_index, 1)

    async def test_multi_card_long_reading_keeps_read_full_button(self):
        view = make_result("Một điều cần nhớ. " * 500, cards=3)
        self.assertEqual(read_button(view).custom_id, "tarot_read_full")
        view.stop()


if __name__ == "__main__":
    unittest.main()
