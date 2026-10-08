"""T23.3–5: no automatic owner decisions, secure handoff and private status."""
import unittest
from unittest.mock import AsyncMock, patch

from features.feedback.store import FeedbackStore, FeedbackStorageError


class OwnerGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_link_validates_real_repo_not_host_prefix(self):
        store = FeedbackStore()
        for issue in (
            "https://github.com/HoenMike/DiscordMikeBotevil/issues/123",
            "https://github.com/HoenMike/DiscordMikeBot/issues/not-an-id",
            "https://github.com.attacker.test/HoenMike/DiscordMikeBot/issues/5",
            "https://github.com/HoenMike/DiscordMikeBot/pull/123",
            "https://github.com/HoenMike/DiscordMikeBot/issues/5?token=x",
        ):
            with self.subTest(issue=issue), self.assertRaises(FeedbackStorageError):
                await store.link_delivery(ticket_id="FB-1", issue_url=issue)

    async def test_reopen_requires_explanation(self):
        store = FeedbackStore()
        with self.assertRaises(FeedbackStorageError):
            await store.reopen_own(ticket_id="FB-1", reporter_id=123, explanation="bad")

    async def test_reopen_only_owned_reviewed_ticket(self):
        class DB:
            is_cloud = True
            def __init__(self, rowcount=1):
                self.rowcount = rowcount
                self.args = None
                self.sql = None
            async def connect(self): pass
            def execute(self, sql, args):
                self.sql, self.args = sql, args
                parent = self
                class Cursor:
                    rowcount = parent.rowcount
                    async def __aenter__(self): return self
                    async def __aexit__(self, *e): return None
                return Cursor()
        db = DB()
        with patch("features.feedback.store.db_client", db), patch.object(
            FeedbackStore, "resolve_id", new=AsyncMock(return_value="FB-1")
        ):
            await FeedbackStore().reopen_own(
                ticket_id="FB-1", reporter_id=123,
                explanation="The same bug still occurs after the shipped fix.",
            )
        self.assertIn("reporter_id=?",db.sql)
        self.assertIn("status IN ('rejected','duplicate','verified','closed')", db.sql)
        self.assertEqual(db.args[-1],"123")
        with patch("features.feedback.store.db_client", DB(rowcount=0)), patch.object(
            FeedbackStore, "resolve_id", new=AsyncMock(return_value="FB-1")
        ):
            with self.assertRaises(FeedbackStorageError):
                await FeedbackStore().reopen_own(
                    ticket_id="FB-1", reporter_id=987,
                    explanation="The bug still occurs after the recent release.",
                )

    def test_proposal_pipeline_requires_owner_admin_action(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        app = (root / "web/app.py").read_text(encoding="utf-8")
        self.assertIn("@feedback_connector_required\ndef connector_propose_feedback_review",app)
        self.assertIn("@login_required\ndef admin_feedback_proposal_decision",app)
        self.assertIn("X-CSRF-Token",app)
        self.assertIn("type(data.get('accept')) is not bool",app)
        self.assertIn("Review writes disabled pending owner-authenticated approval",app)
        self.assertIn("owner-dashboard",app)
        html = (root / "web/templates/feedback.html").read_text(encoding="utf-8")
        self.assertIn("Chấp nhận đề xuất",html)
        self.assertIn("Bỏ qua đề xuất",html)
        self.assertIn("Lưu liên kết triển khai",html)


if __name__=="__main__":
    unittest.main()
