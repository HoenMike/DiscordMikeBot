"""Single-ticket owner authorization; never approve feedback generally."""
import unittest
from unittest.mock import AsyncMock, patch

from features.feedback.one_time_approval_fb01401 import (
    APPROVED_TICKET, apply_approved_decision_once,
)


class ExplicitOwnerApprovalTests(unittest.IsolatedAsyncioTestCase):
    def valid(self, status="submitted"):
        return {
            "id": APPROVED_TICKET, "category": "bug", "status": status,
            "description": "báo lỗi: tóm tắt 12h qua của @i'm_bd lại lấy tin nhắn cả channel",
        }

    async def test_approves_exact_ticket_only_once(self):
        with patch("features.feedback.one_time_approval_fb01401.feedback_store") as db:
            db.admin_detail = AsyncMock(side_effect=[self.valid(), self.valid("approved")])
            db.review = AsyncMock()
            self.assertEqual(await apply_approved_decision_once(), "approved")
            kwargs = db.review.await_args.kwargs
            self.assertEqual(kwargs["ticket_id"], APPROVED_TICKET)
            self.assertEqual(kwargs["status"], "approved")
            self.assertIn("owner-explicit", kwargs["actor_id"])

    async def test_already_approved_is_idempotent(self):
        with patch("features.feedback.one_time_approval_fb01401.feedback_store") as db:
            db.admin_detail = AsyncMock(return_value=self.valid("approved"))
            db.review = AsyncMock()
            self.assertEqual(await apply_approved_decision_once(), "already_approved")
            db.review.assert_not_awaited()

    async def test_unrelated_ticket_content_cannot_be_approved(self):
        with patch("features.feedback.one_time_approval_fb01401.feedback_store") as db:
            wrong = self.valid()
            wrong["description"] = "báo lỗi: chức năng tarot daily hiển thị sai"
            db.admin_detail = AsyncMock(return_value=wrong)
            db.review = AsyncMock()
            self.assertEqual(await apply_approved_decision_once(), "skipped_content_mismatch")
            db.review.assert_not_awaited()

    async def test_non_submitted_ticket_is_not_overwritten(self):
        with patch("features.feedback.one_time_approval_fb01401.feedback_store") as db:
            db.admin_detail = AsyncMock(return_value=self.valid("rejected"))
            db.review = AsyncMock()
            self.assertEqual(await apply_approved_decision_once(), "skipped_other_status")
            db.review.assert_not_awaited()

    async def test_missing_ticket_is_not_created(self):
        with patch("features.feedback.one_time_approval_fb01401.feedback_store") as db:
            db.admin_detail = AsyncMock(return_value=None)
            db.review = AsyncMock()
            self.assertEqual(await apply_approved_decision_once(), "not_found")
            db.review.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
