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
            "d.followup_source_tool",
        ):
            self.assertIn(expected, dashboard)


if __name__ == "__main__":
    unittest.main()
