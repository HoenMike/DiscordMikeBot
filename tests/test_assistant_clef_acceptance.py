"""T22.3 Clef routing acceptance: untrusted model output must not open tools."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from features.assistant.providers.cloudflare import CloudflareDecisionRouter, ClefDecision
from features.assistant.router import route_message


class ClefOutputValidationTests(unittest.TestCase):
    def test_cloudflare_choice_with_calibrated_confidence(self):
        decision = CloudflareDecisionRouter._parse_choice({
            "choice": "discord_history",
            "probabilities": {"discord_history": 0.94, "chat": 0.06},
        })
        self.assertEqual(decision, ClefDecision("discord_history", 0.94))

    def test_invalid_outputs_do_not_gain_implicit_confidence(self):
        for payload in (
            "web_search", None, {}, {"choice": "execute_python", "confidence": 1.0},
            {"choice": "web_search"}, {"choice": "archive_search", "confidence": "nan"},
            {"choice": "web_search", "confidence": "inf"},
            {"choice": "discord_history", "confidence": "-inf"},
        ):
            with self.subTest(payload=payload):
                result = CloudflareDecisionRouter._parse_choice(payload)
                self.assertTrue(result is None or result.confidence == 0.0)


class ClefRouterSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def _route(self, text, choice, confidence=0.96, allowed=frozenset({"web.search", "discord_history.search", "archive.search"})):
        clef = SimpleNamespace(
            enabled=True,
            classify=AsyncMock(return_value=ClefDecision(choice, confidence)),
        )
        return await route_message(
            text,
            cloudflare_router=clef,
            allowed_search_tools=allowed,
        )

    async def test_clef_routes_allowed_sources_with_specific_evidence(self):
        cases = (
            ("Giá xe máy điện mới nhất hôm nay là bao nhiêu?", "web_search", "web.search"),
            ("Hồi đầu năm Theo từng nói gì về mua xe vậy?", "discord_history", "discord_history.search"),
            ("Trong Archive có cái meme mèo nào không?", "archive_search", "archive.search"),
        )
        for query, choice, tool in cases:
            with self.subTest(choice=choice):
                result = await self._route(query, choice)
                self.assertEqual(result.tool, tool)
                self.assertEqual(result.source, f"clef_{choice}")

    async def test_clef_confidence_must_be_finite_and_bounded(self):
        for value in (float("nan"), float("inf"), float("-inf"), -1.0, 1.1):
            with self.subTest(confidence=value):
                decision = await self._route(
                    "Giá xe máy điện mới nhất hôm nay là bao nhiêu?",
                    "web_search", confidence=value,
                )
                self.assertIsNone(decision.tool)
                self.assertEqual(decision.source, "local_low_confidence")

    async def test_unknown_intent_is_not_reported_as_success(self):
        decision = await self._route(
            "Giá xe máy điện mới nhất hôm nay là bao nhiêu?",
            "execute_python",
        )
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "local_clef_unknown")

    async def test_clef_cannot_override_source_privacy_or_provider_gate(self):
        query = "Thông tin trong tin nhắn Discord hôm nay có gì mới?"
        decision = await self._route(query, "web_search")
        self.assertIsNone(decision.tool)
        decision = await self._route(
            "Giá xe máy điện mới nhất hôm nay là bao nhiêu?",
            "web_search", allowed=frozenset(),
        )
        self.assertIsNone(decision.tool)
        self.assertEqual(decision.source, "clef_web_search_blocked")


if __name__ == "__main__":
    unittest.main()
