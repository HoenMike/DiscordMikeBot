import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
import aiosqlite
import config
from features.tarot.deck import DrawnCard

VN_TZ = timezone(timedelta(hours=7))

class TarotManager:
    """Quản lý lưu trữ SQLite cho lịch sử bốc bài và Daily Cooldown."""

    def __init__(self):
        self.db_path = str(config.DB_PATH)
        self._db: Optional[aiosqlite.Connection] = None
        self._user_last_action: dict[int, float] = {}

    def check_user_cooldown(self, user_id: int, cooldown_seconds: float = 30.0) -> Tuple[bool, float]:
        """
        Kiểm tra cooldown 30s giữa 2 lần bốc bài / gọi lệnh của 1 user.
        Trả về (can_proceed, remaining_seconds).
        """
        import time
        now = time.time()
        last_time = self._user_last_action.get(user_id, 0.0)
        elapsed = now - last_time
        if elapsed < cooldown_seconds:
            return False, cooldown_seconds - elapsed
        return True, 0.0

    def record_user_action(self, user_id: int) -> None:
        """Ghi nhận mốc thời gian vừa thực hiện hành động của user."""
        import time
        self._user_last_action[user_id] = time.time()

    async def _get_db(self):
        from core.db import db_client
        return db_client

    async def init_db(self) -> None:
        """Tạo các bảng lịch sử Tarot nếu chưa có."""
        db = await self._get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tarot_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                guild_id     INTEGER,
                channel_id   INTEGER,
                spread_type  TEXT NOT NULL,
                question     TEXT,
                cards_json   TEXT NOT NULL,
                ai_reading   TEXT,
                topic_tag    TEXT NOT NULL DEFAULT 'general',
                mood_tag     TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tarot_daily_tracker (
                user_id         INTEGER PRIMARY KEY,
                last_daily_date TEXT NOT NULL,
                last_drawn_json TEXT NOT NULL,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tarot_user_preferences (
                user_id         INTEGER PRIMARY KEY,
                memory_enabled  INTEGER NOT NULL DEFAULT 1,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tarot_ratings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                guild_id     INTEGER,
                spread_type  TEXT NOT NULL,
                reader_style TEXT,
                is_positive  INTEGER NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tarot_weekly_guild_config (
                guild_id       INTEGER PRIMARY KEY,
                channel_id     INTEGER NOT NULL,
                last_sent_week TEXT NOT NULL DEFAULT '',
                updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Tự động cập nhật thêm cột topic_tag và mood_tag nếu bảng tarot_history đã tồn tại từ trước
        try:
            await db.execute("ALTER TABLE tarot_history ADD COLUMN topic_tag TEXT NOT NULL DEFAULT 'general'")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE tarot_history ADD COLUMN mood_tag TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass

        # Tự động dọn dẹp các quẻ bài quá cũ (> 90 ngày) để tối ưu hóa lưu trữ DB
        try:
            await db.execute("DELETE FROM tarot_history WHERE created_at < datetime('now', '-90 days')")
        except Exception:
            pass

        await db.commit()
        print("[TarotManager] Đã khởi tạo cơ sở dữ liệu Tarot thành công.", flush=True)

    async def close(self) -> None:
        """Đóng kết nối SQLite khi shutdown."""
        from core.db import db_client
        await db_client.close()

    @staticmethod
    def get_current_vn_date_str() -> str:
        """Lấy ngày hiện tại theo giờ Việt Nam dạng YYYY-MM-DD."""
        return datetime.now(VN_TZ).strftime("%Y-%m-%d")

    async def check_daily_cooldown(self, user_id: int) -> Tuple[bool, Optional[dict]]:
        """
        Kiểm tra xem user đã bốc Daily Card trong ngày hôm nay chưa (theo múi giờ GMT+7).
        Trả về (can_draw, last_draw_data)
        """
        today_str = self.get_current_vn_date_str()
        db = await self._get_db()
        async with db.execute(
            "SELECT last_daily_date, last_drawn_json FROM tarot_daily_tracker WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return True, None

        last_date, last_json = row
        if last_date == today_str:
            try:
                card_data = json.loads(last_json)
            except Exception:
                card_data = None
            return False, card_data

        return True, None

    async def get_active_daily_cooldowns(self) -> List[dict]:
        """Lấy danh sách tất cả người dùng đang có daily cooldown trong ngày hôm nay."""
        today_str = self.get_current_vn_date_str()
        db = await self._get_db()
        async with db.execute(
            "SELECT user_id, last_daily_date, last_drawn_json, updated_at FROM tarot_daily_tracker WHERE last_daily_date = ? ORDER BY updated_at DESC",
            (today_str,)
        ) as cursor:
            rows = await cursor.fetchall()

        results = []
        for r in rows:
            try:
                card_data = json.loads(r[2])
            except Exception:
                card_data = {}
            results.append({
                "user_id": r[0],
                "last_daily_date": r[1],
                "card_data": card_data,
                "updated_at": r[3]
            })
        return results

    async def reset_daily_cooldown(self, user_id: int) -> bool:
        """Gỡ bỏ Daily Cooldown cho 1 user cụ thể."""
        db = await self._get_db()
        await db.execute("DELETE FROM tarot_daily_tracker WHERE user_id = ?", (user_id,))
        await db.commit()
        self._user_last_action.pop(user_id, None)
        return True

    async def reset_all_daily_cooldowns(self) -> bool:
        """Gỡ bỏ toàn bộ Daily Cooldown cho tất cả người dùng hôm nay."""
        today_str = self.get_current_vn_date_str()
        db = await self._get_db()
        await db.execute("DELETE FROM tarot_daily_tracker WHERE last_daily_date = ?", (today_str,))
        await db.commit()
        self._user_last_action.clear()
        return True

    async def record_daily_draw(self, user_id: int, drawn_card: DrawnCard, user_name: str = "", user_avatar: str = "") -> None:
        """Lưu lại lượt bốc Daily Card hôm nay của user kèm tên và avatar."""
        today_str = self.get_current_vn_date_str()
        card_dict = {
            "id": drawn_card.card.id,
            "name_vi": drawn_card.card.name_vi,
            "name_en": drawn_card.card.name_en,
            "is_reversed": drawn_card.is_reversed,
            "drawn_at": datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y"),
            "user_name": user_name,
            "user_avatar": user_avatar
        }
        card_json = json.dumps(card_dict, ensure_ascii=False)

        db = await self._get_db()
        await db.execute("""
            INSERT INTO tarot_daily_tracker (user_id, last_daily_date, last_drawn_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                last_daily_date = excluded.last_daily_date,
                last_drawn_json = excluded.last_drawn_json,
                updated_at = excluded.updated_at
        """, (user_id, today_str, card_json))
        await db.commit()

    async def save_tarot_history(
        self,
        user_id: int,
        guild_id: Optional[int],
        channel_id: Optional[int],
        spread_type: str,
        question: Optional[str],
        drawn_cards: List[DrawnCard],
        ai_reading: str,
        topic_tag: str = "general",
        mood_tag: str = ""
    ) -> None:
        """Lưu lịch sử bốc bài vào database kèm topic_tag và mood_tag."""
        cards_list = [
            {
                "position_index": c.position_index,
                "position_title": c.position_title,
                "id": c.card.id,
                "name_vi": c.card.name_vi,
                "name_en": c.card.name_en,
                "is_reversed": c.is_reversed
            }
            for c in drawn_cards
        ]
        cards_json = json.dumps(cards_list, ensure_ascii=False)

        db = await self._get_db()
        await db.execute("""
            INSERT INTO tarot_history (user_id, guild_id, channel_id, spread_type, question, cards_json, ai_reading, topic_tag, mood_tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, guild_id, channel_id, spread_type, question, cards_json, ai_reading, topic_tag or "general", mood_tag or ""))
        await db.commit()

    async def get_user_history(self, user_id: int, limit: int = 5) -> List[dict]:
        """Lấy lịch sử các lượt bốc bài gần nhất của user."""
        db = await self._get_db()
        async with db.execute("""
            SELECT id, spread_type, question, cards_json, ai_reading, topic_tag, mood_tag, created_at
            FROM tarot_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit)) as cursor:
            rows = await cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "spread_type": r[1],
                "question": r[2],
                "cards": json.loads(r[3]),
                "ai_reading": r[4],
                "topic_tag": r[5] if len(r) > 5 else "general",
                "mood_tag": r[6] if len(r) > 6 else "",
                "created_at": r[7] if len(r) > 7 else (r[6] if len(r) > 6 else "")
            })
        return results

    async def get_user_recent_context(self, user_id: int) -> Optional[dict]:
        """
        Lấy ngữ cảnh lần đọc trước gần nhất trong vòng 10 ngày (trừ khi user đã tắt memory).
        Trả về dict: {"topic_tag": ..., "mood_tag": ..., "last_card_name": ..., "days_ago": ...} hoặc None.
        """
        if not await self.is_user_memory_enabled(user_id):
            return None

        db = await self._get_db()
        async with db.execute("""
            SELECT topic_tag, mood_tag, cards_json, created_at
            FROM tarot_history
            WHERE user_id = ? AND created_at >= datetime('now', '-10 days')
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        topic_tag, mood_tag, cards_json, created_at = row
        try:
            cards = json.loads(cards_json)
            lead_card = cards[0]["name_vi"] if cards else "Ẩn danh"
            orient = "Ngược" if cards and cards[0].get("is_reversed") else "Xuôi"
            lead_card_full = f"{lead_card} ({orient})"
        except Exception:
            lead_card_full = "Một lá bài"

        # Tính khoảng thời gian
        days_str = "vài ngày trước"
        return {
            "topic_tag": topic_tag or "general",
            "mood_tag": mood_tag or "",
            "last_card_name": lead_card_full,
            "approx_time": days_str
        }

    async def get_user_recent_card_ids(self, user_id: int, limit: int = 5) -> List[str]:
        """Lấy tối đa 5 lá bài gần nhất user vừa bốc để áp dụng Card Fatigue."""
        db = await self._get_db()
        async with db.execute("""
            SELECT cards_json FROM tarot_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 3
        """, (user_id,)) as cursor:
            rows = await cursor.fetchall()

        recent_ids = []
        for r in rows:
            try:
                cards = json.loads(r[0])
                for c in cards:
                    cid = c.get("id")
                    if cid and cid not in recent_ids:
                        recent_ids.append(cid)
            except Exception:
                pass
        return recent_ids[:limit]

    async def is_user_memory_enabled(self, user_id: int) -> bool:
        """Kiểm tra xem user có cho phép bot nhớ ngữ cảnh không."""
        db = await self._get_db()
        async with db.execute("SELECT memory_enabled FROM tarot_user_preferences WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if row is not None:
            return bool(row[0])
        return True

    async def set_user_memory_preference(self, user_id: int, enabled: bool) -> None:
        """Bật/tắt tùy chọn nhớ ngữ cảnh cho user."""
        db = await self._get_db()
        await db.execute("""
            INSERT INTO tarot_user_preferences (user_id, memory_enabled, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                memory_enabled = excluded.memory_enabled,
                updated_at = excluded.updated_at
        """, (user_id, 1 if enabled else 0))
        await db.commit()

    async def clear_user_history(self, user_id: int) -> None:
        """Xóa toàn bộ lịch sử bốc bài và daily cooldown của user."""
        db = await self._get_db()
        await db.execute("DELETE FROM tarot_history WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM tarot_daily_tracker WHERE user_id = ?", (user_id,))
        await db.commit()

    async def save_rating(self, user_id: int, guild_id: Optional[int], spread_type: str, reader_style: str, is_positive: bool) -> None:
        """Lưu đánh giá 👍/👎 của user cho bài giải."""
        db = await self._get_db()
        await db.execute("""
            INSERT INTO tarot_ratings (user_id, guild_id, spread_type, reader_style, is_positive, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (user_id, guild_id, spread_type, reader_style, 1 if is_positive else 0))
        await db.commit()

    async def get_weekly_guild_configs(self) -> List[dict]:
        """Lấy danh sách các server đã đăng ký nhận lá bài tuần."""
        db = await self._get_db()
        async with db.execute("SELECT guild_id, channel_id, last_sent_week FROM tarot_weekly_guild_config") as cursor:
            rows = await cursor.fetchall()
        return [{"guild_id": r[0], "channel_id": r[1], "last_sent_week": r[2]} for r in rows]

    async def set_weekly_guild_channel(self, guild_id: int, channel_id: int) -> None:
        """Đăng ký kênh nhận lá bài tuần cho server."""
        db = await self._get_db()
        await db.execute("""
            INSERT INTO tarot_weekly_guild_config (guild_id, channel_id, last_sent_week, updated_at)
            VALUES (?, ?, '', datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                updated_at = excluded.updated_at
        """, (guild_id, channel_id))
        await db.commit()

    async def update_weekly_guild_sent(self, guild_id: int, week_str: str) -> None:
        """Ghi nhận đã gửi bài tuần cho server."""
        db = await self._get_db()
        await db.execute("UPDATE tarot_weekly_guild_config SET last_sent_week = ?, updated_at = datetime('now') WHERE guild_id = ?", (week_str, guild_id))
        await db.commit()

    async def get_rating_stats(self) -> dict:
        """Lấy thống kê đánh giá tổng thể và phân loại theo Reader Style & Spread Type."""
        db = await self._get_db()
        async with db.execute("SELECT is_positive, reader_style, spread_type FROM tarot_ratings") as cursor:
            rows = await cursor.fetchall()

        total = len(rows)
        likes = sum(1 for r in rows if r[0] == 1)
        dislikes = total - likes
        rate = round((likes / total * 100), 1) if total > 0 else 100.0

        # Phân tích theo style
        by_style = {}
        for r in rows:
            st = r[1] or "neutral"
            if st not in by_style:
                by_style[st] = {"style": st, "total": 0, "likes": 0, "dislikes": 0}
            by_style[st]["total"] += 1
            if r[0] == 1:
                by_style[st]["likes"] += 1
            else:
                by_style[st]["dislikes"] += 1

        for st, data in by_style.items():
            data["rate"] = round((data["likes"] / data["total"] * 100), 1) if data["total"] > 0 else 100.0

        # Phân tích theo spread
        by_spread = {}
        for r in rows:
            sp = r[2] or "daily"
            if sp not in by_spread:
                by_spread[sp] = {"spread": sp, "total": 0, "likes": 0, "dislikes": 0}
            by_spread[sp]["total"] += 1
            if r[0] == 1:
                by_spread[sp]["likes"] += 1
            else:
                by_spread[sp]["dislikes"] += 1

        for sp, data in by_spread.items():
            data["rate"] = round((data["likes"] / data["total"] * 100), 1) if data["total"] > 0 else 100.0

        return {
            "total": total,
            "likes": likes,
            "dislikes": dislikes,
            "satisfaction_rate": rate,
            "by_style": list(by_style.values()),
            "by_spread": list(by_spread.values())
        }

    async def get_all_ratings_detailed(self) -> List[dict]:
        """Lấy toàn bộ danh sách đánh giá chi tiết để xuất Dataset (JSON/CSV)."""
        db = await self._get_db()
        async with db.execute("""
            SELECT id, user_id, guild_id, spread_type, reader_style, is_positive, created_at
            FROM tarot_ratings
            ORDER BY id DESC
        """) as cursor:
            rows = await cursor.fetchall()

        results = []
        for r in rows:
            rating_id, u_id, g_id, sp_type, r_style, is_pos, c_at = r
            results.append({
                "rating_id": rating_id,
                "user_id": u_id,
                "guild_id": g_id,
                "spread_type": sp_type,
                "reader_style": r_style,
                "rating": "LIKE" if is_pos == 1 else "DISLIKE",
                "is_positive": bool(is_pos),
                "created_at": c_at
            })
        return results

