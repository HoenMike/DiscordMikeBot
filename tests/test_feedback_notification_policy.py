"""Regression coverage for T23 terminal-only DM policy."""
import unittest
from features.feedback.notifications import NOTIFIABLE_ACTIONS, format_feedback_notification


class NotificationPolicyTests(unittest.TestCase):
    def test_only_final_outcomes_notify(self):
        for status in ("verified", "rejected", "duplicate"):
            self.assertIn(status, NOTIFIABLE_ACTIONS)
        for status in ("submitted", "triage", "needs_info", "approved",
                       "deferred", "planned", "in_progress", "in_review",
                       "deployed", "closed", "reopened", "deleted"):
            with self.subTest(status=status):
                self.assertNotIn(status, NOTIFIABLE_ACTIONS)

    def test_notification_keeps_public_number(self):
        message = format_feedback_notification(
            number=15, status="verified", reason="Fixed in version 3.8.4"
        )
        self.assertIn("#15", message)
        self.assertIn("3.8.4", message)
