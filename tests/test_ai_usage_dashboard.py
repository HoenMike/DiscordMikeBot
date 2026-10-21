"""T31 usage dashboard: API authorization, aggregation and classic UI invariants."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.ai_usage import build_dashboard_payload

ROOT = Path(__file__).resolve().parents[1]
FIXED_NOW = datetime(2026, 10, 18, 7, 0, tzinfo=timezone.utc)
ROWS = [
    ("2026-10-18", "google-gemini", "chat", "gemini-3.8-flash",
     2, 2, 0, 0, 4000, 500, 100, 500, 12000),
    ("2026-10-17", "cloudflare-workers", "routing", "@cf/cloudflare/clef-flash",
     3, 2, 1, 2, 0, 0, 0, 0, 0),
]


class UsageDashboardPayloadTests(unittest.TestCase):
    def test_aggregates_by_day_model_feature_without_raw_messages(self):
        report = build_dashboard_payload(
            ROWS, days=7, at=FIXED_NOW, first_recorded_at="2026-10-10T06:00:00+00:00")
        self.assertEqual(report["totals"]["calls"], 5)
        self.assertEqual(report["totals"]["success"], 4)
        self.assertEqual(report["totals"]["failed"], 1)
        self.assertEqual(report["totals"]["unpriced"], 2)
        self.assertEqual(report["totals"]["usd_micros"], 12000)
        self.assertEqual(report["today_utc"]["calls"], 2)
        self.assertEqual(report["forecast_30d_usd_micros"], round(12000 * 30 / 7))
        self.assertTrue(report["incomplete"])
        self.assertFalse(report["early_sample"])
        self.assertEqual(report["by_model"][1]["provider"], "cloudflare-workers")
        self.assertEqual(report["by_feature"][1]["feature"], "routing")
        self.assertNotIn("raw_intent", str(report))
        self.assertNotIn("discord_id", str(report))

    def test_zero_events_unknown_prices_and_short_sample(self):
        empty = build_dashboard_payload([], days=30, at=FIXED_NOW)
        self.assertIsNone(empty["forecast_30d_usd_micros"])
        self.assertEqual(empty["totals"]["calls"], 0)
        unknown = build_dashboard_payload(
            [ROWS[1]], days=30, at=FIXED_NOW,
            first_recorded_at="2026-10-18T06:50:00+00:00")
        self.assertIsNone(unknown["forecast_30d_usd_micros"])
        self.assertTrue(unknown["early_sample"])
        self.assertTrue(unknown["incomplete"])

    def test_truncated_data_disables_forecast(self):
        report = build_dashboard_payload(
            [ROWS[0]], days=7, at=FIXED_NOW, truncated=True)
        self.assertTrue(report["truncated"])
        self.assertIsNone(report["forecast_30d_usd_micros"])

    def test_invalid_period_rejected(self):
        with self.assertRaises(ValueError):
            build_dashboard_payload([], days=365, at=FIXED_NOW)

    def test_classic_dashboard_keeps_feedback_and_loads_usage_lazily(self):
        html = (ROOT / "web/templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="tab-btn-feedback"', html)
        self.assertIn('id="tab-content-feedback"', html)
        self.assertIn("openFeedbackFrame()", html)
        self.assertIn('id="tab-btn-ai-usage"', html)
        self.assertIn('id="tab-content-ai-usage"', html)
        self.assertIn("else if (tab === 'ai-usage')", html)
        self.assertIn("loadAIUsage(false)", html)
        self.assertIn("if (currentTab !== 'ai-usage') return", html)
        self.assertIn("body.replaceChildren()", html)
        self.assertIn("td.textContent = String(cells[i])", html)
        self.assertIn("30 ngày", html)
        self.assertNotIn('id="asumi-sidebar"', html)


class UsageDashboardFlaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.app import app
        cls.app = app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    def login(self):
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True

    def test_not_logged_in_is_401(self):
        res = self.client.get("/api/admin/ai-usage?days=7")
        self.assertEqual(res.status_code, 401)

    def test_bad_window_is_rejected_before_store_call(self):
        self.login()
        with patch("core.ai_usage.store.dashboard", new_callable=AsyncMock) as get:
            res = self.client.get("/api/admin/ai-usage?days=90")
        self.assertEqual(res.status_code, 400)
        get.assert_not_called()

    def test_report_sends_safe_aggregate_from_existing_session(self):
        self.login()
        payload = build_dashboard_payload(ROWS, days=7, at=FIXED_NOW,
                                          first_recorded_at="2026-10-10T06:00:00+00:00")
        with patch("core.ai_usage.store.dashboard", new_callable=AsyncMock,
                   return_value=payload) as get:
            res = self.client.get("/api/admin/ai-usage?days=7")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json["totals"]["calls"], 5)
        self.assertEqual(res.headers.get("Cache-Control"), "no-store, private")
        get.assert_awaited_once_with(7)
        self.assertNotIn("prompt", res.json)

    def test_turso_failure_does_not_fake_zero_cost(self):
        self.login()
        with patch("core.ai_usage.store.dashboard", new_callable=AsyncMock,
                   side_effect=RuntimeError("DB offline")):
            res = self.client.get("/api/admin/ai-usage?days=30")
        self.assertEqual(res.status_code, 503)
        self.assertIn("error", res.json)
        self.assertNotIn("totals", res.json)


if __name__ == "__main__":
    unittest.main()
