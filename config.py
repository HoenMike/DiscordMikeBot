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

# Ép đầu ra của python flush ngay lập tức
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Chuyển hướng stdout và stderr sang redirector để hứng log
sys.stdout = LogStreamRedirector(sys.stdout)
sys.stderr = LogStreamRedirector(sys.stderr)

print("ℹ️ Hệ thống Logging và Dashboard Buffer đã hoạt động từ config.py.", flush=True)

# Config variables
from dotenv import load_dotenv
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Stats variables
start_time = datetime.now(timezone.utc)
summary_count = 0
active_interactions = set()
is_shutting_down = False
