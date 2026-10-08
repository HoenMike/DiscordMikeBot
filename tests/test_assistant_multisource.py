"""T22.5: bounded supervised multi-source planning, user consent and privacy."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from features.assistant.cog import choose_conversation_route
from features.assistant.multisource import (
    rank_verified_history_hits,
    safe_literal_public_query,
    split_cross_source_request,
)
from features.assistant.providers.discord_history import HistoryHit, HistorySearchResult
from features.assistant.router import RouteDecision, route_locally
from features.assistant.tools import CommandToolRegistry, ToolExecutionResult


HISTORY = "tìm xem hồi đầu năm <@123456789012345678> có nhắn gì về mua xe"
PUBLIC = "giá Honda SH160i hôm nay"
COMBINED = HISTORY + " rồi tìm trên web " + PUBLIC


def hit(mid, content):
    return HistoryHit(
        message_id=mid, channel_id=777, author_id=123456789012345678,
        author_name="Theo", content=content, date="2026-01-20",
        jump_url=f"https://discord.com/channels/123/777/{mid}",
        channel_name="general",
    )


class CrossSourcePlannerTests(unittest.TestCase):
    def test_literal_public_query_only(self):
        parsed = split_cross_source_request(COMBINED)
        self.assertEqual(parsed.history_query, HISTORY)
        self.assertEqual(parsed.public_query, PUBLIC)
        self.assertTrue(parsed.explicit_web)
        decision = route_locally(COMBINED)
        self.assertEqual(decision.tool, "multi_source.search")
        self.assertEqual(decision.source, "local_explicit_multisource")
        self.assertEqual(decision.arguments["public_query"], PUBLIC)

    def test_implicit_history_to_web_requires_public_query(self):
        query = HISTORY + " rồi kiểm tra giá mẫu đó bây giờ"
        parsed = split_cross_source_request(query)
        self.assertIsNotNone(parsed)
        self.assertFalse(parsed.explicit_web)
        self.assertEqual(parsed.public_query, "")
        self.assertEqual(route_locally(query).tool, "multi_source.search")

    def test_normal_search_not_accidentally_upgraded(self):
        for query in (
            HISTORY,
            "tìm trên web giá Honda SH160i hôm nay",
            "Hôm nay có gì vui không?",
            "giá Honda SH160i hôm nay",
        ):
            with self.subTest(query=query):
                self.assertNotEqual(route_locally(query).tool, "multi_source.search")

    def test_external_query_must_be_standalone(self):
        self.assertTrue(safe_literal_public_query(PUBLIC))
        for query in (
            "giá mẫu đó hôm nay",
            "giá chiếc xe đó hôm nay",
            "giá trong tin nhắn Discord hôm nay",
            "giá Honda trong server hôm nay",
            "giá <@123456789012345678> hôm nay",
            "giá https://discord.com/channels/111/222/333 hôm nay",
            "cái phía trên giá bao nhiêu",
        ):
            with self.subTest(query=query):
                self.assertFalse(safe_literal_public_query(query))

    def test_acl_verified_hit_ranking_is_stable(self):
        items = (
            hit(10, "Xe điện khác"),
            hit(11, "Mình thích Honda SH160i để đi làm"),
            hit(12, "Honda SH160i đời mới"),
        )
        ranked = rank_verified_history_hits(items, PUBLIC)
        self.assertEqual([h.message_id for h in ranked], [11, 12, 10])
        self.assertEqual(rank_verified_history_hits(items, "giá xe hôm nay"), items)


class MultiSourceExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = CommandToolRegistry(SimpleNamespace())
        self.msg = SimpleNamespace(
            author=SimpleNamespace(id=31),
            reply=AsyncMock(side_effect=[
                SimpleNamespace(id=101), SimpleNamespace(id=102),
                SimpleNamespace(id=103),
            ]),
        )
        self.report = HistorySearchResult(
            status="ok", sort_mode="relevance",
            hits=(hit(10, "Mua xe VinFast"), hit(11, "Honda SH160i là lựa chọn của mình")),
        )
        self.registry.history.search = AsyncMock(return_value=self.report)

    async def test_user_literal_only_is_forwarded_to_public_provider(self):
        web_result = ToolExecutionResult(
            handled=True, response_message_ids=(201,),
            response_context="Web Search public results",
            details={"web_search_status": "ok", "web_result_count": 2},
        )
        with patch.object(
            self.registry, "_execute_web_search",
            new=AsyncMock(return_value=web_result),
        ) as web:
            output = await self.registry.execute(route_locally(COMBINED), self.msg)

        self.assertEqual(web.await_count, 1)
        web_decision = web.await_args.args[0]
        self.assertEqual(web_decision.tool, "web.search")
        self.assertEqual(web_decision.arguments["query"], PUBLIC)
        self.assertEqual(web_decision.source, "multisource_explicit_public")
        self.registry.history.search.assert_awaited_once_with(self.msg, HISTORY)
        self.assertEqual(output.details["multisource_status"], "completed")
        self.assertEqual(output.details["multisource_public_origin"], "user_literal")
        self.assertEqual(output.details["multisource_steps"], 2)
        # The original history reply is locally reordered; never fed to Brave.
        first_reply = self.msg.reply.await_args_list[0].args[0]
        self.assertLess(first_reply.find("Honda SH160i"), first_reply.find("VinFast"))
        self.assertIn("không chứng minh", self.msg.reply.await_args_list[-1].args[0])

    async def test_no_public_api_call_for_deictic_query(self):
        unsafe = HISTORY + " rồi tìm trên web giá mẫu đó hôm nay"
        with patch.object(self.registry, "_execute_web_search", new=AsyncMock()) as web:
            output = await self.registry.execute(route_locally(unsafe), self.msg)
        web.assert_not_awaited()
        self.assertEqual(output.details["multisource_status"], "needs_public_query")
        self.assertEqual(output.details["multisource_steps"], 1)
        self.assertIn("ghi rõ truy vấn", self.msg.reply.await_args_list[-1].args[0])

    async def test_no_web_if_history_denied_or_no_results(self):
        for status in ("permission_error", "no_results", "indexing"):
            with self.subTest(status=status):
                self.registry.history.search.reset_mock(
                    return_value=True, side_effect=True,
                )
                self.registry.history.search.return_value = HistorySearchResult(status=status)
                self.msg.reply.reset_mock(side_effect=True)
                self.msg.reply.side_effect = lambda *a, **k: SimpleNamespace(id=9)
                with patch.object(self.registry, "_execute_web_search", new=AsyncMock()) as web:
                    output = await self.registry.execute(route_locally(COMBINED), self.msg)
                web.assert_not_awaited()
                self.assertEqual(output.details["multisource_status"], "history_unavailable")

    async def test_web_failure_returns_history_provenance_and_no_false_success(self):
        web_result = ToolExecutionResult(
            handled=True, response_message_ids=(201,),
            response_context="Web Search: quota_exhausted",
            details={"web_search_status": "quota_exhausted"},
        )
        with patch.object(
            self.registry, "_execute_web_search", new=AsyncMock(return_value=web_result),
        ):
            output = await self.registry.execute(route_locally(COMBINED), self.msg)
        self.assertEqual(output.details["multisource_status"], "web_unavailable")
        self.assertEqual(self.msg.reply.await_count, 1)
        self.assertIn("Jump to Message", self.msg.reply.await_args.args[0])

    async def test_invalid_manually_constructed_decision_fails_closed(self):
        decision = RouteDecision(
            intent="multi_source", tool="multi_source.search",
            arguments={
                "history_query": "xin chào",
                "public_query": PUBLIC,
                "explicit_web": True,
            },
        )
        with patch.object(self.registry, "_execute_web_search", new=AsyncMock()) as web:
            output = await self.registry.execute(decision, self.msg)
        web.assert_not_awaited()
        self.registry.history.search.assert_not_awaited()
        self.assertEqual(output.details["multisource_status"], "invalid_history")

    async def test_explicit_multisource_overrides_live_reply(self):
        decision = await choose_conversation_route(
            COMBINED,
            previous_session=SimpleNamespace(intent="discord_history"),
            is_live_continuation=True, has_images=False,
            cloudflare_router=None, min_confidence=0.55,
        )
        self.assertEqual(decision.tool, "multi_source.search")


if __name__ == "__main__":
    unittest.main()
