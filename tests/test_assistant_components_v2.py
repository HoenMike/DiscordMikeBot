"""T25.1: native Discord Components V2 Search reply contract."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from features.assistant.providers.brave import BraveHit, BraveSearchResult
from features.assistant.router import route_locally
from features.assistant.search_presenter import build_search_embed, build_search_layout
from features.assistant.tools import CommandToolRegistry


class NativeSearchLayoutTests(unittest.IsolatedAsyncioTestCase):
    def hits(self):
        return (
            BraveHit("CKTG lịch", "https://example.org/worlds", "Lịch giải"),
            BraveHit("Lịch thể thao", "https://example.org/games", "Kết quả"),
        )

    async def test_layout_is_genuine_v2_without_embeds_or_unsafe_markup(self):
        layout = build_search_layout(
            "Khi nào CKTG @everyone bắt đầu?", self.hits(),
            "CKTG bắt đầu vào tháng 10. Xem lịch gốc.",
        )
        self.assertIsInstance(layout, discord.ui.LayoutView)
        self.assertEqual(len(layout.children), 1)
        panel = layout.children[0]
        self.assertIsInstance(panel, discord.ui.Container)
        self.assertEqual(len(panel.children), 3)
        self.assertIsInstance(panel.children[0], discord.ui.TextDisplay)
        self.assertIsInstance(panel.children[1], discord.ui.Separator)
        self.assertIsInstance(panel.children[2], discord.ui.TextDisplay)
        self.assertNotIn("@everyone", panel.children[0].content)
        body = panel.children[2].content
        self.assertTrue(body.startswith("**CKTG bắt đầu vào tháng 10.**"))
        self.assertIn("[1](https://example.org/worlds)", body)
        self.assertIn("[2](https://example.org/games)", body)
        legacy = build_search_embed(
            "Khi nào CKTG @everyone bắt đầu?", self.hits(),
            "CKTG bắt đầu vào tháng 10. Xem lịch gốc.",
        )
        self.assertEqual(body, legacy.description)
        self.assertLessEqual(len(body), 3900)

    async def test_policy_disabled_sends_legacy_embed(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=30),
            reply=AsyncMock(return_value=SimpleNamespace(id=301)),
        )
        answer = BraveSearchResult(status="ok", hits=self.hits())
        with patch(
            "features.assistant.tools.brave_search.search",
            new=AsyncMock(return_value=answer),
        ), patch.object(
            registry, "_summarize_public_search",
            new=AsyncMock(return_value="CKTG bắt đầu vào tháng 10."),
        ), patch("core.constants.ASUMI_SEARCH_NATIVE_V2_ENABLED", False):
            result = await registry.execute(
                route_locally("tìm trên web lịch CKTG"), msg,
            )
        self.assertIn("embed", msg.reply.await_args.kwargs)
        self.assertNotIn("view", msg.reply.await_args.kwargs)
        self.assertEqual(result.details["web_ui_renderer"], "legacy_embed")

    async def test_default_v2_sends_view_with_no_embed(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=30),
            reply=AsyncMock(return_value=SimpleNamespace(id=301)),
        )
        answer = BraveSearchResult(status="ok", hits=self.hits())
        with patch(
            "features.assistant.tools.brave_search.search",
            new=AsyncMock(return_value=answer),
        ), patch.object(
            registry, "_summarize_public_search",
            new=AsyncMock(return_value="CKTG bắt đầu vào tháng 10."),
        ), patch("core.constants.ASUMI_SEARCH_NATIVE_V2_ENABLED", True):
            result = await registry.execute(
                route_locally("tìm trên web lịch CKTG"), msg,
            )
        kwargs = msg.reply.await_args.kwargs
        self.assertIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertNotIn("embed", kwargs)
        self.assertNotIn("content", kwargs)
        self.assertEqual(result.details["web_ui_renderer"], "components_v2")
        self.assertEqual(result.response_message_ids, (301,))


if __name__ == "__main__":
    unittest.main()
