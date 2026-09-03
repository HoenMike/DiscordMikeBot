# gunicorn.conf.py
import os

# Port to bind to
port = os.environ.get("PORT", "8080")
bind = f"0.0.0.0:{port}"

# Only use 1 worker process to avoid starting multiple Discord Bot threads
workers = 1

# Use threads for handling concurrent Flask requests
threads = 4

# Increase timeout to 120 seconds to prevent Gunicorn from killing the worker
# while the Discord bot is logging in and syncing slash commands
timeout = 120

# Keepalive connection timeout
keepalive = 5


def post_fork(server, worker):
    """
    Hook được Gunicorn gọi ngay sau khi Worker process được fork ra.
    Đây là vị trí chuẩn xác và an toàn nhất để kích hoạt Discord Bot thread:
    - Đảm bảo Bot và Flask cùng nằm chung trong 1 worker process memory.
    - Tránh việc bot bị mất luồng khi Master process fork.
    - Giúp Web Dashboard truy cập trực tiếp trạng thái live của Bot (bot.is_ready, guilds, latency).
    """
    server.log.info("🚀 [Gunicorn Worker %s] Đang khởi động Discord Bot worker thread...", worker.pid)
    import signal
    from app import ensure_bot_started, handle_sigterm
    try:
        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigterm)
    except Exception as sig_err:
        server.log.warning("⚠️ Không thể đăng ký signal handler trong worker: %s", sig_err)
    ensure_bot_started()


def on_exit(server):
    """Dọn dẹp khi Gunicorn tắt máy."""
    server.log.info("🔌 [Gunicorn on_exit] Máy chủ đang tắt hoàn tất.")
