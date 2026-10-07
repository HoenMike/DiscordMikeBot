from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from core.db import db_client

URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


class ArchiveStore:
    """Explicit, user-owned long-term memory. No passive writes."""

    def __init__(self):
        self._ready = False

    async def ensure_schema(self) -> None:
        if self._ready:
            return
        await db_client.connect()
        await db_client.execute("""
            CREATE TABLE IF NOT EXISTS asumi_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                guild_id INTEGER,
                channel_id INTEGER,
                source_message_id INTEGER,
                source_author_id INTEGER,
                source_author_name TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'message',
                source_content TEXT NOT NULL DEFAULT '',
                source_jump_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db_client.execute("""
            CREATE INDEX IF NOT EXISTS idx_asumi_archive_owner
            ON asumi_archive(owner_user_id, id DESC)
        """)
        await db_client.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_asumi_archive_owner_source
            ON asumi_archive(owner_user_id, guild_id, channel_id, source_message_id)
            WHERE source_message_id IS NOT NULL
        """)
        await db_client.commit()
        self._ready = True

    async def _resolve_reply(self, message):
        ref = getattr(message, "reference", None)
        if not ref:
            return None
        resolved = getattr(ref, "resolved", None)
        if resolved is not None and hasattr(resolved, "content"):
            return resolved
        message_id = getattr(ref, "message_id", None)
        fetch = getattr(getattr(message, "channel", None), "fetch_message", None)
        if message_id and fetch:
            try:
                return await fetch(message_id)
            except Exception:
                return None
        return None

    @staticmethod
    def _jump_url(message) -> str:
        if getattr(message, "jump_url", None):
            return str(message.jump_url)
        guild_id = getattr(getattr(message, "guild", None), "id", None)
        channel_id = getattr(getattr(message, "channel", None), "id", None)
        message_id = getattr(message, "id", None)
        if guild_id and channel_id and message_id:
            return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        return ""

    @staticmethod
    def _payload(message) -> tuple[str, str, str, dict[str, Any]]:
        content = (getattr(message, "content", "") or "").strip()
        had_original_text = bool(content)
        urls = [u.rstrip(".,!?)]}>") for u in URL_RE.findall(content)]
        attachments = []
        embeds = []

        for attachment in list(getattr(message, "attachments", None) or [])[:8]:
            attachments.append({
                "filename": getattr(attachment, "filename", "") or "",
                "content_type": getattr(attachment, "content_type", "") or "",
                "size": int(getattr(attachment, "size", 0) or 0),
                "url": str(getattr(attachment, "url", "") or ""),
            })

        for embed in list(getattr(message, "embeds", None) or [])[:4]:
            item = {
                "title": (getattr(embed, "title", "") or "")[:300],
                "description": (getattr(embed, "description", "") or "")[:1200],
                "url": str(getattr(embed, "url", "") or ""),
            }
            embeds.append(item)
            if item["url"]:
                urls.append(item["url"])

        if not content:
            lines = [
                f"{item['title']} — {item['description']}".strip(" —")
                for item in embeds
                if item["title"] or item["description"]
            ]
            lines.extend(
                f"[Attachment] {item['filename']}"
                for item in attachments
                if item["filename"]
            )
            content = "\n".join(lines)

        primary_url = urls[0] if urls else (
            attachments[0]["url"] if attachments else ""
        )
        if attachments and (urls or embeds or had_original_text):
            kind = "mixed"
        elif attachments:
            kind = "media"
        elif urls or embeds:
            kind = "link"
        else:
            kind = "message"

        return (
            content[:6000],
            primary_url,
            kind,
            {"attachments": attachments, "embeds": embeds},
        )

    @staticmethod
    def _decode(row) -> dict[str, Any]:
        try:
            metadata = json.loads(row[12] or "{}")
        except Exception:
            metadata = {}
        return {
            "id": int(row[0]),
            "owner_user_id": int(row[1]),
            "guild_id": row[2],
            "channel_id": row[3],
            "source_message_id": row[4],
            "source_author_id": row[5],
            "source_author_name": row[6] or "",
            "source_kind": row[7] or "message",
            "source_content": row[8] or "",
            "source_jump_url": row[9] or "",
            "source_url": row[10] or "",
            "note": row[11] or "",
            "metadata": metadata,
            "created_at": row[13] or "",
        }

    async def save(self, owner_user_id: int, trigger_message, note: str = ""):
        await self.ensure_schema()
        replied = await self._resolve_reply(trigger_message)
        source = replied or trigger_message

        if replied is None:
            has_attachment = bool(getattr(trigger_message, "attachments", None))
            has_url = bool(URL_RE.search(getattr(trigger_message, "content", "") or ""))
            if not has_attachment and not has_url:
                return None, (
                    "Reply vào đúng message/link/ảnh cần lưu rồi nói @Asumi nhớ cái này, "
                    "hoặc gửi link/ảnh ngay trong tin nhắn."
                ), False

        content, source_url, source_kind, metadata = self._payload(source)
        if not content and not source_url and not metadata["attachments"]:
            return None, "Mình không thấy nội dung nào đủ rõ để lưu.", False

        guild = getattr(source, "guild", None) or getattr(trigger_message, "guild", None)
        channel = getattr(source, "channel", None) or getattr(trigger_message, "channel", None)
        author = getattr(source, "author", None)
        guild_id = getattr(guild, "id", None)
        channel_id = getattr(channel, "id", None)
        source_message_id = getattr(source, "id", None)
        source_author_id = getattr(author, "id", None)
        source_author_name = (
            getattr(author, "display_name", None)
            or getattr(author, "name", None)
            or "Unknown"
        )
        note = (note or "").strip()[:500]

        if source_message_id is not None:
            async with db_client.execute("""
                SELECT id, owner_user_id, guild_id, channel_id, source_message_id,
                       source_author_id, source_author_name, source_kind, source_content,
                       source_jump_url, source_url, note, metadata_json, created_at
                FROM asumi_archive
                WHERE owner_user_id=? AND guild_id IS ? AND channel_id IS ?
                  AND source_message_id=?
                ORDER BY id DESC LIMIT 1
            """, (owner_user_id, guild_id, channel_id, source_message_id)) as cur:
                row = await cur.fetchone()
            if row:
                item = self._decode(row)
                if note and note != item["note"]:
                    await db_client.execute(
                        "UPDATE asumi_archive SET note=?, updated_at=datetime('now') "
                        "WHERE id=? AND owner_user_id=?",
                        (note, item["id"], owner_user_id),
                    )
                    await db_client.commit()
                    item["note"] = note
                return item, "", False

        await db_client.execute("""
            INSERT OR IGNORE INTO asumi_archive (
                owner_user_id, guild_id, channel_id, source_message_id,
                source_author_id, source_author_name, source_kind, source_content,
                source_jump_url, source_url, note, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            owner_user_id, guild_id, channel_id, source_message_id,
            source_author_id, source_author_name, source_kind, content,
            self._jump_url(source), source_url, note,
            json.dumps(metadata, ensure_ascii=False),
        ))
        await db_client.commit()

        if source_message_id is not None:
            query = """
                SELECT id, owner_user_id, guild_id, channel_id, source_message_id,
                       source_author_id, source_author_name, source_kind, source_content,
                       source_jump_url, source_url, note, metadata_json, created_at
                FROM asumi_archive
                WHERE owner_user_id=? AND guild_id IS ? AND channel_id IS ?
                  AND source_message_id=?
                ORDER BY id DESC LIMIT 1
            """
            params = (owner_user_id, guild_id, channel_id, source_message_id)
        else:
            query = """
                SELECT id, owner_user_id, guild_id, channel_id, source_message_id,
                       source_author_id, source_author_name, source_kind, source_content,
                       source_jump_url, source_url, note, metadata_json, created_at
                FROM asumi_archive
                WHERE owner_user_id=?
                ORDER BY id DESC LIMIT 1
            """
            params = (owner_user_id,)

        async with db_client.execute(query, params) as cur:
            row = await cur.fetchone()

        return (self._decode(row), "", True) if row else (
            None, "Không đọc lại được mục Archive vừa lưu.", False
        )

    @staticmethod
    def _fold(text: str) -> str:
        normalized = unicodedata.normalize("NFD", (text or "").lower())
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @classmethod
    def _score(cls, item: dict[str, Any], query: str) -> int:
        query_folded = cls._fold(query).strip()
        if not query_folded:
            return 1
        haystack = cls._fold(" ".join([
            item["source_content"], item["source_author_name"], item["note"],
            item["source_url"], json.dumps(item["metadata"], ensure_ascii=False),
        ]))
        score = 20 if query_folded in haystack else 0
        stop = {
            "cai", "nay", "do", "tim", "lai", "nho", "luu", "archive",
            "cho", "toi", "minh", "gui", "hom", "truoc",
        }
        for token in re.findall(r"[a-z0-9_]{2,}", query_folded):
            if token not in stop and token in haystack:
                score += 4
        return score

    async def search(self, owner_user_id: int, query: str = "", limit: int = 5):
        await self.ensure_schema()
        async with db_client.execute("""
            SELECT id, owner_user_id, guild_id, channel_id, source_message_id,
                   source_author_id, source_author_name, source_kind, source_content,
                   source_jump_url, source_url, note, metadata_json, created_at
            FROM asumi_archive
            WHERE owner_user_id=?
            ORDER BY id DESC LIMIT 250
        """, (owner_user_id,)) as cur:
            rows = await cur.fetchall()

        items = [self._decode(row) for row in rows]
        safe_limit = max(1, min(int(limit), 10))
        if not (query or "").strip():
            return items[:safe_limit]

        ranked = [(self._score(item, query), i, item) for i, item in enumerate(items)]
        ranked = [entry for entry in ranked if entry[0] > 0]
        ranked.sort(key=lambda entry: (-entry[0], entry[1]))
        return [entry[2] for entry in ranked[:safe_limit]]

    async def get_by_ids(
        self,
        owner_user_id: int,
        archive_ids: list[int],
    ) -> list[dict[str, Any]]:
        await self.ensure_schema()
        normalized = []
        seen = set()
        for value in archive_ids:
            try:
                archive_id = int(value)
            except (TypeError, ValueError):
                continue
            if archive_id > 0 and archive_id not in seen:
                seen.add(archive_id)
                normalized.append(archive_id)

        if not normalized:
            return []

        placeholders = ",".join("?" for _ in normalized)
        params = (owner_user_id, *normalized)
        async with db_client.execute(
            f"""
            SELECT id, owner_user_id, guild_id, channel_id, source_message_id,
                   source_author_id, source_author_name, source_kind, source_content,
                   source_jump_url, source_url, note, metadata_json, created_at
            FROM asumi_archive
            WHERE owner_user_id=? AND id IN ({placeholders})
            """,
            params,
        ) as cur:
            rows = await cur.fetchall()

        by_id = {int(row[0]): self._decode(row) for row in rows}
        return [by_id[item_id] for item_id in normalized if item_id in by_id]

    async def forget(self, owner_user_id: int, archive_id: int) -> bool:
        await self.ensure_schema()
        cur = await db_client.execute(
            "DELETE FROM asumi_archive WHERE id=? AND owner_user_id=?",
            (int(archive_id), owner_user_id),
        )
        await db_client.commit()
        return int(cur.rowcount or 0) > 0


archive_store = ArchiveStore()
