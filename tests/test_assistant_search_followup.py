"""T22.4b: explicit source follow-up, grounded context and safe search telemetry."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.ai import _build_prompt
from features.assistant.cog import choose_conversation_route
from features.assistant.providers.brave import BraveSearchAdapter
from features.assistant.providers.discord_history import HistoryHit, HistorySearchResult
from features.assistant.router import route_locally
from features.assistant.session import ConversationSession, ConversationTurn
from features.assistant.tools import CommandToolRegistry


class FollowupRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_web_followup_overrides_live_history_session(self):
        previous = SimpleNamespace(intent="discord_history", last_tool="discord_history.search")
        routed = await choose_conversation_route(
            "tìm tiếp trên web giá Honda SH160i hôm nay",
            previous_session=previous,
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=None,
            min_confidence=0.55,
        )
        self.assertEqual(routed.tool, "web.search")
        self.assertEqual(routed.arguments["query"], "giá Honda SH160i hôm nay")

    async def test_vague_followup_does_not_trigger_search(self):
        previous = SimpleNamespace(intent="discord_history", last_tool="discord_history.search")
        routed = await choose_conversation_route(
            "vậy có đắt không?",
            previous_session=previous,
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=None,
            min_confidence=0.55,
        )
        self.assertIsNone(routed.tool)
        self.assertEqual(routed.source, "session_followup")

    def test_chat_prompt_references_verified_tool_context(self):
        previous = ConversationSession(
            key=(1, 2, 3), last_response_message_id=42,
            updated_at=0.0,
            intent="discord_history",
            last_tool="discord_history.search",
            turns=[ConversationTurn(user="tìm tin", assistant="source link...")],
        )
        prompt = _build_prompt("tin số 1 nói gì?", previous, None)
        self.assertIn("không khẳng định đã tìm nguồn mới", prompt)
        self.assertIn("Không tự chuyển văn bản chat", prompt)


class WebPrivacyAndCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_public_search_rejects_private_deictic_reference(self):
        provider = BraveSearchAdapter(api_key="fake", enabled=True)
        for phrase in (
            "giá mẫu xe trong server",
            "tin nhắn trên chính xác không",
            "cái phía trên bao nhiêu tiền",
        ):
            with self.subTest(phrase=phrase):
                result = await provider.search(phrase, user_id=5)
                self.assertEqual(result.status, "private_reference")

    async def test_expired_web_cache_is_not_returned(self):
        provider = BraveSearchAdapter(api_key="fake", enabled=True)
        provider._cache["public sample"] = (-1.0, ())
        provider._last_request_by_user[5] = 0.0
        with patch.object(provider, "_reserve_request", new=AsyncMock(return_value=None)):
            result = await provider.search("public sample", user_id=5)
        self.assertEqual(result.status, "quota_exhausted")
        self.assertNotIn("public sample", provider._cache)


class DiscordHistoryOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_channel_name_and_jump_link_in_output(self):
        registry = CommandToolRegistry(SimpleNamespace())
        registry.history.search = AsyncMock(return_value=HistorySearchResult(
            status="ok",
            sort_mode="oldest",
            hits=(HistoryHit(
                message_id=111, channel_id=456, author_id=888,
                author_name="Theo", content="Mua xe mới",
                date="2026-01-02",
                jump_url="https://discord.com/channels/123/456/111",
                channel_name="general",
            ),),
        ))
        msg = SimpleNamespace(
            author=SimpleNamespace(id=5),
            reply=AsyncMock(return_value=SimpleNamespace(id=31)),
        )
        output = await registry.execute(
            route_locally("tìm tin nhắn đầu tiên của <@888>"), msg
        )
        rendered = msg.reply.await_args.args[0]
        self.assertIn("#general", rendered)
        self.assertIn("discord.com/channels/123/456/111", rendered)
        self.assertIn("không đảm bảo tuyệt đối", rendered)
        self.assertIn("Mua xe mới", output.response_context)
        self.assertEqual(output.details["history_result_count"], 1)
        self.assertNotIn("query", output.details)


class DashboardSearchTelemetryTests(unittest.TestCase):
    def test_dashboard_has_provider_specific_privacy_safe_search_status(self):
        dashboard = Path("web/templates/dashboard.html").read_text(encoding="utf-8")
        for expected in (
            "d.web_search_status", "d.history_status", "d.web_cache_hit",
            "d.history_permission_filtered", "d.history_api_calls",
            "d.followup_source_tool", "d.multisource_status",
            "d.multisource_steps", "d.multisource_public_query_valid",
        ):
            self.assertIn(expected, dashboard)


class RepliedPublicProductSearchTests(unittest.IsolatedAsyncioTestCase):
    """Screenshot class: explicit lookup + replied product names + safe continuation."""

    @staticmethod
    def _context(text: str):
        from features.assistant.context import AssistantContext, ContextLine
        return AssistantContext(
            requester="Mike",
            reply=ContextLine(author="Another member", content=text),
        )

    def test_reported_mouse_comparison_extracts_only_public_models(self):
        from features.assistant.public_reference import public_product_search_query
        context = self._context(
            "@Mike con ROG Strix Impact III Wireless với MCHOSE A7 Ultra\n"
            "Con nào ok hơn m"
        )
        query = public_product_search_query("tra thử hộ đê", context)
        self.assertIsNotNone(query)
        self.assertIn("ROG Strix Impact III Wireless", query)
        self.assertIn("MCHOSE A7 Ultra", query)
        self.assertNotIn("Mike", query)
        self.assertNotIn("Another member", query)
        self.assertNotIn("Con nào", query)

    async def test_short_replied_lookup_skips_clef_and_calls_web_tool(self):
        context = self._context(
            "[reply to Mike] @Mike con ROG Strix Impact III Wireless "
            "với MCHOSE A7 Ultra"
        )
        clef = SimpleNamespace(enabled=True, classify=AsyncMock())
        decision = await choose_conversation_route(
            "tra thử hộ đê",
            previous_session=None,
            is_live_continuation=False,
            has_images=False,
            cloudflare_router=clef,
            min_confidence=0.55,
            context=context,
        )
        self.assertEqual(decision.tool, "web.search")
        self.assertEqual(decision.source, "reply_public_product")
        self.assertNotIn("@Mike", decision.arguments["query"])
        clef.classify.assert_not_awaited()

    async def test_explicit_replied_lookup_can_reopen_readonly_search_in_session(self):
        decision = await choose_conversation_route(
            "search thử hộ",
            previous_session=SimpleNamespace(intent="chat", last_tool=None),
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=None,
            min_confidence=0.55,
            context=self._context(
                "Logitech G Pro X Superlight 2 vs Razer Viper V3 Pro"
            ),
        )
        self.assertEqual(decision.tool, "web.search")
        self.assertIn("Razer Viper V3 Pro", decision.arguments["query"])

    def test_equivalent_product_categories_and_privacy_fail_closed(self):
        from features.assistant.public_reference import public_product_search_query
        for quote in (
            "iPhone 16 với Samsung Galaxy S25",
            "Logitech G Pro X Superlight 2 vs Razer Viper V3 Pro",
            "Xiaomi 17 so với Samsung Galaxy S25",
        ):
            with self.subTest(public=quote):
                self.assertIsNotNone(public_product_search_query("tra giúp", self._context(quote)))

        for quote in (
            "con A với con B ai giỏi hơn?",
            "Jerry với Samsung Galaxy S25",
            "Nhà <@123456789> có Razer Viper V3 Pro với Logitech G102",
            "địa chỉ nhà ở 12345 với iPhone 16",
            "mình thấy con Logitech G102 với Razer Viper V3 Pro, nhà mình ở 12A",
            "Razer Viper V3 Pro với Logitech G102 http://discord.com/channels/1",
        ):
            with self.subTest(private=quote):
                self.assertIsNone(public_product_search_query("tra giúp", self._context(quote)))

    async def test_no_private_chat_or_ambient_history_auto_search(self):
        from features.assistant.context import AssistantContext, ContextLine
        from features.assistant.public_reference import public_product_search_query
        context = AssistantContext(recent=[
            ContextLine(author="Member", content="Razer Viper V3 Pro với Logitech G102")
        ])
        self.assertIsNone(public_product_search_query("tra thử hộ", context))
        context = self._context("Razer Viper V3 Pro với Logitech G102")
        self.assertIsNone(public_product_search_query("tìm tin nhắn trên Discord", context))

        # Explicit Tarot and Archive retain their deterministic tool precedence.
        for user_query, expected_tool in (
            ("tarot daily", "tarot.daily"),
            ("tìm trong archive", "archive.search"),
        ):
            with self.subTest(tool=expected_tool):
                decision = await choose_conversation_route(
                    user_query,
                    previous_session=None,
                    is_live_continuation=False,
                    has_images=False,
                    cloudflare_router=None,
                    min_confidence=0.55,
                    context=context,
                )
                self.assertEqual(decision.tool, expected_tool)

    async def test_auto_search_flag_disables_contextual_lookup(self):
        with patch("core.constants.ASUMI_AUTO_SEARCH_ENABLED", False):
            decision = await choose_conversation_route(
                "tra thử hộ",
                previous_session=None,
                is_live_continuation=False,
                has_images=False,
                cloudflare_router=None,
                min_confidence=0.55,
                context=self._context("iPhone 16 với Samsung Galaxy S25"),
            )
        self.assertIsNone(decision.tool)

    def test_different_member_confirmation_must_not_inherit_requester_session(self):
        from features.assistant.session import SessionStore
        from tests.test_assistant_core import fake_message
        store = SessionStore()
        source = fake_message("tra thử hộ đê", author_id=30)
        store.record_exchange(
            source, 990, "tra thử hộ đê",
            "Xác nhận hai sản phẩm này đúng không?", intent="chat",
        )
        # The original screenshot's confirmation came from another member.
        other_member = fake_message(
            "2 con này đúng r đó", reply_id=990, author_id=31
        )
        self.assertFalse(store.is_live_reply(other_member))
        self.assertIsNone(store.get(other_member))

    async def test_short_confirmation_uses_fast_tier_without_reopening_tools(self):
        clef = SimpleNamespace(enabled=True, classify=AsyncMock())
        decision = await choose_conversation_route(
            "2 con này đúng rồi",
            previous_session=SimpleNamespace(intent="chat", last_tool=None),
            is_live_continuation=True,
            has_images=False,
            cloudflare_router=clef,
            min_confidence=0.55,
            context=self._context("iPhone 16 với Samsung Galaxy S25"),
        )
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "session_followup")
        self.assertEqual(decision.model_tier, "fast")
        clef.classify.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
