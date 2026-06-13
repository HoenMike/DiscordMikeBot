import os
import discord
from discord.ext import commands
from google import genai
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from threading import Thread
from flask import Flask

# ==========================================
# 1. KHỞI TẠO SERVER WEB GIẢ LẬP (DÀNH CHO RENDER)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "🚀 Bot Discord đang chạy ngầm và hoạt động tốt!"

def run_web_server():
    # Render sẽ cấp một cổng thông qua biến môi trường PORT, mặc định là 8080 nếu chạy local
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Chạy server web trên một luồng (Thread) riêng biệt để không làm nghẽn Bot Discord"""
    t = Thread(target=run_web_server)
    t.start()

# ==========================================
# 2. CẤU HÌNH BOT DISCORD & AI GEMINI
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🎉 Bot tóm tắt đã kết nối thành công: {bot.user}")

@bot.command(name="tomtat")
async def tomtat(ctx, hours: float = 2.0):
    await ctx.send(f"⏳ Đang thu thập tin nhắn trong khoảng {hours} giờ qua, đợi xíu nhé...")

    now_utc = datetime.now(timezone.utc)
    start_time_utc = now_utc - timedelta(hours=hours)
    
    tz_vietnam = timezone(timedelta(hours=7))
    start_time_local = start_time_utc.astimezone(tz_vietnam)

    raw_messages = []
    
    # Giới hạn trần 300 tin nhắn để tránh quá tải bộ nhớ trên gói Free của Render
    async for msg in ctx.channel.history(after=start_time_utc, limit=300):
        if msg.id == ctx.message.id or msg.author.bot:
            continue
        raw_messages.append(f"{msg.author.display_name}: {msg.content}")

    if not raw_messages:
        await ctx.send(f"❌ Không tìm thấy tin nhắn nào trong {hours} giờ qua.")
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
        embed.add_field(name="Khoảng thời gian", value=f"{hours} giờ qua", inline=True)
        embed.add_field(name="Số tin nhắn quét được", value=f"{len(raw_messages)} tin nhắn", inline=True)
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author.display_name}")

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Lỗi: {e}")
        await ctx.send("❌ Đã xảy ra lỗi trong quá trình AI xử lý dữ liệu!")

# ==========================================
# 3. KÍCH HOẠT VÀ CHẠY ĐỒNG THỜI
# ==========================================
if __name__ == "__main__":
    # Kích hoạt server Web trước
    keep_alive()
    # Chạy Bot Discord sau
    bot.run(DISCORD_TOKEN)
