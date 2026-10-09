"""T22.3: Clef may propose sources; code gates provider use and privacy."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.cog import AssistantCog, choose_conversation_route
from features.assistant.providers.cloudflare import ClefDecision
from features.assistant.router import (
    _safe_public_web_query,
    route_locally,
    route_message,
)


class T22SourceRouterTests(unittest.IsolatedAsyncioTestCase):
    async def decision(self, query, intent, allowed, confidence=0.96):
        clef = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision(intent, confidence)),
        )
        return await route_message(
            query,
            cloudflare_router=clef,
            min_confidence=0.55,
            allowed_search_tools=frozenset(allowed),
        )

    async def test_current_public_price_gets_brave_when_enabled(self):
        decision = await self.decision(
            "Giá xe máy điện mới nhất hôm nay là bao nhiêu?",
            "web_search", {"web.search"},
        )
        self.assertEqual(decision.tool, "web.search")
        self.assertEqual(decision.source, "clef_web_search")
        self.assertIn("hôm nay", decision.arguments["query"])

    async def test_public_search_does_not_run_when_provider_disabled(self):
        decision = await self.decision(
            "Giá xe máy điện mới nhất hôm nay là bao nhiêu?",
            "web_search", set(),
        )
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "clef_web_search_blocked")

    async def test_cktg_schedule_auto_routes_to_brave_without_clef(self):
        clef = SimpleNamespace(enabled=False, classify=AsyncMock())
        result = await route_message(
            "khi nào CKTG bắt đầu đánh?", cloudflare_router=clef,
            allowed_search_tools=frozenset({"web.search"}),
        )
        self.assertEqual(result.tool, "web.search")
        self.assertEqual(result.source, "local_public_event_schedule")
        self.assertRegex(result.arguments["query"], r"20\d{2}$")
        clef.classify.assert_not_awaited()

        for unsafe in (
            "khi nào CKTG của <@123456789012345678> bắt đầu?",
            "khi nào CKTG trong server diễn ra?",
        ):
            with self.subTest(unsafe=unsafe):
                blocked = await route_message(
                    unsafe, cloudflare_router=clef,
                    allowed_search_tools=frozenset({"web.search"}),
                )
                self.assertIsNone(blocked.tool)

    async def test_private_discord_message_not_sent_to_brave(self):
        for query in (
            "Giá chiếc xe Theo nhắn trong server hôm nay là bao nhiêu?",
            "Có đúng giá xe trong tin nhắn <@123456789012345678>?",
            "Tin này https://discord.com/channels/111/222/333 có gì mới?",
            "Cái này đúng không?",
        ):
            with self.subTest(query=query):
                decision = await self.decision(
                    query, "web_search", {"web.search"},
                )
                self.assertIsNone(decision.tool)

    async def test_discord_history_only_for_historical_questions(self):
        decision = await self.decision(
            "Hồi đầu năm Theo từng nói gì về mua xe vậy?",
            "discord_history", {"discord_history.search"},
        )
        self.assertEqual(decision.tool, "discord_history.search")
        self.assertIn("mua xe", decision.arguments["query"])

    async def test_history_intent_not_used_for_public_news(self):
        decision = await self.decision(
            "Tin tức giá xe mới nhất hôm nay?",
            "discord_history", {"discord_history.search"},
        )
        self.assertIsNone(decision.tool)

    async def test_saved_archive_requires_clear_save_context(self):
        decision = await self.decision(
            "Có gì trong Archive tôi đã lưu về mèo?",
            "archive_search", {"archive.search"},
        )
        self.assertEqual(decision.tool, "archive.search")
        self.assertIn("semantic_query", decision.arguments)

    async def test_history_user_message_does_not_use_archive(self):
        decision = await self.decision(
            "Theo từng nói gì hồi đầu năm về mua xe?",
            "archive_search", {"archive.search"},
        )
        self.assertIsNone(decision.tool)

    async def test_low_confidence_never_triggers_search(self):
        decision = await self.decision(
            "Giá xe mới nhất hôm nay?",
            "web_search", {"web.search"}, confidence=0.40,
        )
        self.assertIsNone(decision.tool)

    async def test_clef_failure_fails_open_to_chat_but_closed_to_search(self):
        clef = SimpleNamespace(
            enabled=True, classify=AsyncMock(side_effect=TimeoutError()),
        )
        decision = await route_message(
            "Giá xe mới nhất hôm nay?",
            cloudflare_router=clef,
            allowed_search_tools=frozenset({"web.search"}),
        )
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "local_clef_error")

    async def test_reply_followup_does_not_search_without_explicit_request(self):
        clef = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision("web_search", 1.0)),
        )
        decision = await choose_conversation_route(
            "vậy cái đó nghĩa sao?",
            previous_session=SimpleNamespace(intent="web_search"),
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=clef,
            min_confidence=0.55,
            allowed_search_tools=frozenset({"web.search"}),
        )
        self.assertEqual(decision.source, "session_followup")
        self.assertIsNone(decision.tool)
        clef.classify.assert_not_awaited()

    def test_history_recall_beats_ambiguous_archive_phrase(self):
        decision = route_locally(
            "tìm lại chuyện hồi đầu năm <@123456789012345678> mua xe"
        )
        self.assertEqual(decision.tool, "discord_history.search")
        self.assertEqual(route_locally("tìm lại meme mèo").tool, "archive.search")

    async def test_public_search_synthesis_uses_only_brave_snippets(self):
        from features.assistant.providers.brave import BraveHit, BraveSearchResult
        from features.assistant.tools import CommandToolRegistry

        registry = CommandToolRegistry(SimpleNamespace())
        message = SimpleNamespace(
            author=SimpleNamespace(id=44),
            reply=AsyncMock(return_value=SimpleNamespace(id=456)),
        )
        brave_report = BraveSearchResult(
            status="ok",
            hits=(BraveHit(
                title="EV report",
                url="https://example.com/ev",
                description="Public EV update",
            ),),
        )
        with patch(
            "features.assistant.tools.brave_search.search",
            new=AsyncMock(return_value=brave_report),
        ), patch.object(
            registry, "_summarize_public_search",
            new=AsyncMock(return_value="Thông tin này mới [1]."),
        ) as synth, patch.dict(
            "os.environ", {"ASUMI_WEB_SEARCH_SYNTHESIS_ENABLED": "true"}
        ):
            result = await registry.execute(
                await self.decision(
                    "Giá xe điện hôm nay bao nhiêu?",
                    "web_search", {"web.search"},
                ),
                message,
            )
        embed = message.reply.await_args.kwargs["embed"]
        self.assertIn("Thông tin này mới", embed.description)
        self.assertNotIn("[1]", embed.description)
        self.assertIn("https://example.com/ev", embed.fields[0].value)
        self.assertTrue(result.details["web_synthesized"])
        synth.assert_awaited_once()
        self.assertNotIn("query", result.details)

    async def test_grounded_synthesis_failure_falls_back_to_source_list(self):
        from features.assistant.providers.brave import BraveHit, BraveSearchResult
        from features.assistant.tools import CommandToolRegistry

        registry = CommandToolRegistry(SimpleNamespace())
        message = SimpleNamespace(
            author=SimpleNamespace(id=44),
            reply=AsyncMock(return_value=SimpleNamespace(id=457)),
        )
        brave_report = BraveSearchResult(
            status="ok",
            hits=(BraveHit(
                title="Official update",
                url="https://example.com/news",
                description="Public update",
            ),),
        )
        with patch(
            "features.assistant.tools.brave_search.search",
            new=AsyncMock(return_value=brave_report),
        ), patch.object(
            registry, "_summarize_public_search",
            new=AsyncMock(side_effect=TimeoutError()),
        ), patch.dict(
            "os.environ", {"ASUMI_WEB_SEARCH_SYNTHESIS_ENABLED": "true"}
        ):
            result = await registry.execute(
                await self.decision(
                    "Tin tức mới nhất hôm nay?",
                    "web_search", {"web.search"},
                ),
                message,
            )
        embed = message.reply.await_args.kwargs["embed"]
        self.assertIn("https://example.com/news", embed.fields[0].value)
        self.assertIn("chưa thể xác minh", embed.description)
        self.assertFalse(result.details["web_synthesized"])

    async def test_cktg_route_now_synthesizes_answer_first(self):
        from features.assistant.providers.brave import BraveHit, BraveSearchResult
        from features.assistant.tools import CommandToolRegistry
        registry = CommandToolRegistry(SimpleNamespace())
        message = SimpleNamespace(
            author=SimpleNamespace(id=44),
            reply=AsyncMock(return_value=SimpleNamespace(id=600)),
        )
        report = BraveSearchResult(
            status="ok",
            hits=(BraveHit(
                title="Worlds 2026 lịch",
                url="https://example.com/official-worlds-2026",
                description="Thông tin lịch giải đấu.",
            ),),
        )
        decision = await route_message(
            "khi nào CKTG bắt đầu đánh?",
            cloudflare_router=SimpleNamespace(enabled=False),
            allowed_search_tools=frozenset({"web.search"}),
        )
        self.assertEqual(decision.source, "local_public_event_schedule")
        with patch(
            "features.assistant.tools.brave_search.search",
            new=AsyncMock(return_value=report),
        ), patch.object(
            registry, "_summarize_public_search",
            new=AsyncMock(return_value="CKTG bắt đầu ngày 15/10/2026."),
        ) as synth, patch(
            "core.constants.ASUMI_WEB_SEARCH_SYNTHESIS_ENABLED", True,
        ):
            result = await registry.execute(decision, message)
        synth.assert_awaited_once()
        embed = message.reply.await_args.kwargs["embed"]
        self.assertTrue(embed.description.startswith("CKTG bắt đầu"))
        self.assertIn("https://example.com/official-worlds-2026", embed.fields[0].value)
        self.assertTrue(result.details["web_synthesized"])

    def test_public_safety_gate(self):
        self.assertTrue(_safe_public_web_query(
            "giá xe ô tô mới nhất hôm nay là bao nhiêu?"
        ))
        self.assertFalse(_safe_public_web_query(
            "giá xe được nhắc trong đoạn chat phía trên?"
        ))

    def test_auto_search_requires_explicit_flag_and_available_provider(self):
        bot = SimpleNamespace()
        with patch("core.constants.ASUMI_AUTO_SEARCH_ENABLED", False):
            cog = AssistantCog(bot)
        cog.cloudflare_router.enabled = True
        self.assertFalse(cog._allowed_auto_search_tools())
        cog.auto_search_enabled = True
        cog.tools.history.enabled = True
        with patch(
            "features.assistant.providers.brave.brave_search.enabled", False,
        ):
            allowed = cog._allowed_auto_search_tools()
        self.assertNotIn("web.search", allowed)
        self.assertIn("discord_history.search", allowed)
        self.assertIn("archive.search", allowed)


if __name__ == "__main__":
    unittest.main()
