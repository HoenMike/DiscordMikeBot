import collections
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

# Giới hạn lưu trữ tối đa 1000 lượt tương tác gần nhất trong RAM đệm
MAX_ACTIVITIES = 1000

class ActivityLogger:
    def __init__(self, maxlen: int = MAX_ACTIVITIES):
        self._activities: collections.deque = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._counter = 0

    def log(
        self,
        action_type: str,  # 'tarot' | 'summary' | 'embed' | 'command'
        action_name: str,
        user_id: int,
        user_name: str,
        user_avatar: Optional[str] = None,
        guild_name: Optional[str] = None,
        guild_id: Optional[int] = None,
        channel_name: Optional[str] = None,
        channel_id: Optional[int] = None,
        prompt: Optional[str] = None,
        response: Optional[str] = None,
        status: str = "success",  # 'success' | 'error' | 'in_progress'
        duration_ms: float = 0.0,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ghi nhận một hoạt động tương tác mới giữa người dùng và Bot."""
        vn_tz = timezone(timedelta(hours=7))
        now_vn = datetime.now(vn_tz)
        
        with self._lock:
            self._counter += 1
            entry = {
                "id": self._counter,
                "timestamp": now_vn.strftime("%Y-%m-%d %H:%M:%S"),
                "time_short": now_vn.strftime("%H:%M:%S"),
                "action_type": action_type,
                "action_name": action_name,
                "user_id": user_id,
                "user_name": user_name,
                "user_avatar": user_avatar or "",
                "guild_name": guild_name or "Direct Message / Unknown",
                "guild_id": guild_id,
                "channel_name": channel_name or "Unknown Channel",
                "channel_id": channel_id,
                "prompt": (prompt or "").strip(),
                "response": (response or "").strip(),
                "status": status,
                "duration_ms": round(duration_ms, 1),
                "details": details or {}
            }
            self._activities.appendleft(entry)
            return entry

    def get_activities(
        self,
        action_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Truy vấn danh sách tương tác với bộ lọc và tìm kiếm."""
        with self._lock:
            items = list(self._activities)

        if action_type and action_type != "all":
            items = [item for item in items if item["action_type"] == action_type]

        if search:
            q = search.lower().strip()
            items = [
                item for item in items
                if q in item["user_name"].lower()
                or q in item["prompt"].lower()
                or q in item["response"].lower()
                or q in item["guild_name"].lower()
                or q in item["action_name"].lower()
            ]

        total = len(items)
        sliced = items[offset : offset + limit]

        # Thống kê nhanh theo loại
        type_counts = {
            "all": len(self._activities),
            "tarot": sum(1 for a in self._activities if a["action_type"] == "tarot"),
            "summary": sum(1 for a in self._activities if a["action_type"] == "summary"),
            "embed": sum(1 for a in self._activities if a["action_type"] == "embed"),
            "command": sum(1 for a in self._activities if a["action_type"] == "command"),
        }

        return {
            "total": total,
            "counts": type_counts,
            "items": sliced
        }

    def clear(self):
        """Xóa toàn bộ bộ đệm hoạt động."""
        with self._lock:
            self._activities.clear()

# Singleton instance
activity_logger = ActivityLogger()
