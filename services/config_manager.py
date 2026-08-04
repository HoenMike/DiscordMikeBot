import json
import time
import aiosqlite
import config as app_config
from utils.constants import DEFAULT_CONFIG


class ConfigManager:
    CACHE_TTL = 300

    def __init__(self):
        self._cache: dict[str, tuple[dict, float]] = {}
        self._db_path = str(app_config.DB_PATH)

    async def init_db(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
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
            await db.commit()
        print("[ConfigManager] Đã khởi tạo cơ sở dữ liệu cấu hình.", flush=True)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _cache_key(self, guild_id: int, channel_id: int) -> str:
        return f"{guild_id}:{channel_id}"

    def _get_cached(self, guild_id: int, channel_id: int) -> dict | None:
        key = self._cache_key(guild_id, channel_id)
        entry = self._cache.get(key)
        if entry is None:
            return None
        config, timestamp = entry
        if time.time() - timestamp > self.CACHE_TTL:
            del self._cache[key]
            return None
        return config

    def _set_cached(self, guild_id: int, channel_id: int, config: dict) -> None:
        key = self._cache_key(guild_id, channel_id)
        self._cache[key] = (config, time.time())

    def _invalidate_guild(self, guild_id: int) -> None:
        keys_to_remove = [k for k in self._cache if k.startswith(f"{guild_id}:")]
        for k in keys_to_remove:
            del self._cache[k]

    def _invalidate_channel(self, guild_id: int, channel_id: int) -> None:
        self._cache.pop(self._cache_key(guild_id, channel_id), None)

    async def get_guild_config_raw(self, guild_id: int) -> dict:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT config_json FROM guild_config WHERE guild_id = ?",
                (guild_id,)
            )
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else {}

    async def get_channel_config_raw(self, channel_id: int) -> dict:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT config_json FROM channel_config WHERE channel_id = ?",
                (channel_id,)
            )
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else {}

    async def get_effective_config(self, guild_id: int, channel_id: int) -> dict:
        cached = self._get_cached(guild_id, channel_id)
        if cached is not None:
            return cached

        guild_raw = await self.get_guild_config_raw(guild_id)
        channel_raw = await self.get_channel_config_raw(channel_id)

        merged = self._deep_merge(DEFAULT_CONFIG, guild_raw)
        merged = self._deep_merge(merged, channel_raw)

        self._set_cached(guild_id, channel_id, merged)
        return merged

    async def set_guild_config(self, guild_id: int, key: str, value) -> None:
        current = await self.get_guild_config_raw(guild_id)
        self._set_nested(current, key, value)

        async with aiosqlite.connect(self._db_path) as db:
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

        async with aiosqlite.connect(self._db_path) as db:
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
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM guild_config WHERE guild_id = ?", (guild_id,))
            await db.commit()
        self._invalidate_guild(guild_id)

    async def reset_channel_config(self, channel_id: int, guild_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM channel_config WHERE channel_id = ?", (channel_id,))
            await db.commit()
        self._invalidate_channel(guild_id, channel_id)

    @staticmethod
    def _set_nested(d: dict, key: str, value) -> None:
        parts = key.split(".")
        current = d
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
