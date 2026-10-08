"""T23.3: ChatGPT may propose; owner is the only authority to apply."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from features.feedback.store import FeedbackStore, FeedbackStorageError, SCHEMA


class _Query:
    def __init__(self, result=None, changed=1):
        self.rows = result or []
        self.rowcount = changed

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class _CloudDB:
    is_cloud = True

    def __init__(self, rows=None):
        self.rows = rows or []
        self.statements = []

    async def connect(self):
        pass

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        query = _Query(self.rows)
        # Asumi's adapter supports both await and async with.
        class _Awaitable:
            def __await__(self):
                async def run():
                    return query
                return run().__await__()

            async def __aenter__(self):
                return query

            async def __aexit__(self, *args):
                pass
        return _Awaitable()


class ProposalTests(unittest.IsolatedAsyncioTestCase):
    async def test_proposal_never_calls_review_or_changes_ticket_status(self):
        db = _CloudDB()
        store = FeedbackStore()
        ticket = {"status": "submitted", "category": "bug"}
        with patch("features.feedback.store.db_client", db), patch.object(
            store, "admin_detail", new=AsyncMock(return_value=ticket)
        ), patch.object(store, "review", new=AsyncMock()) as review:
            proposal = await store.propose_review(
                ticket_id="FB-AAA", target_status="approved",
                reason="This is a confirmed reproducible user-facing bug.",
            )
        self.assertTrue(proposal.startswith("FP-"))
        self.assertEqual(len(db.statements), 1)
        self.assertIn("INSERT INTO asumi_feedback_review_proposals", db.statements[0][0])
        review.assert_not_awaited()

    async def test_invalid_proposal_cannot_approve_anything(self):
        store = FeedbackStore()
        for target in ["verified", "closed", "in_progress", "delete", ""]:
            with self.subTest(target=target), self.assertRaises(FeedbackStorageError):
                await store.propose_review(
                    ticket_id="FB-AAA", target_status=target,
                    reason="Ten characters long",
                )

    async def test_unresolved_ticket_must_be_checked_before_proposing(self):
        store = FeedbackStore()
        with patch.object(store, "admin_detail", new=AsyncMock(return_value={
            "status": "verified", "category": "bug",
        })), self.assertRaises(FeedbackStorageError):
            await store.propose_review(
                ticket_id="FB-AAA", target_status="approved",
                reason="This is a confirmed bug and requires fixing",
            )

    async def test_dismiss_does_not_review_reporter_ticket(self):
        db = _CloudDB(rows=[("FB-AAA", "approved", "Looks valid to fix", "pending")])
        store = FeedbackStore()
        with patch("features.feedback.store.db_client", db), patch.object(
            store, "review", new=AsyncMock(),
        ) as review:
            result = await store.decide_proposal(
                proposal_id="FP-AAA", accept=False, actor_id="owner-dashboard",
            )
        self.assertEqual(result, "FB-AAA")
        review.assert_not_awaited()
        self.assertIn("UPDATE asumi_feedback_review_proposals", db.statements[-1][0])
        self.assertEqual(db.statements[-1][1][0], "dismissed")

    async def test_accept_updates_ticket_only_after_owner_confirmation(self):
        db = _CloudDB(rows=[("FB-AAA", "approved", "Looks valid to fix", "pending")])
        store = FeedbackStore()
        with patch("features.feedback.store.db_client", db), patch.object(
            store, "review", new=AsyncMock(),
        ) as review:
            await store.decide_proposal(
                proposal_id="FP-AAA", accept=True, actor_id="owner-dashboard",
            )
        review.assert_awaited_once()
        self.assertEqual(review.await_args.kwargs["ticket_id"], "FB-AAA")
        self.assertEqual(review.await_args.kwargs["status"], "approved")
        self.assertEqual(review.await_args.kwargs["actor_id"], "owner-dashboard")

    async def test_already_processed_proposal_is_rejected(self):
        db = _CloudDB(rows=[("FB-AAA", "approved", "Valid", "accepted")])
        with patch("features.feedback.store.db_client", db), self.assertRaises(
            FeedbackStorageError
        ):
            await FeedbackStore().decide_proposal(
                proposal_id="FP-AAA", accept=True, actor_id="owner-dashboard",
            )

    def test_schema_separate_proposals(self):
        schema = "\n".join(SCHEMA)
        self.assertIn("asumi_feedback_review_proposals", schema)
        self.assertIn("state TEXT NOT NULL DEFAULT 'pending'", schema)
        self.assertNotIn("AFTER INSERT ON asumi_feedback_review_proposals", schema)

    def test_admin_requires_session_csrf_but_connector_cannot_decide(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "web/app.py").read_text(encoding="utf-8")
        self.assertIn("def connector_propose_feedback_review(", src)
        self.assertIn("def admin_feedback_proposal_decision(", src)
        self.assertIn("X-CSRF-Token", src)
        self.assertIn("@feedback_connector_required", src)
        self.assertIn("@login_required", src)


if __name__ == "__main__":
    unittest.main()
