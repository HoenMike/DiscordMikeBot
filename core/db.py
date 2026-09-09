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


import threading


class _LoopConnection:
    """Đại diện cho kết nối DB độc lập trên một asyncio event loop cụ thể."""
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.turso_client: Optional[Any] = None
        self.local_db: Optional[aiosqlite.Connection] = None
        self.is_cloud: bool = False
        self.connected: bool = False
        self.lock = asyncio.Lock()
        self.logged: bool = False

    async def close(self) -> None:
        """Đóng an toàn các kết nối thuộc loop này."""
        if self.turso_client is not None:
            try:
                res = self.turso_client.close()
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass
            self.turso_client = None

        if self.local_db is not None:
            try:
                await self.local_db.close()
            except Exception:
                pass
            self.local_db = None

        self.connected = False
        self.is_cloud = False


class DatabaseClient:
    """
    Client cơ sở dữ liệu Async đa nền tảng (Turso Cloud LibSQL / Local SQLite).
    Hỗ trợ đa luồng (Multi-threading) và đa Event Loop an toàn tuyệt đối:
    Mỗi event loop (Discord Bot loop và Flask request temporary loops) 
    sở hữu kết nối riêng biệt, ngăn chặn triệt để xung đột tài nguyên hoặc 'Future attached to different loop'.
    """

    def __init__(self):
        self._connections: Dict[asyncio.AbstractEventLoop, _LoopConnection] = {}
        self._thread_lock = threading.Lock()

    def _get_connection(self) -> _LoopConnection:
        """Lấy hoặc tạo kết nối riêng cho event loop đang chạy hiện tại."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("DatabaseClient chỉ có thể được gọi từ bên trong một running asyncio event loop.")

        with self._thread_lock:
            # Dọn dẹp các loop cũ đã bị đóng để tránh rò rỉ bộ nhớ
            closed_loops = [l for l in self._connections if l.is_closed()]
            for cl in closed_loops:
                self._connections.pop(cl, None)

            if loop not in self._connections:
                self._connections[loop] = _LoopConnection(loop)
            return self._connections[loop]

    @property
    def is_cloud(self) -> bool:
        try:
            conn = self._get_connection()
            return conn.is_cloud
        except Exception:
            return False

    async def reset(self) -> None:
        """Đóng kết nối của event loop hiện tại."""
        conn = self._get_connection()
        async with conn.lock:
            await conn.close()

    async def _connect_conn(self, conn: _LoopConnection, force: bool = False) -> None:
        """Kết nối nội bộ cho một _LoopConnection cụ thể."""
        async with conn.lock:
            if conn.connected and not force:
                return

            # Đóng kết nối cũ nếu force reconnect
            await conn.close()

            # 1. Thử kết nối Turso Cloud nếu có token cấu hình
            if HAS_LIBSQL and config.TURSO_AUTH_TOKEN and config.TURSO_DATABASE_URL:
                client = None
                try:
                    url = config.TURSO_DATABASE_URL
                    if url.startswith("libsql://"):
                        url = "https://" + url[len("libsql://"):]

                    client = libsql_client.create_client(
                        url=url,
                        auth_token=config.TURSO_AUTH_TOKEN
                    )
                    await client.execute("SELECT 1")
                    conn.turso_client = client
                    conn.is_cloud = True
                    conn.connected = True
                    if not conn.logged:
                        conn.logged = True
                        print(f"☁️ [Database] Đã kết nối thành công tới Turso Cloud LibSQL ({config.TURSO_DATABASE_URL})!", flush=True)
                    return
                except Exception as e:
                    print(f"⚠️ [Database] Không thể kết nối Turso Cloud ({e}). Đang tự động chuyển sang Local SQLite...", flush=True)
                    if client is not None:
                        try:
                            res = client.close()
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass
                    conn.turso_client = None
                    conn.is_cloud = False

            # 2. Fallback sang Local aiosqlite
            conn.local_db = await aiosqlite.connect(str(config.DB_PATH))
            await conn.local_db.execute("PRAGMA journal_mode=WAL")
            await conn.local_db.execute("PRAGMA synchronous=NORMAL")
            conn.is_cloud = False
            conn.connected = True
            if not conn.logged:
                conn.logged = True
                print(f"💾 [Database] Đang sử dụng Local SQLite: {config.DB_PATH}", flush=True)

    async def connect(self) -> None:
        """Khởi tạo kết nối đến Cloud hoặc Local DB cho loop hiện tại."""
        conn = self._get_connection()
        await self._connect_conn(conn)

    async def _execute_internal(self, sql: str, params: Union[Tuple, List, dict, None] = None) -> CursorWrapper:
        """Thực thi câu lệnh SQL trên kết nối của loop hiện tại."""
        conn = self._get_connection()
        if not conn.connected:
            await self._connect_conn(conn)

        # 1. Thực thi trên Turso Cloud
        if conn.is_cloud and conn.turso_client is not None:
            args = list(params) if isinstance(params, (tuple, list)) else (params or [])
            try:
                rs = await conn.turso_client.execute(sql, args)
                return CursorWrapper(
                    rows=rs.rows,
                    last_insert_id=getattr(rs, 'last_insert_rowid', None),
                    rows_affected=getattr(rs, 'rows_affected', 0)
                )
            except Exception as e:
                err_msg = str(e).lower()
                # Tự động reconnect nếu connection bị drop hoặc session bị đóng
                if any(kw in err_msg for kw in ["closed", "session", "cannot reuse", "connection", "503"]):
                    print(f"⚠️ [Database] Lỗi kết nối Turso ({e}), đang tự động kết nối lại...", flush=True)
                    await self._connect_conn(conn, force=True)
                    if conn.is_cloud and conn.turso_client is not None:
                        rs = await conn.turso_client.execute(sql, args)
                        return CursorWrapper(
                            rows=rs.rows,
                            last_insert_id=getattr(rs, 'last_insert_rowid', None),
                            rows_affected=getattr(rs, 'rows_affected', 0)
                        )
                raise

        # 2. Thực thi trên Local SQLite
        if conn.local_db is None:
            await self._connect_conn(conn, force=True)

        if conn.local_db is not None:
            cursor = await conn.local_db.execute(sql, params or ())
            rows = await cursor.fetchall()
            last_id = cursor.lastrowid
            row_cnt = cursor.rowcount
            return CursorWrapper(rows=rows, last_insert_id=last_id, rows_affected=row_cnt)

        raise RuntimeError("Không có kết nối Database hợp lệ để thực thi truy vấn.")

    def execute(self, sql: str, params: Union[Tuple, List, dict, None] = None) -> AsyncQueryContext:
        """Thực thi một câu lệnh SQL và trả về AsyncQueryContext (hỗ trợ cả `await db.execute()` và `async with db.execute()`)."""
        return AsyncQueryContext(self._execute_internal(sql, params))

    async def executemany(self, sql: str, params_list: List[Any]) -> None:
        """Thực thi nhiều lệnh SQL tuần tự."""
        for p in params_list:
            await self.execute(sql, p)

    async def commit(self) -> None:
        """Commit transaction (aiosqlite) - Turso tự động commit mỗi statement."""
        conn = self._get_connection()
        if not conn.is_cloud and conn.local_db:
            await conn.local_db.commit()

    async def close(self) -> None:
        """Đóng kết nối của loop hiện tại."""
        conn = self._get_connection()
        async with conn.lock:
            await conn.close()


# Singleton instance dùng chung
db_client = DatabaseClient()

