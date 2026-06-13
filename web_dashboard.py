from flask import Flask, jsonify, render_template_string
from datetime import datetime, timezone
import psutil
import platform
import math
import config
from bot_instance import bot

app = Flask('')

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
    now = datetime.now(timezone.utc)
    uptime_delta = now - config.start_time
    
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
        "summaries": config.summary_count,
        "model": "Gemma 4 (gemma-4-31b-it)",
        "logs": list(config.log_buffer)
    })

@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    config.log_buffer.clear()
    print("🧹 Đã xóa toàn bộ logs hệ thống theo yêu cầu từ Dashboard.", flush=True)
    return jsonify({"success": True})
