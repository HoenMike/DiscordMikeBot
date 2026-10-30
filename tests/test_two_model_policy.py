"""Two-SKU Gemini policy across every generation entry point."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import config
from core import ai as shared_ai
from core import constants as policy
from features.assistant.ai import _candidate_models
from features.cabin.constants import CABIN_FALLBACK_MODELS
from features.summary.ai_summary import _generate_with_fallback


class TwoGeminiModelsTests(unittest.IsolatedAsyncioTestCase):
    def test_exact_global_model_allowlist_and_role_mapping(self):
        self.assertEqual(
            policy.ALLOWED_GEMINI_MODELS,
            frozenset({"gemini-3.8-flash", "gemini-3.5-flash-lite"}),
        )
        self.assertEqual(_candidate_models("fast"), ["gemini-3.5-flash-lite"])
        self.assertEqual(_candidate_models("balanced"), ["gemini-3.8-flash"])
        self.assertEqual(_candidate_models("deep"), ["gemini-3.8-flash"])
        self.assertEqual(CABIN_FALLBACK_MODELS, ["gemini-3.5-flash-lite"])
        self.assertEqual(config.GEMINI_DATA_MODEL, policy.GEMINI_GENERAL_MODEL)
        self.assertEqual(config.GEMINI_SUMMARY_MODEL, policy.GEMINI_GENERAL_MODEL)
        self.assertEqual(config.GEMINI_QA_MODEL, policy.GEMINI_GENERAL_MODEL)
        self.assertEqual(config.GEMINI_TAROT_MODEL, policy.GEMINI_GENERAL_MODEL)
        self.assertEqual(config.GEMINI_CABIN_MODEL, policy.GEMINI_TINY_MODEL)
        self.assertEqual(config.TAROT_FALLBACK_MODELS, [policy.GEMINI_GENERAL_MODEL])
        self.assertEqual(config.SUMMARY_FALLBACK_MODELS, [policy.GEMINI_GENERAL_MODEL])
        self.assertEqual(config.QA_FALLBACK_MODELS, [policy.GEMINI_GENERAL_MODEL])

    async def test_provider_boundary_blocks_retired_models_before_network(self):
        with patch("core.ai.get_aio_client", side_effect=AssertionError("network reached")) as client:
            for model in ("gemini-3.6-flash", "gemini-3.7-flash",
                          "gemini-3.1-flash-lite", "gemma-4-31b-it"):
                with self.subTest(model=model):
                    with self.assertRaisesRegex(ValueError, "not allowed"):
                        await shared_ai.bounded_ai_generate(model, "test", None, 1)
            client.assert_not_called()

    async def test_legacy_summary_model_does_not_override_general_policy(self):
        with patch("features.summary.ai_summary.bounded_ai_generate",
                   new=AsyncMock(return_value=SimpleNamespace(text="ok"))) as call:
            result = await _generate_with_fallback(
                "some text", None,
                primary_model="gemini-3.6-flash",
                fallback_models=["gemini-3.5-flash-lite", "gemini-3.7-flash"],
            )
        self.assertEqual(result, "ok")
        self.assertEqual(call.await_count, 1)
        self.assertEqual(call.await_args.kwargs["model"], policy.GEMINI_GENERAL_MODEL)

    def test_runtime_has_no_legacy_fallback_literals(self):
        runtime_files = (
            "core/constants.py", "config.py", "features/assistant/ai.py",
            "features/tarot/ai.py", "features/cabin/constants.py",
            "features/summary/ai_summary.py",
        )
        for name in runtime_files:
            source = Path(name).read_text(encoding="utf-8")
            with self.subTest(path=name):
                for retired in (
                    "gemini-3.6-flash", "gemini-3.7-flash",
                    "gemini-3.1-flash-lite", "gemma-4-31b-it",
                ):
                    self.assertNotIn(retired, source)


if __name__ == "__main__":
    unittest.main()
