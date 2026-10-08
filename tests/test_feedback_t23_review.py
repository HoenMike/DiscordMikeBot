"""T23.2 moderation: owner-only dashboard and durable review event semantics."""
import unittest
from unittest.mock import AsyncMock, patch
from features.feedback.store import FeedbackStore, FeedbackStorageError


class ReviewPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_status_is_rejected_without_db(self):
        with self.assertRaisesRegex(FeedbackStorageError,"Trạng thái"):
            await FeedbackStore().review(ticket_id="FB-1",status="malicious",reason="x",actor_id="admin")

    async def test_reject_requires_reason(self):
        with self.assertRaisesRegex(FeedbackStorageError,"lý do"):
            await FeedbackStore().review(ticket_id="FB-1",status="rejected",reason="",actor_id="admin")

    async def test_verified_requires_release_and_reason(self):
        with self.assertRaisesRegex(FeedbackStorageError,"lý do"):
            await FeedbackStore().review(ticket_id="FB-1",status="verified",reason="",actor_id="admin")
        with self.assertRaisesRegex(FeedbackStorageError,"phiên bản"):
            await FeedbackStore().review(ticket_id="FB-1",status="verified",reason="tested",actor_id="admin")

    async def test_transition_updates_only_one_ticket(self):
        class Cursor:
            rowcount=1
            async def __aenter__(self): return self
            async def __aexit__(self,*_): return None
        class DB:
            is_cloud=True
            def __init__(self): self.calls=[]
            async def connect(self): pass
            def execute(self,sql,args):
                self.calls.append((sql,args));return Cursor()
        db=DB()
        with patch("features.feedback.store.db_client",db):
            await FeedbackStore().review(
                ticket_id="FB-ABCD",status="rejected",reason="Wrong usage; documented behavior",
                actor_id="dashboard-admin",
            )
        self.assertEqual(len(db.calls),1)
        self.assertIn("WHERE ticket_id=?",db.calls[0][0])
        self.assertEqual(db.calls[0][1][3],"FB-ABCD")


class DashboardPrivacyTests(unittest.TestCase):
    def test_routes_have_admin_guard_and_csrf(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "web/app.py").read_text(encoding="utf-8")
        self.assertIn("def feedback_dashboard()", source)
        self.assertIn("def feedback_evidence(", source)
        self.assertIn("X-CSRF-Token", source)
        self.assertEqual(source.count("def feedback_review("), 1)

if __name__ == "__main__":
    unittest.main()
