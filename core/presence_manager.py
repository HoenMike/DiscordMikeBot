"""
core/presence_manager.py - Quản lý trạng thái và hoạt động động của Bot (Dynamic Presence & Status).

Hỗ trợ:
- Trạng thái rõ ràng: Online (Xanh), Idle (Cam / Đang cập nhật), DND (Đỏ / Lỗi / Stuck).
- Hiển thị chuẩn hóa: "Live v{CURRENT_VERSION} | .m help" (loại bỏ xoay tua các lệnh / không cần thiết).
- Chuyển đổi trạng thái tự động theo vòng đời:
    + Khởi động xong: Live (Xanh 🟢)
    + Trước khi tắt / Redeploy / Update: Updating (Cam 🟡)
    + Khi bị kẹt / lag Gateway / lỗi kết nối: Error (Đỏ 🔴) kèm watchdog tự phục hồi khi ổn định.
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

DEFAULT_PRESENCE_TEXT = f"Live v{CURRENT_VERSION} | .m help"


class PresenceManager:
    """Quản lý trạng thái hiển thị của Discord Bot."""

    def __init__(self):
        self._status: str = "online"
        self._activity_type: str = "custom"
        self._activity_text: str = DEFAULT_PRESENCE_TEXT
        self._is_rotating: bool = False
        self._rotation_index: int = 0
        self._rotation_items: List[str] = [DEFAULT_PRESENCE_TEXT]
        self._rotation_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._is_updating: bool = False
        self._is_auto_error: bool = False
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
                "is_updating": self._is_updating,
                "version": CURRENT_VERSION,
            }

    async def init_db(self, bot: discord.Client) -> None:
        """Tải cấu hình presence đã lưu từ Database (nếu có) và chuẩn hóa dữ liệu."""
        from core.db import db_client
        try:
            await db_client.execute("""
                CREATE TABLE IF NOT EXISTS bot_presence_config (
                    id             INTEGER PRIMARY KEY DEFAULT 1,
                    status         TEXT NOT NULL DEFAULT 'online',
                    activity_type  TEXT NOT NULL DEFAULT 'custom',
                    activity_text  TEXT NOT NULL,
                    is_rotating    INTEGER NOT NULL DEFAULT 0,
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
                        saved_text = row[2] or ""

                        # Nếu trong DB là các text xoay tua cũ (chứa slash command /tarot, /tomtat) hoặc phiên bản cũ
                        if not saved_text or any(cmd in saved_text for cmd in ["/tarot", "/tomtat", "AutoEmbed"]) or saved_text.startswith("Live v"):
                            self._activity_text = DEFAULT_PRESENCE_TEXT
                            self._is_rotating = False
                        else:
                            self._activity_text = saved_text
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
            save_db=True
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
            self._activity_text = text or DEFAULT_PRESENCE_TEXT
            self._is_rotating = is_rotating

        # Dừng vòng lặp xoay tua cũ nếu đang chạy
        if self._rotation_task and not self._rotation_task.done():
            self._rotation_task.cancel()
            self._rotation_task = None

        if save_db:
            asyncio.create_task(self._save_to_db())

        if not bot.is_ready():
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
                print(f"✨ [PresenceManager] Trạng thái Discord: [{self._status.upper()}] {self._activity_text}", flush=True)
            return True
        except Exception as e:
            print(f"❌ [PresenceManager] Lỗi khi đổi trạng thái bot: {e}", flush=True)
            return False

    async def _rotation_loop(self, bot: discord.Client):
        """Vòng lặp xoay tua trạng thái nếu được bật (mỗi 45 giây)."""
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

    async def set_updating(self, bot: discord.Client, reason: str = ""):
        """Đặt trạng thái bot sang Đang Cập Nhật / Redeploy trước khi tắt máy (Idle - Vàng/Cam 🟡)."""
        self._is_updating = True
        if self._rotation_task and not self._rotation_task.done():
            self._rotation_task.cancel()
            self._rotation_task = None

        text = reason or f"Đang cập nhật... | v{CURRENT_VERSION}"
        with self._lock:
            self._status = "idle"
            self._activity_type = "custom"
            self._activity_text = text
            self._is_rotating = False

        if bot.is_ready():
            try:
                act = discord.CustomActivity(name="Custom Status", state=text)
                await bot.change_presence(status=discord.Status.idle, activity=act)
                print(f"🔄 [PresenceManager] Đã chuyển trạng thái sang UPDATING (Idle 🟡): {text}", flush=True)
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"⚠️ [PresenceManager] Lỗi khi chuyển trạng thái updating: {e}", flush=True)

    async def set_redeploying(self, bot: discord.Client):
        """Alias cho set_updating phục vụ graceful shutdown."""
        await self.set_updating(bot)

    async def set_maintenance(self, bot: discord.Client, reason: str = "Đang bảo trì / fix bug..."):
        """Đặt trạng thái bot đang bảo trì sang DND (Đỏ 🔴)."""
        await self.apply_presence(
            bot=bot,
            status="dnd",
            activity_type="custom",
            text=reason,
            is_rotating=False,
            save_db=True
        )

    async def set_error(self, bot: discord.Client, reason: str = "Đang gặp sự cố kỹ thuật...", auto_recover: bool = False):
        """Đặt trạng thái bot khi gặp lỗi hoặc bị kẹt/treo sang DND (Đỏ 🔴) để Admin thấy."""
        self._is_auto_error = auto_recover
        with self._lock:
            self._status = "dnd"
            self._activity_type = "custom"
            self._activity_text = reason
            self._is_rotating = False

        if bot.is_ready():
            try:
                act = discord.CustomActivity(name="Custom Status", state=reason)
                await bot.change_presence(status=discord.Status.dnd, activity=act)
                print(f"🛑 [PresenceManager] Đã chuyển trạng thái sang ERROR (DND - Đỏ 🔴): {reason}", flush=True)
            except Exception as e:
                print(f"⚠️ [PresenceManager] Lỗi khi đổi trạng thái error: {e}", flush=True)

        if not auto_recover:
            asyncio.create_task(self._save_to_db())

    async def set_live(self, bot: discord.Client):
        """Khôi phục trạng thái bot hoạt động bình thường (Online - Xanh 🟢)."""
        self._is_updating = False
        self._is_auto_error = False
        await self.apply_presence(
            bot=bot,
            status="online",
            activity_type="custom",
            text=DEFAULT_PRESENCE_TEXT,
            is_rotating=False,
            save_db=True
        )

    async def start_watchdog(self, bot: discord.Client) -> None:
        """Kích hoạt tác vụ giám sát sức khỏe kết nối (Watchdog) để tự động phát hiện stuck/lỗi."""
        if self._watchdog_task and not self._watchdog_task.done():
            return
        self._watchdog_task = asyncio.create_task(self._watchdog_loop(bot))
        print("🛡️ [PresenceManager] Đã kích hoạt Watchdog giám sát sức khỏe kết nối.", flush=True)

    async def _watchdog_loop(self, bot: discord.Client):
        """Vòng lặp định kỳ (mỗi 20 giây) kiểm tra latency và kết nối Gateway để tự động chuyển đỏ nếu stuck."""
        consecutive_lag_count = 0
        while True:
            try:
                await asyncio.sleep(20.0)

                # Bỏ qua nếu đang trong quá trình update/shutdown có chủ đích
                if self._is_updating:
                    continue

                if not bot.is_ready():
                    consecutive_lag_count += 1
                    if consecutive_lag_count >= 2 and self._status != "dnd":
                        print("⚠️ [Watchdog] Bot mất kết nối Gateway! Chuyển trạng thái sang DND (Đỏ 🔴).", flush=True)
                        await self.set_error(bot, f"Mất kết nối Discord | v{CURRENT_VERSION}", auto_recover=True)
                    continue

                # Kiểm tra độ trễ Gateway WebSocket
                latency = bot.latency
                import math
                if math.isnan(latency) or math.isinf(latency) or latency > 5.0:
                    consecutive_lag_count += 1
                    if consecutive_lag_count >= 2 and self._status != "dnd":
                        print(f"⚠️ [Watchdog] Gateway lag/stuck ({latency:.1f}s)! Chuyển sang DND (Đỏ 🔴).", flush=True)
                        await self.set_error(bot, f"Lag Gateway ({latency:.1f}s) | .m help", auto_recover=True)
                else:
                    # Kết nối hoàn toàn bình thường
                    if consecutive_lag_count > 0:
                        consecutive_lag_count = 0
                        # Nếu trước đó bị watchdog đánh dấu lỗi tự động, tự động phục hồi về Live (Xanh)
                        if self._is_auto_error and self._status == "dnd":
                            print("✨ [Watchdog] Kết nối đã ổn định trở lại! Tự động khôi phục Live (Xanh 🟢).", flush=True)
                            await self.set_live(bot)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ [Watchdog] Lỗi vòng lặp giám sát: {e}", flush=True)
                await asyncio.sleep(10.0)

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
