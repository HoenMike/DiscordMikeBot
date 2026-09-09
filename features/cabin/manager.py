"""
features/cabin/manager.py - Quản lý phiên Dịch Cabin AI với bộ đệm RAM và đồng bộ Database.
"""

import asyncio
import collections
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from features.cabin.constants import (
    DEFAULT_CABIN_COOLDOWN_SECONDS,
    DEFAULT_DURATION_SECONDS,
)


@dataclass
class CabinSession:
    """Đại diện cho một phiên dịch cabin đang hoạt động của một người dùng trong server."""
    guild_id: int
    channel_id: Optional[int]
    target_id: int
    target_name: str
    creator_id: int
    creator_name: str
    expires_at: float
    created_at: float
    translated_count: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.expires_at - time.time()))


class CabinManager:
    """Quản lý các phiên dịch cabin in-memory kèm sao lưu cơ sở dữ liệu bền vững."""

    def __init__(self):
        # Key: (guild_id, target_id) -> CabinSession
        self._sessions: Dict[Tuple[int, int], CabinSession] = {}
        # Key: (guild_id, target_id) -> float (timestamp lần dịch gần nhất)
        self._last_translated: Dict[Tuple[int, int], float] = {}
        # In-flight guard: chống gửi 2 request AI song song khi user chat dồn dập
        self._in_flight: Set[Tuple[int, int]] = set()
        # Bộ đệm người dùng đang bật Khiên Chống Cabin: (guild_id, user_id)
        self._shields: Set[Tuple[int, int]] = set()
        # Rolling message cache: channel_id -> collections.deque(maxlen=35)
        # Mỗi phần tử: (timestamp: float, author_name: str, content: str)
        self._channel_cache: Dict[int, collections.deque] = {}
        self._channel_last_activity: Dict[int, float] = {}
        self._db_initialized = False

    async def _get_db(self):
        from core.db import db_client
        await db_client.connect()
        return db_client

    async def init_db(self) -> None:
        """Khởi tạo bảng cơ sở dữ liệu và nạp lại các phiên cabin còn hiệu lực vào RAM."""
        if self._db_initialized:
            return
        
        db = await self._get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cabin_sessions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id         INTEGER NOT NULL,
                channel_id       INTEGER,
                target_id        INTEGER NOT NULL,
                target_name      TEXT NOT NULL,
                creator_id       INTEGER NOT NULL,
                creator_name     TEXT NOT NULL,
                expires_at       REAL NOT NULL,
                created_at       REAL NOT NULL,
                translated_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(guild_id, target_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cabin_shields (
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                user_name  TEXT,
                created_at REAL NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()

        # Dọn dẹp các session cũ đã hết hạn từ trước
        now = time.time()
        await db.execute("DELETE FROM cabin_sessions WHERE expires_at <= ?", (now,))
        await db.commit()

        # Nạp các session còn hiệu lực vào RAM
        async with db.execute("""
            SELECT guild_id, channel_id, target_id, target_name, creator_id, creator_name, expires_at, created_at, translated_count
            FROM cabin_sessions
            WHERE expires_at > ?
        """, (now,)) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                s = CabinSession(
                    guild_id=int(r[0]),
                    channel_id=int(r[1]) if r[1] else None,
                    target_id=int(r[2]),
                    target_name=str(r[3]),
                    creator_id=int(r[4]),
                    creator_name=str(r[5]),
                    expires_at=float(r[6]),
                    created_at=float(r[7]),
                    translated_count=int(r[8]) if len(r) > 8 else 0,
                )
                self._sessions[(s.guild_id, s.target_id)] = s

        # Nạp danh sách người dùng đang mang Khiên Chống Cabin vào RAM
        async with db.execute("SELECT guild_id, user_id FROM cabin_shields") as cursor:
            shield_rows = await cursor.fetchall()
            for sr in shield_rows:
                self._shields.add((int(sr[0]), int(sr[1])))

        self._db_initialized = True

    async def start_session(
        self,
        guild_id: int,
        channel_id: Optional[int],
        target_id: int,
        target_name: str,
        creator_id: int,
        creator_name: str,
        duration_seconds: int = DEFAULT_DURATION_SECONDS,
    ) -> CabinSession:
        """Bắt đầu phiên dịch cabin cho một người dùng."""
        now = time.time()
        expires_at = now + duration_seconds

        session = CabinSession(
            guild_id=guild_id,
            channel_id=channel_id,
            target_id=target_id,
            target_name=target_name,
            creator_id=creator_id,
            creator_name=creator_name,
            expires_at=expires_at,
            created_at=now,
            translated_count=0,
        )
        self._sessions[(guild_id, target_id)] = session

        # Luôn reset thời gian dịch gần nhất (cooldown) khi bắt đầu mới hoặc khi có người khác đè quyền
        self._last_translated.pop((guild_id, target_id), None)

        try:
            db = await self._get_db()
            await db.execute("""
                INSERT INTO cabin_sessions (
                    guild_id, channel_id, target_id, target_name, creator_id, creator_name, expires_at, created_at, translated_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, target_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    target_name = excluded.target_name,
                    creator_id = excluded.creator_id,
                    creator_name = excluded.creator_name,
                    expires_at = excluded.expires_at,
                    created_at = excluded.created_at,
                    translated_count = 0
            """, (
                guild_id, channel_id, target_id, target_name,
                creator_id, creator_name, expires_at, now, 0
            ))
            await db.commit()
        except Exception as e:
            print(f"⚠️ [CabinManager] Lỗi lưu session vào DB: {e}", flush=True)

        return session

    async def stop_session(self, guild_id: int, target_id: int) -> bool:
        """Dừng phiên dịch cabin của một người dùng trong server."""
        key = (guild_id, target_id)
        had_session = key in self._sessions
        if had_session:
            del self._sessions[key]

        self._last_translated.pop(key, None)

        try:
            db = await self._get_db()
            await db.execute(
                "DELETE FROM cabin_sessions WHERE guild_id = ? AND target_id = ?",
                (guild_id, target_id)
            )
            await db.commit()
        except Exception as e:
            print(f"⚠️ [CabinManager] Lỗi xoá session trong DB: {e}", flush=True)

        return had_session

    def get_session(self, guild_id: int, target_id: int) -> Optional[CabinSession]:
        """Lấy thông tin phiên cabin nếu đang hoạt động và chưa hết hạn."""
        key = (guild_id, target_id)
        session = self._sessions.get(key)
        if not session:
            return None

        if session.is_expired:
            self._sessions.pop(key, None)
            self._last_translated.pop(key, None)
            return None

        return session

    def is_active(self, guild_id: int, target_id: int) -> bool:
        """Kiểm tra người dùng có đang trong phiên cabin hợp lệ hay không."""
        return self.get_session(guild_id, target_id) is not None

    def get_active_session_by_creator(self, guild_id: int, creator_id: int) -> Optional[CabinSession]:
        """
        Kiểm tra xem người dùng này đã tạo một phiên cabin nào khác đang còn hiệu lực trong server hay chưa.
        Giới hạn 1 người chỉ được tạo tối đa 1 phiên cabin tại một thời điểm.
        """
        now = time.time()
        for (g_id, t_id), session in list(self._sessions.items()):
            if g_id == guild_id and session.creator_id == creator_id:
                if session.expires_at > now:
                    return session
                else:
                    self._sessions.pop((g_id, t_id), None)
                    self._last_translated.pop((g_id, t_id), None)
        return None

    def has_shield(self, guild_id: int, user_id: int) -> bool:
        """Kiểm tra người dùng có đang mang Khiên Chống Cabin hay không."""
        return (guild_id, user_id) in self._shields

    async def toggle_shield(
        self,
        guild_id: int,
        user_id: int,
        user_name: str,
        enable: Optional[bool] = None
    ) -> bool:
        """
        Bật hoặc tắt Khiên Chống Cabin cho một người dùng.
        Nếu enable là None -> tự động đảo trạng thái (Toggle).
        Trả về True nếu khiên đang BẬT, False nếu khiên đã TẮT.
        """
        key = (guild_id, user_id)
        if enable is None:
            enable = (key not in self._shields)

        db = await self._get_db()
        if enable:
            self._shields.add(key)
            now = time.time()
            try:
                await db.execute("""
                    INSERT INTO cabin_shields (guild_id, user_id, user_name, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        user_name = excluded.user_name,
                        created_at = excluded.created_at
                """, (guild_id, user_id, user_name, now))
                await db.commit()
            except Exception as e:
                print(f"⚠️ [CabinManager] Lỗi lưu khiên vào DB: {e}", flush=True)

            # Nếu người này đang trong buồng cabin -> Phá hủy session cabin ngay lập tức!
            await self.stop_session(guild_id, user_id)
            return True
        else:
            self._shields.discard(key)
            try:
                await db.execute(
                    "DELETE FROM cabin_shields WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                await db.commit()
            except Exception as e:
                print(f"⚠️ [CabinManager] Lỗi xóa khiên khỏi DB: {e}", flush=True)
            return False

    async def list_all_shields(self) -> List[dict]:
        """Lấy danh sách tất cả người dùng đang được bảo vệ bởi Khiên Chống Cabin từ Database."""
        shields = []
        try:
            db = await self._get_db()
            async with db.execute(
                "SELECT guild_id, user_id, user_name, created_at FROM cabin_shields ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    shields.append({
                        "guild_id": row[0],
                        "user_id": row[1],
                        "user_name": row[2] or f"User {row[1]}",
                        "created_at": row[3],
                    })
        except Exception as e:
            print(f"⚠️ [CabinManager] Lỗi đọc danh sách khiên: {e}", flush=True)
            # Fallback từ in-memory set nếu DB có lỗi
            for g_id, u_id in self._shields:
                shields.append({
                    "guild_id": g_id,
                    "user_id": u_id,
                    "user_name": f"User {u_id}",
                    "created_at": time.time(),
                })
        return shields

    def list_all_sessions(self) -> List[CabinSession]:
        """Lấy danh sách tất cả các phiên cabin đang hoạt động trên toàn bộ hệ thống."""
        now = time.time()
        valid = []
        expired_keys = []
        for key, s in list(self._sessions.items()):
            if s.expires_at > now:
                valid.append(s)
            else:
                expired_keys.append(key)

        for ek in expired_keys:
            self._sessions.pop(ek, None)
            self._last_translated.pop(ek, None)

        return valid

    def check_cooldown(
        self,
        guild_id: int,
        target_id: int,
        cooldown_seconds: float = DEFAULT_CABIN_COOLDOWN_SECONDS,
        update: bool = True
    ) -> bool:
        """
        Kiểm tra xem target có đang trong thời gian chờ (cooldown) hay không.
        Nếu update=True, tự động cập nhật thời điểm dịch gần nhất khi vượt qua cooldown.
        Trả về True nếu được phép dịch, False nếu đang trong thời gian chờ.
        """
        key = (guild_id, target_id)
        now = time.time()
        last_time = self._last_translated.get(key, 0.0)

        if now - last_time < cooldown_seconds:
            return False

        if update:
            self._last_translated[key] = now
        return True

    def update_cooldown(self, guild_id: int, target_id: int) -> None:
        """Ghi nhận thời điểm vừa dịch thành công câu cho target."""
        self._last_translated[(guild_id, target_id)] = time.time()

    def reset_cooldown(self, guild_id: int, target_id: int) -> None:
        """Reset thời gian cooldown dịch gần nhất cho nạn nhân về 0."""
        self._last_translated.pop((guild_id, target_id), None)

    async def increment_translated_count(self, guild_id: int, target_id: int) -> None:
        """Tăng số lượng tin nhắn đã dịch cho phiên này."""
        session = self.get_session(guild_id, target_id)
        if session:
            session.translated_count += 1
            try:
                db = await self._get_db()
                await db.execute(
                    "UPDATE cabin_sessions SET translated_count = translated_count + 1 WHERE guild_id = ? AND target_id = ?",
                    (guild_id, target_id)
                )
                await db.commit()
            except Exception:
                pass

    def list_guild_sessions(self, guild_id: int) -> List[CabinSession]:
        """Lấy danh sách tất cả các phiên cabin đang hoạt động trong server."""
        now = time.time()
        valid = []
        expired_keys = []
        for key, s in list(self._sessions.items()):
            if key[0] == guild_id:
                if s.expires_at > now:
                    valid.append(s)
                else:
                    expired_keys.append(key)

        for ek in expired_keys:
            self._sessions.pop(ek, None)
            self._last_translated.pop(ek, None)

        return valid

    def has_active_cabin_in_guild(self, guild_id: int) -> bool:
        """Kiểm tra máy chủ hiện tại có ai đang bị cabin hay không (để tối ưu không cache thừa)."""
        now = time.time()
        return any(k[0] == guild_id and s.expires_at > now for k, s in self._sessions.items())

    def record_channel_message(self, guild_id: int, channel_id: int, author_name: str, content: str) -> None:
        """Lưu tạm tin nhắn vào RAM rolling cache nếu server đang có phiên cabin hoạt động."""
        if not self.has_active_cabin_in_guild(guild_id):
            return

        now = time.time()
        self._channel_last_activity[channel_id] = now
        if channel_id not in self._channel_cache:
            self._channel_cache[channel_id] = collections.deque(maxlen=35)

        # Cắt ngắn nếu tin nhắn quá dài (giữ tối đa 180 ký tự để tiết kiệm RAM và Token)
        truncated_content = content[:180].strip()
        if truncated_content:
            self._channel_cache[channel_id].append((now, author_name, truncated_content))

    async def get_channel_context(
        self,
        channel,
        window_minutes: int = 30,
        max_messages: int = 25
    ) -> List[Tuple[str, str]]:
        """
        Lấy danh sách (tác giả, nội dung) tin nhắn gần nhất từ RAM buffer siêu tốc (<0.1ms).
        Nếu RAM buffer chưa có đủ tin nhắn (cold start), mới gọi Discord API 1 lần duy nhất để nạp đầy cache.
        """
        channel_id = channel.id
        now = time.time()
        cutoff = now - (window_minutes * 60)

        cached_deque = self._channel_cache.get(channel_id)
        valid_cached = []
        if cached_deque:
            valid_cached = [(author, text) for (ts, author, text) in cached_deque if ts >= cutoff]

        # Nếu trong RAM đã có >= 5 tin nhắn hợp lệ -> Dùng ngay từ RAM (độ trễ 0ms!)
        if len(valid_cached) >= 5:
            return valid_cached[-max_messages:]

        # Nếu chưa đủ (ví dụ bot vừa khởi động lại hoặc mới bắt đầu cabin kênh này) -> Cold start backfill
        try:
            from datetime import datetime, timezone, timedelta
            time_cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
            fetched_messages = []

            async for hist_msg in channel.history(limit=35, after=time_cutoff_dt, oldest_first=False):
                if hist_msg.author.bot or not hist_msg.content:
                    continue
                clean_text = hist_msg.clean_content.strip()
                if clean_text.startswith((".m", ".M", "/", "!", "?", ";", "$", "~")):
                    continue
                fetched_messages.append((hist_msg.created_at.timestamp(), hist_msg.author.display_name, clean_text[:180]))

            # Đảo lại theo thứ tự thời gian tăng dần
            fetched_messages.reverse()

            # Nạp vào RAM cache
            if channel_id not in self._channel_cache:
                self._channel_cache[channel_id] = collections.deque(maxlen=35)

            for ts, author, text in fetched_messages:
                self._channel_cache[channel_id].append((ts, author, text))
            self._channel_last_activity[channel_id] = now

            return [(author, text) for (ts, author, text) in fetched_messages[-max_messages:]]
        except Exception as e:
            print(f"⚠️ [CabinManager] Lỗi backfill context từ channel.history: {e}", flush=True)
            return valid_cached[-max_messages:] if valid_cached else []

    def acquire_in_flight(self, guild_id: int, target_id: int) -> bool:
        """Khóa chống xử lý song song nhiều tin nhắn cùng lúc cho cùng 1 nạn nhân."""
        key = (guild_id, target_id)
        if key in self._in_flight:
            return False
        self._in_flight.add(key)
        return True

    def release_in_flight(self, guild_id: int, target_id: int) -> None:
        """Giải phóng khóa in-flight sau khi hoàn tất dịch."""
        self._in_flight.discard((guild_id, target_id))

    async def cleanup_expired(self) -> int:
        """Dọn dẹp các session và cache kênh đã quá hạn trong RAM và Database."""
        now = time.time()
        expired_keys = [k for k, s in self._sessions.items() if s.expires_at <= now]
        for k in expired_keys:
            self._sessions.pop(k, None)
            self._last_translated.pop(k, None)
            self._in_flight.discard(k)

        # Dọn dẹp cache của các channel không còn hoạt động trong 1 tiếng
        inactive_cutoff = now - 3600
        stale_channels = [cid for cid, last_t in self._channel_last_activity.items() if last_t < inactive_cutoff]
        for cid in stale_channels:
            self._channel_cache.pop(cid, None)
            self._channel_last_activity.pop(cid, None)

        try:
            db = await self._get_db()
            await db.execute("DELETE FROM cabin_sessions WHERE expires_at <= ?", (now,))
            await db.commit()
        except Exception:
            pass

        return len(expired_keys)


cabin_manager = CabinManager()
