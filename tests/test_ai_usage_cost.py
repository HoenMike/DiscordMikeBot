"""Cost ledger tests: price changes, token semantics, privacy and projections."""
import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.ai_usage import (
    estimate_micros, extract_usage, normalize_model, render_report,
    task_family, usage_event, store,
)


class TestUsageCalculation(unittest.TestCase):
    def test_model_normalization_and_task_buckets(self):
        self.assertEqual(normalize_model("models/GEMINI-3.8-FLASH"), "gemini-3.8-flash")
        self.assertEqual(task_family("Asumi Conversation"), "chat")
        self.assertEqual(task_family("MapReduce Chunk 1/3"), "summary")
        self.assertEqual(task_family("Tarot Custom Spread"), "tarot")
        self.assertEqual(task_family("Cabin AI"), "cabin")
        self.assertEqual(task_family("Dungeon DM"), "dnd")

    def test_thinking_and_cached_tokens_not_double_charged(self):
        meta = SimpleNamespace(prompt_token_count=3000, candidates_token_count=500,
                               thoughts_token_count=100, cached_content_token_count=1000)
        response = SimpleNamespace(usage_metadata=meta, model_version="models/gemini-3.8-flash")
        usage = extract_usage(response)
        self.assertEqual(usage, {"prompt": 3000, "output": 500, "thinking": 100, "cached": 1000})
        at = datetime(2026, 10, 18, tzinfo=timezone.utc)
        # (2000*0.75 + 1000*0.075 + 600*3.75) micro-USD.
        self.assertEqual(estimate_micros("gemini-3.8-flash", usage, at), 3825)
        self.assertEqual(estimate_micros("gemini-3.8-flash", usage,
                                         datetime(2027, 1, 1, tzinfo=timezone.utc)), 7650)

    def test_unrecognized_or_missing_usage_does_not_appear_free(self):
        at = datetime(2026, 10, 18, tzinfo=timezone.utc)
        response = SimpleNamespace(usage_metadata=None, model_version="gemini-3.8-flash")
        event = usage_event(model="gemini-3.8-flash", response=response, at=at)
        self.assertIsNone(event[11])
        self.assertEqual(event[12], "UNPRICED")
        valid = {"prompt": 100, "output": 50, "thinking": 0, "cached": 0}
        self.assertIsNone(estimate_micros("gemma-4-31b-it", valid, at))

    def test_no_negative_invalid_or_duplicate_thinking_count(self):
        meta = SimpleNamespace(prompt_token_count=100, candidates_token_count=30,
                               thoughts_token_count=40, cached_content_token_count=101)
        self.assertIsNone(extract_usage(SimpleNamespace(usage_metadata=meta)))
        meta.cached_content_token_count = 10
        meta.prompt_token_count = -1
        self.assertIsNone(extract_usage(SimpleNamespace(usage_metadata=meta)))

    def test_event_never_stores_prompt_or_response_body(self):
        meta = SimpleNamespace(prompt_token_count=200, candidates_token_count=25,
                               thoughts_token_count=0, cached_content_token_count=0)
        response = SimpleNamespace(usage_metadata=meta, model_version="gemini-3.5-flash-lite",
                                   text="private Discord reply", prompt="private Discord prompt")
        event = usage_event(model="gemini-3.5-flash-lite", response=response,
                            label="Asumi Conversation", latency_ms=99)
        self.assertEqual(len(event), 15)
        self.assertNotIn("private", repr(event))
        self.assertEqual(event[3], "chat")
        self.assertGreater(event[11], 0)

    def test_failed_request_unknown_billing_and_zero_private_data(self):
        event = usage_event(model="gemini-3.8-flash", label="Tarot", outcome="failed",
                            error_type="TimeoutError")
        self.assertIsNone(event[11])
        self.assertEqual(event[12], "FAILED_UNKNOWN_BILLING")
        self.assertEqual(event[-1], "TimeoutError")

    def test_forecast_and_runway_are_marked_conditional(self):
        # task, model, calls, ok, errors, unpriced, in, out, thinking, cached, microUSD
        rows = [("chat", "gemini-3.8-flash", 8, 7, 1, 0, 24000, 4000, 2000, 0, 500000),
                ("tarot", "gemini-3.5-flash-lite", 2, 2, 0, 1, 4000, 500, 0, 0, 100000)]
        report = render_report(rows, days=30, prepay_vnd=150000,
                               eligible_credits_vnd=1298530)
        self.assertIn("15,600đ", report)
        self.assertIn("30 ngày", report)
        self.assertIn("GIẢ ĐỊNH", report)
        self.assertIn("chưa định giá 1", report)
        self.assertIn("thinking", report.lower())

    def test_only_failed_or_unpriced_calls_never_show_zero_forecast(self):
        rows = [("chat", "gemma-4-31b-it", 2, 1, 1, 1, 100, 20, 0, 0, 0)]
        report = render_report(rows, days=7, prepay_vnd=150000)
        self.assertIn("CHƯA XÁC ĐỊNH", report)
        self.assertIn("Chưa đủ dữ liệu", report)
        self.assertIn("chưa định giá", report)
        self.assertNotIn("0đ / 30 ngày", report)
        self.assertNotIn("tháng**", report)

    def test_no_history_report_does_not_fabricate_costs(self):
        self.assertIn("Chưa có dữ liệu", render_report([], days=7))


class TestUsageStore(unittest.IsolatedAsyncioTestCase):
    async def test_fail_closed_if_turso_is_unavailable(self):
        with patch("config.TURSO_AUTH_TOKEN", "configured"), \
             patch("core.ai_usage.db_client") as db:
            db.connect = AsyncMock()
            db.is_cloud = False
            with self.assertRaisesRegex(RuntimeError, "requires Turso"):
                await store._init()

    async def test_core_ai_records_success_without_interrupting_request(self):
        from core.ai import bounded_ai_generate
        result = SimpleNamespace(text="reply", model_version="gemini-3.8-flash",
                                 usage_metadata=SimpleNamespace(prompt_token_count=100,
                                     candidates_token_count=20, thoughts_token_count=0,
                                     cached_content_token_count=0))
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(return_value=result)))
        with patch("core.ai.get_aio_client", return_value=fake), \
             patch("core.ai._track_ai_call") as track:
            reply = await bounded_ai_generate("gemini-3.8-flash", "hello", None, 2, label="Asumi Conversation")
        self.assertIs(reply, result)
        self.assertEqual(track.call_args[0][2], "ok")
        self.assertIs(track.call_args.kwargs["response"], result)

    async def test_core_ai_records_failed_attempt_without_changing_exception(self):
        from core.ai import bounded_ai_generate
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(
            side_effect=RuntimeError("provider down"))))
        with patch("core.ai.get_aio_client", return_value=fake), \
             patch("core.ai._track_ai_call") as track:
            with self.assertRaisesRegex(RuntimeError, "provider down"):
                await bounded_ai_generate("gemini-3.8-flash", "hello", None, 2, label="Tarot")
        self.assertEqual(track.call_args[0][2], "failed")


if __name__ == "__main__":
    unittest.main()
