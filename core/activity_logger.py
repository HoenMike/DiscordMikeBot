import collections
import json
import time
import asyncio
import threading
import queue
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import config

# Giới hạn lưu trữ tối đa lượt tương tác và console logs trong RAM đệm
MAX_ACTIVITIES = 1000
MAX_CONSOLE_LOGS = 500

class ActivityLogger:
    def __init__(self, maxlen: int = MAX_ACTIVITIES):
        self._activities: collections.deque = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._counter = 0
        self._db_initialized = False
        self._pending_console_logs: collections.deque = collections.deque(maxlen=2000)
        self._flush_task: Optional[asyncio.Task] = None

    async def init_db(self):
        """Khởi tạo các bảng lưu trữ bền vững bot_activities và console_logs và nạp dữ liệu cũ vào RAM."""
        from core.db import db_client
        await db_client.connect()
        
        await db_client.execute("""
            CREATE TABLE IF NOT EXISTS bot_activities (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT NOT NULL,
                time_short   TEXT NOT NULL,
                action_type  TEXT NOT NULL,
                action_name  TEXT NOT NULL,
                user_id      INTEGER NOT NULL,
                user_name    TEXT NOT NULL,
                user_avatar  TEXT,
                guild_name   TEXT,
                guild_id     INTEGER,
                channel_name TEXT,
                channel_id   INTEGER,
                prompt       TEXT,
                response     TEXT,
                status       TEXT NOT NULL DEFAULT 'success',
                duration_ms  REAL DEFAULT 0.0,
                details_json TEXT DEFAULT '{}',
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db_client.execute("""
            CREATE TABLE IF NOT EXISTS console_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                log_line   TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db_client.commit()

        # 1. Nạp các log tương tác gần nhất từ DB vào RAM (để deploy lại vẫn giữ nguyên)
        async with db_client.execute("SELECT id, timestamp, time_short, action_type, action_name, user_id, user_name, user_avatar, guild_name, guild_id, channel_name, channel_id, prompt, response, status, duration_ms, details_json FROM bot_activities ORDER BY id DESC LIMIT 500") as cursor:
            rows = await cursor.fetchall()
            with self._lock:
                self._activities.clear()
                for r in reversed(rows):
                    try:
                        det = json.loads(r[16]) if r[16] else {}
                    except Exception:
                        det = {}
                    item = {
                        "id": r[0],
                        "timestamp": r[1],
                        "time_short": r[2],
                        "action_type": r[3],
                        "action_name": r[4],
                        "user_id": r[5],
                        "user_name": r[6],
                        "user_avatar": r[7] or "",
                        "guild_name": r[8] or "",
                        "guild_id": r[9],
                        "channel_name": r[10] or "",
                        "channel_id": r[11],
                        "prompt": r[12] or "",
                        "response": r[13] or "",
                        "status": r[14] or "success",
                        "duration_ms": float(r[15] or 0.0),
                        "details": det
                    }
                    self._activities.appendleft(item)
                    if r[0] > self._counter:
                        self._counter = r[0]

        # 2. Nạp console logs gần nhất từ DB vào log_buffer
        async with db_client.execute("SELECT log_line FROM console_logs ORDER BY id DESC LIMIT 300") as cursor:
            c_rows = await cursor.fetchall()
            # Giữ lại các log đang có, chèn log từ DB vào đầu
            existing_logs = list(config.log_buffer)
            config.log_buffer.clear()
            for r in reversed(c_rows):
                config.log_buffer.append(r[0])
            
            if c_rows:
                config.log_buffer.append(f"🚀 === PHIÊN CHẠY MỚI (DEPLOY/STARTUP) ===")

            for l in existing_logs:
                if l not in config.log_buffer:
                    config.log_buffer.append(l)

        # 3. Khởi động async task flush console logs định kỳ
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._console_log_flush_loop())

        # 4. Tự động dọn dẹp các bản ghi cũ
        await self.prune_old_records()

        self._db_initialized = True
        print(f"📊 [ActivityLogger] Đã nạp {len(self._activities)} tương tác & {len(c_rows)} console logs từ DB bền vững.", flush=True)

    def log(
        self,
        action_type: str,  # 'tarot' | 'summary' | 'embed' | 'command'
        action_name: str,
        user_id: int,
        user_name: str,
        user_avatar: Optional[str] = None,
        guild_name: Optional[str] = None,
        guild_id: Optional[int] = None,
        channel_name: Optional[str] = None,
        channel_id: Optional[int] = None,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        status: str = "success",  # 'success' | 'error' | 'in_progress'
        duration_ms: float = 0.0,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ghi nhận một hoạt động tương tác mới giữa người dùng và Bot."""
        vn_tz = timezone(timedelta(hours=7))
        now_vn = datetime.now(vn_tz)
        
        with self._lock:
            self._counter += 1
            curr_id = self._counter
            entry = {
                "id": curr_id,
                "timestamp": now_vn.strftime("%Y-%m-%d %H:%M:%S"),
                "time_short": now_vn.strftime("%H:%M:%S"),
                "action_type": action_type,
                "action_name": action_name,
                "user_id": user_id,
                "user_name": user_name,
                "user_avatar": user_avatar or "",
                "guild_name": guild_name or "Direct Message / Unknown",
                "guild_id": guild_id,
                "channel_name": channel_name or "Unknown Channel",
                "channel_id": channel_id,
                "prompt": (prompt or "").strip(),
                "response": (response or "").strip(),
                "status": status,
                "duration_ms": round(duration_ms, 1),
                "details": details or {}
            }
            self._activities.appendleft(entry)

        # Lưu bất đồng bộ vào Database (Turso Cloud / SQLite)
        self._persist_activity_async(entry)
        return entry

    def _persist_activity_async(self, entry: dict):
        """Lưu bản ghi tương tác vào Database mà không chặn luồng chính."""
        async def _do_save():
            try:
                from core.db import db_client
                await db_client.execute(
                    """
                    INSERT INTO bot_activities (
                        timestamp, time_short, action_type, action_name,
                        user_id, user_name, user_avatar, guild_name, guild_id,
                        channel_name, channel_id, prompt, response, status, duration_ms, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["timestamp"], entry["time_short"], entry["action_type"], entry["action_name"],
                        entry["user_id"], entry["user_name"], entry["user_avatar"], entry["guild_name"],
                        entry["guild_id"], entry["channel_name"], entry["channel_id"], entry["prompt"],
                        entry["response"], entry["status"], entry["duration_ms"], json.dumps(entry["details"], ensure_ascii=False)
                    )
                )
                await db_client.commit()
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                asyncio.create_task(_do_save())
        except RuntimeError:
            pass

    def log_console(self, log_line: str):
        """Đưa console log vào hàng đợi lưu bền vững ngầm."""
        self._pending_console_logs.append(log_line)

    async def prune_old_records(self):
        """Tự động dọn dẹp các log và hoạt động cũ để giữ dung lượng DB luôn gọn gàng và không bao giờ vượt limit."""
        try:
            from core.db import db_client
            # Giữ tối đa 2,000 dòng console log gần nhất
            await db_client.execute("""
                DELETE FROM console_logs 
                WHERE id NOT IN (SELECT id FROM console_logs ORDER BY id DESC LIMIT 2000)
            """)
            # Giữ tối đa 5,000 bot activities gần nhất
            await db_client.execute("""
                DELETE FROM bot_activities 
                WHERE id NOT IN (SELECT id FROM bot_activities ORDER BY id DESC LIMIT 5000)
            """)
            await db_client.commit()
        except Exception as e:
            print(f"⚠️ [ActivityLogger] Lỗi dọn dẹp DB tự động: {e}", flush=True)

    async def _console_log_flush_loop(self):
        """Task chạy ngầm định kỳ gom batch console logs và lưu vào Database mỗi 3 giây."""
        prune_ticks = 0
        while True:
            try:
                await asyncio.sleep(3.0)
                prune_ticks += 1
                if prune_ticks >= 300:  # Tự động dọn dẹp DB mỗi ~15 phút
                    prune_ticks = 0
                    await self.prune_old_records()

                if not self._pending_console_logs:
                    continue

                batch = []
                while self._pending_console_logs and len(batch) < 50:
                    batch.append(self._pending_console_logs.popleft())

                if batch:
                    from core.db import db_client
                    params = [(l,) for l in batch]
                    await db_client.executemany("INSERT INTO console_logs (log_line) VALUES (?)", params)
                    await db_client.commit()
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2.0)

    def get_activities(
        self,
        action_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Truy vấn danh sách tương tác với bộ lọc và tìm kiếm."""
        with self._lock:
            items = list(self._activities)

        if action_type and action_type != "all":
            items = [item for item in items if item["action_type"] == action_type]

        if search:
            q = search.lower().strip()
            items = [
                item for item in items
                if q in item["user_name"].lower()
                or q in item["prompt"].lower()
                or q in item["response"].lower()
                or q in item["guild_name"].lower()
                or q in item["action_name"].lower()
            ]

        total = len(items)
        sliced = items[offset : offset + limit]

        # Thống kê nhanh theo loại
        type_counts = {
            "all": len(self._activities),
            "tarot": sum(1 for a in self._activities if a["action_type"] == "tarot"),
            "summary": sum(1 for a in self._activities if a["action_type"] == "summary"),
            "embed": sum(1 for a in self._activities if a["action_type"] == "embed"),
            "command": sum(1 for a in self._activities if a["action_type"] == "command"),
        }

        return {
            "total": total,
            "counts": type_counts,
            "items": sliced
        }

    async def clear_db(self):
        """Xóa toàn bộ hoạt động trong RAM và trong Database khi Admin yêu cầu."""
        with self._lock:
            self._activities.clear()
            self._counter = 0
        from core.db import db_client
        await db_client.execute("DELETE FROM bot_activities")
        await db_client.commit()

    async def clear_console_logs_db(self):
        """Xóa toàn bộ console logs trong RAM và trong Database khi Admin yêu cầu."""
        config.log_buffer.clear()
        from core.db import db_client
        await db_client.execute("DELETE FROM console_logs")
        await db_client.commit()

    def update_activity(self, activity_id: int, updates: dict):
        """Cập nhật thông tin (ví dụ: likes, dislikes, status, response) cho một activity đã log."""
        target_entry = None
        with self._lock:
            for item in self._activities:
                if item["id"] == activity_id:
                    if "details" in updates and isinstance(item.get("details"), dict):
                        item["details"].update(updates["details"])
                        updates_copy = dict(updates)
                        updates_copy["details"] = item["details"]
                        item.update({k: v for k, v in updates_copy.items() if k != "details"})
                    else:
                        item.update(updates)
                    target_entry = dict(item)
                    break

        if target_entry:
            async def _do_update():
                try:
                    from core.db import db_client
                    await db_client.execute(
                        "UPDATE bot_activities SET details_json = ?, status = COALESCE(?, status) WHERE id = ?",
                        (json.dumps(target_entry.get("details", {}), ensure_ascii=False), updates.get("status"), activity_id)
                    )
                    await db_client.commit()
                except Exception:
                    pass

            try:
                loop = asyncio.get_running_loop()
                if loop and loop.is_running():
                    asyncio.create_task(_do_update())
            except RuntimeError:
                pass

    def clear(self):
        """Xóa bộ đệm hoạt động (sync fallback)."""
        with self._lock:
            self._activities.clear()


# Singleton instance
activity_logger = ActivityLogger()
