"""
core/presence_manager.py - Quản lý trạng thái và hoạt động động của Bot (Dynamic Presence & Status).

Hỗ trợ:
- Chuyển đổi trạng thái linh hoạt: Online (Xanh), Idle (Cam), DND (Đỏ), Invisible (Xám).
- Các loại hoạt động: Custom Status, Playing, Watching, Listening, Competing.
- Chế độ xoay tua tự động (Auto-Rotating Presence).
- Tự động thay đổi trạng thái theo vòng đời bot (Khởi động xong -> Live, Redeploy -> Idle, Maintenance -> DND).
- Điều khiển tức thì từ Web Dashboard và Discord Slash Command.
"""

import asyncio
import json
import threading
from typing import Dict, Any, Optional, List
import discord

from core.version import CURRENT_VERSION

# Các loại trạng thái hỗ trợ
STATUS_MAP = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible,
}

# Các loại hoạt động hỗ trợ
ACTIVITY_TYPE_MAP = {
    "custom": discord.ActivityType.custom,
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "competing": discord.ActivityType.competing,
}

DEFAULT_ROTATION_ITEMS = [
    f"Live v{CURRENT_VERSION} | $m help",
    "🔮 /tarot - Bốc bài Tarot AI chiêm tinh",
    "📝 /tomtat - Tóm tắt kênh chat thông minh",
    "👑 AutoEmbed 9 mạng xã hội siêu gọn",
]


class PresenceManager:
    """Quản lý trạng thái hiển thị của Discord Bot."""

    def __init__(self):
        self._status: str = "online"
        self._activity_type: str = "custom"
        self._activity_text: str = f"Live v{CURRENT_VERSION} | $m help"
        self._is_rotating: bool = True
        self._rotation_index: int = 0
        self._rotation_items: List[str] = list(DEFAULT_ROTATION_ITEMS)
        self._rotation_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        self._db_initialized: bool = False

    @property
    def current_status(self) -> str:
        return self._status

    @property
    def current_activity_type(self) -> str:
        return self._activity_type

    @property
    def current_activity_text(self) -> str:
        return self._activity_text

    @property
    def is_rotating(self) -> bool:
        return self._is_rotating

    def get_info(self) -> Dict[str, Any]:
        """Trả về toàn bộ thông tin cấu hình trạng thái hiện tại."""
        with self._lock:
            return {
                "status": self._status,
                "activity_type": self._activity_type,
                "activity_text": self._activity_text,
                "is_rotating": self._is_rotating,
                "rotation_items": list(self._rotation_items),
                "version": CURRENT_VERSION,
            }

    async def init_db(self, bot: discord.Client) -> None:
        """Tải cấu hình presence đã lưu từ Database (nếu có)."""
        from core.db import db_client
        try:
            await db_client.execute("""
                CREATE TABLE IF NOT EXISTS bot_presence_config (
                    id             INTEGER PRIMARY KEY DEFAULT 1,
                    status         TEXT NOT NULL DEFAULT 'online',
                    activity_type  TEXT NOT NULL DEFAULT 'custom',
                    activity_text  TEXT NOT NULL,
                    is_rotating    INTEGER NOT NULL DEFAULT 1,
                    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            await db_client.commit()

            async with db_client.execute("SELECT status, activity_type, activity_text, is_rotating FROM bot_presence_config WHERE id = 1") as cursor:
                row = await cursor.fetchone()
                if row:
                    with self._lock:
                        self._status = row[0] or "online"
                        self._activity_type = row[1] or "custom"
                        self._activity_text = row[2] or f"Live v{CURRENT_VERSION} | $m help"
                        self._is_rotating = bool(row[3])
        except Exception as e:
            print(f"⚠️ [PresenceManager] Lỗi nạp cấu hình Presence: {e}", flush=True)

        self._db_initialized = True
        await self.apply_presence(
            bot=bot,
            status=self._status,
            activity_type=self._activity_type,
            text=self._activity_text,
            is_rotating=self._is_rotating,
            save_db=False
        )

    def _build_activity(self, activity_type: str, text: str) -> Optional[discord.BaseActivity]:
        """Tạo đối tượng discord Activity phù hợp."""
        if not text:
            return None

        act_type_lower = activity_type.lower()
        if act_type_lower == "custom":
            return discord.CustomActivity(name="Custom Status", state=text)
        elif act_type_lower == "playing":
            return discord.Game(name=text)
        elif act_type_lower == "watching":
            return discord.Activity(type=discord.ActivityType.watching, name=text)
        elif act_type_lower == "listening":
            return discord.Activity(type=discord.ActivityType.listening, name=text)
        elif act_type_lower == "competing":
            return discord.Activity(type=discord.ActivityType.competing, name=text)
        else:
            return discord.CustomActivity(name="Custom Status", state=text)

    async def apply_presence(
        self,
        bot: discord.Client,
        status: str = "online",
        activity_type: str = "custom",
        text: str = "",
        is_rotating: bool = False,
        save_db: bool = True
    ) -> bool:
        """Áp dụng trạng thái mới lên Discord Bot và lưu cấu hình."""
        status_clean = status.lower()
        
        with self._lock:
            self._status = status_clean
            self._activity_type = activity_type.lower()
            self._activity_text = text or f"Live v{CURRENT_VERSION} | $m help"
            self._is_rotating = is_rotating

        # Dừng vòng lặp xoay tua cũ nếu đang chạy
        if self._rotation_task and not self._rotation_task.done():
            self._rotation_task.cancel()
            self._rotation_task = None

        if save_db:
            asyncio.create_task(self._save_to_db())

        if not bot.is_ready():
            # Nếu bot chưa kết nối xong, tự động đợi kết nối rồi áp dụng
            asyncio.create_task(self._wait_and_apply(bot))
            return True

        return await self._do_change_presence(bot)

    async def _wait_and_apply(self, bot: discord.Client):
        """Đợi bot kết nối Discord Gateway hoàn tất rồi mới áp dụng trạng thái."""
        try:
            await bot.wait_until_ready()
            await asyncio.sleep(1.0)
            await self._do_change_presence(bot)
        except Exception as e:
            print(f"⚠️ [PresenceManager] Lỗi khi chờ bot ready để áp dụng presence: {e}", flush=True)

    async def _do_change_presence(self, bot: discord.Client) -> bool:
        """Thực hiện cập nhật presence trực tiếp lên Discord Gateway."""
        if not bot.is_ready():
            return False

        discord_status = STATUS_MAP.get(self._status, discord.Status.online)
        try:
            if self._is_rotating:
                if self._rotation_task and not self._rotation_task.done():
                    self._rotation_task.cancel()
                self._rotation_task = asyncio.create_task(self._rotation_loop(bot))
                print(f"✨ [PresenceManager] Đã kích hoạt xoay tua trạng thái [{self._status.upper()}].", flush=True)
            else:
                act = self._build_activity(self._activity_type, self._activity_text)
                await bot.change_presence(status=discord_status, activity=act)
                print(f"✨ [PresenceManager] Đã cập nhật trạng thái: [{self._status.upper()}] ({self._activity_type}) - {self._activity_text}", flush=True)
            return True
        except Exception as e:
            print(f"❌ [PresenceManager] Lỗi khi đổi trạng thái bot: {e}", flush=True)
            return False

    async def _rotation_loop(self, bot: discord.Client):
        """Vòng lặp tự động thay đổi trạng thái định kỳ mỗi 45 giây."""
        while True:
            try:
                if not self._is_rotating:
                    break

                text = self._rotation_items[self._rotation_index % len(self._rotation_items)]
                self._rotation_index += 1

                discord_status = STATUS_MAP.get(self._status, discord.Status.online)
                act = self._build_activity(self._activity_type, text)
                if bot.is_ready():
                    await bot.change_presence(status=discord_status, activity=act)

                await asyncio.sleep(45.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ [PresenceManager] Lỗi trong vòng lặp rotation: {e}", flush=True)
                await asyncio.sleep(15.0)

    async def set_redeploying(self, bot: discord.Client):
        """Đặt trạng thái bot đang redeploy / cập nhật phiên bản."""
        if self._rotation_task and not self._rotation_task.done():
            self._rotation_task.cancel()
            self._rotation_task = None

        if bot.is_ready():
            try:
                act = discord.CustomActivity(name="Custom Status", state="Đang redeploy / cập nhật phiên bản mới...")
                await bot.change_presence(status=discord.Status.idle, activity=act)
                print("🔄 [PresenceManager] Đã chuyển trạng thái sang REDEPLOYING (Idle).", flush=True)
            except Exception:
                pass

    async def set_maintenance(self, bot: discord.Client, reason: str = "Đang bảo trì / fix bug đợi sửa..."):
        """Đặt trạng thái bot đang bảo trì sang DND để người dùng vẫn xem được lý do."""
        await self.apply_presence(
            bot=bot,
            status="dnd",
            activity_type="custom",
            text=reason,
            is_rotating=False,
            save_db=True
        )

    async def set_error(self, bot: discord.Client, reason: str = "Đang gặp lỗi kỹ thuật / fix bug đợi xíu..."):
        """Đặt trạng thái bot khi gặp lỗi sang DND (tuyệt đối không để offline)."""
        await self.apply_presence(
            bot=bot,
            status="dnd",
            activity_type="custom",
            text=reason,
            is_rotating=False,
            save_db=True
        )

    async def set_live(self, bot: discord.Client):
        """Khôi phục trạng thái bot hoạt động bình thường (Live)."""
        await self.apply_presence(
            bot=bot,
            status="online",
            activity_type="custom",
            text=f"Live v{CURRENT_VERSION} | $m help",
            is_rotating=True,
            save_db=True
        )

    async def _save_to_db(self):
        """Lưu cấu hình presence vào Database."""
        from core.db import db_client
        try:
            await db_client.execute("""
                INSERT INTO bot_presence_config (id, status, activity_type, activity_text, is_rotating, updated_at)
                VALUES (1, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    activity_type = excluded.activity_type,
                    activity_text = excluded.activity_text,
                    is_rotating = excluded.is_rotating,
                    updated_at = datetime('now')
            """, (self._status, self._activity_type, self._activity_text, 1 if self._is_rotating else 0))
            await db_client.commit()
        except Exception:
            pass


# Singleton instance
presence_manager = PresenceManager()
