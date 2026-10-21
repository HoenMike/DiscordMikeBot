"""Fast-path usage, privacy and context-aware conversation regressions."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from features.assistant.usage_intent import parse_usage_intent
from features.assistant.usage_report import usage_window, format_quick_usage
from features.assistant.router import route_locally, RouteDecision
from features.assistant.cog import AssistantCog, choose_conversation_route, _self_contained_public_research_followup
from features.assistant.tools import CommandToolRegistry, ToolExecutionResult
from features.assistant.ai import ASSISTANT_SYSTEM_PROMPT, _build_prompt, _filter_unseen_custom_emotes
from features.assistant.session import ConversationSession, ConversationTurn
from features.assistant.context import AssistantContext, ContextLine


class UsageRouteTests(unittest.TestCase):
    def test_common_owner_queries_are_direct_routes(self):
        cases = {
            "token": "7d",
            "hết bao nhiêu token rồi": "7d",
            "đã xài bao nhiêu token hôm nay?": "today",
            "token tháng này": "month",
            "token 30 ngày": "30d",
            "bot đã tốn bao nhiêu tiền?": "7d",
            "gemini chi phí tháng này bao nhiêu": "month",
            "TOKEN 7 ngày": "7d",
        }
        for query, period in cases.items():
            with self.subTest(query=query):
                self.assertEqual(parse_usage_intent(query).period, period)
                routed = route_locally(query)
                self.assertEqual(routed.tool, "ai_usage.report")
                self.assertEqual(routed.arguments["period"], period)

    def test_unrelated_context_security_and_chat_do_not_hijack(self):
        for query in (
            "JWT access token này dùng làm gì?",
            "API key lưu ở đâu",
            "phân tích số liệu startup ở Mỹ",
            "tốn bao nhiêu tiền mua xe?",
            "token xài làm gì trong context window?",
            "bao nhiêu token cho một trang A4?",
            "tarot daily",
        ):
            with self.subTest(query=query):
                self.assertIsNone(parse_usage_intent(query))
                self.assertNotEqual(route_locally(query).tool, "ai_usage.report")

    def test_vietnam_day_and_month_windows_are_real_calendar_windows(self):
        # Oct 21 2026 16:36 ICT = 09:36 UTC.
        now = datetime(2026, 10, 21, 9, 36, tzinfo=timezone.utc)
        start, end = usage_window("today", now)
        self.assertEqual(start.isoformat(), "2026-10-20T17:00:00+00:00")
        self.assertEqual(end, now)
        month, _ = usage_window("month", now)
        self.assertEqual(month.isoformat(), "2026-09-30T17:00:00+00:00")
        with self.assertRaises(ValueError):
            usage_window("all-time", now)

    def test_unknown_cost_is_never_reported_as_zero(self):
        unknown = [("chat", "gemini-3.8-flash", 1, 1, 0, 1, 0, 0, 0, 0, 0)]
        self.assertIn("CHƯA XÁC ĐỊNH", format_quick_usage(unknown, "today"))
        self.assertIn("Chưa có dữ liệu", format_quick_usage([], "month"))
        priced = [("chat", "gemini-3.8-flash", 2, 2, 0, 0, 1000, 200, 100, 0, 2200)]
        result = format_quick_usage(priced, "7d")
        self.assertIn("1,000 token", result)
        self.assertIn("~$0.0022", result)


class UsageOwnerPrivacyTests(unittest.IsolatedAsyncioTestCase):
    def registry(self, is_owner=True):
        reg = CommandToolRegistry.__new__(CommandToolRegistry)
        reg.bot = SimpleNamespace(is_owner=AsyncMock(return_value=is_owner))
        return reg

    def message(self):
        member = SimpleNamespace(
            id=120, send=AsyncMock(return_value=SimpleNamespace(id=88)),
        )
        return SimpleNamespace(
            author=member, guild=SimpleNamespace(id=20),
            reply=AsyncMock(return_value=SimpleNamespace(id=99)),
        )

    async def test_owner_report_is_sent_by_dm_not_in_channel(self):
        reg, msg = self.registry(True), self.message()
        with patch("features.assistant.usage_report.quick_usage_report",
                   new=AsyncMock(return_value="SECRET SPEND $123")) as quick:
            result = await reg.execute(route_locally("token"), msg)
        self.assertTrue(result.handled)
        self.assertEqual(result.details["ai_usage_status"], "sent_dm")
        quick.assert_awaited_once_with("7d")
        msg.author.send.assert_awaited_once()
        self.assertIn("SECRET SPEND", msg.author.send.await_args.args[0])
        self.assertNotIn("SECRET SPEND", msg.reply.await_args.args[0])
        self.assertNotIn("SECRET SPEND", result.response_context)

    async def test_unauthorized_cannot_read_turso_or_dm(self):
        reg, msg = self.registry(False), self.message()
        with patch("features.assistant.usage_report.quick_usage_report",
                   new_callable=AsyncMock) as quick:
            result = await reg.execute(route_locally("token"), msg)
        quick.assert_not_awaited()
        msg.author.send.assert_not_awaited()
        self.assertEqual(result.details["ai_usage_status"], "unauthorized")

    async def test_report_unavailable_fails_closed_not_zero(self):
        reg, msg = self.registry(True), self.message()
        with patch("features.assistant.usage_report.quick_usage_report",
                   new=AsyncMock(side_effect=RuntimeError("Turso down"))):
            result = await reg.execute(route_locally("token"), msg)
        self.assertEqual(result.details["ai_usage_status"], "unavailable")
        self.assertNotIn("0 token", msg.reply.await_args.args[0])


class ConversationalQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_usage_fast_path_skips_history_and_clef_entirely(self):
        cog = AssistantCog.__new__(AssistantCog)
        cog.should_handle = Mock(return_value=True)
        cog._query_from_message = Mock(return_value="token")
        cog.context_builder = SimpleNamespace(build=AsyncMock())
        cog.tools = SimpleNamespace(execute=AsyncMock(return_value=ToolExecutionResult(
            handled=True, details={"ai_usage_status": "sent_dm"},
        )))
        cog._log_dashboard_activity = Mock()
        message = SimpleNamespace(id=1234)
        self.assertTrue(await cog.handle_conversation_message(message))
        cog.context_builder.build.assert_not_awaited()
        cog.tools.execute.assert_awaited_once()
        self.assertEqual(cog.tools.execute.await_args.args[0].tool, "ai_usage.report")

    async def test_usage_bypasses_live_followup(self):
        with patch("features.assistant.cog.route_message", new_callable=AsyncMock) as route:
            decision = await choose_conversation_route(
                "hôm nay xài bao nhiêu token?", previous_session=SimpleNamespace(intent="chat"),
                is_live_continuation=True, has_images=False,
                cloudflare_router=None, min_confidence=0.55,
            )
        self.assertEqual(decision.tool, "ai_usage.report")
        route.assert_not_awaited()

    async def test_fully_public_question_reconsiders_tools_but_vague_followup_does_not(self):
        self.assertTrue(_self_contained_public_research_followup("Theo BLS 2025 có bao nhiêu công ty đóng cửa?"))
        self.assertFalse(_self_contained_public_research_followup("10% đó là bao nhiêu công ty?"))
        self.assertFalse(_self_contained_public_research_followup("Trong server này 2025 nói gì về 10%?"))
        expected = RouteDecision(intent="web_search", tool="web.search")
        with patch("features.assistant.cog.route_message", new=AsyncMock(return_value=expected)) as routed:
            result = await choose_conversation_route(
                "Theo BLS 2025 có bao nhiêu công ty đóng cửa?",
                previous_session=SimpleNamespace(intent="chat"),
                is_live_continuation=True, has_images=False,
                cloudflare_router=object(), min_confidence=0.55,
                allowed_search_tools=frozenset({"web.search"}),
            )
        self.assertEqual(result.tool, "web.search")
        routed.assert_awaited_once()

    async def test_custom_emoji_reuses_current_chat_not_fake_ids(self):
        known = "<:maythicnhonko:123456789012345678>"
        unknown = "<:made_up:987654321098765432>"
        ctx = AssistantContext(recent=[
            ContextLine(author="Friend", content="haizz " + known),
        ])
        reply = _filter_unseen_custom_emotes("Okay " + known + " " + unknown, "", ctx)
        self.assertIn(known, reply)
        self.assertNotIn(unknown, reply)
        self.assertNotIn(known, _filter_unseen_custom_emotes(known, "", None))

    async def test_prompt_knows_past_bot_answers_are_not_verified_and_emoji_names_unreliable(self):
        s = ConversationSession(
            key=(1, 2, 3), last_response_message_id=40, updated_at=0,
            turns=[ConversationTurn(user="Có 10% không?", assistant="Có 10% [1.1].")],
        )
        ctx = AssistantContext(recent=[
            ContextLine(author="Friend", content="ôi chịu <:maythicnhonko:111>"),
        ])
        p = _build_prompt("10% tức bao nhiêu công ty?", s, ctx)
        self.assertIn("không phải kết quả fact-check", p)
        self.assertIn("đừng đoán ý nghĩa qua tên", p)
        self.assertIn("không tự nâng cấp thành nguồn", ASSISTANT_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
