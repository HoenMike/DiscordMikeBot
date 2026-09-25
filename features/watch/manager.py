"""
features/watch/manager.py - Persistent Watch database management, CRUD,
run history, result memory, search usage, and budget gatekeeper.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import config
from core.activity_logger import activity_logger
from core.db import db_client
from features.watch.constants import (
    CONDITION_MAX_LEN,
    MAX_STORED_RESULTS_PER_WATCH,
    QUERY_MAX_LEN,
    TITLE_MAX_LEN,
    VALID_CADENCE_HOURS,
)
from features.watch.models import (
    EvaluationStatus,
    RunStatus,
    SearchResult,
    SearchUsage,
    WatchDefinition,
    WatchResult,
    WatchRun,
    WatchStatus,
)
from features.watch.search import get_current_month_key, get_remaining_days_in_month


class WatchManager:
    """Manages all persistent database operations for Watch definitions, results, runs, and budgets."""

    def __init__(self):
        self._db_initialized = False
        self._lock = asyncio.Lock()

    async def init_db(self) -> None:
        """Creates required tables and indexes if they do not exist."""
        await db_client.connect()

        # 1. Watch definitions table
        await db_client.execute("""
            CREATE TABLE IF NOT EXISTS watch_definitions (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id           INTEGER NOT NULL,
                guild_id                INTEGER,
                channel_id              INTEGER NOT NULL,
                title                   TEXT NOT NULL,
                search_query            TEXT NOT NULL,
                condition_prompt        TEXT,
                status                  TEXT NOT NULL DEFAULT 'active',
                cadence_hours           INTEGER NOT NULL DEFAULT 24,
                next_run_at             TEXT,
                last_checked_at         TEXT,
                last_notified_at        TEXT,
                state_json              TEXT DEFAULT '{}',
                notify_only_on_change   INTEGER NOT NULL DEFAULT 1,
                stop_after_trigger      INTEGER NOT NULL DEFAULT 0,
                failure_count           INTEGER NOT NULL DEFAULT 0,
                last_error              TEXT,
                created_at              TEXT NOT NULL,
                updated_at              TEXT NOT NULL
            )
        """)

        # 2. Watch results memory table
        await db_client.execute("""
            CREATE TABLE IF NOT EXISTS watch_results (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id            INTEGER NOT NULL,
                fingerprint         TEXT NOT NULL,
                url                 TEXT NOT NULL,
                canonical_url       TEXT NOT NULL,
                title               TEXT NOT NULL,
                snippet             TEXT,
                source_domain       TEXT,
                published_at        TEXT,
                discovered_at       TEXT NOT NULL,
                evaluation_status   TEXT NOT NULL DEFAULT 'discovered',
                event_fingerprint   TEXT,
                metadata_json       TEXT DEFAULT '{}',
                UNIQUE(watch_id, fingerprint)
            )
        """)

        # 3. Watch runs observability history
        await db_client.execute("""
            CREATE TABLE IF NOT EXISTS watch_runs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id            INTEGER NOT NULL,
                started_at          TEXT NOT NULL,
                finished_at         TEXT NOT NULL,
                status              TEXT NOT NULL,
                search_performed    INTEGER NOT NULL DEFAULT 0,
                cache_hit           INTEGER NOT NULL DEFAULT 0,
                search_result_count INTEGER NOT NULL DEFAULT 0,
                new_result_count    INTEGER NOT NULL DEFAULT 0,
                ai_called           INTEGER NOT NULL DEFAULT 0,
                meaningful_change   INTEGER NOT NULL DEFAULT 0,
                notification_sent   INTEGER NOT NULL DEFAULT 0,
                duration_ms         REAL DEFAULT 0.0,
                error_text          TEXT
            )
        """)

        # 4. Monthly search usage accounting
        await db_client.execute("""
            CREATE TABLE IF NOT EXISTS watch_search_usage (
                month_key           TEXT PRIMARY KEY,
                search_requests     INTEGER NOT NULL DEFAULT 0,
                cache_hits          INTEGER NOT NULL DEFAULT 0,
                ai_evaluations      INTEGER NOT NULL DEFAULT 0,
                notifications_sent  INTEGER NOT NULL DEFAULT 0,
                updated_at          TEXT NOT NULL
            )
        """)

        # Indexes for fast scheduler queries and lookups
        await db_client.execute("CREATE INDEX IF NOT EXISTS idx_watch_def_status_next ON watch_definitions(status, next_run_at)")
        await db_client.execute("CREATE INDEX IF NOT EXISTS idx_watch_def_owner ON watch_definitions(owner_user_id)")
        await db_client.execute("CREATE INDEX IF NOT EXISTS idx_watch_res_wid_fp ON watch_results(watch_id, fingerprint)")
        await db_client.execute("CREATE INDEX IF NOT EXISTS idx_watch_res_wid_eval ON watch_results(watch_id, evaluation_status)")
        await db_client.execute("CREATE INDEX IF NOT EXISTS idx_watch_runs_wid_started ON watch_runs(watch_id, started_at)")

        await db_client.commit()
        self._db_initialized = True

    # =========================================================================
    # WATCH DEFINITIONS CRUD
    # =========================================================================

    async def count_active_watches(self, user_id: Optional[int] = None) -> int:
        if user_id is not None:
            async with db_client.execute(
                "SELECT COUNT(*) FROM watch_definitions WHERE owner_user_id = ? AND status = ?",
                (user_id, WatchStatus.ACTIVE.value),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        else:
            async with db_client.execute(
                "SELECT COUNT(*) FROM watch_definitions WHERE status = ?",
                (WatchStatus.ACTIVE.value,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def create_watch(
        self,
        owner_user_id: int,
        channel_id: int,
        title: str,
        search_query: str,
        guild_id: Optional[int] = None,
        condition_prompt: Optional[str] = None,
        cadence_hours: int = 24,
        stop_after_trigger: bool = False,
        notify_only_on_change: bool = True,
    ) -> WatchDefinition:
        """Validates limits, persists a new Watch, and schedules its initial baseline run."""
        clean_title = title.strip()[:TITLE_MAX_LEN]
        clean_query = search_query.strip()[:QUERY_MAX_LEN]
        clean_condition = condition_prompt.strip()[:CONDITION_MAX_LEN] if condition_prompt else None

        if not clean_title:
            raise ValueError("Tiêu đề Watch không được để trống!")
        if not clean_query:
            raise ValueError("Nội dung tìm kiếm (search query) không được để trống!")

        # Validate cadence
        if cadence_hours < getattr(config, "WATCH_MIN_INTERVAL_HOURS", 4):
            raise ValueError(f"Khoảng thời gian tối thiểu là {config.WATCH_MIN_INTERVAL_HOURS} giờ!")

        # Enforce user active limit
        user_active = await self.count_active_watches(owner_user_id)
        max_user = getattr(config, "WATCH_MAX_ACTIVE_PER_USER", 5)
        if user_active >= max_user:
            raise ValueError(f"Bạn đã đạt giới hạn tối đa {max_user} Watch đang hoạt động!")

        # Enforce global active limit
        global_active = await self.count_active_watches()
        max_global = getattr(config, "WATCH_MAX_ACTIVE_GLOBAL", 30)
        if global_active >= max_global:
            raise ValueError(f"Hệ thống đã đạt giới hạn tối đa {max_global} Watch toàn cầu!")

        now_utc = datetime.now(timezone.utc).isoformat()
        # Schedule initial run immediately for silent baseline establishment
        next_run_at = now_utc

        cursor = await db_client.execute(
            """
            INSERT INTO watch_definitions (
                owner_user_id, guild_id, channel_id, title, search_query, condition_prompt,
                status, cadence_hours, next_run_at, last_checked_at, last_notified_at,
                state_json, notify_only_on_change, stop_after_trigger, failure_count,
                last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, '{}', ?, ?, 0, NULL, ?, ?)
            """,
            (
                owner_user_id,
                guild_id,
                channel_id,
                clean_title,
                clean_query,
                clean_condition,
                WatchStatus.ACTIVE.value,
                cadence_hours,
                next_run_at,
                1 if notify_only_on_change else 0,
                1 if stop_after_trigger else 0,
                now_utc,
                now_utc,
            ),
        )
        await db_client.commit()
        watch_id = cursor.lastrowid

        watch = WatchDefinition(
            id=watch_id,
            owner_user_id=owner_user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            title=clean_title,
            search_query=clean_query,
            condition_prompt=clean_condition,
            status=WatchStatus.ACTIVE.value,
            cadence_hours=cadence_hours,
            next_run_at=next_run_at,
            last_checked_at=None,
            last_notified_at=None,
            state_json="{}",
            notify_only_on_change=1 if notify_only_on_change else 0,
            stop_after_trigger=1 if stop_after_trigger else 0,
            failure_count=0,
            last_error=None,
            created_at=now_utc,
            updated_at=now_utc,
        )

        try:
            activity_logger.log(
                action_type="watch",
                action_name="Tạo Watch mới",
                user_id=owner_user_id,
                user_name=f"User {owner_user_id}",
                guild_id=guild_id,
                channel_id=channel_id,
                prompt=f"Watch #{watch_id}: {clean_title} | Query: {clean_query}",
                response=f"Đã lên lịch theo dõi mỗi {cadence_hours}h",
                status="success",
                details={"watch_id": watch_id, "cadence_hours": cadence_hours},
            )
        except Exception:
            pass

        return watch

    def _row_to_watch(self, r: Tuple[Any, ...]) -> WatchDefinition:
        return WatchDefinition(
            id=r[0],
            owner_user_id=r[1],
            guild_id=r[2],
            channel_id=r[3],
            title=r[4],
            search_query=r[5],
            condition_prompt=r[6],
            status=r[7],
            cadence_hours=r[8],
            next_run_at=r[9],
            last_checked_at=r[10],
            last_notified_at=r[11],
            state_json=r[12] or "{}",
            notify_only_on_change=r[13],
            stop_after_trigger=r[14],
            failure_count=r[15],
            last_error=r[16],
            created_at=r[17],
            updated_at=r[18],
        )

    async def get_watch(self, watch_id: int) -> Optional[WatchDefinition]:
        async with db_client.execute(
            """
            SELECT id, owner_user_id, guild_id, channel_id, title, search_query, condition_prompt,
                   status, cadence_hours, next_run_at, last_checked_at, last_notified_at,
                   state_json, notify_only_on_change, stop_after_trigger, failure_count,
                   last_error, created_at, updated_at
            FROM watch_definitions WHERE id = ?
            """,
            (watch_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_watch(row) if row else None

    async def list_user_watches(self, owner_user_id: int) -> List[WatchDefinition]:
        async with db_client.execute(
            """
            SELECT id, owner_user_id, guild_id, channel_id, title, search_query, condition_prompt,
                   status, cadence_hours, next_run_at, last_checked_at, last_notified_at,
                   state_json, notify_only_on_change, stop_after_trigger, failure_count,
                   last_error, created_at, updated_at
            FROM watch_definitions WHERE owner_user_id = ? ORDER BY id DESC
            """,
            (owner_user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_watch(r) for r in rows]

    async def list_all_watches(self, status: Optional[str] = None) -> List[WatchDefinition]:
        if status:
            async with db_client.execute(
                """
                SELECT id, owner_user_id, guild_id, channel_id, title, search_query, condition_prompt,
                       status, cadence_hours, next_run_at, last_checked_at, last_notified_at,
                       state_json, notify_only_on_change, stop_after_trigger, failure_count,
                       last_error, created_at, updated_at
                FROM watch_definitions WHERE status = ? ORDER BY id DESC
                """,
                (status,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_watch(r) for r in rows]
        else:
            async with db_client.execute(
                """
                SELECT id, owner_user_id, guild_id, channel_id, title, search_query, condition_prompt,
                       status, cadence_hours, next_run_at, last_checked_at, last_notified_at,
                       state_json, notify_only_on_change, stop_after_trigger, failure_count,
                       last_error, created_at, updated_at
                FROM watch_definitions ORDER BY id DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_watch(r) for r in rows]

    async def get_due_watches(self, limit: int = 10) -> List[WatchDefinition]:
        """Returns watches that are active and whose next_run_at <= current UTC time."""
        now_utc = datetime.now(timezone.utc).isoformat()
        async with db_client.execute(
            """
            SELECT id, owner_user_id, guild_id, channel_id, title, search_query, condition_prompt,
                   status, cadence_hours, next_run_at, last_checked_at, last_notified_at,
                   state_json, notify_only_on_change, stop_after_trigger, failure_count,
                   last_error, created_at, updated_at
            FROM watch_definitions
            WHERE status = ? AND (next_run_at IS NULL OR next_run_at <= ?)
            ORDER BY next_run_at ASC LIMIT ?
            """,
            (WatchStatus.ACTIVE.value, now_utc, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_watch(r) for r in rows]

    async def pause_watch(self, watch_id: int, user_id: int, is_admin: bool = False) -> bool:
        watch = await self.get_watch(watch_id)
        if not watch:
            return False
        if watch.owner_user_id != user_id and not is_admin:
            raise PermissionError("Bạn không phải chủ sở hữu của Watch này!")

        now_utc = datetime.now(timezone.utc).isoformat()
        await db_client.execute(
            "UPDATE watch_definitions SET status = ?, next_run_at = NULL, updated_at = ? WHERE id = ?",
            (WatchStatus.PAUSED.value, now_utc, watch_id),
        )
        await db_client.commit()

        try:
            activity_logger.log(
                action_type="watch",
                action_name="Tạm dừng Watch",
                user_id=user_id,
                user_name=f"User {user_id}",
                guild_id=watch.guild_id,
                channel_id=watch.channel_id,
                prompt=f"Tạm dừng Watch #{watch_id}: {watch.title}",
                response="Trạng thái chuyển sang paused",
                status="success",
                details={"watch_id": watch_id},
            )
        except Exception:
            pass

        return True

    async def resume_watch(self, watch_id: int, user_id: int, is_admin: bool = False) -> bool:
        watch = await self.get_watch(watch_id)
        if not watch:
            return False
        if watch.owner_user_id != user_id and not is_admin:
            raise PermissionError("Bạn không phải chủ sở hữu của Watch này!")

        # Verify limits before resuming
        user_active = await self.count_active_watches(watch.owner_user_id)
        max_user = getattr(config, "WATCH_MAX_ACTIVE_PER_USER", 5)
        if user_active >= max_user:
            raise ValueError(f"Không thể kích hoạt lại: Bạn đã có {user_active}/{max_user} Watch đang hoạt động!")

        global_active = await self.count_active_watches()
        max_global = getattr(config, "WATCH_MAX_ACTIVE_GLOBAL", 30)
        if global_active >= max_global:
            raise ValueError(f"Không thể kích hoạt lại: Hệ thống đã đạt giới hạn {max_global} Watch toàn cầu!")

        now_utc = datetime.now(timezone.utc).isoformat()
        # Schedule run immediately upon resume
        await db_client.execute(
            "UPDATE watch_definitions SET status = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
            (WatchStatus.ACTIVE.value, now_utc, now_utc, watch_id),
        )
        await db_client.commit()

        try:
            activity_logger.log(
                action_type="watch",
                action_name="Kích hoạt lại Watch",
                user_id=user_id,
                user_name=f"User {user_id}",
                guild_id=watch.guild_id,
                channel_id=watch.channel_id,
                prompt=f"Kích hoạt lại Watch #{watch_id}: {watch.title}",
                response="Trạng thái chuyển sang active",
                status="success",
                details={"watch_id": watch_id},
            )
        except Exception:
            pass

        return True

    async def delete_watch(self, watch_id: int, user_id: int, is_admin: bool = False) -> bool:
        watch = await self.get_watch(watch_id)
        if not watch:
            return False
        if watch.owner_user_id != user_id and not is_admin:
            raise PermissionError("Bạn không phải chủ sở hữu của Watch này!")

        await db_client.execute("DELETE FROM watch_results WHERE watch_id = ?", (watch_id,))
        await db_client.execute("DELETE FROM watch_runs WHERE watch_id = ?", (watch_id,))
        await db_client.execute("DELETE FROM watch_definitions WHERE id = ?", (watch_id,))
        await db_client.commit()

        try:
            activity_logger.log(
                action_type="watch",
                action_name="Xóa Watch",
                user_id=user_id,
                user_name=f"User {user_id}",
                guild_id=watch.guild_id,
                channel_id=watch.channel_id,
                prompt=f"Xóa Watch #{watch_id}: {watch.title}",
                response="Đã xóa Watch và toàn bộ dữ liệu lịch sử liên quan",
                status="success",
                details={"watch_id": watch_id},
            )
        except Exception:
            pass

        return True

    async def update_watch_schedule_and_state(
        self,
        watch_id: int,
        next_run_at: str,
        last_checked_at: Optional[str] = None,
        last_notified_at: Optional[str] = None,
        state_json: Optional[str] = None,
        status: Optional[str] = None,
        last_error: Optional[str] = None,
        failure_count_delta: int = 0,
        reset_failure: bool = False,
    ) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        updates = ["updated_at = ?", "next_run_at = ?"]
        params: List[Any] = [now_utc, next_run_at]

        if last_checked_at is not None:
            updates.append("last_checked_at = ?")
            params.append(last_checked_at)
        if last_notified_at is not None:
            updates.append("last_notified_at = ?")
            params.append(last_notified_at)
        if state_json is not None:
            updates.append("state_json = ?")
            params.append(state_json)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if last_error is not None:
            updates.append("last_error = ?")
            params.append(last_error)

        if reset_failure:
            updates.append("failure_count = 0")
        elif failure_count_delta != 0:
            updates.append("failure_count = failure_count + ?")
            params.append(failure_count_delta)

        params.append(watch_id)
        sql = f"UPDATE watch_definitions SET {', '.join(updates)} WHERE id = ?"
        await db_client.execute(sql, params)
        await db_client.commit()

    # =========================================================================
    # SEARCH RESULTS MEMORY & DEDUPLICATION
    # =========================================================================

    async def get_known_fingerprints(self, watch_id: int) -> Set[str]:
        async with db_client.execute(
            "SELECT fingerprint FROM watch_results WHERE watch_id = ?",
            (watch_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return {r[0] for r in rows}

    async def save_new_results(
        self,
        watch_id: int,
        results: List[SearchResult],
        initial_status: str = EvaluationStatus.DISCOVERED.value,
    ) -> List[SearchResult]:
        """
        Inserts new results ignoring duplicates. Returns only results that were newly discovered.
        """
        if not results:
            return []

        known = await self.get_known_fingerprints(watch_id)
        newly_discovered: List[SearchResult] = []
        now_utc = datetime.now(timezone.utc).isoformat()

        for item in results:
            if item.fingerprint in known:
                continue
            try:
                await db_client.execute(
                    """
                    INSERT INTO watch_results (
                        watch_id, fingerprint, url, canonical_url, title, snippet,
                        source_domain, published_at, discovered_at, evaluation_status,
                        event_fingerprint, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        watch_id,
                        item.fingerprint,
                        item.url,
                        item.canonical_url,
                        item.title,
                        item.snippet,
                        item.source_domain,
                        item.published_at,
                        now_utc,
                        initial_status,
                        json.dumps(item.metadata, ensure_ascii=False),
                    ),
                )
                known.add(item.fingerprint)
                newly_discovered.append(item)
            except Exception:
                # Unique constraint violation or concurrency collision
                pass

        if newly_discovered:
            await db_client.commit()
            await self.prune_results(watch_id)

        return newly_discovered

    async def get_pending_results(self, watch_id: int) -> List[WatchResult]:
        """Fetches results that have been discovered but not yet successfully evaluated."""
        async with db_client.execute(
            """
            SELECT id, watch_id, fingerprint, url, canonical_url, title, snippet,
                   source_domain, published_at, discovered_at, evaluation_status,
                   event_fingerprint, metadata_json
            FROM watch_results
            WHERE watch_id = ? AND evaluation_status = ?
            ORDER BY id ASC
            """,
            (watch_id, EvaluationStatus.DISCOVERED.value),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                WatchResult(
                    id=r[0],
                    watch_id=r[1],
                    fingerprint=r[2],
                    url=r[3],
                    canonical_url=r[4],
                    title=r[5],
                    snippet=r[6] or "",
                    source_domain=r[7] or "",
                    published_at=r[8],
                    discovered_at=r[9],
                    evaluation_status=r[10],
                    event_fingerprint=r[11],
                    metadata_json=r[12] or "{}",
                )
                for r in rows
            ]

    async def get_watch_results(self, watch_id: int, limit: int = 50) -> List[WatchResult]:
        """Fetches latest stored results for a watch."""
        async with db_client.execute(
            """
            SELECT id, watch_id, fingerprint, url, canonical_url, title, snippet,
                   source_domain, published_at, discovered_at, evaluation_status,
                   event_fingerprint, metadata_json
            FROM watch_results
            WHERE watch_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (watch_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                WatchResult(
                    id=r[0],
                    watch_id=r[1],
                    fingerprint=r[2],
                    url=r[3],
                    canonical_url=r[4],
                    title=r[5],
                    snippet=r[6] or "",
                    source_domain=r[7] or "",
                    published_at=r[8],
                    discovered_at=r[9],
                    evaluation_status=r[10],
                    event_fingerprint=r[11],
                    metadata_json=r[12] or "{}",
                )
                for r in rows
            ]

    async def mark_results_status(
        self,
        watch_id: int,
        fingerprints: List[str],
        status: str,
        event_fingerprint: Optional[str] = None,
    ) -> None:
        if not fingerprints:
            return
        placeholders = ", ".join(["?"] * len(fingerprints))
        params: List[Any] = [status]
        if event_fingerprint is not None:
            sql = f"UPDATE watch_results SET evaluation_status = ?, event_fingerprint = ? WHERE watch_id = ? AND fingerprint IN ({placeholders})"
            params.extend([event_fingerprint, watch_id, *fingerprints])
        else:
            sql = f"UPDATE watch_results SET evaluation_status = ? WHERE watch_id = ? AND fingerprint IN ({placeholders})"
            params.extend([watch_id, *fingerprints])
        await db_client.execute(sql, params)
        await db_client.commit()

    async def prune_results(self, watch_id: int, keep_latest: int = MAX_STORED_RESULTS_PER_WATCH) -> None:
        """
        Retains the latest N results per watch, but NEVER prunes pending unevaluated results.
        """
        try:
            # Delete evaluated records that are not in the top keep_latest
            await db_client.execute(
                f"""
                DELETE FROM watch_results
                WHERE watch_id = ?
                  AND evaluation_status != ?
                  AND id NOT IN (
                      SELECT id FROM watch_results
                      WHERE watch_id = ?
                      ORDER BY id DESC LIMIT ?
                  )
                """,
                (watch_id, EvaluationStatus.DISCOVERED.value, watch_id, keep_latest),
            )
            await db_client.commit()
        except Exception:
            pass

    # =========================================================================
    # RUN HISTORY OBSERVABILITY
    # =========================================================================

    async def save_run(self, run: WatchRun) -> int:
        cursor = await db_client.execute(
            """
            INSERT INTO watch_runs (
                watch_id, started_at, finished_at, status, search_performed,
                cache_hit, search_result_count, new_result_count, ai_called,
                meaningful_change, notification_sent, duration_ms, error_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.watch_id,
                run.started_at,
                run.finished_at,
                run.status,
                run.search_performed,
                run.cache_hit,
                run.search_result_count,
                run.new_result_count,
                run.ai_called,
                run.meaningful_change,
                run.notification_sent,
                run.duration_ms,
                run.error_text,
            ),
        )
        await db_client.commit()
        return cursor.lastrowid or 0

    async def get_recent_runs(self, watch_id: Optional[int] = None, limit: int = 50) -> List[WatchRun]:
        if watch_id is not None:
            sql = """
                SELECT id, watch_id, started_at, finished_at, status, search_performed,
                       cache_hit, search_result_count, new_result_count, ai_called,
                       meaningful_change, notification_sent, duration_ms, error_text
                FROM watch_runs WHERE watch_id = ? ORDER BY id DESC LIMIT ?
            """
            params = (watch_id, limit)
        else:
            sql = """
                SELECT id, watch_id, started_at, finished_at, status, search_performed,
                       cache_hit, search_result_count, new_result_count, ai_called,
                       meaningful_change, notification_sent, duration_ms, error_text
                FROM watch_runs ORDER BY id DESC LIMIT ?
            """
            params = (limit,)

        async with db_client.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [
                WatchRun(
                    id=r[0],
                    watch_id=r[1],
                    started_at=r[2],
                    finished_at=r[3],
                    status=r[4],
                    search_performed=r[5],
                    cache_hit=r[6],
                    search_result_count=r[7],
                    new_result_count=r[8],
                    ai_called=r[9],
                    meaningful_change=r[10],
                    notification_sent=r[11],
                    duration_ms=float(r[12] or 0.0),
                    error_text=r[13],
                )
                for r in rows
            ]

    # =========================================================================
    # MONTHLY SEARCH BUDGET & USAGE ACCOUNTING
    # =========================================================================

    async def get_search_usage(self, month_key: Optional[str] = None) -> SearchUsage:
        key = month_key or get_current_month_key()
        async with db_client.execute(
            """
            SELECT month_key, search_requests, cache_hits, ai_evaluations,
                   notifications_sent, updated_at
            FROM watch_search_usage WHERE month_key = ?
            """,
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return SearchUsage(
                    month_key=row[0],
                    search_requests=row[1],
                    cache_hits=row[2],
                    ai_evaluations=row[3],
                    notifications_sent=row[4],
                    updated_at=row[5],
                )
            return SearchUsage(month_key=key, updated_at=datetime.now(timezone.utc).isoformat())

    async def increment_usage(
        self,
        month_key: Optional[str] = None,
        search_requests: int = 0,
        cache_hits: int = 0,
        ai_evaluations: int = 0,
        notifications_sent: int = 0,
    ) -> None:
        key = month_key or get_current_month_key()
        now_utc = datetime.now(timezone.utc).isoformat()

        # Check existing row
        usage = await self.get_search_usage(key)
        new_sr = usage.search_requests + search_requests
        new_ch = usage.cache_hits + cache_hits
        new_ae = usage.ai_evaluations + ai_evaluations
        new_ns = usage.notifications_sent + notifications_sent

        # Upsert
        await db_client.execute(
            """
            INSERT INTO watch_search_usage (
                month_key, search_requests, cache_hits, ai_evaluations, notifications_sent, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(month_key) DO UPDATE SET
                search_requests = ?,
                cache_hits = ?,
                ai_evaluations = ?,
                notifications_sent = ?,
                updated_at = ?
            """,
            (key, new_sr, new_ch, new_ae, new_ns, now_utc, new_sr, new_ch, new_ae, new_ns, now_utc),
        )
        await db_client.commit()

    async def check_budget_gate(self) -> Tuple[bool, SearchUsage, str]:
        """
        Enforces hard monthly budget limit.
        Returns: (can_search: bool, usage: SearchUsage, reason: str)
        """
        usage = await self.get_search_usage()
        limit = getattr(config, "WATCH_MONTHLY_SEARCH_BUDGET", 900)

        if usage.search_requests >= limit:
            return (
                False,
                usage,
                f"Hạn ngạch tìm kiếm tháng {usage.month_key} đã đạt giới hạn ({usage.search_requests}/{limit}).",
            )
        return True, usage, "OK"

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Aggregates metrics for Admin Console."""
        usage = await self.get_search_usage()
        monthly_limit = getattr(config, "WATCH_MONTHLY_SEARCH_BUDGET", 900)
        days_left = get_remaining_days_in_month()
        remaining_budget = max(0, monthly_limit - usage.search_requests)
        daily_allowance = round(remaining_budget / days_left, 1)

        active_count = await self.count_active_watches()

        # Checks today
        now_utc = datetime.now(timezone.utc)
        today_prefix = now_utc.strftime("%Y-%m-%d")
        checks_today = 0
        meaningful_today = 0
        async with db_client.execute(
            "SELECT COUNT(*), SUM(meaningful_change) FROM watch_runs WHERE started_at LIKE ?",
            (f"{today_prefix}%",),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                checks_today = row[0] or 0
                meaningful_today = row[1] or 0

        # Total meaningful change rate
        meaningful_rate = 0.0
        async with db_client.execute("SELECT COUNT(*), SUM(meaningful_change) FROM watch_runs") as cursor:
            row = await cursor.fetchone()
            if row and row[0] and row[0] > 0:
                meaningful_rate = round(((row[1] or 0) / row[0]) * 100, 1)

        # Degraded / config_error watches
        degraded_count = 0
        async with db_client.execute(
            "SELECT COUNT(*) FROM watch_definitions WHERE status = ? OR failure_count >= 3",
            (WatchStatus.CONFIG_ERROR.value,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                degraded_count = row[0] or 0

        return {
            "active_watches": active_count,
            "checks_today": checks_today,
            "monthly_searches": usage.search_requests,
            "monthly_limit": monthly_limit,
            "budget_remaining": remaining_budget,
            "daily_allowance": daily_allowance,
            "days_left": days_left,
            "cache_hits": usage.cache_hits,
            "ai_evaluations": usage.ai_evaluations,
            "notifications_sent": usage.notifications_sent,
            "meaningful_change_rate": meaningful_rate,
            "meaningful_today": meaningful_today,
            "degraded_watches": degraded_count,
            "brave_configured": bool(getattr(config, "BRAVE_SEARCH_API_KEY", "")),
        }


# Singleton manager instance
watch_manager = WatchManager()
