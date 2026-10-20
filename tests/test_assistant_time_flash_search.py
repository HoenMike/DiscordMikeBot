"""Regression: date-grounded banter, Flash-only deep tasks and T1 live schedules."""
import unittest
from datetime import datetime as ActualDatetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.ai import _build_prompt, _candidate_models, generate_chat_reply
from features.assistant.cog import choose_conversation_route
from features.assistant.router import (
    _obvious_public_event_schedule_search,
    _public_event_query,
    _safe_public_web_query,
    route_message,
)


class FrozenVietnamClock(ActualDatetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 20, 9, 19, tzinfo=tz)


class DateGroundingTests(unittest.TestCase):
    def test_october_20_banter_uses_real_vietnam_date(self):
        with patch("features.assistant.ai.datetime", FrozenVietnamClock):
            prompt = _build_prompt(
                "<@123456789012345678> nó đòi chúc 20/10 kìa",
                None,
                SimpleNamespace(
                    to_prompt_text=lambda: "Trước đó mọi người chat tháng 3.",
                    recent=[], social_referent=None,
                ),
            )
        self.assertIn("20/10/2026", prompt)
        self.assertIn("UTC+7", prompt)
        self.assertIn("MỐC NGÀY LƯỢT NÀY", prompt)
        self.assertIn("không được bịa đang tháng 3", prompt)


class TeamScheduleRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_t1_next_game_routes_to_brave_without_clef(self):
        router = SimpleNamespace(enabled=False, classify=AsyncMock())
        query = "sắp tới khi nào T1 có trận đấu á?"
        decision = await route_message(
            query, cloudflare_router=router,
            allowed_search_tools=frozenset({"web.search"}),
        )
        self.assertEqual(decision.tool, "web.search")
        self.assertEqual(decision.source, "local_public_event_schedule")
        self.assertIn("League of Legends esports", decision.arguments["query"])
        self.assertIn("GMT+7", decision.arguments["query"])
        router.classify.assert_not_awaited()

    async def test_t1_next_game_on_reply_remains_public_search(self):
        decision = await choose_conversation_route(
            "T1 sắp tới khi nào có trận đấu?",
            previous_session=SimpleNamespace(intent="chat"),
            is_live_continuation=True, has_images=False,
            cloudflare_router=SimpleNamespace(enabled=False),
            min_confidence=0.55,
            allowed_search_tools=frozenset({"web.search"}),
        )
        self.assertEqual(decision.tool, "web.search")

    async def test_private_discord_context_never_leaves_for_brave(self):
        queries = [
            "T1 trong tin nhắn hồi nãy sắp đấu ai?",
            "sắp tới khi nào <@123456789012345678> có trận đấu với T1?",
            "sắp tới tôi có trận đấu với bạn bè lúc nào?",
            "khi nào con T1 theo tin nhắn phía trên có trận?",
            "https://discord.com/channels/1/2/3 T1 sắp đấu khi nào?",
        ]
        for query in queries:
            with self.subTest(query=query):
                self.assertFalse(_obvious_public_event_schedule_search(query))
                self.assertFalse(_safe_public_web_query(query))
                decision = await route_message(
                    query,
                    cloudflare_router=SimpleNamespace(enabled=False),
                    allowed_search_tools=frozenset({"web.search"}),
                )
                self.assertIsNone(decision.tool)

    def test_no_search_for_vague_or_private_games(self):
        self.assertFalse(_obvious_public_event_schedule_search("sắp tới đi đánh trận game nào vậy?"))
        self.assertFalse(_obvious_public_event_schedule_search("t1 chơi được không?"))

    def test_t1_search_is_anchored_to_vn_today(self):
        with patch("features.assistant.router.datetime", FrozenVietnamClock):
            query = _public_event_query("Khi nào T1 có trận tiếp theo?")
        self.assertIn("2026", query)
        self.assertIn("2026-10-20", query)
        self.assertIn("League of Legends esports", query)


class QualityTierTests(unittest.IsolatedAsyncioTestCase):
    def test_no_pro_in_any_default_chat_tier(self):
        for tier in ("fast", "balanced", "deep"):
            with self.subTest(tier=tier):
                self.assertNotIn("gemini-3.1-pro-preview", _candidate_models(tier))
        self.assertEqual(_candidate_models("deep")[0], "gemini-3.8-flash")

    async def test_deep_uses_flash_with_medium_thinking(self):
        with patch(
            "features.assistant.ai.bounded_ai_generate",
            new=AsyncMock(return_value=SimpleNamespace(text="Đã phân tích")),
        ) as generate:
            result = await generate_chat_reply("Giải thích kiến trúc hệ thống", model_tier="deep")
        self.assertEqual(result.model, "gemini-3.8-flash")
        self.assertEqual(generate.await_args.kwargs["model"], "gemini-3.8-flash")
        config = generate.await_args.kwargs["config"]
        self.assertIn("medium", str(config.thinking_config.thinking_level).lower())


if __name__ == "__main__":
    unittest.main()
