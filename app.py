import os
import sys
import asyncio
import signal
import traceback
from threading import Thread, Lock

from bot_instance import bot
from web import app
from core.presence_manager import presence_manager

bot_started = False
bot_start_lock = Lock()


@bot.event
async def on_ready():
    print(f"🎉 Bot Discord đã kết nối thành công: {bot.user} (ID: {bot.user.id})", flush=True)
    # Khởi tạo trạng thái Presence động từ cấu hình
    try:
        await presence_manager.init_db(bot)
    except Exception as e:
        print(f"⚠️ [Presence] Lỗi khởi tạo presence on_ready: {e}", flush=True)


def run_discord_bot():
    """Khởi chạy Discord bot worker thread."""
    try:
        print("🤖 Bắt đầu chạy bot.run()...", flush=True)
        bot.run(config.DISCORD_TOKEN)
    except Exception as run_error:
        print(f"❌ Lỗi crash khi chạy bot.run(): {run_error}", flush=True)
        traceback.print_exc(file=sys.stdout)


def ensure_bot_started():
    """Khởi động bot Discord ngay lập tức khi ứng dụng được nạp."""
    global bot_started
    if not bot_started:
        with bot_start_lock:
            if not bot_started:
                bot_started = True
                print("🚀 [Bot Runner] Khởi động Discord Bot worker thread trong luồng phụ...", flush=True)
                bot_thread = Thread(target=run_discord_bot, daemon=True)
                bot_thread.start()


# Tự động kích hoạt bot ngay khi Gunicorn import module app.py
ensure_bot_started()


@app.before_request
def start_bot_on_first_request():
    """Safety net: Kích hoạt bot nếu vì lý do nào đó luồng chưa chạy."""
    ensure_bot_started()


# ==========================================
# GRACEFUL SHUTDOWN HANDLER
# ==========================================
async def graceful_shutdown():
    """Dọn dẹp an toàn các tiến trình trước khi tắt bot."""
    config.is_shutting_down = True
    print("👋 Bắt đầu quy trình tắt bot graceful...", flush=True)

    # Đổi trạng thái bot sang Đang Redeploy / Tắt
    try:
        await presence_manager.set_redeploying(bot)
    except Exception:
        pass

    wait_time = 0
    while config.active_interactions and wait_time < 15:
        print(f"⏳ Đang chờ {len(config.active_interactions)} lệnh dở hoàn thành... ({wait_time}s)", flush=True)
        await asyncio.sleep(1)
        wait_time += 1

    if config.active_interactions:
        print(f"⚠️ Hết thời gian chờ. Hủy bỏ {len(config.active_interactions)} lệnh còn lại...", flush=True)
        for interaction in list(config.active_interactions):
            try:
                print(f"   ↳ Gửi thông báo hủy lệnh tới user @{interaction.user.display_name}", flush=True)
                await interaction.followup.send(
                    "❌ Bot đang tái khởi động hệ thống. Vui lòng thực hiện lại lệnh sau 15-30 giây!",
                    ephemeral=True
                )
            except Exception as e:
                print(f"⚠️ Không thể gửi thông báo shutdown tới user: {e}", flush=True)

    try:
        await bot.close()
        print("🔌 Đã đóng kết nối bot Discord thành công.", flush=True)
    except Exception as e:
        print(f"⚠️ Lỗi khi đóng bot: {e}", flush=True)


def handle_sigterm(signum, frame):
    if config.is_shutting_down:
        return
    config.is_shutting_down = True
    print(f"📥 Nhận được tín hiệu tắt máy (signal {signum}). Đang tắt máy dọn dẹp...", flush=True)

    if bot.loop and bot.loop.is_running():
        future = asyncio.run_coroutine_threadsafe(graceful_shutdown(), bot.loop)
        try:
            future.result(timeout=20)
        except Exception as e:
            print(f"⚠️ Hết thời gian chờ hoặc xảy ra lỗi khi tắt bot: {e}", flush=True)

    print("☠️ Tiến trình kết thúc.", flush=True)
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)


if __name__ == "__main__":
    if not bot_started:
        bot_started = True
        print("🚀 [Local Mode] Khởi chạy Discord Bot ngay lập tức...", flush=True)
        bot_thread = Thread(target=run_discord_bot, daemon=True)
        bot_thread.start()

    port = int(os.environ.get("PORT", 8080))
    print(f"ℹ️ Khởi chạy Flask Server trên cổng {port}...", flush=True)
    app.run(host='0.0.0.0', port=port)
