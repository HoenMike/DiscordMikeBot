"""
features/cabin/constants.py - Hằng số và hàm hỗ trợ định dạng cho tính năng Dịch Cabin AI.
"""

import re
from typing import Optional
import config

# Mô hình AI mặc định và danh sách dự phòng
DEFAULT_CABIN_MODEL = getattr(config, "GEMINI_CABIN_MODEL", "gemini-3.8-flash")
_raw_cabin_fallbacks = getattr(config, "CABIN_FALLBACK_MODELS", [
    DEFAULT_CABIN_MODEL,
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
])
_seen = set()
CABIN_FALLBACK_MODELS = [m for m in _raw_cabin_fallbacks if m and not (m in _seen or _seen.add(m))]

# Giới hạn thời gian và tham số vận hành
MIN_DURATION_SECONDS = 60           # 1 phút
DEFAULT_DURATION_SECONDS = 1800     # 30 phút
MAX_DURATION_SECONDS = 10800        # 3 giờ (180 phút)

DEFAULT_CABIN_COOLDOWN_SECONDS = 8.0  # Cooldown giữa 2 lần bot dịch cho cùng 1 người
CONTEXT_HISTORY_MINUTES = 5           # Chỉ quét tin nhắn trong vòng 5 phút gần nhất
CONTEXT_MAX_MESSAGES = 4              # Chỉ lấy tối đa 3-4 tin nhắn gần nhất để làm tham khảo phụ

CABIN_EMBED_COLOR = 0xE67E22          # Màu cam microphone trực tiếp


def parse_duration(text: Optional[str]) -> Optional[int]:
    """
    Phân tích chuỗi thời gian người dùng nhập thành số giây.
    Hỗ trợ:
      - '10m', '30p', '45 min', '30 phut', '30 phút' -> số phút * 60
      - '1h', '2h', '1.5h', '1 tiếng', '2 gio', '2 giờ' -> số giờ * 3600
      - '60s', '120s' -> số giây
      - Số thuần túy (ví dụ '20') -> mặc định tính theo phút
    """
    if not text:
        return DEFAULT_DURATION_SECONDS

    cleaned = text.strip().lower()
    if not cleaned:
        return DEFAULT_DURATION_SECONDS

    # 1. Định dạng giờ (h, hr, tiếng, giờ)
    hour_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:h|hr|hours?|tiếng|tieng|giờ|gio)$", cleaned)
    if hour_match:
        try:
            val = float(hour_match.group(1))
            secs = int(val * 3600)
            return max(MIN_DURATION_SECONDS, min(secs, MAX_DURATION_SECONDS))
        except (ValueError, OverflowError):
            return None

    # 2. Định dạng phút (m, min, phút, phut, p)
    min_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:m|min|mins?|p|phút|phut)$", cleaned)
    if min_match:
        try:
            val = float(min_match.group(1))
            secs = int(val * 60)
            return max(MIN_DURATION_SECONDS, min(secs, MAX_DURATION_SECONDS))
        except (ValueError, OverflowError):
            return None

    # 3. Định dạng giây (s, sec, giây, giay)
    sec_match = re.match(r"^(\d+)\s*(?:s|sec|secs?|giây|giay)$", cleaned)
    if sec_match:
        try:
            secs = int(sec_match.group(1))
            return max(MIN_DURATION_SECONDS, min(secs, MAX_DURATION_SECONDS))
        except (ValueError, OverflowError):
            return None

    # 4. Nếu chỉ nhập số nguyên -> mặc định là phút
    if cleaned.isdigit():
        secs = int(cleaned) * 60
        return max(MIN_DURATION_SECONDS, min(secs, MAX_DURATION_SECONDS))

    return None


def format_duration(seconds: int) -> str:
    """Định dạng số giây thành chuỗi mô tả thân thiện (ví dụ: '30 phút', '1 giờ 15 phút')."""
    if seconds < 60:
        return f"{seconds} giây"
    
    minutes = int(seconds // 60)
    hours = minutes // 60
    rem_minutes = minutes % 60

    if hours > 0:
        if rem_minutes > 0:
            return f"{hours} giờ {rem_minutes} phút"
        return f"{hours} giờ"
    return f"{minutes} phút"
