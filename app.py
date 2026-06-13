import os
import sys
import logging
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from threading import Thread
from flask import Flask

# ==========================================
# 0. CẤU HÌNH LOGGING & UNBUFFERED OUTPUT
# ==========================================
# Cấu hình logging để in thẳng ra stdout lập tức (Render Logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Ép đầu ra của python flush ngay lập tức
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("ℹ️ Hệ thống Logging đã được kích hoạt.", flush=True)

# ==========================================
# 1. KHỞI TẠO SERVER WEB (Flask)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    print("ℹ️ Web server nhận được ping từ UptimeRobot hoặc trình duyệt.", flush=True)
    return "🚀 Bot Discord đang chạy ngầm và hoạt động tốt!"

# ==========================================
# 2. CẤU HÌNH BOT DISCORD & AI GEMINI / GEMMA
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print(f"ℹ️ [Cấu hình] DISCORD_TOKEN: {'Đã nhập (Độ dài: ' + str(len(DISCORD_TOKEN)) + ')' if DISCORD_TOKEN else 'TRỐNG (None)'}", flush=True)
print(f"ℹ️ [Cấu hình] GEMINI_API_KEY: {'Đã nhập (Độ dài: ' + str(len(GEMINI_API_KEY)) + ')' if GEMINI_API_KEY else 'TRỐNG (None)'}", flush=True)

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

class SummaryBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("🔄 Đang đồng bộ hóa Slash Commands...", flush=True)
        try:
            synced = await self.tree.sync()
            print(f"🎉 Đã đồng bộ hóa {len(synced)} Slash Commands toàn cầu thành công!", flush=True)
        except Exception as sync_error:
            print(f"❌ Lỗi khi đồng bộ hóa Slash Commands: {sync_error}", flush=True)
            traceback.print_exc(file=sys.stdout)

bot = SummaryBot()

@bot.event
async def on_ready():
    print(f"🎉 Bot tóm tắt đã kết nối thành công: {bot.user}", flush=True)

# Lệnh Slash Command /tomtat
@bot.tree.command(name="tomtat", description="Tóm tắt nội dung cuộc trò chuyện trong một kênh")
@app_commands.describe(
    channel="Kênh chat cần tóm tắt (Mặc định là kênh hiện tại)",
    hours="Số giờ trước cần tóm tắt (Mặc định là 2.0 giờ)"
)
async def tomtat(interaction: discord.Interaction, channel: discord.TextChannel = None, hours: float = 2.0):
    await interaction.response.defer(ephemeral=False)
    
    target_channel = channel or interaction.channel
    
    # Gửi thông báo tạm thời ban đầu
    followup_msg = await interaction.followup.send(
        f"⏳ Đang thu thập tin nhắn trong kênh {target_channel.mention} trong {hours} giờ qua, đợi xíu nhé..."
    )

    now_utc = datetime.now(timezone.utc)
    start_time_utc = now_utc - timedelta(hours=hours)

    raw_messages = []
    
    # Giới hạn trần 300 tin nhắn để tránh quá tải bộ nhớ trên gói Free của Render
    async for msg in target_channel.history(after=start_time_utc, limit=300):
        if msg.author.bot:
            continue
        raw_messages.append(f"{msg.author.display_name}: {msg.content}")

    if not raw_messages:
        await interaction.followup.send(f"❌ Không tìm thấy tin nhắn nào trong kênh {target_channel.mention} trong {hours} giờ qua.")
        return

    chat_history_text = "\n".join(raw_messages)

    prompt = f"""
    Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp. 
    Dưới đây là lịch sử trò chuyện của một nhóm chat trong vòng {hours} giờ qua. 
    Hãy tóm tắt lại nội dung cuộc trò chuyện này một cách ngắn gọn, súc tích và dễ hiểu bằng Tiếng Việt.
    
    Yêu cầu:
    - Nêu rõ các chủ đề chính mà mọi người đang thảo luận.
    - Nếu có kết luận hoặc thống nhất nào quan trọng, hãy liệt kê ra.
    - Giữ độ dài bài tóm tắt ngắn gọn (dưới 1500 ký tự).
    
    Dữ liệu trò chuyện:
    \"\"\"
    {chat_history_text}
    \"\"\"
    """

    try:
        response = ai_client.models.generate_content(
            model='gemma-4-31b-it',
            contents=prompt,
        )
        summary_result = response.text

        embed = discord.Embed(
            title="📝 TÓM TẮT CUỘC TRÒ CHUYỆN",
            description=summary_result,
            color=discord.Color.green()
        )
        embed.add_field(name="Kênh chat", value=target_channel.mention, inline=True)
        embed.add_field(name="Khoảng thời gian", value=f"{hours} giờ qua", inline=True)
        embed.add_field(name="Số tin nhắn quét được", value=f"{len(raw_messages)} tin nhắn", inline=True)
        embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)
        try:
            await followup_msg.delete()
            print("ℹ️ Đã xóa thông báo tạm thời sau khi tóm tắt xong.", flush=True)
        except Exception as delete_error:
            print(f"⚠️ Không xóa được thông báo tải: {delete_error}", flush=True)

    except Exception as e:
        print(f"❌ Lỗi trong quá trình xử lý lệnh /tomtat: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        try:
            await interaction.followup.send("❌ Đã xảy ra lỗi trong quá trình AI xử lý dữ liệu!")
        except Exception as send_error:
            print(f"⚠️ Không thể gửi thông báo lỗi đến Discord: {send_error}", flush=True)

# ==========================================
# 3. KÍCH HOẠT VÀ CHẠY ĐỒNG THỜI
# ==========================================
def run_discord_bot():
    try:
        print("🤖 Bắt đầu chạy bot.run()...", flush=True)
        bot.run(DISCORD_TOKEN)
    except Exception as run_error:
        print(f"❌ Lỗi crash khi chạy bot.run(): {run_error}", flush=True)
        traceback.print_exc(file=sys.stdout)

# Khởi chạy luồng chạy Bot Discord ngay khi module được import (hỗ trợ cả Gunicorn)
print("🚀 Khởi chạy Discord Bot trong luồng phụ...", flush=True)
bot_thread = Thread(target=run_discord_bot)
bot_thread.daemon = True
bot_thread.start()

if __name__ == "__main__":
    # Nếu chạy cục bộ: `python app.py`
    port = int(os.environ.get("PORT", 8080))
    print(f"ℹ️ Khởi chạy Flask Server trên cổng {port}...", flush=True)
    app.run(host='0.0.0.0', port=port)
