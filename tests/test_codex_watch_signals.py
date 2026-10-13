"""Regression tests for the Codex Reset Watch's false-positive boundaries."""
import unittest
from datetime import datetime, timedelta, timezone

from features.codex_watch.signals import (
    classify_post, estimate_window, extract_signals,
    forecast_warning, format_alert, parse_time, fresh_feed,
)

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def tweet(post_id: str, text: str, at: str = "2026-10-13T01:03:59Z",
          kind: str = "candidate") -> dict:
    return {
        "id": post_id, "url": f"https://x.com/thsottiaux/status/{post_id}",
        "text": text, "at": at, "kind": kind,
        "explicit_reset_claim": False,
    }


class ResetSignalsTest(unittest.TestCase):
    def test_real_commitment_even_when_tracker_does_not_mark_claim(self):
        post = tweet("2109812360596865224", "Global reset landing by EOD PST time. Enjoy")
        result = classify_post(post, NOW)
        self.assertEqual("announced", result.stage)
        self.assertIn("13/10", result.window_vn)
        self.assertIn("13:59", result.window_vn)  # Oct 12 PDT end of day
        self.assertIn("PST viết mơ hồ", result.window_vn)

    def test_day8_not_completed(self):
        self.assertIsNone(classify_post(tweet("2109812216212099456", "Day 8/ Reset"), NOW))

    def test_old_completed_not_reannounced(self):
        post = tweet("2109132167112782291", "Put the reset in the bag. All propagated.",
                     "2026-10-11T04:01:09Z")
        self.assertEqual("completed", classify_post(post, NOW).stage)
        self.assertIn("ĐÃ HOÀN TẤT", format_alert(classify_post(post, NOW)))
        self.assertIsNone(classify_post(post, NOW + timedelta(days=5)))

    def test_banked_is_not_global_completed(self):
        post = tweet("2107913674593644711",
                     "Loading a banked reset in everyone's paid accounts.",
                     "2026-10-07T19:19:17Z", kind="banked")
        result = classify_post(post, datetime(2026,10,8,2,tzinfo=timezone.utc))
        self.assertEqual("banked", result.stage)
        self.assertIn("KHÔNG TỰ ĐỘNG", format_alert(result))

    def test_ambiguous_landed_does_not_claim_global(self):
        post = tweet("2108040921044639779", "Confirmed landed across all accounts.",
                     "2026-10-08T03:44:55Z")
        self.assertIsNone(classify_post(post, datetime(2026,10,8,6,tzinfo=timezone.utc)))

    def test_jokes_polls_and_fake_identity_rejected(self):
        texts = ["I do like giving resets", "Day 6/ Reset",
                 "The community demands a reset!", "Reset voting results",
                 "Global reset might be cool someday"]
        for i, text in enumerate(texts):
            with self.subTest(text=text):
                self.assertIsNone(classify_post(tweet(str(2109812360596865200+i), text), NOW))
        bad = tweet("2109812360596865224", "Global reset landing by EOD")
        bad["url"] = "https://evil.example/status/2109812360596865224"
        self.assertIsNone(classify_post(bad, NOW))

    def test_propagated_other_features_not_assumed_global_reset(self):
        post = tweet("2109812360596865224",
                     "New UI rollout all propagated. Enjoy.")
        self.assertIsNone(classify_post(post, NOW))

    def test_cancellation_takes_precedence_over_landing_word(self):
        post = tweet("2109812360596865224",
                     "Global reset landing delayed until tomorrow.")
        self.assertEqual("changed", classify_post(post, NOW).stage)

    def test_stale_feed_and_mismatched_source_rejected(self):
        good = {"fetched_at": "2026-10-13T05:55:00Z", "stale": False}
        self.assertTrue(fresh_feed(good, NOW))
        bad = {**good, "fetched_at": "2026-10-12T01:00:00Z"}
        self.assertFalse(fresh_feed(bad, NOW))
        data = {**bad, "tweets":[tweet("2109812360596865224", "Global reset landing by EOD")]}
        self.assertEqual([], extract_signals(data, NOW))

    def test_forecast_does_not_confuse_commitment_83_with_probability(self):
        self.assertFalse(forecast_warning(
            {"probabilities":{"model_24h":19,"model_48h":34,"commitment":0.83}}, (87,94)
        ))
        self.assertTrue(forecast_warning(
            {"probabilities":{"model_24h":78,"model_48h":80}}, (87,94)
        ))
        self.assertFalse(forecast_warning(
            {"probabilities":{"model_24h":99,"model_48h":96}}, None
        ))

    def test_no_link_onebox_and_no_user_supplied_mentions(self):
        signal = classify_post(tweet("2109812360596865224",
              "Global reset landing by EOD PST time. Enjoy"), NOW)
        msg = format_alert(signal)
        self.assertIn("<https://x.com/thsottiaux/status/2109812360596865224>", msg)
        self.assertNotIn("@everyone", msg)
        self.assertLess(len(msg), 500)


if __name__ == "__main__":
    unittest.main()
