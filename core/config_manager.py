import json
import time
import asyncio
import aiosqlite
import config as app_config

try:
    from features.embed.constants import DEFAULT_CONFIG, PROXY_DOMAINS
except ImportError:
    DEFAULT_CONFIG = {
        "platforms_enabled": {},
        "nsfw_mode": "spoiler",
        "auto_embed_enabled": True,
        "suppress_original_embed": True,
    }
    PROXY_DOMAINS = {}


class ConfigManager:
    """Quản lý cấu hình guild/channel với cache trong bộ nhớ và SQLite.

    Sử dụng kết nối persistent để tối ưu hiệu năng truy vấn.
    Cache được phân tầng: effective config, guild raw, channel raw, proxy domains.
    """

    CACHE_TTL = 300

    def __init__(self):
        # Cache effective config (guild_id:channel_id -> (config dict, timestamp))
        self._cache: dict[str, tuple[dict, float]] = {}
        # Cache guild config raw (guild:{guild_id} -> (config dict, timestamp))
        self._guild_cache: dict[str, tuple[dict, float]] = {}
        # Cache channel config raw (channel:{channel_id} -> (config dict, timestamp))
        self._channel_cache: dict[str, tuple[dict, float]] = {}
        # Cache proxy domains (proxy:{guild_id}:{platform_key} -> (list hoặc None, timestamp))
        self._proxy_cache: dict[str, tuple[list | None, float]] = {}
        # Set guild bị tạm ngưng (suspended) để tra cứu O(1) tức thì
        self._suspended_guilds: set[int] = set()
        self._db_path = str(app_config.DB_PATH)
        self._db: aiosqlite.Connection | None = None

    async def _get_db(self) -> aiosqlite.Connection:
        """Lấy kết nối persistent, tạo mới nếu chưa có hoặc khi chuyển đổi event loop."""
        current_loop = asyncio.get_running_loop()
        if self._db is None or getattr(self._db, '_loop', None) != current_loop:
            self._db = await aiosqlite.connect(self._db_path)
            # Tối ưu hiệu năng SQLite cho workload đọc nhiều
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
        return self._db

    async def init_db(self) -> None:
        """Khởi tạo các bảng cấu hình, proxy domains và danh sách server tạm ngưng."""
        db = await self._get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id     INTEGER PRIMARY KEY,
                config_json  TEXT NOT NULL DEFAULT '{}',
                updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_config (
                channel_id   INTEGER PRIMARY KEY,
                guild_id     INTEGER NOT NULL,
                config_json  TEXT NOT NULL DEFAULT '{}',
                updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_proxy_domains (
                guild_id      INTEGER NOT NULL,
                platform_key  TEXT NOT NULL,
                domains_json  TEXT NOT NULL,
                updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, platform_key)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suspended_guilds (
                guild_id      INTEGER PRIMARY KEY,
                guild_name    TEXT,
                reason        TEXT,
                suspended_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()

        # Nạp danh sách suspended guilds vào RAM
        async with db.execute("SELECT guild_id FROM suspended_guilds") as cursor:
            rows = await cursor.fetchall()
            self._suspended_guilds = {row[0] for row in rows}

    async def close(self) -> None:
        """Đóng kết nối database nếu đang mở."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _is_valid(self, cache_entry: tuple | None) -> bool:
        """Kiểm tra xem mục cache còn hạn không."""
        if cache_entry is None:
            return False
        _, timestamp = cache_entry
        return (time.monotonic() - timestamp) < self.CACHE_TTL

    # ---------------------------------------------------------------------------
    # Truy vấn cấu hình áp dụng thực tế (Effective Config)
    # ---------------------------------------------------------------------------

    async def get_effective_config(
        self,
        guild_id: int | None,
        channel_id: int | None,
    ) -> dict:
        """Lấy cấu hình hiệu lực kết hợp: channel override > guild config > default.

        Kết quả được cache 300 giây.
        """
        if guild_id is None:
            return DEFAULT_CONFIG.copy()

        cache_key = f"{guild_id}:{channel_id}"
        entry = self._cache.get(cache_key)
        if self._is_valid(entry):
            return entry[0]

        guild_cfg = await self.get_guild_config(guild_id)
        channel_cfg = (
            await self.get_channel_config(channel_id)
            if channel_id
            else {}
        )

        effective = DEFAULT_CONFIG.copy()
        effective["platforms_enabled"] = DEFAULT_CONFIG.get("platforms_enabled", {}).copy()

        # Áp dụng guild config
        for k, v in guild_cfg.items():
            if k == "platforms_enabled" and isinstance(v, dict):
                effective["platforms_enabled"].update(v)
            else:
                effective[k] = v

        # Áp dụng channel override (ghi đè guild config)
        for k, v in channel_cfg.items():
            if k == "platforms_enabled" and isinstance(v, dict):
                effective["platforms_enabled"].update(v)
            else:
                effective[k] = v

        self._cache[cache_key] = (effective, time.monotonic())
        return effective

    # ---------------------------------------------------------------------------
    # Cấu hình cấp Guild
    # ---------------------------------------------------------------------------

    async def get_guild_config(self, guild_id: int) -> dict:
        """Lấy cấu hình riêng của guild từ cache hoặc SQLite."""
        cache_key = f"guild:{guild_id}"
        entry = self._guild_cache.get(cache_key)
        if self._is_valid(entry):
            return entry[0]

        db = await self._get_db()
        async with db.execute(
            "SELECT config_json FROM guild_config WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            try:
                cfg = json.loads(row[0])
            except json.JSONDecodeError:
                cfg = {}
        else:
            cfg = {}

        self._guild_cache[cache_key] = (cfg, time.monotonic())
        return cfg

    async def set_guild_config(self, guild_id: int, key: str, value) -> None:
        """Cập nhật một khoá cấu hình cho guild và xoá cache liên quan."""
        cfg = await self.get_guild_config(guild_id)
        if key.startswith("platform_"):
            platform_name = key[len("platform_"):]
            if "platforms_enabled" not in cfg:
                cfg["platforms_enabled"] = {}
            cfg["platforms_enabled"][platform_name] = value
        else:
            cfg[key] = value

        db = await self._get_db()
        await db.execute(
            """
            INSERT INTO guild_config (guild_id, config_json, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                config_json = excluded.config_json,
                updated_at  = excluded.updated_at
            """,
            (guild_id, json.dumps(cfg)),
        )
        await db.commit()

        self._invalidate_guild_cache(guild_id)

    async def reset_guild_config(self, guild_id: int) -> None:
        """Đặt lại cấu hình guild về mặc định."""
        db = await self._get_db()
        await db.execute(
            "DELETE FROM guild_config WHERE guild_id = ?",
            (guild_id,),
        )
        await db.commit()
        self._invalidate_guild_cache(guild_id)

    # ---------------------------------------------------------------------------
    # Cấu hình cấp Channel
    # ---------------------------------------------------------------------------

    async def get_channel_config(self, channel_id: int) -> dict:
        """Lấy cấu hình override của channel từ cache hoặc SQLite."""
        cache_key = f"channel:{channel_id}"
        entry = self._channel_cache.get(cache_key)
        if self._is_valid(entry):
            return entry[0]

        db = await self._get_db()
        async with db.execute(
            "SELECT config_json FROM channel_config WHERE channel_id = ?",
            (channel_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            try:
                cfg = json.loads(row[0])
            except json.JSONDecodeError:
                cfg = {}
        else:
            cfg = {}

        self._channel_cache[cache_key] = (cfg, time.monotonic())
        return cfg

    async def set_channel_config(
        self,
        guild_id: int,
        channel_id: int,
        key: str,
        value,
    ) -> None:
        """Cập nhật override cho channel và xoá cache liên quan."""
        cfg = await self.get_channel_config(channel_id)
        if key.startswith("platform_"):
            platform_name = key[len("platform_"):]
            if "platforms_enabled" not in cfg:
                cfg["platforms_enabled"] = {}
            cfg["platforms_enabled"][platform_name] = value
        else:
            cfg[key] = value

        db = await self._get_db()
        await db.execute(
            """
            INSERT INTO channel_config (channel_id, guild_id, config_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(channel_id) DO UPDATE SET
                config_json = excluded.config_json,
                updated_at  = excluded.updated_at
            """,
            (channel_id, guild_id, json.dumps(cfg)),
        )
        await db.commit()

        self._invalidate_channel_cache(guild_id, channel_id)

    async def reset_channel_config(self, guild_id: int, channel_id: int) -> None:
        """Xoá toàn bộ override của channel, quay lại dùng cấu hình guild."""
        db = await self._get_db()
        await db.execute(
            "DELETE FROM channel_config WHERE channel_id = ?",
            (channel_id,),
        )
        await db.commit()
        self._invalidate_channel_cache(guild_id, channel_id)

    # ---------------------------------------------------------------------------
    # Tuỳ chỉnh Proxy Domain cho Guild
    # ---------------------------------------------------------------------------

    async def get_guild_proxy_domains(
        self,
        guild_id: int,
        platform_key: str,
    ) -> list[str] | None:
        """Lấy danh sách proxy domain tuỳ chỉnh cho guild từ cache hoặc SQLite."""
        cache_key = f"proxy:{guild_id}:{platform_key}"
        entry = self._proxy_cache.get(cache_key)
        if self._is_valid(entry):
            return entry[0]

        db = await self._get_db()
        async with db.execute(
            """
            SELECT domains_json FROM guild_proxy_domains
            WHERE guild_id = ? AND platform_key = ?
            """,
            (guild_id, platform_key),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            try:
                domains = json.loads(row[0])
                if not isinstance(domains, list):
                    domains = None
            except json.JSONDecodeError:
                domains = None
        else:
            domains = None

        self._proxy_cache[cache_key] = (domains, time.monotonic())
        return domains

    async def set_guild_proxy_domains(
        self,
        guild_id: int,
        platform_key: str,
        domains: list[str],
    ) -> None:
        """Thiết lập danh sách proxy domain tuỳ chỉnh cho guild."""
        db = await self._get_db()
        await db.execute(
            """
            INSERT INTO guild_proxy_domains (guild_id, platform_key, domains_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, platform_key) DO UPDATE SET
                domains_json = excluded.domains_json,
                updated_at   = excluded.updated_at
            """,
            (guild_id, platform_key, json.dumps(domains)),
        )
        await db.commit()

        cache_key = f"proxy:{guild_id}:{platform_key}"
        self._proxy_cache[cache_key] = (domains, time.monotonic())

    async def reset_guild_proxy_domains(
        self,
        guild_id: int,
        platform_key: str,
    ) -> None:
        """Khôi phục proxy domains của guild về mặc định hệ thống."""
        db = await self._get_db()
        await db.execute(
            """
            DELETE FROM guild_proxy_domains
            WHERE guild_id = ? AND platform_key = ?
            """,
            (guild_id, platform_key),
        )
        await db.commit()

        cache_key = f"proxy:{guild_id}:{platform_key}"
        self._proxy_cache.pop(cache_key, None)

    async def get_all_guild_proxy_domains(self, guild_id: int) -> dict[str, list[str]]:
        """Lấy tất cả proxy domain tuỳ chỉnh của một guild."""
        db = await self._get_db()
        async with db.execute(
            """
            SELECT platform_key, domains_json FROM guild_proxy_domains
            WHERE guild_id = ?
            """,
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        result = {}
        for platform_key, domains_json in rows:
            try:
                domains = json.loads(domains_json)
                if isinstance(domains, list):
                    result[platform_key] = domains
            except json.JSONDecodeError:
                pass
        return result

    # ---------------------------------------------------------------------------
    # Tiện ích xoá Cache (Cache Invalidation)
    # ---------------------------------------------------------------------------

    def _invalidate_guild_cache(self, guild_id: int) -> None:
        """Xoá cache guild và toàn bộ effective cache liên quan đến guild đó."""
        self._guild_cache.pop(f"guild:{guild_id}", None)
        prefix = f"{guild_id}:"
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            self._cache.pop(k, None)

    def _invalidate_channel_cache(self, guild_id: int, channel_id: int) -> None:
        """Xoá cache channel và effective cache của channel đó."""
        self._channel_cache.pop(f"channel:{channel_id}", None)
        self._cache.pop(f"{guild_id}:{channel_id}", None)

    # ---------------------------------------------------------------------------
    # Quản lý Tạm Ngưng Server (Guild Suspension)
    # ---------------------------------------------------------------------------

    def is_guild_suspended(self, guild_id: int | None) -> bool:
        """Kiểm tra nhanh xem guild có đang bị Admin tạm ngưng hay không (O(1))."""
        if not guild_id:
            return False
        return guild_id in self._suspended_guilds

    async def suspend_guild(self, guild_id: int, guild_name: str = "", reason: str = "") -> None:
        """Tạm ngưng hoạt động của bot trên một server Discord."""
        self._suspended_guilds.add(guild_id)
        db = await self._get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suspended_guilds (
                guild_id      INTEGER PRIMARY KEY,
                guild_name    TEXT,
                reason        TEXT,
                suspended_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute(
            """
            INSERT OR REPLACE INTO suspended_guilds (guild_id, guild_name, reason, suspended_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (guild_id, guild_name, reason)
        )
        await db.commit()

    async def unsuspend_guild(self, guild_id: int) -> None:
        """Gỡ tạm ngưng cho server Discord."""
        self._suspended_guilds.discard(guild_id)
        db = await self._get_db()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suspended_guilds (
                guild_id      INTEGER PRIMARY KEY,
                guild_name    TEXT,
                reason        TEXT,
                suspended_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("DELETE FROM suspended_guilds WHERE guild_id = ?", (guild_id,))
        await db.commit()

    async def get_suspended_guilds_info(self) -> dict[int, dict]:
        """Lấy thông tin chi tiết các server đang bị tạm ngưng."""
        db = await self._get_db()
        async with db.execute("SELECT guild_id, guild_name, reason, suspended_at FROM suspended_guilds") as cursor:
            rows = await cursor.fetchall()
            return {
                row[0]: {
                    "guild_id": row[0],
                    "guild_name": row[1],
                    "reason": row[2],
                    "suspended_at": row[3]
                }
                for row in rows
            }

