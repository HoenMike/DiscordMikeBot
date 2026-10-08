"""One-off owner-authorized ticket decision, scoped to FB-01401CE0D1 only.

The owner explicitly approved this exact screenshot-confirmed bug on
2026-10-08. This is NOT a feedback auto-approval feature.

Remove the call/file after production confirms the decision. The DB status
guard keeps restarts idempotent and never auto-approves unrelated tickets.
"""
from __future__ import annotations

from features.feedback.policy import normalize
from features.feedback.store import feedback_store, FeedbackStorageError

APPROVED_TICKET = "FB-01401CE0D1"
APPROVED_REASON = (
    "Owner explicitly approved this feedback on 2026-10-08. "
    "Bug: member-scoped 12h summary fell back to whole-channel summary "
    "when duration appeared between 'tin nhắn' and 'của @user'. "
    "Fix the router and add exact-phrase regression; pending live verification."
)


async def apply_approved_decision_once() -> str:
    """Only if the persisted DB ticket matches the owner's approved bug."""
    ticket = await feedback_store.admin_detail(APPROVED_TICKET)
    if ticket is None:
        return "not_found"
    if ticket["status"] == "approved":
        return "already_approved"
    if ticket["status"] not in {"submitted", "triage"}:
        return "skipped_other_status"
    description = normalize(ticket.get("description", ""))
    if (
        ticket.get("category") != "bug"
        or "tom tat" not in description
        or "12h" not in description
        or "channel" not in description
    ):
        return "skipped_content_mismatch"
    await feedback_store.review(
        ticket_id=APPROVED_TICKET,
        status="approved",
        reason=APPROVED_REASON,
        actor_id="owner-explicit-approval-2026-10-08",
    )
    result = await feedback_store.admin_detail(APPROVED_TICKET)
    if result is None or result["status"] != "approved":
        raise FeedbackStorageError("Owner-approved decision could not be confirmed on Turso")
    return "approved"
