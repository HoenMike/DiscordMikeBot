"""
core/db.py - Unified Async Database Adapter for Turso LibSQL & Local SQLite.

Cung cấp interface đồng nhất cho toàn bộ hệ thống bot:
- Khi có TURSO_DATABASE_URL & TURSO_AUTH_TOKEN -> Kết nối trực tiếp Turso Cloud (dữ liệu bền vững 100% trên Render).
- Khi không có token hoặc offline -> Tự động fallback sang Local SQLite (data/bot_config.db).
"""

import asyncio
import os
from typing import Any, List, Optional, Tuple, Union
import config

try:
    import libsql_client
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False

import aiosqlite


class CursorWrapper:
    """Wrapper cho kết quả truy vấn đồng nhất giữa aiosqlite và libsql-client."""
    def __init__(self, rows: List[Any], last_insert_id: Optional[int] = None, rows_affected: int = 0):
        self._rows = rows or []
        self.lastrowid = last_insert_id
        self.rowcount = rows_affected

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def fetchone(self) -> Optional[Tuple[Any, ...]]:
        if self._rows:
            row = self._rows[0]
            if isinstance(row, (tuple, list)):
                return tuple(row)
            if hasattr(row, 'values'):
                return tuple(row.values())
            return tuple(row)
        return None

    async def fetchall(self) -> List[Tuple[Any, ...]]:
        res = []
        for row in self._rows:
            if isinstance(row, (tuple, list)):
                res.append(tuple(row))
            elif hasattr(row, 'values'):
                res.append(tuple(row.values()))
            else:
                res.append(tuple(row))
        return res


class AsyncQueryContext:
    """Cho phép vừa có thể `await db.execute(...)` vừa có thể `async with db.execute(...) as cursor:`."""
    def __init__(self, coro):
        self._coro = coro
        self._res: Optional[CursorWrapper] = None

    def __await__(self):
        return self._coro.__await__()

    async def __aenter__(self):
        self._res = await self._coro
        return self._res

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DatabaseClient:
    """Client cơ sở dữ liệu Async đa nền tảng (Turso Cloud LibSQL / Local SQLite)."""

    def __init__(self):
        self._turso_client: Optional[Any] = None
        self._local_db: Optional[aiosqlite.Connection] = None
        self._is_cloud: bool = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_cloud(self) -> bool:
        return self._is_cloud

    async def connect(self) -> None:
        """Khởi tạo kết nối đến Cloud hoặc Local DB."""
        current_loop = asyncio.get_running_loop()
        
        # 1. Thử kết nối Turso Cloud nếu có token cấu hình
        if HAS_LIBSQL and config.TURSO_AUTH_TOKEN and config.TURSO_DATABASE_URL:
            try:
                if self._turso_client is not None and self._loop != current_loop:
                    self._turso_client = None

                # Chuyển đổi giao thức libsql:// sang https:// nếu cần cho HTTP client
                url = config.TURSO_DATABASE_URL
                if url.startswith("libsql://"):
                    url = "https://" + url[len("libsql://"):]

                self._turso_client = libsql_client.create_client(
                    url=url,
                    auth_token=config.TURSO_AUTH_TOKEN
                )
                # Thử ping nhẹ 1 query để xác thực token
                ping_task = asyncio.create_task(self._turso_client.execute("SELECT 1"))
                await ping_task
                self._is_cloud = True
                self._loop = current_loop
                print(f"☁️ [Database] Đã kết nối thành công tới Turso Cloud LibSQL ({config.TURSO_DATABASE_URL})!", flush=True)
                return
            except Exception as e:
                print(f"⚠️ [Database] Không thể kết nối Turso Cloud ({e}). Đang tự động chuyển sang Local SQLite...", flush=True)
                self._turso_client = None
                self._is_cloud = False

        # 2. Fallback sang Local aiosqlite
        if self._local_db is None or getattr(self._local_db, '_loop', None) != current_loop:
            self._local_db = await aiosqlite.connect(str(config.DB_PATH))
            await self._local_db.execute("PRAGMA journal_mode=WAL")
            await self._local_db.execute("PRAGMA synchronous=NORMAL")
            self._is_cloud = False
            self._loop = current_loop
            print(f"💾 [Database] Đang sử dụng Local SQLite: {config.DB_PATH}", flush=True)

    async def _execute_internal(self, sql: str, params: Union[Tuple, List, dict, None] = None) -> CursorWrapper:
        """Thực thi một câu lệnh SQL nội bộ và trả về CursorWrapper tương thích."""
        current_loop = asyncio.get_running_loop()
        if (self._is_cloud and (self._turso_client is None or self._loop != current_loop)) or (not self._is_cloud and (self._local_db is None or getattr(self._local_db, '_loop', None) != current_loop)):
            await self.connect()

        # Thực thi trên Turso Cloud
        if self._is_cloud and self._turso_client:
            args = list(params) if isinstance(params, (tuple, list)) else (params or [])
            exec_task = asyncio.create_task(self._turso_client.execute(sql, args))
            rs = await exec_task
            return CursorWrapper(
                rows=rs.rows,
                last_insert_id=getattr(rs, 'last_insert_rowid', None),
                rows_affected=getattr(rs, 'rows_affected', 0)
            )

        # Thực thi trên Local SQLite
        cursor = await self._local_db.execute(sql, params or ())
        rows = await cursor.fetchall()
        last_id = cursor.lastrowid
        row_cnt = cursor.rowcount
        return CursorWrapper(rows=rows, last_insert_id=last_id, rows_affected=row_cnt)

    def execute(self, sql: str, params: Union[Tuple, List, dict, None] = None) -> AsyncQueryContext:
        """Thực thi một câu lệnh SQL và trả về AsyncQueryContext (hỗ trợ cả `await db.execute()` và `async with db.execute()`)."""
        return AsyncQueryContext(self._execute_internal(sql, params))

    async def executemany(self, sql: str, params_list: List[Any]) -> None:
        """Thực thi nhiều lệnh SQL tuần tự."""
        for p in params_list:
            await self.execute(sql, p)

    async def commit(self) -> None:
        """Commit transaction (aiosqlite) - Turso tự động commit mỗi statement."""
        if not self._is_cloud and self._local_db:
            await self._local_db.commit()

    async def close(self) -> None:
        """Đóng kết nối."""
        if self._turso_client:
            try:
                await self._turso_client.close()
            except Exception:
                pass
            self._turso_client = None

        if self._local_db:
            try:
                await self._local_db.close()
            except Exception:
                pass
            self._local_db = None


# Singleton instance dùng chung
db_client = DatabaseClient()
