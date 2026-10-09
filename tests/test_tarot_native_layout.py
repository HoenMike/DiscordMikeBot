"""T25.1b native read-only Tarot V2 detail and safe rollback."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from features.tarot.deck import DrawnCard, TAROT_DECK
from features.tarot.native_layout import build_full_reading_layout
from features.tarot.tarot_view import TarotResultActionView


class TarotNativeReadingTests(unittest.IsolatedAsyncioTestCase):
    def make_result(self, reading="Bình tĩnh trước mỗi quyết định."):
        card = DrawnCard(
            card=TAROT_DECK["major_02"], is_reversed=False,
            position_index=0, position_title="Lời khuyên",
            position_description="Lời khuyên",
        )
        return TarotResultActionView(
            author_id=7, author_name="Test", drawn_cards=[card],
            question="Hôm nay?", context=None, ai_reading=reading,
            reader_style="auto", spread_key="single", tarot_manager=None,
        )

    def button(self, view):
        return next(x for x in view.children if x.custom_id == "tarot_read_full")

    async def test_builder_shows_real_reading_and_sanitizes_mentions(self):
        v = build_full_reading_layout("Lời khuyên @everyone. Đọc kỹ.")
        self.assertIsInstance(v, discord.ui.LayoutView)
        self.assertIsInstance(v.children[0], discord.ui.Container)
        parts = [x.content for x in v.children[0].children
                 if isinstance(x, discord.ui.TextDisplay)]
        self.assertIn("Luận giải Tarot đầy đủ", parts[0])
        self.assertIn("Lời khuyên", parts[1])
        self.assertNotIn("@everyone", parts[1])
        self.assertEqual(len(v.children), 1)

    async def test_long_reading_references_file_component(self):
        v = build_full_reading_layout("Đây là nội dung. " * 500,
                                      with_attachment=True)
        self.assertIsInstance(v.children[1], discord.ui.File)
        self.assertIn("tarot_reading.txt", v.children[1].media.url)
        part = v.children[0].children[2].content
        self.assertIn("tệp", part)
        self.assertLessEqual(len(part), 3900)

    async def test_button_sends_ephemeral_native_v2_no_embed(self):
        view = self.make_result()
        response = SimpleNamespace(send_message=AsyncMock())
        interaction = SimpleNamespace(user=SimpleNamespace(id=14), response=response)
        with patch("core.constants.ASUMI_TAROT_READING_NATIVE_V2_ENABLED", True):
            await self.button(view).callback(interaction)
        kwargs = response.send_message.await_args.kwargs
        self.assertTrue(kwargs["ephemeral"])
        self.assertIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertNotIn("embed", kwargs)
        self.assertNotIn("file", kwargs)
        view.stop()

    async def test_400_falls_back_to_embed_not_ambiguous_failure(self):
        view = self.make_result("A" * 4100)
        err = discord.HTTPException(
            SimpleNamespace(status=400, reason="Bad Request"), "Invalid Form Body"
        )
        response = SimpleNamespace(send_message=AsyncMock(side_effect=[err, None]))
        interaction = SimpleNamespace(user=SimpleNamespace(id=7), response=response)
        with patch("core.constants.ASUMI_TAROT_READING_NATIVE_V2_ENABLED", True):
            await self.button(view).callback(interaction)
        self.assertEqual(response.send_message.await_count, 2)
        first = response.send_message.await_args_list[0].kwargs
        fallback = response.send_message.await_args_list[1].kwargs
        self.assertIsInstance(first["view"], discord.ui.LayoutView)
        self.assertIsInstance(first["view"].children[1], discord.ui.File)
        self.assertEqual(first["file"].filename, "tarot_reading.txt")
        self.assertIn("embed", fallback)
        self.assertEqual(fallback["file"].filename, "tarot_reading.txt")
        self.assertNotIn("view", fallback)
        view.stop()

    async def test_flag_off_preserves_existing_embed(self):
        view = self.make_result()
        response = SimpleNamespace(send_message=AsyncMock())
        interaction = SimpleNamespace(user=SimpleNamespace(id=7), response=response)
        with patch("core.constants.ASUMI_TAROT_READING_NATIVE_V2_ENABLED", False):
            await self.button(view).callback(interaction)
        self.assertIn("embed", response.send_message.await_args.kwargs)
        self.assertNotIn("view", response.send_message.await_args.kwargs)
        view.stop()


if __name__ == "__main__":
    unittest.main()
