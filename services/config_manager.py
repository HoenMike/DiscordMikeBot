import json
import time
import aiosqlite
import config as app_config
from utils.constants import DEFAULT_CONFIG, PROXY_DOMAINS


class ConfigManager:
    """Quản lý cấu hình guild/channel với cache trong bộ nhớ và SQLite.

    Sử dụng kết nối persistent để tránh overhead mở/đóng trên mỗi query.
    Cache được phân tầng: effective config, guild raw, channel raw, proxy domains.
    """

    CACHE_TTL = 300

    def __init__(self):
        # Cache effective config (guild_id:channel_id -> config dict)
        self._cache: dict[str, tuple[dict, float]] = {}
        # Cache guild config raw (guild:{guild_id} -> config dict)
        self._guild_cache: dict[str, tuple[dict, float]] = {}
        # Cache channel config raw (channel:{channel_id} -> config dict)
        self._channel_cache: dict[str, tuple[dict, float]] = {}
        # Cache proxy domains (proxy:{guild_id}:{platform_key} -> list hoặc None)
        self._proxy_cache: dict[str, tuple[list | None, float]] = {}
        self._db_path = str(app_config.DB_PATH)
        self._db: aiosqlite.Connection | None = None

    async def _get_db(self) -> aiosqlite.Connection:
        """Lấy kết nối persistent, tạo mới nếu chưa có hoặc đã đóng."""
        if self._db is None or not self._db.is_alive():
            self._db = await aiosqlite.connect(self._db_path)
            # Tối ưu hiệu năng SQLite cho workload đọc nhiều
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
        return self._db

    async def init_db(self) -> None:
        """Khởi tạo các bảng cấu hình và proxy domains."""
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
        await db.commit()
        print("[ConfigManager] Đã khởi tạo cơ sở dữ liệu cấu hình.", flush=True)

    async def close(self) -> None:
        """Đóng kết nối persistent khi bot shutdown."""
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:
                pass
            self._db = None

    # ---------------------------------------------------------------------------
    # Tiện ích cache nội bộ
    # ---------------------------------------------------------------------------

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _cache_get(store: dict, key: str, ttl: int) -> object | None:
        """Lấy giá trị từ cache store, trả về None nếu hết hạn hoặc không tồn tại."""
        entry = store.get(key)
        if entry is None:
            return None
        value, timestamp = entry
        if time.time() - timestamp > ttl:
            del store[key]
            return None
        return value

    @staticmethod
    def _cache_set(store: dict, key: str, value: object) -> None:
        """Ghi giá trị vào cache store với timestamp hiện tại."""
        store[key] = (value, time.time())

    def _invalidate_guild(self, guild_id: int) -> None:
        """Xoá tất cả cache liên quan đến guild (effective, guild raw, proxy)."""
        keys_to_remove = [k for k in self._cache if k.startswith(f"{guild_id}:")]
        for k in keys_to_remove:
            del self._cache[k]
        self._guild_cache.pop(f"guild:{guild_id}", None)
        # Xoá proxy cache của guild
        proxy_keys = [k for k in self._proxy_cache if k.startswith(f"proxy:{guild_id}:")]
        for k in proxy_keys:
            del self._proxy_cache[k]

    def _invalidate_channel(self, guild_id: int, channel_id: int) -> None:
        """Xoá cache effective config và channel raw cho kênh cụ thể."""
        self._cache.pop(f"{guild_id}:{channel_id}", None)
        self._channel_cache.pop(f"channel:{channel_id}", None)

    # ---------------------------------------------------------------------------
    # Đọc cấu hình
    # ---------------------------------------------------------------------------

    async def get_guild_config_raw(self, guild_id: int) -> dict:
        """Lấy cấu hình guild từ cache hoặc SQLite."""
        cache_key = f"guild:{guild_id}"
        cached = self._cache_get(self._guild_cache, cache_key, self.CACHE_TTL)
        if cached is not None:
            return cached

        db = await self._get_db()
        cursor = await db.execute(
            "SELECT config_json FROM guild_config WHERE guild_id = ?",
            (guild_id,)
        )
        row = await cursor.fetchone()
        result = json.loads(row[0]) if row else {}
        self._cache_set(self._guild_cache, cache_key, result)
        return result

    async def get_channel_config_raw(self, channel_id: int) -> dict:
        """Lấy cấu hình kênh từ cache hoặc SQLite."""
        cache_key = f"channel:{channel_id}"
        cached = self._cache_get(self._channel_cache, cache_key, self.CACHE_TTL)
        if cached is not None:
            return cached

        db = await self._get_db()
        cursor = await db.execute(
            "SELECT config_json FROM channel_config WHERE channel_id = ?",
            (channel_id,)
        )
        row = await cursor.fetchone()
        result = json.loads(row[0]) if row else {}
        self._cache_set(self._channel_cache, cache_key, result)
        return result

    async def get_effective_config(self, guild_id: int, channel_id: int) -> dict:
        """Lấy cấu hình hiệu lực (merged: default -> guild -> channel) với cache."""
        cache_key = f"{guild_id}:{channel_id}"
        cached = self._cache_get(self._cache, cache_key, self.CACHE_TTL)
        if cached is not None:
            return cached

        guild_raw = await self.get_guild_config_raw(guild_id)
        channel_raw = await self.get_channel_config_raw(channel_id)

        merged = self._deep_merge(DEFAULT_CONFIG, guild_raw)
        merged = self._deep_merge(merged, channel_raw)

        self._cache_set(self._cache, cache_key, merged)
        return merged

    # ---------------------------------------------------------------------------
    # Ghi cấu hình
    # ---------------------------------------------------------------------------

    async def set_guild_config(self, guild_id: int, key: str, value) -> None:
        current = await self.get_guild_config_raw(guild_id)
        self._set_nested(current, key, value)

        db = await self._get_db()
        await db.execute("""
            INSERT INTO guild_config (guild_id, config_json, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
        """, (guild_id, json.dumps(current, ensure_ascii=False)))
        await db.commit()

        self._invalidate_guild(guild_id)

    async def set_channel_config(self, channel_id: int, guild_id: int, key: str, value) -> None:
        current = await self.get_channel_config_raw(channel_id)
        self._set_nested(current, key, value)

        db = await self._get_db()
        await db.execute("""
            INSERT INTO channel_config (channel_id, guild_id, config_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(channel_id) DO UPDATE SET
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
        """, (channel_id, guild_id, json.dumps(current, ensure_ascii=False)))
        await db.commit()

        self._invalidate_channel(guild_id, channel_id)

    async def reset_guild_config(self, guild_id: int) -> None:
        db = await self._get_db()
        await db.execute("DELETE FROM guild_config WHERE guild_id = ?", (guild_id,))
        await db.commit()
        self._invalidate_guild(guild_id)

    async def reset_channel_config(self, channel_id: int, guild_id: int) -> None:
        db = await self._get_db()
        await db.execute("DELETE FROM channel_config WHERE channel_id = ?", (channel_id,))
        await db.commit()
        self._invalidate_channel(guild_id, channel_id)

    # ---------------------------------------------------------------------------
    # Quản lý proxy domains theo guild
    # ---------------------------------------------------------------------------

    async def get_guild_proxy_domains(self, guild_id: int, platform_key: str) -> list[str] | None:
        """Lấy danh sách proxy domain tùy chỉnh của guild cho nền tảng.

        Trả về None nếu guild chưa cấu hình (sẽ dùng danh sách mặc định toàn cục).
        """
        cache_key = f"proxy:{guild_id}:{platform_key}"
        cached = self._cache_get(self._proxy_cache, cache_key, self.CACHE_TTL)
        # Phân biệt None (chưa cache) với None (không có custom config)
        if cached is not None:
            return cached

        # Kiểm tra xem key có trong cache store không (bao gồm cả giá trị None đã cache)
        entry = self._proxy_cache.get(cache_key)
        if entry is not None:
            value, timestamp = entry
            if time.time() - timestamp <= self.CACHE_TTL:
                return value

        db = await self._get_db()
        cursor = await db.execute(
            "SELECT domains_json FROM guild_proxy_domains WHERE guild_id = ? AND platform_key = ?",
            (guild_id, platform_key)
        )
        row = await cursor.fetchone()
        if row:
            domains = json.loads(row[0])
            self._proxy_cache[cache_key] = (domains, time.time())
            return domains

        # Cache giá trị None để tránh query lặp lại
        self._proxy_cache[cache_key] = (None, time.time())
        return None

    async def set_guild_proxy_domains(self, guild_id: int, platform_key: str, domains: list[str]) -> None:
        """Ghi đè danh sách proxy domain cho guild và nền tảng cụ thể."""
        db = await self._get_db()
        await db.execute("""
            INSERT INTO guild_proxy_domains (guild_id, platform_key, domains_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, platform_key) DO UPDATE SET
                domains_json = excluded.domains_json,
                updated_at = excluded.updated_at
        """, (guild_id, platform_key, json.dumps(domains, ensure_ascii=False)))
        await db.commit()

        # Cập nhật cache
        cache_key = f"proxy:{guild_id}:{platform_key}"
        self._proxy_cache[cache_key] = (domains, time.time())

    async def reset_guild_proxy_domains(self, guild_id: int, platform_key: str) -> None:
        """Xoá cấu hình proxy tùy chỉnh, khôi phục về danh sách mặc định toàn cục."""
        db = await self._get_db()
        await db.execute(
            "DELETE FROM guild_proxy_domains WHERE guild_id = ? AND platform_key = ?",
            (guild_id, platform_key)
        )
        await db.commit()

        cache_key = f"proxy:{guild_id}:{platform_key}"
        self._proxy_cache[cache_key] = (None, time.time())

    def get_effective_proxy_domains(self, guild_domains: list[str] | None, platform_key: str) -> list[str]:
        """Trả về danh sách proxy hiệu lực: ưu tiên guild custom, fallback về mặc định."""
        if guild_domains is not None:
            return guild_domains
        return PROXY_DOMAINS.get(platform_key, [])

    # ---------------------------------------------------------------------------
    # Tiện ích nội bộ
    # ---------------------------------------------------------------------------

    @staticmethod
    def _set_nested(d: dict, key: str, value) -> None:
        parts = key.split(".")
        current = d
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
