import os
import collections
from datetime import datetime, timezone, timedelta
import sys

# ==========================================
# 0. KHỞI TẠO BỘ ĐỆM LOG & CHUYỂN HƯỚNG OUTPUT
# ==========================================
log_buffer = collections.deque(maxlen=100)

class LogStreamRedirector:
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, data):
        self.original_stream.write(data)
        self.original_stream.flush()
        
        clean_data = data.strip()
        if clean_data:
            for line in clean_data.split('\n'):
                stripped_line = line.strip()
                if stripped_line:
                    vn_tz = timezone(timedelta(hours=7))
                    timestamp = datetime.now(vn_tz).strftime('%H:%M:%S')
                    log_buffer.append(f"[{timestamp}] {stripped_line}")

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
sys.stdout = LogStreamRedirector(sys.stdout)
sys.stderr = LogStreamRedirector(sys.stderr)

print("ℹ️ Hệ thống Logging và Dashboard Buffer đã hoạt động từ config.py.", flush=True)

# Config variables
import pathlib
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# 1. BIẾN MÔI TRƯỜNG & KHÓA XÁC THỰC
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ==========================================
# 2. CẤU HÌNH AI & MÔ HÌNH (CENTRALIZED AI CONFIG)
# ==========================================
# Model chính dùng cho tóm tắt nội dung (Single-Pass & MapReduce)
# Có thể đổi nhanh tại file .env (GEMINI_MODEL=...) hoặc chỉnh trực tiếp tại đây
GEMINI_SUMMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Model dùng cho AI QA Evaluator tự động đánh giá và chấm điểm
GEMINI_QA_MODEL = os.getenv("GEMINI_QA_MODEL", "gemini-3.5-flash-lite")

# Model dùng cho bốc và luận giải Tarot AI
GEMINI_TAROT_MODEL = os.getenv("GEMINI_TAROT_MODEL", GEMINI_SUMMARY_MODEL)

# Tham số Generation
SUMMARY_TEMPERATURE = float(os.getenv("SUMMARY_TEMPERATURE", "0.1"))
QA_TEMPERATURE = float(os.getenv("QA_TEMPERATURE", "0.3"))
TAROT_TEMPERATURE = float(os.getenv("TAROT_TEMPERATURE", "0.7"))

# ==========================================
# 3. THAM SỐ XỬ LÝ DỮ LIỆU & GIỚI HẠN (LIMITS)
# ==========================================
SINGLE_PASS_MSG_LIMIT = int(os.getenv("SINGLE_PASS_MSG_LIMIT", "300"))       # <= 300 msg: Single-Pass; > 300 msg: MapReduce
MAPREDUCE_CHUNK_SIZE = int(os.getenv("MAPREDUCE_CHUNK_SIZE", "200"))         # Kích thước chunk phân đoạn MapReduce
DISCORD_EMBED_CHAR_LIMIT = int(os.getenv("DISCORD_EMBED_CHAR_LIMIT", "3500")) # Giới hạn ký tự mỗi embed Discord
MAX_FETCH_MESSAGES_LIMIT = 2500   # Giới hạn trần quét tin nhắn tối đa
COMMAND_COOLDOWN_SECONDS = 30.0   # Cooldown lệnh Discord Slash Command
DEFAULT_SCAN_HOURS = 2.0
DEFAULT_SCAN_LIMIT = 150

DATA_DIR = pathlib.Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "bot_config.db"

# Stats variables
start_time = datetime.now(timezone.utc)
summary_count = 0
active_interactions = set()
is_shutting_down = False
test_runs = []
