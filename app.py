import os
import sys
import logging
import traceback
import collections
import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import asyncio
import signal
from threading import Thread
from flask import Flask, jsonify, render_template_string

# ==========================================
# 0. KHỞI TẠO BỘ ĐỆM LOG & CHUYỂN HƯỚNG OUTPUT
# ==========================================
# Lưu trữ tối đa 100 dòng log gần nhất để hiển thị lên Web Dashboard
log_buffer = collections.deque(maxlen=100)

class LogStreamRedirector:
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, data):
        # Viết vào luồng console gốc để vẫn hiện trên Render logs
        self.original_stream.write(data)
        self.original_stream.flush()
        
        # Làm sạch và đưa vào log_buffer của Dashboard
        clean_data = data.strip()
        if clean_data:
            for line in clean_data.split('\n'):
                stripped_line = line.strip()
                if stripped_line:
                    # Tạo mốc thời gian (Múi giờ Việt Nam UTC+7)
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

# Cấu hình logging cơ bản của Python trỏ ra stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

print("ℹ️ Hệ thống Logging và Dashboard Buffer đã hoạt động.", flush=True)

# ==========================================
# 1. CẤU HÌNH BOT DISCORD & AI GEMINI / GEMMA
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print(f"ℹ️ [Cấu hình] DISCORD_TOKEN: {'Đã nhập (Độ dài: ' + str(len(DISCORD_TOKEN)) + ')' if DISCORD_TOKEN else 'TRỐNG (None)'}", flush=True)
print(f"ℹ️ [Cấu hình] GEMINI_API_KEY: {'Đã nhập (Độ dài: ' + str(len(GEMINI_API_KEY)) + ')' if GEMINI_API_KEY else 'TRỐNG (None)'}", flush=True)

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

# Thống kê hoạt động
start_time = datetime.now(timezone.utc)
summary_count = 0

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

# Quản lý trạng thái tắt máy (Graceful Shutdown)
active_interactions = set()
is_shutting_down = False

def split_text(text, limit=3500):
    chunks = []
    current_chunk = []
    current_length = 0
    for line in text.split('\n'):
        # +1 cho ký tự xuống dòng
        if current_length + len(line) + 1 > limit:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    return chunks

@bot.event
async def on_ready():
    print(f"🎉 Bot tóm tắt đã kết nối thành công: {bot.user}", flush=True)

# Lệnh Slash Command /tomtat
@bot.tree.command(name="tomtat", description="Tóm tắt nội dung cuộc trò chuyện trong một kênh")
@app_commands.describe(
    channel="Kênh chat cần tóm tắt (Mặc định là kênh hiện tại)",
    hours="Quét tin nhắn trong X giờ qua (Ví dụ: 2.0)",
    limit="Giới hạn số lượng tin nhắn quét tối đa (Ví dụ: 100)",
    summary_type="Kiểu tóm tắt: Ngắn gọn hoặc Chi tiết kèm Timeline",
    focus="Chủ đề hoặc từ khóa cần tập trung phân tích sâu (Ví dụ: drama, lỗi deploy, game mới)"
)
@app_commands.choices(summary_type=[
    app_commands.Choice(name="Tóm tắt ngắn gọn (Mặc định)", value="short"),
    app_commands.Choice(name="Tóm tắt dài & Timeline chi tiết", value="long")
])
@app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
async def tomtat(
    interaction: discord.Interaction, 
    channel: discord.TextChannel = None, 
    hours: float = None, 
    limit: int = None,
    summary_type: str = "short",
    focus: str = None
):
    global is_shutting_down
    if is_shutting_down:
        await interaction.response.send_message(
            "❌ Bot đang được cập nhật hoặc tái khởi động hệ thống. Vui lòng thực hiện lại lệnh sau 15-30 giây!",
            ephemeral=True
        )
        return

    # Kiểm tra giới hạn trị số đầu vào để tránh quá tải quota của AI
    if hours is not None and (hours <= 0 or hours > 168.0):
        await interaction.response.send_message(
            "❌ Số giờ quét phải lớn hơn 0 và không được vượt quá 168.0 giờ (7 ngày)!",
            ephemeral=True
        )
        return

    if limit is not None and (limit <= 0 or limit > 500):
        await interaction.response.send_message(
            "❌ Số lượng tin nhắn quét phải lớn hơn 0 và không được vượt quá 500 tin nhắn!",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    active_interactions.add(interaction)
    
    target_channel = channel or interaction.channel
    
    # Xác định các giá trị mặc định nếu người dùng bỏ trống
    if hours is None and limit is None:
        hours = 2.0
        limit = 100
        scan_info = "100 tin nhắn trong 2.0 giờ qua"
    elif hours is not None and limit is None:
        limit = 300  # Giới hạn trần an toàn khi lọc theo giờ
        scan_info = f"tin nhắn trong {hours} giờ qua"
    elif limit is not None and hours is None:
        scan_info = f"{limit} tin nhắn gần nhất"
    else:
        scan_info = f"tối đa {limit} tin nhắn trong {hours} giờ qua"

    clean_focus = None
    if focus and focus.strip() and focus.strip().lower() not in ["none", "null", "undefined"]:
        clean_focus = focus.strip()

    print(f"📥 [Lệnh nhận] /tomtat được gọi bởi @{interaction.user.display_name} tại kênh #{target_channel.name}", flush=True)
    print(f"   ↳ Tham số quét: hours={hours}, limit={limit}, kiểu='{summary_type}', focus='{clean_focus}'", flush=True)

    # Gửi thông báo tạm thời ban đầu (rút gọn)
    mode_info = "Tóm tắt ngắn gọn" if summary_type == "short" else "Tóm tắt dài & Timeline chi tiết"
    focus_info = f" | Tập trung: `{clean_focus}`" if clean_focus else ""
    followup_msg = await interaction.followup.send(
        f"⏳ Đang thu thập và phân tích dữ liệu tại {target_channel.mention} (chế độ: *{mode_info}*{focus_info}). Vui lòng đợi một lát..."
    )

    vn_tz = timezone(timedelta(hours=7))
    raw_messages = []
    
    try:
        print(f"⏳ Đang tải lịch sử kênh #{target_channel.name}...", flush=True)
        # Giới hạn tối đa tin nhắn quét để tránh quá tải quota của AI
        max_limit = min(limit, 500) if limit is not None else 300
        
        # Xác định mốc thời gian lọc
        start_time_utc = None
        if hours is not None:
            now_utc = datetime.now(timezone.utc)
            start_time_utc = now_utc - timedelta(hours=hours)
            
        # Quét từ mới nhất trở về trước
        async for msg in target_channel.history(limit=max_limit):
            if start_time_utc and msg.created_at < start_time_utc:
                break
            if msg.author.bot:
                continue
            local_time = msg.created_at.astimezone(vn_tz).strftime('%d/%m %H:%M')
            # Lưu kèm theo created_at để sắp xếp theo trình tự thời gian (cũ -> mới) sau đó
            raw_messages.append((msg.created_at, f"[{local_time}] {msg.author.display_name}: {msg.content}"))
            
        # Sắp xếp lại từ cũ đến mới để AI hiểu dòng thời gian hội thoại đúng trình tự
        raw_messages.sort(key=lambda x: x[0])
        raw_messages = [item[1] for item in raw_messages]

    except Exception as fetch_error:
        print(f"❌ Lỗi khi tải lịch sử chat: {fetch_error}", flush=True)
        traceback.print_exc(file=sys.stdout)
        await interaction.followup.send("❌ Không thể tải lịch sử kênh chat. Hãy kiểm tra quyền hạn của bot!")
        active_interactions.discard(interaction)
        return

    print(f"✅ Đã tải xong: Đọc được {len(raw_messages)} tin nhắn thích hợp.", flush=True)

    if not raw_messages:
        print(f"⚠️ Hủy bỏ: Không tìm thấy tin nhắn nào trong kênh #{target_channel.name} để tóm tắt.", flush=True)
        await interaction.followup.send(f"❌ Không tìm thấy tin nhắn nào thỏa mãn điều kiện quét ({scan_info}) tại kênh {target_channel.mention}.")
        active_interactions.discard(interaction)
        return

    chat_history_text = "\n".join(raw_messages)

    focus_instruction = ""
    if clean_focus:
        focus_instruction = f"""
        ⚠️ BẮT BUỘC TẬP TRUNG SÂU (FOCUS): Người dùng yêu cầu tập trung phân tích đặc biệt sâu vào chủ đề/câu chuyện: "{clean_focus}".
        Yêu cầu:
        1. Trọng tâm toàn bộ bài tóm tắt phải hướng về chủ đề này.
        2. Dành phần lớn nội dung của cả phần Tổng quan, Timeline và Kết luận để làm rõ diễn biến, các tình tiết, ý kiến, tranh luận và phản ứng của các thành viên xoay quanh câu chuyện này.
        3. Các đoạn hội thoại khác không liên quan đến chủ đề "{clean_focus}" hãy bỏ qua hoặc chỉ tóm tắt cực kỳ ngắn gọn (1-2 câu) để tránh làm loãng thông tin.
        """

    if summary_type == "long":
        prompt = f"""
        Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp. 
        Dưới đây là lịch sử trò chuyện của một nhóm chat ({scan_info}). 
        Hãy tóm tắt lại nội dung cuộc trò chuyện này một cách CHI TIẾT, ĐẦY ĐỦ và THÔNG MINH nhất bằng Tiếng Việt.

        {focus_instruction}

        Yêu cầu nghiêm ngặt về định dạng và cấu trúc (BẮT BUỘC TUÂN THỦ):
        - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu (ví dụ: "Dưới đây là...", "Đây là tóm tắt...") hay lời chào kết, cảm ơn xã giao ở cuối. Đi thẳng vào nội dung chính.
        - ĐỘ DÀI BÀI VIẾT: Dưới 3500 ký tự. Viết cô đọng, súc tích, tránh rườm rà hay lặp từ.
        - BỐ CỤC BÀI VIẾT:
          1. **TỔNG QUAN CHỦ ĐỀ**: Tóm tắt ngắn gọn các chủ đề chính đang được thảo luận và không khí chung của cuộc trò chuyện.
          2. **TIMELINE DIỄN BIẾN**:
             - PHÂN CHIA THEO NGÀY: Nếu lịch sử trò chuyện kéo dài nhiều ngày, bạn PHẢI nhóm các timeline theo từng ngày. Dù chỉ có 1 ngày duy nhất hay nhiều ngày, bạn đều phải sử dụng cấu trúc nhóm theo ngày.
             - Mỗi ngày bắt đầu bằng tiêu đề định dạng: `### 📅 NGÀY DD/MM` (Ví dụ: `### 📅 NGÀY 09/06`).
             - GIỮA CÁC NGÀY KHÁC NHAU: Phải ngăn cách bằng một dòng kẻ ngang markdown `---` (để phân tách rõ ràng).
             - CÁC MỐC THỜI GIAN TRONG NGÀY: Sắp xếp theo trình tự THỜI GIAN ĐẢO NGƯỢC (mốc mới nhất lên đầu ngày, mốc cũ hơn xuống dưới).
             - GỘP TIN NHẮN THÔNG MINH: KHÔNG liệt kê máy móc từng tin nhắn riêng lẻ. Hãy gộp nhóm các tin nhắn diễn ra liên tục/gần nhau (cùng một cuộc đối thoại hoặc chủ đề) thành một mốc thời gian.
             - CHỈ TẬP TRUNG vào những khoảng thời gian mọi người hoạt động nhiều (lúc thảo luận sôi nổi). Tránh liệt kê các tin nhắn đơn lẻ, tán gẫu xã giao vô thưởng vô phạt hoặc các mốc thời gian không có hoạt động đáng kể.
             - ĐỊNH DẠNG MỐC THỜI GIAN: Vì tiêu đề ngày đã có `DD/MM`, mốc thời gian ở các gạch đầu dòng CHỈ ghi giờ và phút.
               Định dạng: `- [Giờ_bắt_đầu - Giờ_kết_thúc] @ThànhViên1, @ThànhViên2: Nội dung tóm tắt diễn biến.` (hoặc `- [Giờ:Phút]` nếu chỉ là 1 mốc ngắn).
               Ví dụ: `- [15:31 - 15:34] @Subeo, @Mike: Thảo luận về quán trà sữa Koi Thé.` (Tuyệt đối KHÔNG ghi `- [09/06 15:31 - 15:34]`).

          3. **KẾT LUẬN & QUYẾT ĐỊNH**: Tóm tắt ngắn gọn các quyết định, thống nhất hoặc công việc được chốt lại (nếu có).
        
        Dữ liệu trò chuyện (mốc thời gian Việt Nam [Ngày/Tháng Giờ:Phút]):
        \"\"\"
        {chat_history_text}
        \"\"\"
        """
    else:
        prompt = f"""
        Bạn là một trợ lý ảo quản lý cộng đồng Discord chuyên nghiệp. 
        Dưới đây là lịch sử trò chuyện của một nhóm chat ({scan_info}). 
        Hãy tóm tắt lại nội dung cuộc trò chuyện này một cách NGẮN GỌN, SÚC TÍCH và DỄ HIỂU nhất bằng Tiếng Việt.

        {focus_instruction}

        Yêu cầu cấu trúc (BẮT BUỘC TUÂN THỦ):
        - TUYỆT ĐỐI KHÔNG chứa lời chào, lời mở đầu hay lời kết luận xã giao. Đi thẳng vào nội dung tóm tắt.
        - Giữ độ dài bài tóm tắt ngắn gọn, súc tích (dưới 1000 ký tự).
        - Tóm tắt các chủ đề chính đang thảo luận dưới dạng các gạch đầu dòng ngắn gọn.
        - Liệt kê các quyết định, kết luận quan trọng (nếu có).
        
        Dữ liệu trò chuyện (mốc thời gian Việt Nam [Ngày/Tháng Giờ:Phút]):
        \"\"\"
        {chat_history_text}
        \"\"\"
        """

    try:
        print(f"🧠 Đang gửi dữ liệu đến AI Gemma 4 để phân tích (không chặn event loop)...", flush=True)
        response = await asyncio.to_thread(
            ai_client.models.generate_content,
            model='gemma-4-31b-it',
            contents=prompt,
        )
        summary_result = response.text
        
        title_str = "📝 TÓM TẮT CHI TIẾT & TIMELINE" if summary_type == "long" else "📝 TÓM TẮT CUỘC TRÒ CHUYỆN"
        embed_color = discord.Color.blue() if summary_type == "long" else discord.Color.green()

        # Chia nhỏ kết quả thành nhiều phần nếu vượt quá giới hạn hiển thị của Discord
        chunks = split_text(summary_result, limit=3500)
        
        for i, chunk in enumerate(chunks):
            part_title = title_str
            if len(chunks) > 1:
                part_title += f" (Phần {i+1}/{len(chunks)})"
            
            embed = discord.Embed(
                title=part_title,
                description=chunk,
                color=embed_color
            )
            
            # Chỉ đính kèm chủ đề tập trung vào phần đầu tiên nếu có sử dụng
            if i == 0 and clean_focus:
                embed.add_field(name="Chủ đề tập trung (Focus)", value=f"`{clean_focus}`", inline=False)
            
            embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")
            
            # Tag người dùng đã yêu cầu ở tin nhắn đầu tiên để họ nhận thông báo
            content = f"🔔 {interaction.user.mention} Đã tóm tắt xong cuộc trò chuyện!" if i == 0 else None
            await interaction.followup.send(content=content, embed=embed)

        print(f"🎉 Tóm tắt thành công! Đã gửi {len(chunks)} Embed tới kênh #{target_channel.name}.", flush=True)

        # Tăng số lần tóm tắt thành công
        global summary_count
        summary_count += 1
        
        try:
            await followup_msg.delete()
            print("ℹ️ Đã xóa thông báo tạm thời sau khi gửi tóm tắt.", flush=True)
        except Exception as delete_error:
            print(f"⚠️ Không xóa được thông báo tải: {delete_error}", flush=True)

        active_interactions.discard(interaction)

    except Exception as e:
        print(f"❌ Lỗi trong quá trình xử lý lệnh /tomtat: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        try:
            await interaction.followup.send("❌ Đã xảy ra lỗi trong quá trình AI xử lý dữ liệu!")
        except Exception as send_error:
            print(f"⚠️ Không thể gửi thông báo lỗi đến Discord: {send_error}", flush=True)
        active_interactions.discard(interaction)

@tomtat.error
async def tomtat_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Bạn đang thao tác quá nhanh! Vui lòng đợi {round(error.retry_after, 1)} giây trước khi thử lại.",
            ephemeral=True
        )
    else:
        print(f"❌ Lỗi khi thực thi Slash Command /tomtat: {error}", flush=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi khi thực thi lệnh!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Đã xảy ra lỗi khi thực thi lệnh!", ephemeral=True)
        except Exception as send_error:
            print(f"⚠️ Không thể gửi thông báo lỗi: {send_error}", flush=True)

# ==========================================
# 2. KHỞI TẠO WEB DASHBOARD (Flask)
# ==========================================
app = Flask('')

bot_started = False

@app.before_request
def start_bot_on_first_request():
    global bot_started
    if not bot_started:
        bot_started = True
        print("🚀 [Gunicorn Worker] Nhận request đầu tiên, bắt đầu khởi chạy Discord Bot trong luồng phụ...", flush=True)
        bot_thread = Thread(target=run_discord_bot)
        bot_thread.daemon = True
        bot_thread.start()

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MikeDaBot - Discord Summary Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0b0f19;
            --bg-secondary: #151d30;
            --bg-card: rgba(26, 36, 57, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-purple: #8b5cf6;
            --accent-blue: #3b82f6;
            --status-online: #10b981;
            --status-offline: #ef4444;
            --terminal-bg: #05070c;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden; /* Khóa cuộn trang chính */
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(139, 92, 246, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(59, 130, 246, 0.12) 0%, transparent 40%);
        }

        header {
            padding: 1rem 2rem;
            height: 70px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            background: rgba(11, 15, 25, 0.8);
            backdrop-filter: blur(12px);
            z-index: 10;
        }

        .logo-section {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .bot-avatar {
            width: 42px;
            height: 42px;
            background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
            box-shadow: 0 4px 15px rgba(139, 92, 246, 0.2);
        }

        h1 {
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, #ffffff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.4rem 0.8rem;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            font-size: 0.8rem;
            font-weight: 500;
        }

        .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }

        .dot.online {
            background-color: var(--status-online);
            box-shadow: 0 0 10px var(--status-online);
            animation: pulse 2s infinite;
        }

        .dot.offline {
            background-color: var(--status-offline);
            box-shadow: 0 0 10px var(--status-offline);
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        main {
            flex: 1;
            max-width: 1600px;
            width: 100%;
            margin: 0 auto;
            padding: 1.5rem 2rem;
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 1.5rem;
            height: calc(100vh - 70px);
            overflow: hidden; /* Khóa cuộn container chính */
        }

        @media (max-width: 1024px) {
            main {
                grid-template-columns: 1fr;
                height: calc(100vh - 70px);
                overflow-y: auto; /* Cho phép cuộn trên mobile */
            }
            body {
                overflow: auto;
                height: auto;
            }
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
            height: 100%;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.25rem;
            backdrop-filter: blur(12px);
            transition: all 0.3s ease;
        }

        .card:hover {
            border-color: rgba(139, 92, 246, 0.2);
        }

        .card.flex-card {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.75rem;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 0.85rem;
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .stat-label {
            font-size: 0.7rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stat-value {
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .stat-value.green { color: var(--status-online); }
        .stat-value.purple { color: #c084fc; }
        .stat-value.sky { color: #38bdf8; }

        .info-title {
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #f1f5f9;
        }

        .info-row-container {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 0.5rem;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 0.6rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-size: 0.8rem;
        }

        .info-row:last-child {
            border-bottom: none;
        }

        .info-label {
            color: var(--text-secondary);
        }

        .info-value {
            font-weight: 500;
            color: #e2e8f0;
        }

        .sidebar-footer {
            margin-top: auto;
            padding-top: 0.75rem;
            text-align: center;
            font-size: 0.7rem;
            color: var(--text-secondary);
            border-top: 1px solid rgba(255, 255, 255, 0.04);
        }

        .console-container {
            display: flex;
            flex-direction: column;
            height: 100%;
            overflow: hidden;
        }

        .console-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1.25rem;
            background: #111827;
            border: 1px solid var(--border-color);
            border-bottom: none;
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
        }

        .console-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.8rem;
            font-weight: 600;
            color: #94a3b8;
        }

        .live-indicator {
            display: flex;
            align-items: center;
            gap: 0.25rem;
            font-size: 0.7rem;
            color: var(--status-online);
            font-weight: 500;
            text-transform: uppercase;
        }

        .live-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background-color: var(--status-online);
            animation: blink 1.5s infinite;
        }

        @keyframes blink {
            0%, 100% { opacity: 0.2; }
            50% { opacity: 1; }
        }

        .console-body {
            flex: 1;
            background-color: var(--terminal-bg);
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 16px;
            border-bottom-right-radius: 16px;
            padding: 1.25rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.8rem;
            line-height: 1.5;
            overflow-y: auto;
            color: #38bdf8;
            box-shadow: inset 0 4px 20px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }

        .log-line {
            word-break: break-all;
            white-space: pre-wrap;
        }

        .log-timestamp {
            color: #64748b;
            margin-right: 0.5rem;
        }

        .log-info { color: #38bdf8; }
        .log-warn { color: #f59e0b; }
        .log-error { color: #ef4444; }
        .log-success { color: #10b981; }

        .btn-action {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.3rem 0.6rem;
            border-radius: 6px;
            font-size: 0.7rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn-action.copy:hover {
            background: var(--accent-purple);
            border-color: var(--accent-purple);
        }

        .btn-action.clear:hover {
            background: var(--status-offline);
            border-color: var(--status-offline);
        }
    </style>
</head>
<body>

    <header>
        <div class="logo-section">
            <div class="bot-avatar">🤖</div>
            <div>
                <h1 id="header-bot-name">MikeDaBot</h1>
                <p style="font-size: 0.7rem; color: var(--text-secondary);">Gemma 4 Summary Agent</p>
            </div>
        </div>
        <div class="status-badge">
            <span id="header-status-dot" class="dot offline"></span>
            <span id="header-status-text">Đang kết nối...</span>
        </div>
    </header>

    <main>
        <div class="sidebar">
            <div class="card">
                <div class="info-title">📊 Trạng thái Hệ thống</div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <span class="stat-label">Uptime</span>
                        <span id="stat-uptime" class="stat-value">00h 00m 00s</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">Độ trễ API</span>
                        <span id="stat-latency" class="stat-value">N/A</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">Số Máy Chủ</span>
                        <span id="stat-guilds" class="stat-value">0</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">Thành Viên</span>
                        <span id="stat-users" class="stat-value">0</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">Đã tóm tắt</span>
                        <span id="stat-summaries" class="stat-value purple">0</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-label">RAM Sử Dụng</span>
                        <span id="stat-ram" class="stat-value sky">0.0 MB</span>
                    </div>
                </div>
            </div>

            <div class="card flex-card">
                <div class="info-title">⚙️ Thông tin Cấu hình</div>
                <div class="info-row-container">
                    <div class="info-row">
                        <span class="info-label">Trí tuệ nhân tạo</span>
                        <span class="info-value">Gemma 4</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Model ID</span>
                        <span class="info-value">gemma-4-31b-it</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Lệnh Slash</span>
                        <span class="info-value">/tomtat</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Nền tảng / OS</span>
                        <span id="info-os" class="info-value">Loading...</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Python Version</span>
                        <span class="info-value">3.14.3</span>
                    </div>
                </div>
                <div class="sidebar-footer">
                    <p>© 2026 MikeDaBot - Made with ❤️</p>
                </div>
            </div>
        </div>

        <div class="console-container">
            <div class="console-header">
                <div class="console-title">
                    <span>💻 Console Logs</span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <button class="btn-action copy" onclick="copyConsoleLogs()">Sao chép log</button>
                    <button class="btn-action clear" onclick="clearConsoleLogs()">Xóa log</button>
                    <div class="live-indicator" style="margin-left: 0.5rem;">
                        <span class="live-dot"></span>
                        <span>Live</span>
                    </div>
                </div>
            </div>
            <div id="console-body" class="console-body">
                <div class="log-line"><span class="log-timestamp">[--:--:--]</span> Đang tải log từ máy chủ...</div>
            </div>
        </div>
    </main>

    <script>
        let autoScroll = true;
        const consoleBody = document.getElementById('console-body');

        // Phát hiện cuộn chuột để khóa auto scroll
        consoleBody.addEventListener('scroll', () => {
            const threshold = 40; 
            const isAtBottom = consoleBody.scrollHeight - consoleBody.clientHeight - consoleBody.scrollTop < threshold;
            autoScroll = isAtBottom;
        });

        function formatLogLine(line) {
            if (!line || typeof line !== 'string') return '';
            
            const timestampMatch = line.match(/^\[\d{2}:\d{2}:\d{2}\]/);
            let timestamp = "";
            let content = line;

            if (timestampMatch) {
                timestamp = timestampMatch[0];
                content = line.substring(timestamp.length).trim();
            }

            let styleClass = "log-info";
            
            if (content.includes("❌") || content.includes("Lỗi") || content.includes("error") || content.includes("Exception") || content.includes("[ERROR]")) {
                styleClass = "log-error";
            } else if (content.includes("⚠️") || content.includes("warning") || content.includes("[WARNING]")) {
                styleClass = "log-warn";
            } else if (content.includes("🎉") || content.includes("thành công") || content.includes("success") || content.includes("success!")) {
                styleClass = "log-success";
            }

            return `<div class="log-line"><span class="log-timestamp">${timestamp}</span><span class="${styleClass}">${escapeHtml(content)}</span></div>`;
        }

        function escapeHtml(unsafe) {
            if (!unsafe) return '';
            return unsafe
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
        }

        function copyConsoleLogs() {
            const lines = Array.from(consoleBody.querySelectorAll('.log-line'))
                .map(el => el.textContent)
                .join('\n');
            navigator.clipboard.writeText(lines).then(() => {
                alert("Đã sao chép toàn bộ logs vào Clipboard!");
            }).catch(err => {
                console.error("Không thể sao chép logs: ", err);
            });
        }

        async function clearConsoleLogs() {
            if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ logs trên máy chủ không?")) {
                return;
            }
            try {
                const response = await fetch('/api/logs/clear', { method: 'POST' });
                if (response.ok) {
                    consoleBody.innerHTML = '<div class="log-line"><span class="log-timestamp">[--:--:--]</span> Logs đã được xóa sạch.</div>';
                } else {
                    alert("Không thể xóa logs trên máy chủ.");
                }
            } catch (err) {
                console.error("Lỗi khi xóa logs: ", err);
                alert("Lỗi kết nối khi xóa logs.");
            }
        }

        async function updateDashboard() {
            try {
                const response = await fetch('/api/stats');
                if (!response.ok) {
                    throw new Error("HTTP error " + response.status);
                }
                const data = await response.json();

                // Cập nhật trạng thái
                const isOnline = data.bot_status === "Online";
                const statusDot = document.getElementById('header-status-dot');
                const statusText = document.getElementById('header-status-text');

                if (isOnline) {
                    statusDot.className = "dot online";
                    statusText.textContent = "Online";
                } else {
                    statusDot.className = "dot offline";
                    statusText.textContent = "Offline";
                }

                if (data.bot_name !== "N/A" && data.bot_name) {
                    document.getElementById('header-bot-name').textContent = data.bot_name;
                }

                // Cập nhật giá trị
                document.getElementById('stat-latency').textContent = data.latency;
                document.getElementById('stat-guilds').textContent = data.guilds;
                document.getElementById('stat-users').textContent = data.total_users;
                document.getElementById('stat-summaries').textContent = data.summaries;
                document.getElementById('stat-uptime').textContent = data.uptime;
                document.getElementById('stat-ram').textContent = data.ram_usage;
                document.getElementById('info-os').textContent = data.os_info;

                // Cập nhật logs
                if (data.logs && data.logs.length > 0) {
                    consoleBody.innerHTML = data.logs.map(formatLogLine).join('');
                    if (autoScroll) {
                        consoleBody.scrollTop = consoleBody.scrollHeight;
                    }
                } else {
                    consoleBody.innerHTML = '<div class="log-line"><span class="log-timestamp">[--:--:--]</span> Không có log nào.</div>';
                }

            } catch (error) {
                console.error("Error updating dashboard:", error);
                document.getElementById('header-status-dot').className = "dot offline";
                document.getElementById('header-status-text').textContent = "Lỗi kết nối API";
            }
        }

        // Chạy ngay lập tức và thăm dò mỗi 3 giây
        updateDashboard();
        setInterval(updateDashboard, 3000);
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    print("ℹ️ Web server nhận được ping từ UptimeRobot hoặc trình duyệt.", flush=True)
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stats')
def api_stats():
    import psutil
    import platform

    now = datetime.now(timezone.utc)
    uptime_delta = now - start_time
    
    # Định dạng uptime
    hours_up, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes_up, seconds_up = divmod(remainder, 60)
    uptime_str = f"{hours_up:02d}h {minutes_up:02d}m {seconds_up:02d}s"
    
    bot_latency = "N/A"
    bot_status = "Offline"
    guild_count = 0
    total_users = 0
    bot_name = "N/A"
    
    # Đo RAM sử dụng
    try:
        ram_usage = psutil.Process().memory_info().rss / (1024 * 1024) # MB
        ram_str = f"{ram_usage:.1f} MB"
    except Exception:
        ram_str = "N/A"
        
    if bot.is_ready():
        bot_status = "Online"
        try:
            import math
            latency = bot.latency
            if latency is not None and not math.isnan(latency):
                bot_latency = f"{round(latency * 1000)}ms"
            else:
                bot_latency = "N/A"
        except Exception:
            bot_latency = "N/A"
            
        guild_count = len(bot.guilds)
        total_users = sum(g.member_count for g in bot.guilds if g.member_count)
        bot_name = bot.user.name if bot.user else "N/A"

    return jsonify({
        "bot_status": bot_status,
        "bot_name": bot_name,
        "uptime": uptime_str,
        "latency": bot_latency,
        "guilds": guild_count,
        "total_users": total_users,
        "ram_usage": ram_str,
        "os_info": f"{platform.system()} ({platform.release()})",
        "summaries": summary_count,
        "model": "Gemma 4 (gemma-4-31b-it)",
        "logs": list(log_buffer)
    })

@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    log_buffer.clear()
    print("🧹 Đã xóa toàn bộ logs hệ thống theo yêu cầu từ Dashboard.", flush=True)
    return jsonify({"success": True})

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

# ==========================================
# 4. GRACEFUL SHUTDOWN HANDLER
# ==========================================
async def graceful_shutdown():
    global is_shutting_down
    is_shutting_down = True
    print("👋 Bắt đầu quy trình tắt bot graceful...", flush=True)
    
    # Chờ các lệnh đang chạy dở hoàn thành nốt (tối đa 15 giây)
    wait_time = 0
    while active_interactions and wait_time < 15:
        print(f"⏳ Đang chờ {len(active_interactions)} lệnh dở hoàn thành... ({wait_time}s)", flush=True)
        await asyncio.sleep(1)
        wait_time += 1

    # Nếu sau 15 giây vẫn còn lệnh chưa xong, gửi thông báo hủy cho các lệnh đó
    if active_interactions:
        print(f"⚠️ Hết thời gian chờ. Hủy bỏ {len(active_interactions)} lệnh còn lại...", flush=True)
        for interaction in list(active_interactions):
            try:
                print(f"   ↳ Gửi thông báo hủy lệnh tới user @{interaction.user.display_name}", flush=True)
                await interaction.followup.send(
                    "❌ Bot đang tái khởi động hệ thống. Vui lòng thực hiện lại lệnh sau 15-30 giây!",
                    ephemeral=True
                )
            except Exception as e:
                print(f"⚠️ Không thể gửi thông báo shutdown tới user: {e}", flush=True)
    
    # Đóng kết nối bot
    try:
        await bot.close()
        print("🔌 Đã đóng kết nối bot Discord thành công.", flush=True)
    except Exception as e:
        print(f"⚠️ Lỗi khi đóng bot: {e}", flush=True)

def handle_sigterm(signum, frame):
    global is_shutting_down
    if is_shutting_down:
        return
    is_shutting_down = True
    print(f"📥 Nhận được tín hiệu tắt máy (signal {signum}). Đang tắt máy dọn dẹp...", flush=True)
    
    if bot.loop and bot.loop.is_running():
        # Chạy coroutine trong thread của bot
        future = asyncio.run_coroutine_threadsafe(graceful_shutdown(), bot.loop)
        try:
            # Chờ tối đa 20 giây cho việc hoàn tất các lệnh dở và đóng bot
            future.result(timeout=20)
        except Exception as e:
            print(f"⚠️ Hết thời gian chờ hoặc xảy ra lỗi khi tắt bot: {e}", flush=True)
            
    print("☠️ Tiến trình kết thúc.", flush=True)
    sys.exit(0)

# Đăng ký signal handler
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

if __name__ == "__main__":
    # Nếu chạy cục bộ: `python app.py`
    # Khởi chạy bot ngay lập tức mà không cần đợi request đầu tiên
    if not bot_started:
        bot_started = True
        print("🚀 [Local Mode] Khởi chạy Discord Bot ngay lập tức...", flush=True)
        bot_thread = Thread(target=run_discord_bot)
        bot_thread.daemon = True
        bot_thread.start()
        
    port = int(os.environ.get("PORT", 8080))
    print(f"ℹ️ Khởi chạy Flask Server trên cổng {port}...", flush=True)
    app.run(host='0.0.0.0', port=port)
