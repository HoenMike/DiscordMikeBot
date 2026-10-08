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


feedback_store = FeedbackStore()
