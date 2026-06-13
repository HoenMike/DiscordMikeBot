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
        
        # Tăng số lần tóm tắt thành công
        global summary_count
        summary_count += 1
        
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
# 2. KHỞI TẠO WEB DASHBOARD (Flask)
# ==========================================
app = Flask('')

HTML_TEMPLATE = """
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
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(139, 92, 246, 0.15) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(59, 130, 246, 0.15) 0%, transparent 40%);
        }

        header {
            padding: 1.5rem 4rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            background: rgba(11, 15, 25, 0.8);
            backdrop-filter: blur(12px);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .logo-section {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .bot-avatar {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue));
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            box-shadow: 0 8px 20px rgba(139, 92, 246, 0.3);
        }

        h1 {
            font-size: 1.5rem;
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
            padding: 0.5rem 1rem;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            font-size: 0.875rem;
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
            max-width: 1400px;
            width: 100%;
            margin: 0 auto;
            padding: 2rem 4rem;
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 2rem;
        }

        @media (max-width: 1024px) {
            main {
                grid-template-columns: 1fr;
                padding: 1.5rem;
            }
            header {
                padding: 1rem 1.5rem;
            }
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            transition: all 0.3s ease;
        }

        .card:hover {
            border-color: rgba(139, 92, 246, 0.2);
            transform: translateY(-2px);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .stat-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stat-value {
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .stat-value.green { color: var(--status-online); }
        .stat-value.purple { color: #c084fc; }

        .info-title {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #f1f5f9;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 0.75rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-size: 0.875rem;
        }

        .info-row:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .info-label {
            color: var(--text-secondary);
        }

        .info-value {
            font-weight: 500;
            color: #e2e8f0;
        }

        .console-container {
            display: flex;
            flex-direction: column;
            height: calc(100vh - 200px);
            min-height: 500px;
        }

        @media (max-width: 1024px) {
            .console-container {
                height: 500px;
            }
        }

        .console-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
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
            font-size: 0.875rem;
            font-weight: 600;
            color: #94a3b8;
        }

        .live-indicator {
            display: flex;
            align-items: center;
            gap: 0.25rem;
            font-size: 0.75rem;
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
            padding: 1.5rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.875rem;
            line-height: 1.6;
            overflow-y: auto;
            color: #38bdf8;
            box-shadow: inset 0 4px 20px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
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

        .btn-copy {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 0.35rem 0.75rem;
            border-radius: 6px;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn-copy:hover {
            background: var(--accent-purple);
            border-color: var(--accent-purple);
        }

        footer {
            padding: 2rem;
            text-align: center;
            font-size: 0.875rem;
            color: var(--text-secondary);
            border-top: 1px solid var(--border-color);
            background: rgba(11, 15, 25, 0.5);
            margin-top: auto;
        }
    </style>
</head>
<body>

    <header>
        <div class="logo-section">
            <div class="bot-avatar">🤖</div>
            <div>
                <h1 id="header-bot-name">MikeDaBot</h1>
                <p style="font-size: 0.75rem; color: var(--text-secondary);">Gemma 4 Summary Agent</p>
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
                        <span class="stat-label">Bot Status</span>
                        <span id="stat-bot-status" class="stat-value" style="color: var(--status-offline);">Offline</span>
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
                        <span class="stat-label">Đã tóm tắt</span>
                        <span id="stat-summaries" class="stat-value purple">0</span>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="info-title">⚙️ Thông tin Cấu hình</div>
                <div class="info-row">
                    <span class="info-label">Trí tuệ nhân tạo</span>
                    <span class="info-value">Gemma 4</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Model ID</span>
                    <span class="info-value">gemma-4-31b-it</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Uptime</span>
                    <span id="info-uptime" class="info-value">00h 00m 00s</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Lệnh Slash</span>
                    <span class="info-value">/tomtat</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Python Version</span>
                    <span class="info-value">3.14.3</span>
                </div>
            </div>
        </div>

        <div class="console-container">
            <div class="console-header">
                <div class="console-title">
                    <span>💻 Console Logs</span>
                </div>
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <button class="btn-copy" onclick="copyConsoleLogs()">Sao chép log</button>
                    <div class="live-indicator">
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

    <footer>
        <p>© 2026 MikeDaBot - Phát triển với ❤️ để tóm tắt các cuộc trò chuyện Discord</p>
    </footer>

    <script>
        let autoScroll = true;
        const consoleBody = document.getElementById('console-body');

        // Detect user manual scroll to turn off autoscroll
        consoleBody.addEventListener('scroll', () => {
            const threshold = 40; // px
            const isAtBottom = consoleBody.scrollHeight - consoleBody.clientHeight - consoleBody.scrollTop < threshold;
            autoScroll = isAtBottom;
        });

        function formatLogLine(line) {
            // Check if line contains a timestamp like [11:42:00]
            const timestampMatch = line.match(/^\[\d{2}:\d{2}:\d{2}\]/);
            let timestamp = "";
            let content = line;

            if (timestampMatch) {
                timestamp = timestampMatch[0];
                content = line.substring(timestamp.length).trim();
            }

            let styleClass = "log-info";
            
            // Detect logs level and styles
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

        async function updateDashboard() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();

                // Update Status Bar
                const isOnline = data.bot_status === "Online";
                const statusDot = document.getElementById('header-status-dot');
                const statusText = document.getElementById('header-status-text');

                if (isOnline) {
                    statusDot.className = "dot online";
                    statusText.textContent = "Online";
                    
                    document.getElementById('stat-bot-status').textContent = "Online";
                    document.getElementById('stat-bot-status').style.color = "var(--status-online)";
                } else {
                    statusDot.className = "dot offline";
                    statusText.textContent = "Offline";
                    
                    document.getElementById('stat-bot-status').textContent = "Offline";
                    document.getElementById('stat-bot-status').style.color = "var(--status-offline)";
                }

                // Update Bot Name
                if (data.bot_name !== "N/A") {
                    document.getElementById('header-bot-name').textContent = data.bot_name;
                }

                // Update Stats values
                document.getElementById('stat-latency').textContent = data.latency;
                document.getElementById('stat-guilds').textContent = data.guilds;
                document.getElementById('stat-summaries').textContent = data.summaries;
                document.getElementById('info-uptime').textContent = data.uptime;

                // Update logs
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
                
                // Set to offline states
                document.getElementById('header-status-dot').className = "dot offline";
                document.getElementById('header-status-text').textContent = "Lỗi kết nối API";
                document.getElementById('stat-bot-status').textContent = "Offline";
                document.getElementById('stat-bot-status').style.color = "var(--status-offline)";
            }
        }

        // Run immediately and then poll every 3 seconds
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
    now = datetime.now(timezone.utc)
    uptime_delta = now - start_time
    
    # Định dạng uptime
    hours_up, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes_up, seconds_up = divmod(remainder, 60)
    uptime_str = f"{hours_up:02d}h {minutes_up:02d}m {seconds_up:02d}s"
    
    bot_latency = "N/A"
    bot_status = "Offline"
    guild_count = 0
    bot_name = "N/A"
    
    if bot.is_ready():
        bot_status = "Online"
        bot_latency = f"{round(bot.latency * 1000)}ms"
        guild_count = len(bot.guilds)
        bot_name = bot.user.name

    return jsonify({
        "bot_status": bot_status,
        "bot_name": bot_name,
        "uptime": uptime_str,
        "latency": bot_latency,
        "guilds": guild_count,
        "summaries": summary_count,
        "model": "Gemma 4 (gemma-4-31b-it)",
        "logs": list(log_buffer)
    })

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
