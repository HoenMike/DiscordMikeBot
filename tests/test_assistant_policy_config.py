"""Asumi policy lives in code; only tokens/identifiers are deployment inputs."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from core import constants as policy
from features.assistant.providers.brave import BraveSearchAdapter
from features.assistant.providers.cloudflare import CloudflareDecisionRouter
from features.assistant.providers.discord_history import DiscordHistorySearcher
from features.assistant.providers.vectorize import ArchiveSemanticIndex
from features.assistant.router import route_message
from features.assistant.tools import CommandToolRegistry


class InCodeSearchPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_gas_price_routes_to_real_search_without_clef(self):
        decision = await route_message(
            "giá xăng hôm nay như nào", cloudflare_router=None,
            allowed_search_tools=frozenset(),
        )
        self.assertEqual(decision.tool, "web.search")
        self.assertEqual(decision.source, "local_fresh_public")
        self.assertEqual(decision.arguments["query"], "giá xăng hôm nay như nào")

    async def test_private_context_never_auto_exports_to_brave(self):
        for query in (
            "giá xăng trong server hôm nay như nào",
            "giá xe trong đoạn chat phía trên hôm nay ra sao",
            "giá xăng ở https://discord.com/channels/1/2/3 hôm nay",
            "giá xăng <@123456789012345678> hôm nay",
        ):
            with self.subTest(query=query):
                decision = await route_message(
                    query, cloudflare_router=None,
                    allowed_search_tools=frozenset(),
                )
                self.assertNotEqual(decision.tool, "web.search")

    async def test_vague_question_and_greeting_do_not_spend_search(self):
        for query in ("hello", "xăng có tốt hơn dầu không?", "hôm nay khỏe không?"):
            with self.subTest(query=query):
                decision = await route_message(query, cloudflare_router=None)
                self.assertIsNone(decision.tool)

    def test_no_key_means_no_paid_provider(self):
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "",
                                      "ASUMI_WEB_SEARCH_ENABLED": "true"}, clear=True):
            self.assertFalse(BraveSearchAdapter.from_env().enabled)

    def test_key_automatically_activates_without_env_switch(self):
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "ci-only-brave",
                                      "ASUMI_WEB_SEARCH_ENABLED": "false",
                                      "ASUMI_WEB_SEARCH_MONTHLY_REQUEST_CAP": "999999"}, clear=True):
            adapter = BraveSearchAdapter.from_env()
        self.assertTrue(adapter.enabled)
        self.assertEqual(adapter.monthly_cap, policy.ASUMI_WEB_SEARCH_MONTHLY_REQUEST_CAP)
        self.assertLessEqual(adapter.monthly_cap, 900)

    def test_discord_history_is_code_configured_not_env(self):
        with patch.dict("os.environ", {"ASUMI_DISCORD_HISTORY_ENABLED": "false"}, clear=True):
            p = DiscordHistorySearcher.from_env(SimpleNamespace())
        self.assertEqual(p.enabled, policy.ASUMI_DISCORD_HISTORY_ENABLED)

    def test_clef_requires_cloudflare_credentials_not_env_flag(self):
        with patch.dict("os.environ", {
            "CLOUDFLARE_ACCOUNT_ID": "ci-account",
            "CLOUDFLARE_API_TOKEN": "ci-token",
            "CF_ASSISTANT_ENABLED": "false",
        }, clear=True):
            self.assertEqual(CloudflareDecisionRouter.from_env().enabled, policy.ASUMI_CLEF_ENABLED)

    def test_archive_vectorize_stays_code_gated(self):
        with patch.dict("os.environ", {
            "CLOUDFLARE_ACCOUNT_ID": "ci-account",
            "CLOUDFLARE_API_TOKEN": "ci-token",
            "CLOUDFLARE_VECTORIZE_TOKEN": "ci-vector",
            "CF_ARCHIVE_SEMANTIC_ENABLED": "true",
        }, clear=True):
            self.assertFalse(ArchiveSemanticIndex.from_env().enabled)

    async def test_missing_brave_key_returns_honest_error_not_fake_chat_answer(self):
        registry = CommandToolRegistry(SimpleNamespace())
        msg = SimpleNamespace(
            author=SimpleNamespace(id=1),
            reply=AsyncMock(return_value=SimpleNamespace(id=3)),
        )
        with patch("features.assistant.tools.brave_search.search",
                   new=AsyncMock(return_value=SimpleNamespace(
                       status="disabled", hits=(), elapsed_ms=0.0,
                       cache_hit=False, remaining=None))):
            decision = await route_message("giá xăng hôm nay như nào")
            result = await registry.execute(decision, msg)
        self.assertTrue(result.handled)
        text = msg.reply.await_args.args[0]
        self.assertIn("đã tích hợp", text)
        self.assertIn("BRAVE_SEARCH_API_KEY", text)

if __name__ == "__main__":
    unittest.main()
