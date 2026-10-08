"""Cloud-only durable feedback tickets with atomic evidence metadata.

The unified DB adapter automatically falls back to local SQLite when Turso is
unreachable. Feedback deliberately FAILS CLOSED on that fallback.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit
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
    number: int | None = None

    @property
    def label(self) -> str:
        return f"#{self.number}" if self.number else self.id


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
      replaces_ticket_id TEXT,
      replaced_by_ticket_id TEXT,
      deleted_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(guild_id, source_message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asumi_feedback_numbers (
      number INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_id TEXT NOT NULL UNIQUE REFERENCES asumi_feedback(ticket_id)
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS feedback_allocate_number
    AFTER INSERT ON asumi_feedback
    BEGIN
      INSERT OR IGNORE INTO asumi_feedback_numbers(ticket_id) VALUES (NEW.ticket_id);
    END
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

# Installed AFTER adding missing columns to existing 3.8.3 databases.
LIFECYCLE_TRIGGERS = (
    """
    CREATE TRIGGER IF NOT EXISTS feedback_revision_guard
    BEFORE INSERT ON asumi_feedback
    WHEN NEW.replaces_ticket_id IS NOT NULL
    BEGIN
      SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM asumi_feedback original
        WHERE original.ticket_id=NEW.replaces_ticket_id
          AND original.reporter_id=NEW.reporter_id
          AND original.guild_id=NEW.guild_id
          AND original.status<>'deleted'
          AND original.replaced_by_ticket_id IS NULL
      ) THEN RAISE(ABORT,'Feedback revision not permitted') END;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS feedback_deleted_dismiss_proposals
    AFTER UPDATE OF status ON asumi_feedback
    WHEN NEW.status='deleted' AND OLD.status<>'deleted'
    BEGIN
      UPDATE asumi_feedback_review_proposals
      SET state='dismissed', reviewed_at=NEW.updated_at,
          reviewer_id=NEW.reporter_id
      WHERE ticket_id=NEW.ticket_id AND state='pending';
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS feedback_revision_retire
    AFTER INSERT ON asumi_feedback
    WHEN NEW.replaces_ticket_id IS NOT NULL
    BEGIN
      UPDATE asumi_feedback
      SET status='deleted', replaced_by_ticket_id=NEW.ticket_id,
          deleted_at=NEW.created_at, updated_at=NEW.created_at,
          last_reviewer_id=NEW.reporter_id,
          review_reason='Người gửi đã thay thế bằng một ticket mới'
      WHERE ticket_id=NEW.replaces_ticket_id;
    END
    """,
)

LIFECYCLE_COLUMNS = {
    "replaces_ticket_id": "TEXT",
    "replaced_by_ticket_id": "TEXT",
    "deleted_at": "TEXT",
}


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
            async with db_client.execute("PRAGMA table_info(asumi_feedback)") as cursor:
                columns = {str(row[1]) for row in await cursor.fetchall()}
            for name, kind in LIFECYCLE_COLUMNS.items():
                if name not in columns:
                    await db_client.execute(f"ALTER TABLE asumi_feedback ADD COLUMN {name} {kind}")
            for statement in LIFECYCLE_TRIGGERS:
                await db_client.execute(statement)
            if not db_client.is_cloud:
                raise FeedbackStorageError("Mất Turso trong lúc cập nhật vòng đời ticket.")
            # Existing UUID tickets get stable numbers in chronological order.
            # New inserts are numbered atomically by the database trigger.
            await db_client.execute(
                "INSERT OR IGNORE INTO asumi_feedback_numbers(ticket_id) "
                "SELECT f.ticket_id FROM asumi_feedback f "
                "LEFT JOIN asumi_feedback_numbers n ON n.ticket_id=f.ticket_id "
                "WHERE n.ticket_id IS NULL ORDER BY f.created_at, f.ticket_id"
            )
            if not db_client.is_cloud:
                raise FeedbackStorageError("Turso không sẵn sàng để đánh số ticket.")
            return True
        except Exception as exc:
            print(f"[Feedback] Durable DB unavailable at startup: {type(exc).__name__}", flush=True)
            return False

    async def resolve_id(self, reference: str) -> str | None:
        """Resolve #15, 15, or the original FB-UUID. IDs never change."""
        value = str(reference or "").strip().upper()
        number = value[1:] if value.startswith("#") else value
        await self._require_cloud()
        if number.isdecimal() and 0 < len(number) <= 12 and int(number) > 0:
            async with db_client.execute(
                "SELECT ticket_id FROM asumi_feedback_numbers WHERE number=?",
                (int(number),),
            ) as cursor:
                row = await cursor.fetchone()
            if not db_client.is_cloud:
                raise FeedbackStorageError("Không thể tra số ticket trong Turso.")
            return str(row[0]) if row else None
        return value if value.startswith("FB-") and len(value) <= 30 else None

    async def find_source(
        self, *, guild_id: int, source_message_id: int, reporter_id: int
    ) -> FeedbackTicket | None:
        await self._require_cloud()
        async with db_client.execute(
            "SELECT f.ticket_id, f.status, f.title, f.category, f.created_at, f.review_reason, n.number "
            "FROM asumi_feedback f JOIN asumi_feedback_numbers n ON n.ticket_id=f.ticket_id "
            "WHERE f.guild_id=? AND f.source_message_id=? AND f.reporter_id=?",
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
                "SELECT f.ticket_id, f.status, f.title, f.category, f.created_at, f.review_reason, n.number "
                "FROM asumi_feedback f JOIN asumi_feedback_numbers n ON n.ticket_id=f.ticket_id "
                "WHERE f.guild_id=? AND f.source_message_id=? AND f.reporter_id=?",
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
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            return None
        async with db_client.execute(
            "SELECT f.ticket_id, f.status, f.title, f.category, f.created_at, f.review_reason, n.number "
            "FROM asumi_feedback f JOIN asumi_feedback_numbers n ON n.ticket_id=f.ticket_id "
            "WHERE f.ticket_id=? AND f.reporter_id=?",
            (resolved, str(reporter_id)),
        ) as cursor:
            record = await cursor.fetchone()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không đọc được từ Turso Cloud.")
        return FeedbackTicket(*record) if record else None


    async def reopen_own(
        self, *, ticket_id: str, reporter_id: int, explanation: str,
    ) -> None:
        """Reporter may reopen their OWN reviewed issue with new evidence."""
        reason = explanation.strip()
        if not 10 <= len(reason) <= 1000:
            raise FeedbackStorageError("Hãy giải thích ngắn gọn vì sao lỗi vẫn còn (10–1000 ký tự).")
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            raise FeedbackStorageError("Không tìm thấy ticket.")
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        async with db_client.execute(
            "UPDATE asumi_feedback "
            "SET status='reopened',review_reason=?,updated_at=?,last_reviewer_id=? "
            "WHERE ticket_id=? AND reporter_id=? "
            "AND status IN ('rejected','duplicate','verified','closed')",
            (reason, now, str(reporter_id), resolved, str(reporter_id)),
        ) as cursor:
            count = cursor.rowcount
        if not db_client.is_cloud or count != 1:
            raise FeedbackStorageError(
                "Chỉ có thể mở lại ticket đã được xử lý của chính bạn."
            )

    async def add_info_own(self, *, ticket_id: str, reporter_id: int, explanation: str) -> None:
        """Reporter can answer an admin clarification request, without editing decisions."""
        explanation = explanation.strip()
        if not 10 <= len(explanation) <= 1000:
            raise FeedbackStorageError("Cần giải thích thêm từ 10 đến 1000 ký tự.")
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            raise FeedbackStorageError("Không tìm thấy ticket.")
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        async with db_client.execute(
            "UPDATE asumi_feedback SET "
            "user_explanation=SUBSTR(user_explanation || CASE WHEN user_explanation='' "
            "THEN '' ELSE CHAR(10) END || ?, 1, 1800), "
            "status='submitted', updated_at=?, last_reviewer_id=? "
            "WHERE ticket_id=? AND reporter_id=? AND status='needs_info'",
            (explanation, now, str(reporter_id), resolved, str(reporter_id)),
        ) as cursor:
            changed = cursor.rowcount
        if not db_client.is_cloud or changed != 1:
            raise FeedbackStorageError("Ticket không yêu cầu bổ sung hoặc không thuộc về bạn.")

    async def own_list(
        self, *, reporter_id: int, guild_id: int, limit: int = 10,
        offset: int = 0, include_deleted: bool = False,
    ) -> list[dict]:
        """Private reporter-only paginated list. Never expose another guild/user."""
        await self._require_cloud()
        limit = min(20, max(1, int(limit)))
        offset = min(10000, max(0, int(offset)))
        sql = (
            "SELECT f.ticket_id, n.number, f.title, f.category, f.status, "
            "f.description, f.user_explanation, f.review_reason, f.bot_version, "
            "f.created_at, f.replaces_ticket_id, f.replaced_by_ticket_id, "
            "(SELECT newer.number FROM asumi_feedback_numbers newer "
            "WHERE newer.ticket_id=f.replaced_by_ticket_id) "
            "FROM asumi_feedback f "
            "JOIN asumi_feedback_numbers n ON n.ticket_id=f.ticket_id "
            "WHERE f.reporter_id=? AND f.guild_id=? "
        )
        if not include_deleted:
            sql += "AND f.status<>'deleted' "
        sql += "ORDER BY n.number DESC LIMIT ? OFFSET ?"
        async with db_client.execute(
            sql, (str(reporter_id), str(guild_id), limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không đọc được lịch sử feedback.")
        names = ("id", "number", "title", "category", "status", "description",
                 "explanation", "reason", "bot_version", "created_at",
                 "replaces_ticket_id", "replaced_by_ticket_id", "replacement_number")
        return [dict(zip(names, row)) for row in rows]

    async def soft_delete_own(self, *, ticket_id: str, reporter_id: int, guild_id: int) -> int:
        """Soft-delete; keep immutable report, evidence and history for audit."""
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            raise FeedbackStorageError("Ticket không tồn tại.")
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        async with db_client.execute(
            "UPDATE asumi_feedback SET status='deleted', deleted_at=?, updated_at=?, "
            "review_reason='Người gửi đã xóa ticket', last_reviewer_id=? "
            "WHERE ticket_id=? AND reporter_id=? AND guild_id=? AND status<>'deleted'",
            (now, now, str(reporter_id), resolved, str(reporter_id), str(guild_id)),
        ) as cursor:
            changed = cursor.rowcount
        if not db_client.is_cloud or changed != 1:
            raise FeedbackStorageError("Ticket không thuộc bạn hoặc đã được xóa.")
        async with db_client.execute(
            "SELECT number FROM asumi_feedback_numbers WHERE ticket_id=?", (resolved,),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def replace_own(
        self, *, ticket_id: str, reporter_id: int, guild_id: int,
        source_message_id: int, bot_version: str, description: str,
        explanation: str = "",
    ) -> FeedbackTicket:
        """Single INSERT statement + DB trigger atomically retires old ticket.

        Shares immutable private R2 evidence metadata; neither ticket's image
        is deleted. The original stays in the audited timeline as 'deleted'.
        """
        title = description.strip()[:110]
        description = description.strip()
        if not 10 <= len(description) <= 3000:
            raise FeedbackStorageError("Mô tả mới phải có từ 10 đến 3000 ký tự.")
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            raise FeedbackStorageError("Không tìm thấy ticket cần thay thế.")
        new_id = "FB-" + uuid.uuid4().hex[:10].upper()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        await self._require_cloud()
        async with db_client.execute(
            "INSERT INTO asumi_feedback "
            "(ticket_id,source_message_id,guild_id,channel_id,reporter_id,"
            "reply_to_message_id,reported_bot_message_id,bot_version,category,"
            "title,description,user_explanation,design_rule,evidence_json,"
            "replaces_ticket_id,created_at,updated_at) "
            "SELECT ?,?,f.guild_id,f.channel_id,f.reporter_id,"
            "f.reply_to_message_id,f.reported_bot_message_id,?,f.category,"
            "?,?,?,f.design_rule,f.evidence_json,f.ticket_id,?,? "
            "FROM asumi_feedback f "
            "WHERE f.ticket_id=? AND f.reporter_id=? AND f.guild_id=? "
            "AND f.replaced_by_ticket_id IS NULL "
            "AND f.status<>'deleted'",
            (new_id, str(source_message_id), bot_version, title, description,
             explanation[:1800], now, now, resolved, str(reporter_id), str(guild_id)),
        ) as cursor:
            changed = cursor.rowcount
        if not db_client.is_cloud or changed != 1:
            raise FeedbackStorageError(
                "Không thể thay thế ticket (có thể đã duyệt hoặc bị xóa)."
            )
        created = await self.own_ticket(new_id, reporter_id=reporter_id)
        if created is None:
            raise FeedbackStorageError(
                "Ticket mới có thể đã được lưu; vui lòng xem /feedback mine.",
                may_have_committed=True,
            )
        return created

    async def admin_list(self, *, status: str = "", limit: int = 50) -> list[dict]:
        await self._require_cloud()
        limit = max(1, min(100, int(limit)))
        sql = (
            "SELECT f.ticket_id, f.status, f.title, f.category, f.created_at, f.review_reason, "
            "reporter_id, bot_version, guild_id, channel_id, description, "
            "user_explanation, evidence_json, github_issue_url, github_pr_url, resolved_version, "
            "source_message_id, reported_bot_message_id, n.number, "
            "f.replaces_ticket_id, f.replaced_by_ticket_id, f.deleted_at, "
            "(SELECT newer.number FROM asumi_feedback_numbers newer WHERE newer.ticket_id=f.replaced_by_ticket_id) "
            "FROM asumi_feedback f JOIN asumi_feedback_numbers n ON n.ticket_id=f.ticket_id"
        )
        args = ()
        if status:
            sql += " WHERE f.status=?"
            args = (status[:30],)
        sql += f" ORDER BY n.number DESC LIMIT {limit}"
        async with db_client.execute(sql, args) as cursor:
            rows = await cursor.fetchall()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Turso unavailable")
        fields = ("id", "status", "title", "category", "created_at", "reason",
                  "reporter_id", "bot_version", "guild_id", "channel_id",
                  "description", "user_explanation", "evidence", "github_issue_url", "github_pr_url", "resolved_version",
                  "source_message_id", "reported_bot_message_id", "number",
                  "replaces_ticket_id", "replaced_by_ticket_id", "deleted_at", "replacement_number")
        output = []
        for row in rows:
            entry = dict(zip(fields, row))
            entry["display_id"] = f"#{entry['number']}"
            try:
                entry["evidence"] = json.loads(entry["evidence"] or "[]")
            except ValueError:
                entry["evidence"] = []
            output.append(entry)
        return output

    async def admin_detail(self, ticket_id: str) -> dict | None:
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            return None
        cols = (
            "f.ticket_id, f.status, f.title, f.category, f.created_at, f.review_reason, "
            "reporter_id, bot_version, guild_id, channel_id, description, "
            "user_explanation, evidence_json, github_issue_url, github_pr_url, "
            "resolved_version, source_message_id, reported_bot_message_id, n.number, "
            "f.replaces_ticket_id, f.replaced_by_ticket_id, f.deleted_at, "
            "(SELECT newer.number FROM asumi_feedback_numbers newer WHERE newer.ticket_id=f.replaced_by_ticket_id)"
        )
        async with db_client.execute(
            "SELECT " + cols + " FROM asumi_feedback f "
            "JOIN asumi_feedback_numbers n ON n.ticket_id=f.ticket_id "
            "WHERE f.ticket_id=?",
            (resolved,)
        ) as cursor:
            row = await cursor.fetchone()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Turso unavailable")
        if row is None:
            return None
        names = ("id", "status", "title", "category", "created_at", "reason",
                 "reporter_id", "bot_version", "guild_id", "channel_id",
                 "description", "user_explanation", "evidence",
                 "github_issue_url", "github_pr_url", "resolved_version",
                 "source_message_id", "reported_bot_message_id", "number",
                 "replaces_ticket_id", "replaced_by_ticket_id", "deleted_at", "replacement_number")
        record = dict(zip(names, row))
        record["display_id"] = f"#{record['number']}"
        try:
            record["evidence"] = json.loads(record["evidence"] or "[]")
        except (ValueError, TypeError):
            record["evidence"] = []
        return record

    async def admin_events(self, *, ticket_id: str) -> list[dict]:
        """Owner audit timeline, including reporter deletions and replacements."""
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            return []
        async with db_client.execute(
            "SELECT actor_id, action, old_status, new_status, reason, created_at "
            "FROM asumi_feedback_events WHERE ticket_id=? "
            "ORDER BY event_id DESC LIMIT 40",
            (resolved,),
        ) as cursor:
            rows = await cursor.fetchall()
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không đọc được lịch sử review.")
        return [
            dict(zip(("actor_id", "action", "old_status", "new_status",
                      "reason", "created_at"), row))
            for row in rows
        ]

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
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            raise FeedbackStorageError("Không tìm thấy ticket.")
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        # Verified means AFTER a deployed release. Never let a sidebar form
        # jump straight from submitted/approved to "fixed".
        guard = " AND status='deployed'" if status == "verified" else ""
        # Single atomic guarded UPDATE, trigger writes event/outbox on success.
        async with db_client.execute(
            "UPDATE asumi_feedback SET status=?, review_reason=?, updated_at=?, last_reviewer_id=? "
            "WHERE ticket_id=? AND status<>? AND status<>'deleted'" + guard,
            (status, (reason + (f" [release: {verified_version[:50]}]" if verified_version else ""))[:1800],
             now, actor_id[:80], resolved, status),
        ) as cursor:
            changed = cursor.rowcount
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không xác minh được ghi nhận trên Turso")
        if changed != 1:
            raise FeedbackStorageError(
                "Không thể cập nhật: ticket đã bị xóa, không tồn tại hoặc phải được deployed trước khi verified."
            )

    async def link_delivery(
        self, *, ticket_id: str, issue_url: str = "", pr_url: str = "",
        version: str = "",
    ) -> None:
        """Owner-approved refs only, never trusted from reporter ticket text."""
        for value, segment in ((issue_url, "issues"), (pr_url, "pull")):
            if not value:
                continue
            parsed = urlsplit(value)
            parts = parsed.path.strip("/").split("/")
            if (
                parsed.scheme != "https" or parsed.netloc != "github.com"
                or parsed.query or parsed.fragment or len(value) > 200
                or len(parts) != 4
                or parts[:3] != ["HoenMike", "DiscordMikeBot", segment]
                or not parts[3].isdigit()
            ):
                raise FeedbackStorageError("GitHub link không hợp lệ.")
        current = await self.admin_detail(ticket_id)
        if current is None:
            raise FeedbackStorageError("Không tìm thấy ticket")
        if (issue_url or pr_url or version) and current["status"] not in {
            "approved", "planned", "in_progress", "in_review", "deployed", "verified", "closed"
        }:
            raise FeedbackStorageError("Chỉ tạo GitHub Issue sau khi duyệt feedback")
        await self._require_cloud()
        await db_client.execute(
            "UPDATE asumi_feedback SET github_issue_url=?, github_pr_url=?, "
            "resolved_version=?, updated_at=? WHERE ticket_id=?",
            (issue_url, pr_url, version[:50],
             datetime.now(timezone.utc).isoformat(timespec="seconds"), current["id"]),
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
            (proposal_id, current["id"], target_status, reason, source[:40],
             datetime.now(timezone.utc).isoformat(timespec="microseconds")),
        )
        if not db_client.is_cloud:
            raise FeedbackStorageError("Không xác minh được đề xuất trên Turso.")
        return proposal_id

    async def list_proposals(self, *, ticket_id: str, limit: int = 20) -> list[dict]:
        resolved = await self.resolve_id(ticket_id)
        if not resolved:
            return []
        async with db_client.execute(
            "SELECT proposal_id,ticket_id,target_status,reason,source,state,created_at,"
            "reviewed_at,reviewer_id FROM asumi_feedback_review_proposals "
            "WHERE ticket_id=? ORDER BY created_at DESC LIMIT ?",
            (resolved, max(1,min(50,limit))),
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
            "COALESCE(e.reason,f.review_reason), n.event_type, nums.number "
            "FROM asumi_feedback_notifications n "
            "JOIN asumi_feedback f ON f.ticket_id=n.ticket_id "
            "JOIN asumi_feedback_numbers nums ON nums.ticket_id=n.ticket_id "
            "LEFT JOIN asumi_feedback_events e ON "
            "e.ticket_id=n.ticket_id AND e.created_at=n.created_at "
            "AND e.new_status=n.event_type AND e.action='review' "
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
