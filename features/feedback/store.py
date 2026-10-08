"""Cloud-only durable feedback tickets with atomic evidence metadata.

The unified DB adapter automatically falls back to local SQLite when Turso is
unreachable. Feedback deliberately FAILS CLOSED on that fallback.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.db import db_client


class FeedbackStorageError(Exception):
    def __init__(self, message: str, *, may_have_committed: bool = False):
        super().__init__(message)
        self.may_have_committed = may_have_committed


@dataclass(frozen=True)
class FeedbackTicket:
    id: str
    status: str
    title: str
    category: str
    created_at: str
    reason: str = ""


SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS asumi_feedback (
      ticket_id TEXT PRIMARY KEY,
      source_message_id TEXT NOT NULL,
      guild_id TEXT NOT NULL,
      channel_id TEXT NOT NULL,
      reporter_id TEXT NOT NULL,
      reply_to_message_id TEXT,
      reported_bot_message_id TEXT,
      bot_version TEXT NOT NULL,
      category TEXT NOT NULL,
      title TEXT NOT NULL,
      description TEXT NOT NULL,
      user_explanation TEXT NOT NULL DEFAULT '',
      design_rule TEXT NOT NULL DEFAULT 'unknown',
      evidence_json TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL DEFAULT 'submitted',
      review_reason TEXT NOT NULL DEFAULT '',
      last_reviewer_id TEXT NOT NULL DEFAULT '',
      github_issue_url TEXT NOT NULL DEFAULT '',
      github_pr_url TEXT NOT NULL DEFAULT '',
      resolved_version TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(guild_id, source_message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asumi_feedback_events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_id TEXT NOT NULL,
      actor_id TEXT NOT NULL,
      action TEXT NOT NULL,
      old_status TEXT,
      new_status TEXT NOT NULL,
      reason TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS feedback_submitted_event
    AFTER INSERT ON asumi_feedback
    BEGIN
      INSERT INTO asumi_feedback_events
        (ticket_id, actor_id, action, old_status, new_status, reason, created_at)
      VALUES (NEW.ticket_id, NEW.reporter_id, 'submit', NULL, NEW.status, '',
              NEW.created_at);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS feedback_review_event
    AFTER UPDATE OF status ON asumi_feedback
    WHEN NEW.status <> OLD.status
    BEGIN
      INSERT INTO asumi_feedback_events
      (ticket_id, actor_id, action, old_status, new_status, reason, created_at)
      VALUES (NEW.ticket_id, NEW.last_reviewer_id, 'review', OLD.status, NEW.status,
              NEW.review_reason, NEW.updated_at);
      INSERT INTO asumi_feedback_notifications
      (notification_id, ticket_id, reporter_id, event_type, created_at)
      VALUES (NEW.ticket_id || ':' || NEW.status || ':' || NEW.updated_at,
              NEW.ticket_id, NEW.reporter_id, NEW.status, NEW.updated_at);
    END
    """,
    """
    CREATE TABLE IF NOT EXISTS asumi_feedback_review_proposals (
      proposal_id TEXT PRIMARY KEY,
      ticket_id TEXT NOT NULL,
      target_status TEXT NOT NULL,
      reason TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'chatgpt',
      state TEXT NOT NULL DEFAULT 'pending',
      reviewed_at TEXT,
      reviewer_id TEXT,
      created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS asumi_feedback_review_proposals_ticket_idx
    ON asumi_feedback_review_proposals (ticket_id, state, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS asumi_feedback_notifications (
      notification_id TEXT PRIMARY KEY,
      ticket_id TEXT NOT NULL,
      reporter_id TEXT NOT NULL,
      event_type TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'pending',
      attempts INTEGER NOT NULL DEFAULT 0,
      last_error TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      delivered_at TEXT,
      UNIQUE(ticket_id, event_type, created_at)
    )
    """,
)


class FeedbackStore:
    async def _require_cloud(self) -> None:
        await db_client.connect()
        if not db_client.is_cloud:
            raise FeedbackStorageError(
                "Turso Cloud chưa khả dụng. Không lưu feedback vào SQLite tạm của Render."
            )

    async def init(self) -> bool:
        try:
            await self._require_cloud()
            for statement in SCHEMA:
                await db_client.execute(statement)
                if not db_client.is_cloud:
                    raise FeedbackStorageError("Mất kết nối Turso trong lúc tạo schema.")
            return True
        except Exception as exc:
            print(f"[Feedback] Durable DB unavailable at startup: {type(exc).__name__}", flush=True)
            return False

    async def find_source(
        self, *, guild_id: int, source_message_id: int, reporter_id: int
    ) -> FeedbackTicket | None:
        await self._require_cloud()
        async with db_client.execute(
            "SELECT ticket_id, status, title, category, created_at, review_reason "
            "FROM asumi_feedback WHERE guild_id=? AND source_message_id=? AND reporter_id=?",
            (str(guild_id), str(source_message_id), str(reporter_id)),
        ) as cursor:
            row = await cursor.fetchone()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Mất kết nối Turso khi kiểm tra ticket.")
        return FeedbackTicket(*row) if row else None

    async def create(
        self, *, guild_id: int, channel_id: int, reporter_id: int,
        source_message_id: int, bot_version: str, category: str,
        title: str, description: str, explanation: str,
        design_rule: str, reply_to_message_id: int | None,
        reported_bot_message_id: int | None,
        evidence: list[dict[str, Any]],
    ) -> FeedbackTicket:
        await self._require_cloud()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        key = f"FB-{uuid.uuid4().hex[:10].upper()}"
        if category not in {"bug", "feature", "ux", "other"}:
            raise FeedbackStorageError("Loại feedback không hợp lệ.")
        if not title.strip() or not description.strip():
            raise FeedbackStorageError("Mô tả feedback không được rỗng.")
        args = (
            key, str(source_message_id), str(guild_id), str(channel_id),
            str(reporter_id), str(reply_to_message_id) if reply_to_message_id else None,
            str(reported_bot_message_id) if reported_bot_message_id else None,
            bot_version, category, title[:130], description[:3000],
            explanation[:1800], design_rule[:80],
            json.dumps(evidence, ensure_ascii=False), now, now,
        )
        sql = """
          INSERT INTO asumi_feedback (
            ticket_id, source_message_id, guild_id, channel_id, reporter_id,
            reply_to_message_id, reported_bot_message_id, bot_version, category,
            title, description, user_explanation, design_rule, evidence_json,
            created_at, updated_at
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(guild_id, source_message_id) DO NOTHING
        """
        inserted = False
        try:
            await db_client.execute(sql, args)
            inserted = True
            if not db_client.is_cloud:
                raise FeedbackStorageError("Mất Turso; không xác nhận ticket.", may_have_committed=True)
            async with db_client.execute(
                "SELECT ticket_id, status, title, category, created_at, review_reason "
                "FROM asumi_feedback WHERE guild_id=? AND source_message_id=? AND reporter_id=?",
                (str(guild_id), str(source_message_id), str(reporter_id)),
            ) as cursor:
                record = await cursor.fetchone()
            if not db_client.is_cloud or record is None:
                raise FeedbackStorageError("Không xác minh được ticket đã lưu trên Turso.", may_have_committed=True)
            return FeedbackTicket(*record)
        except FeedbackStorageError:
            raise
        except Exception as exc:
            raise FeedbackStorageError(
                "Turso không lưu được ticket. Hãy thử lại.",
                may_have_committed=inserted,
            ) from exc

    async def own_ticket(self, ticket_id: str, *, reporter_id: int) -> FeedbackTicket | None:
        await self._require_cloud()
        async with db_client.execute(
            "SELECT ticket_id, status, title, category, created_at, review_reason "
            "FROM asumi_feedback WHERE ticket_id=? AND reporter_id=?",
            (ticket_id.strip().upper(), str(reporter_id)),
        ) as cursor:
            record = await cursor.fetchone()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không đọc được từ Turso Cloud.")
        return FeedbackTicket(*record) if record else None


    async def admin_list(self, *, status: str = "", limit: int = 50) -> list[dict]:
        await self._require_cloud()
        limit = max(1, min(100, int(limit)))
        sql = (
            "SELECT ticket_id, status, title, category, created_at, review_reason, "
            "reporter_id, bot_version, guild_id, channel_id, description, "
            "user_explanation, evidence_json, github_issue_url, github_pr_url, resolved_version FROM asumi_feedback"
        )
        args = ()
        if status:
            sql += " WHERE status=?"
            args = (status[:30],)
        sql += f" ORDER BY created_at DESC LIMIT {limit}"
        async with db_client.execute(sql, args) as cursor:
            rows = await cursor.fetchall()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Turso unavailable")
        fields = ("id", "status", "title", "category", "created_at", "reason",
                  "reporter_id", "bot_version", "guild_id", "channel_id",
                  "description", "user_explanation", "evidence", "github_issue_url", "github_pr_url", "resolved_version")
        output = []
        for row in rows:
            entry = dict(zip(fields, row))
            try:
                entry["evidence"] = json.loads(entry["evidence"] or "[]")
            except ValueError:
                entry["evidence"] = []
            output.append(entry)
        return output

    async def admin_detail(self, ticket_id: str) -> dict | None:
        await self._require_cloud()
        cols = (
            "ticket_id, status, title, category, created_at, review_reason, "
            "reporter_id, bot_version, guild_id, channel_id, description, "
            "user_explanation, evidence_json, github_issue_url, github_pr_url, "
            "resolved_version"
        )
        async with db_client.execute(
            "SELECT " + cols + " FROM asumi_feedback WHERE ticket_id=?",
            (ticket_id.upper(),)
        ) as cursor:
            row = await cursor.fetchone()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Turso unavailable")
        if row is None:
            return None
        names = ("id", "status", "title", "category", "created_at", "reason",
                 "reporter_id", "bot_version", "guild_id", "channel_id",
                 "description", "user_explanation", "evidence",
                 "github_issue_url", "github_pr_url", "resolved_version")
        record = dict(zip(names, row))
        try:
            record["evidence"] = json.loads(record["evidence"] or "[]")
        except (ValueError, TypeError):
            record["evidence"] = []
        return record

    async def review(
        self, *, ticket_id: str, status: str, reason: str,
        actor_id: str, verified_version: str = ""
    ) -> None:
        """Owner review with atomic status, event and notification via SQL trigger."""
        allowed = {
            "triage", "needs_info", "approved", "rejected", "duplicate",
            "deferred", "planned", "in_progress", "in_review", "deployed",
            "verified", "closed", "reopened",
        }
        if status not in allowed:
            raise FeedbackStorageError("Trạng thái không hợp lệ")
        reason = reason.strip()
        if status in {"rejected", "duplicate", "deferred", "needs_info", "verified"} and not reason:
            raise FeedbackStorageError("Cần ghi lý do quyết định")
        if status == "verified" and not verified_version.strip():
            raise FeedbackStorageError("Cần phiên bản đã triển khai và nghiệm thu")
        await self._require_cloud()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        # Single atomic guarded UPDATE, trigger writes event/outbox on success.
        async with db_client.execute(
            "UPDATE asumi_feedback SET status=?, review_reason=?, updated_at=?, last_reviewer_id=? "
            "WHERE ticket_id=? AND status<>?",
            (status, (reason + (f" [release: {verified_version[:50]}]" if verified_version else ""))[:1800],
             now, actor_id[:80], ticket_id.upper(), status),
        ) as cursor:
            changed = cursor.rowcount
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không xác minh được ghi nhận trên Turso")
        if changed != 1:
            raise FeedbackStorageError("Không thấy ticket hoặc trạng thái đã được cập nhật")

    async def link_delivery(
        self, *, ticket_id: str, issue_url: str = "", pr_url: str = "",
        version: str = "",
    ) -> None:
        """Owner-approved refs only, never trusted from reporter ticket text."""
        for value, required in ((issue_url, "/issues/"), (pr_url, "/pull/")):
            if value and (not value.startswith("https://github.com/HoenMike/DiscordMikeBot")
                          or required not in value or len(value)>200):
                raise FeedbackStorageError("GitHub link không hợp lệ.")
        current = await self.admin_detail(ticket_id)
        if current is None:
            raise FeedbackStorageError("Không tìm thấy ticket")
        if issue_url and current["status"] not in {
            "approved", "planned", "in_progress", "in_review", "deployed", "verified", "closed"
        }:
            raise FeedbackStorageError("Chỉ tạo GitHub Issue sau khi duyệt feedback")
        await self._require_cloud()
        await db_client.execute(
            "UPDATE asumi_feedback SET github_issue_url=?, github_pr_url=?, "
            "resolved_version=?, updated_at=? WHERE ticket_id=?",
            (issue_url, pr_url, version[:50],
             datetime.now(timezone.utc).isoformat(timespec="seconds"), ticket_id.upper()),
        )
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không thể cập nhật Turso")

    async def review_metrics(self) -> dict:
        await self._require_cloud()
        async with db_client.execute(
            "SELECT status, COUNT(*) FROM asumi_feedback GROUP BY status"
        ) as cursor:
            counts = await cursor.fetchall()
        async with db_client.execute(
            "SELECT state, COUNT(*) FROM asumi_feedback_notifications GROUP BY state"
        ) as cursor:
            delivery = await cursor.fetchall()
        async with db_client.execute(
            "SELECT COUNT(*) FROM asumi_feedback_notifications "
            "WHERE state='pending' AND attempts>=5"
        ) as cursor:
            failed = await cursor.fetchone()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Turso unavailable")
        return {
            "tickets_by_status": {str(s): int(n) for s,n in counts},
            "notification_by_state": {str(s): int(n) for s,n in delivery},
            "notification_needs_attention": int(failed[0] if failed else 0),
        }

    async def propose_review(
        self, *, ticket_id: str, target_status: str, reason: str, source: str = "chatgpt"
    ) -> str:
        """Untrusted AI proposes; NEVER changes the feedback ticket status."""
        if target_status not in {"approved", "rejected", "deferred", "needs_info", "duplicate"}:
            raise FeedbackStorageError("Trạng thái đề xuất không hợp lệ.")
        reason = reason.strip()
        if not (10 <= len(reason) <= 1800):
            raise FeedbackStorageError("Đề xuất phải có lý do rõ ràng (10–1800 ký tự).")
        current = await self.admin_detail(ticket_id)
        if current is None:
            raise FeedbackStorageError("Ticket không tồn tại.")
        if current["status"] not in {"submitted", "triage", "needs_info", "deferred", "reopened"}:
            raise FeedbackStorageError("Ticket đã được xử lý; hãy kiểm tra lại trước khi đề xuất.")
        await self._require_cloud()
        proposal_id = "FP-" + uuid.uuid4().hex[:12].upper()
        await db_client.execute(
            "INSERT INTO asumi_feedback_review_proposals "
            "(proposal_id,ticket_id,target_status,reason,source,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (proposal_id, ticket_id.upper(), target_status, reason, source[:40],
             datetime.now(timezone.utc).isoformat(timespec="microseconds")),
        )
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không xác minh được đề xuất trên Turso.")
        return proposal_id

    async def list_proposals(self, *, ticket_id: str, limit: int = 20) -> list[dict]:
        await self._require_cloud()
        async with db_client.execute(
            "SELECT proposal_id,ticket_id,target_status,reason,source,state,created_at,"
            "reviewed_at,reviewer_id FROM asumi_feedback_review_proposals "
            "WHERE ticket_id=? ORDER BY created_at DESC LIMIT ?",
            (ticket_id.upper(), max(1,min(50,limit))),
        ) as cursor:
            rows = await cursor.fetchall()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không đọc được đề xuất trên Turso.")
        names = ("id","ticket_id","target_status","reason","source","state",
                 "created_at","reviewed_at","reviewer_id")
        return [dict(zip(names, row)) for row in rows]

    async def decide_proposal(self, *, proposal_id: str, accept: bool, actor_id: str) -> str:
        """Only callable after authenticated owner action via admin CSRF session."""
        await self._require_cloud()
        async with db_client.execute(
            "SELECT ticket_id,target_status,reason,state "
            "FROM asumi_feedback_review_proposals WHERE proposal_id=?",
            (proposal_id.upper(),),
        ) as cursor:
            row = await cursor.fetchone()
        if not db_client.is_cloud or not row:
            raise FeedbackStorageError("Đề xuất không tồn tại.")
        ticket_id, target_status, reason, state = row
        if state != "pending":
            raise FeedbackStorageError("Đề xuất đã được xử lý.")
        # A dismissal only resolves the proposal, never rejects the reporter.
        if accept:
            await self.review(
                ticket_id=ticket_id, status=target_status, reason=reason,
                actor_id=actor_id,
            )
        await self._require_cloud()
        async with db_client.execute(
            "UPDATE asumi_feedback_review_proposals "
            "SET state=?,reviewed_at=?,reviewer_id=? "
            "WHERE proposal_id=? AND state='pending'",
            ("accepted" if accept else "dismissed",
             datetime.now(timezone.utc).isoformat(timespec="microseconds"),
             actor_id[:80], proposal_id.upper()),
        ) as cursor:
            changed = cursor.rowcount
        if not db_client.is_cloud or changed != 1:
            raise FeedbackStorageError("Không thể xác nhận trạng thái đề xuất.")
        return ticket_id

    async def pending_notifications(self, limit: int = 20) -> list[tuple]:
        await self._require_cloud()
        async with db_client.execute(
            "SELECT n.notification_id, n.ticket_id, n.reporter_id, n.event_type, "
            "f.review_reason, f.status FROM asumi_feedback_notifications n "
            "JOIN asumi_feedback f ON f.ticket_id=n.ticket_id "
            "WHERE n.state='pending' AND n.attempts<5 "
            "ORDER BY n.created_at ASC LIMIT ?",
            (min(50,max(1,int(limit))),),
        ) as cursor:
            rows = await cursor.fetchall()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không thể đọc notification outbox")
        return rows

    async def mark_notification(self, notification_id: str, *, delivered: bool, error: str = "") -> None:
        await self._require_cloud()
        await db_client.execute(
            "UPDATE asumi_feedback_notifications "
            "SET state=CASE WHEN ? THEN 'delivered' ELSE 'pending' END, "
            "attempts=attempts+1, last_error=?, "
            "delivered_at=CASE WHEN ? THEN ? ELSE NULL END "
            "WHERE notification_id=? AND state='pending'",
            (1 if delivered else 0, error[:100], 1 if delivered else 0,
             datetime.now(timezone.utc).isoformat(timespec="seconds"),
             notification_id),
        )
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không thể cập nhật outbox")




feedback_store = FeedbackStore()
