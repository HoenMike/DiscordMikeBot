"""Turso-backed per-guild config and idempotent (best effort) delivery."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.db import db_client


class WatchStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class WatchConfig:
    guild_id: int
    channel_id: int
    role_id: int
    enabled: bool
    active_after: datetime


class CodexWatchStore:
    async def cloud(self):
        await db_client.connect()
        if not db_client.is_cloud:
            raise WatchStorageError("Codex Watch cần Turso Cloud; Local SQLite không được gửi ping.")

    async def initialize(self):
        await self.cloud()
        await db_client.execute(
            """CREATE TABLE IF NOT EXISTS asumi_codex_watch (
              guild_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL,
              role_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
              active_after TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        await db_client.execute(
            """CREATE TABLE IF NOT EXISTS asumi_codex_watch_delivery (
              guild_id TEXT NOT NULL, event_key TEXT NOT NULL,
              status TEXT NOT NULL, lease_until TEXT NOT NULL,
              source_url TEXT NOT NULL, message_id TEXT,
              updated_at TEXT NOT NULL, PRIMARY KEY (guild_id, event_key)
            )"""
        )
        if not db_client.is_cloud:
            raise WatchStorageError("Turso không khả dụng khi tạo bảng.")

    async def setup(self, guild_id: int, channel_id: int, role_id: int):
        await self.cloud()
        now = datetime.now(timezone.utc).isoformat()
        await db_client.execute(
            """INSERT INTO asumi_codex_watch
            (guild_id,channel_id,role_id,enabled,active_after,updated_at)
            VALUES(?,?,?,0,?,?)
            ON CONFLICT(guild_id) DO UPDATE SET
            channel_id=excluded.channel_id, role_id=excluded.role_id,
            enabled=0, active_after=excluded.active_after,
            updated_at=excluded.updated_at""",
            (str(guild_id),str(channel_id),str(role_id),now,now),
        )
        if not db_client.is_cloud:
            raise WatchStorageError("Turso không lưu được cấu hình.")

    async def set_enabled(self, guild_id: int, enabled: bool) -> bool:
        await self.cloud()
        now = datetime.now(timezone.utc).isoformat()
        async with db_client.execute(
            """UPDATE asumi_codex_watch SET enabled=?,active_after=?,updated_at=?
            WHERE guild_id=?""", (int(enabled),now,now,str(guild_id))
        ) as cur:
            updated = cur.rowcount == 1
        if not db_client.is_cloud:
            raise WatchStorageError("Turso không khả dụng.")
        return updated

    async def get(self, guild_id: int) -> WatchConfig | None:
        await self.cloud()
        async with db_client.execute(
            "SELECT guild_id,channel_id,role_id,enabled,active_after "
            "FROM asumi_codex_watch WHERE guild_id=?",(str(guild_id),)
        ) as cur:
            row = await cur.fetchone()
        if not db_client.is_cloud:
            raise WatchStorageError("Không thể xác minh trạng thái Turso.")
        return self._config(row) if row else None

    async def enabled_configs(self) -> list[WatchConfig]:
        await self.cloud()
        async with db_client.execute(
            "SELECT guild_id,channel_id,role_id,enabled,active_after "
            "FROM asumi_codex_watch WHERE enabled=1"
        ) as cur:
            rows = await cur.fetchall()
        if not db_client.is_cloud:
            raise WatchStorageError("Không thể xác minh trạng thái Turso.")
        return [self._config(row) for row in rows]

    @staticmethod
    def _config(row) -> WatchConfig:
        return WatchConfig(int(row[0]),int(row[1]),int(row[2]),
                           bool(row[3]),datetime.fromisoformat(row[4]))

    async def claim(self, guild_id: int, event_key: str, source_url: str) -> bool:
        """Atomic lease; no duplicate while retry window is pending."""
        await self.cloud()
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(minutes=7)).isoformat()
        async with db_client.execute(
            """INSERT INTO asumi_codex_watch_delivery
              (guild_id,event_key,status,lease_until,source_url,updated_at)
              VALUES(?,?,'sending',?,?,?)
              ON CONFLICT(guild_id,event_key) DO UPDATE SET
                status='sending', lease_until=excluded.lease_until,
                updated_at=excluded.updated_at
              WHERE asumi_codex_watch_delivery.status IN ('sending','retry')
                AND asumi_codex_watch_delivery.lease_until < excluded.updated_at""",
            (str(guild_id),event_key,expiry,source_url,now.isoformat())
        ) as cur:
            won = cur.rowcount == 1
        if not db_client.is_cloud:
            raise WatchStorageError("Turso mất kết nối trước khi claim.")
        return won

    async def complete(self, guild_id: int, event_key: str, message_id: int):
        await self.cloud()
        await db_client.execute(
            """UPDATE asumi_codex_watch_delivery SET
               status='delivered',message_id=?,updated_at=?
               WHERE guild_id=? AND event_key=? AND status='sending'""",
            (str(message_id), datetime.now(timezone.utc).isoformat(),
             str(guild_id),event_key),
        )
        if not db_client.is_cloud:
            raise WatchStorageError("Không xác minh được kết quả đã gửi.")

    async def failed(self, guild_id: int, event_key: str):
        await self.cloud()
        now = datetime.now(timezone.utc)
        await db_client.execute(
            """UPDATE asumi_codex_watch_delivery SET
               status='retry',lease_until=?,updated_at=?
               WHERE guild_id=? AND event_key=? AND status='sending'""",
            ((now+timedelta(minutes=5)).isoformat(),now.isoformat(),
             str(guild_id),event_key),
        )
        if not db_client.is_cloud:
            raise WatchStorageError("Không ghi được retry.")

codex_watch_store = CodexWatchStore()
