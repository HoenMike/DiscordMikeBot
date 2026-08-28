import os
import collections
from datetime import datetime, timezone, timedelta
import sys

# ==========================================
# 0. KHỞI TẠO BỘ ĐỆM LOG & FILE GHI ERROR
# ==========================================
log_buffer = collections.deque(maxlen=500)

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
ERROR_LOG_PATH = os.path.join(LOG_DIR, "error.log")

try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    pass


def is_error_log(text: str, is_stderr: bool = False) -> bool:
    stripped = text.strip()
    # 1. Các cảnh báo bình thường, fallback của bot hoặc warning của Python/thư viện
    if any(k in stripped for k in [
        "⚠️", "Warning:", "SyntaxWarning", "RuntimeWarning", "UserWarning",
        "503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "chuyển sang model",
        "Thử proxy", "Không tìm thấy OG", "Direct use of automatic function calling"
    ]):
        return False

    if is_stderr:
        if any(w in stripped for w in ["Warning:", "SyntaxWarning:", "RuntimeWarning:"]):
            return False
        return True

    lower = stripped.lower()
    # 2. Chỉ coi là lỗi thực sự nếu bắt đầu bằng ❌ hoặc có crash/traceback nghiêm trọng
    return any(keyword in lower for keyword in ["❌", "[error]", "traceback (most recent call last)", "syntaxerror:", "nameerror:", "typeerror:"])


def append_to_error_file(timestamp_full: str, line: str):
    try:
        with open(ERROR_LOG_PATH, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{timestamp_full}] {line}\n")
    except Exception:
        pass


class LogStreamRedirector:
    def __init__(self, original_stream, is_stderr: bool = False):
        self.original_stream = original_stream
        self.is_stderr = is_stderr

    def write(self, data):
        self.original_stream.write(data)
        self.original_stream.flush()
        
        clean_data = data.strip()
        if clean_data:
            for line in clean_data.split('\n'):
                stripped_line = line.strip()
                if stripped_line:
                    # Lọc bỏ thông báo ping UptimeRobot / Trình duyệt nếu có
                    if "Web server nhận được ping từ UptimeRobot" in stripped_line:
                        continue

                    vn_tz = timezone(timedelta(hours=7))
                    now_vn = datetime.now(vn_tz)
                    timestamp_short = now_vn.strftime('%H:%M:%S')
                    timestamp_full = now_vn.strftime('%Y-%m-%d %H:%M:%S')

                    formatted_line = f"[{timestamp_short}] {stripped_line}"
                    # Lưu vào RAM buffer phục vụ live Dashboard
                    log_buffer.append(formatted_line)

                    # Lưu bền vững vào Database
                    try:
                        from core.activity_logger import activity_logger
                        activity_logger.log_console(formatted_line)
                    except Exception:
                        pass

                    # Nếu là Error Log, lưu bền vững vào file logs/error.log
                    if is_error_log(stripped_line, self.is_stderr):
                        append_to_error_file(timestamp_full, stripped_line)

    def flush(self):
        self.original_stream.flush()

    def reconfigure(self, *args, **kwargs):
        if hasattr(self.original_stream, 'reconfigure'):
            self.original_stream.reconfigure(*args, **kwargs)

# Ép đầu ra của python flush ngay lập tức và hỗ trợ UTF-8 an toàn trên Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

# Chuyển hướng stdout và stderr sang redirector để hứng log
sys.stdout = LogStreamRedirector(sys.stdout, is_stderr=False)
sys.stderr = LogStreamRedirector(sys.stderr, is_stderr=True)

# Config variables
import pathlib
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# 1. BIẾN MÔI TRƯỜNG & KHÓA XÁC THỰC
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Khóa bảo mật & Mật khẩu Admin Web Console
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Crtm123123@")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "mikedabot_secure_session_key_2026_salt")

# ==========================================
# 2. CẤU HÌNH AI & MÔ HÌNH (CENTRALIZED AI CONFIG)
# ==========================================
try:
    from core.constants import (
        DEFAULT_GEMINI_DATA_MODEL,
        DEFAULT_GEMINI_SUMMARY_MODEL,
        DEFAULT_GEMINI_QA_MODEL,
        DEFAULT_GEMINI_TAROT_MODEL,
        DEFAULT_TAROT_FALLBACK_MODELS,
        DEFAULT_SUMMARY_TEMPERATURE,
        DEFAULT_QA_TEMPERATURE,
        DEFAULT_TAROT_TEMPERATURE,
        DEFAULT_SINGLE_PASS_MSG_LIMIT,
        DEFAULT_MAPREDUCE_CHUNK_SIZE,
        DEFAULT_DISCORD_EMBED_CHAR_LIMIT,
        MAX_FETCH_MESSAGES_LIMIT,
        DEFAULT_COMMAND_COOLDOWN_SECONDS,
        DEFAULT_SCAN_HOURS,
        DEFAULT_SCAN_LIMIT,
    )
except ImportError:
    DEFAULT_GEMINI_DATA_MODEL = "gemini-3.1-flash-lite"
    DEFAULT_GEMINI_SUMMARY_MODEL = "gemini-3.5-flash-lite"
    DEFAULT_GEMINI_QA_MODEL = "gemini-3.5-flash-lite"
    DEFAULT_GEMINI_TAROT_MODEL = "gemini-3.7-flash"
    DEFAULT_TAROT_FALLBACK_MODELS = [
        "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
        "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemma-4-31b-it"
    ]
    DEFAULT_SUMMARY_TEMPERATURE = 0.1
    DEFAULT_QA_TEMPERATURE = 0.3
    DEFAULT_TAROT_TEMPERATURE = 0.7
    DEFAULT_SINGLE_PASS_MSG_LIMIT = 300
    DEFAULT_MAPREDUCE_CHUNK_SIZE = 200
    DEFAULT_DISCORD_EMBED_CHAR_LIMIT = 3500
    MAX_FETCH_MESSAGES_LIMIT = 4000
    DEFAULT_COMMAND_COOLDOWN_SECONDS = 30.0
    DEFAULT_SCAN_HOURS = 2.0
    DEFAULT_SCAN_LIMIT = 150

# Model chính dùng cho xử lý dữ liệu nền, trích xuất dữ liệu thô (nhẹ, nhanh, tiết kiệm token)
GEMINI_DATA_MODEL = os.getenv("GEMINI_DATA_MODEL", DEFAULT_GEMINI_DATA_MODEL)

# Model dùng cho tóm tắt nội dung tin nhắn (Single-Pass & MapReduce Reduce)
GEMINI_SUMMARY_MODEL = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_SUMMARY_MODEL)

# Model dùng cho AI QA Evaluator tự động đánh giá và chấm điểm
GEMINI_QA_MODEL = os.getenv("GEMINI_QA_MODEL", DEFAULT_GEMINI_QA_MODEL)

# Model chuyên sâu dùng cho bốc và luận giải Tarot AI (Thinking / Deep Reasoning)
GEMINI_TAROT_MODEL = os.getenv("GEMINI_TAROT_MODEL", DEFAULT_GEMINI_TAROT_MODEL)

# Danh sách chuỗi Fallback mô hình dự phòng khi gặp quá tải (503 / 429 Quota Exceeded)
TAROT_FALLBACK_MODELS = [
    GEMINI_TAROT_MODEL,
    *[m for m in DEFAULT_TAROT_FALLBACK_MODELS if m != GEMINI_TAROT_MODEL]
]

# Tham số Generation
SUMMARY_TEMPERATURE = float(os.getenv("SUMMARY_TEMPERATURE", str(DEFAULT_SUMMARY_TEMPERATURE)))
QA_TEMPERATURE = float(os.getenv("QA_TEMPERATURE", str(DEFAULT_QA_TEMPERATURE)))
TAROT_TEMPERATURE = float(os.getenv("TAROT_TEMPERATURE", str(DEFAULT_TAROT_TEMPERATURE)))

# ==========================================
# 3. THAM SỐ XỬ LÝ DỮ LIỆU & GIỚI HẠN (LIMITS)
# ==========================================
SINGLE_PASS_MSG_LIMIT = int(os.getenv("SINGLE_PASS_MSG_LIMIT", str(DEFAULT_SINGLE_PASS_MSG_LIMIT)))
MAPREDUCE_CHUNK_SIZE = int(os.getenv("MAPREDUCE_CHUNK_SIZE", str(DEFAULT_MAPREDUCE_CHUNK_SIZE)))
DISCORD_EMBED_CHAR_LIMIT = int(os.getenv("DISCORD_EMBED_CHAR_LIMIT", str(DEFAULT_DISCORD_EMBED_CHAR_LIMIT)))
COMMAND_COOLDOWN_SECONDS = float(os.getenv("COMMAND_COOLDOWN_SECONDS", str(DEFAULT_COMMAND_COOLDOWN_SECONDS)))

DATA_DIR = pathlib.Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "bot_config.db"

# Cấu hình Turso Cloud SQLite (Persistent Cloud Storage)
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "libsql://mikebotdb-hoenmike.aws-ap-northeast-1.turso.io")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()

# Stats variables
start_time = datetime.now(timezone.utc)
summary_count = 0
active_interactions = set()
is_shutting_down = False
test_runs = []

