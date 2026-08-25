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

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
        return self._db

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
        await db.commit()
        print("[TarotManager] Đã khởi tạo cơ sở dữ liệu Tarot thành công.", flush=True)

    async def close(self) -> None:
        """Đóng kết nối SQLite khi shutdown."""
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:
                pass
            self._db = None

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

    async def record_daily_draw(self, user_id: int, drawn_card: DrawnCard) -> None:
        """Lưu lại lượt bốc Daily Card hôm nay của user."""
        today_str = self.get_current_vn_date_str()
        card_dict = {
            "id": drawn_card.card.id,
            "name_vi": drawn_card.card.name_vi,
            "name_en": drawn_card.card.name_en,
            "is_reversed": drawn_card.is_reversed,
            "drawn_at": datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y")
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
        ai_reading: str
    ) -> None:
        """Lưu lịch sử bốc bài vào database."""
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
            INSERT INTO tarot_history (user_id, guild_id, channel_id, spread_type, question, cards_json, ai_reading)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, guild_id, channel_id, spread_type, question, cards_json, ai_reading))
        await db.commit()

    async def get_user_history(self, user_id: int, limit: int = 5) -> List[dict]:
        """Lấy lịch sử các lượt bốc bài gần nhất của user."""
        db = await self._get_db()
        async with db.execute("""
            SELECT id, spread_type, question, cards_json, ai_reading, created_at
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
                "created_at": r[5]
            })
        return results
