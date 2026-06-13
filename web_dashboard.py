from flask import Flask, jsonify, render_template_string
from datetime import datetime, timezone, timedelta
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

        /* TABS NAVIGATION */
        .tabs-header {
            display: flex;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }

        .tab-btn {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.5rem 1.25rem;
            border-radius: 8px;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: 'Outfit', sans-serif;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .tab-btn:hover {
            background: rgba(255, 255, 255, 0.07);
            color: var(--text-primary);
        }

        .tab-btn.active {
            background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue));
            border-color: transparent;
            color: white;
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.25);
        }

        .console-container {
            display: flex;
            flex-direction: column;
            height: calc(100% - 50px);
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

        /* AUDIT PANEL CSS */
        .audit-split-panel {
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 1.25rem;
            flex: 1;
            height: calc(100% - 50px);
            overflow: hidden;
        }

        @media (max-width: 900px) {
            .audit-split-panel {
                grid-template-columns: 1fr;
            }
        }

        .test-list-pane {
            background: rgba(11, 15, 25, 0.4);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            overflow-y: auto;
        }

        .test-list-header {
            font-size: 0.8rem;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-secondary);
            letter-spacing: 0.5px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.5rem;
        }

        .test-list-container {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            overflow-y: auto;
            flex: 1;
        }

        .test-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.75rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .test-item:hover {
            border-color: rgba(139, 92, 246, 0.4);
            background: rgba(255, 255, 255, 0.04);
        }

        .test-item.active {
            border-color: var(--accent-purple);
            background: rgba(139, 92, 246, 0.08);
            box-shadow: inset 0 0 10px rgba(139, 92, 246, 0.15);
        }

        .test-meta {
            display: flex;
            justify-content: space-between;
            font-size: 0.7rem;
            color: var(--text-secondary);
            margin-bottom: 0.25rem;
        }

        .score-badge {
            background: rgba(16, 185, 129, 0.1);
            color: var(--status-online);
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.75rem;
        }

        .score-badge.low {
            background: rgba(239, 44, 44, 0.1);
            color: var(--status-offline);
        }

        .score-badge.mid {
            background: rgba(245, 158, 11, 0.1);
            color: #f59e0b;
        }

        .test-detail-pane {
            background: var(--terminal-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.25rem;
            overflow-y: auto;
            height: 100%;
            font-family: 'Outfit', sans-serif;
            font-size: 0.9rem;
            line-height: 1.6;
            color: #f1f5f9;
        }

        .test-detail-section {
            margin-bottom: 1.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 1.25rem;
        }

        .test-detail-section:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .section-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--accent-purple);
            margin-bottom: 0.5rem;
            font-weight: 700;
        }

        .code-block {
            font-family: 'Fira Code', monospace;
            font-size: 0.8rem;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 6px;
            padding: 0.75rem;
            white-space: pre-wrap;
            word-break: break-all;
            color: #e2e8f0;
            border: 1px solid rgba(255, 255, 255, 0.02);
            max-height: 200px;
            overflow-y: auto;
        }

        .markdown-text {
            white-space: pre-wrap;
            color: #e2e8f0;
        }

        .markdown-text h3 {
            font-size: 1.05rem;
            margin-bottom: 0.5rem;
            color: #c084fc;
        }

        .markdown-text h4 {
            font-size: 0.95rem;
            margin-top: 0.75rem;
            margin-bottom: 0.25rem;
            color: #38bdf8;
        }

        .markdown-text ul {
            margin-left: 1.25rem;
            margin-bottom: 0.5rem;
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

        <div style="display: flex; flex-direction: column; overflow: hidden; height: 100%;">
            <div class="tabs-header">
                <button id="tab-logs-btn" class="tab-btn active" onclick="switchTab('logs')">💻 Logs & Stats</button>
                <button id="tab-audit-btn" class="tab-btn" onclick="switchTab('audit')">🔬 AI Self-Audit & Test</button>
            </div>

            <!-- TAB LOGS CONTENT -->
            <div id="tab-logs-content" class="console-container">
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

            <!-- TAB AUDIT CONTENT -->
            <div id="tab-audit-content" class="audit-split-panel" style="display: none;">
                <div class="test-list-pane">
                    <div style="display: flex; justify-content: space-between; align-items: center;" class="test-list-header">
                        <span>Lịch sử Test ({20 gần nhất})</span>
                        <button class="btn-action copy" id="run-test-btn" onclick="runSelfAuditTest()">Chạy Test AI</button>
                    </div>
                    <div id="test-loading" style="display:none; color: #a855f7; font-size: 0.75rem; text-align: center; padding: 0.5rem; background: rgba(139, 92, 246, 0.05); border-radius: 6px; border: 1px dashed rgba(139, 92, 246, 0.2);">
                        ⏳ Đang chạy tóm tắt & AI QA đánh giá (khoảng 10-15s)...
                    </div>
                    <div id="test-runs-list" class="test-list-container">
                        <div style="text-align: center; color: var(--text-secondary); font-size: 0.8rem; margin-top: 1rem;">Chưa có lượt test nào được ghi nhận. Hãy bấm "Chạy Test AI".</div>
                    </div>
                </div>

                <div id="test-details-pane" class="test-detail-pane">
                    <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100%; color: var(--text-secondary); text-align: center; gap: 0.5rem;">
                        <span style="font-size: 2rem;">🔬</span>
                        <p style="font-weight: 500;">AI Self-Audit Playground</p>
                        <p style="font-size: 0.75rem; max-width: 300px;">Chọn một lượt chạy thử nghiệm bên trái hoặc bấm nút "Chạy Test AI" để chạy phân tích đánh giá chất lượng tự động.</p>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        let autoScroll = true;
        let activeTab = 'logs';
        let testRunsData = [];
        let selectedTestIndex = null;
        const consoleBody = document.getElementById('console-body');

        // Phát hiện cuộn chuột để khóa auto scroll
        consoleBody.addEventListener('scroll', () => {
            const threshold = 40; 
            const isAtBottom = consoleBody.scrollHeight - consoleBody.clientHeight - consoleBody.scrollTop < threshold;
            autoScroll = isAtBottom;
        });

        // Tab switcher
        function switchTab(tabName) {
            activeTab = tabName;
            document.getElementById('tab-logs-btn').className = tabName === 'logs' ? 'tab-btn active' : 'tab-btn';
            document.getElementById('tab-audit-btn').className = tabName === 'audit' ? 'tab-btn active' : 'tab-btn';
            
            document.getElementById('tab-logs-content').style.display = tabName === 'logs' ? 'flex' : 'none';
            document.getElementById('tab-audit-content').style.display = tabName === 'audit' ? 'grid' : 'none';
            
            if (tabName === 'audit') {
                renderTestRuns();
            }
        }

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

        // Render danh sách các lượt test runs
        function renderTestRuns() {
            const listContainer = document.getElementById('test-runs-list');
            if (testRunsData.length === 0) {
                listContainer.innerHTML = `<div style="text-align: center; color: var(--text-secondary); font-size: 0.8rem; margin-top: 1rem;">Chưa có lượt test nào được ghi nhận. Hãy bấm "Chạy Test AI".</div>`;
                return;
            }
            
            listContainer.innerHTML = testRunsData.map((run, idx) => {
                const isActive = idx === selectedTestIndex ? 'active' : '';
                const score = parseFloat(run.score) || 0;
                let scoreClass = 'green';
                if (score < 5) scoreClass = 'low';
                else if (score < 8) scoreClass = 'mid';
                
                return `
                    <div class="test-item ${isActive}" onclick="selectTestRun(${idx})">
                        <div class="test-meta">
                            <span>${run.timestamp}</span>
                            <span class="score-badge ${scoreClass}">${run.score} / 10</span>
                        </div>
                        <div style="font-size: 0.8rem; font-weight: 600; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${escapeHtml(run.source)}
                        </div>
                        <div style="font-size: 0.7rem; color: var(--text-secondary); margin-top: 0.15rem;">
                            Mode: ${run.mode} | Focus: ${run.focus ? run.focus : 'Không'}
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Chọn xem chi tiết một lượt test
        function selectTestRun(index) {
            selectedTestIndex = index;
            renderTestRuns();
            
            const detailPane = document.getElementById('test-details-pane');
            const run = testRunsData[index];
            if (!run) return;
            
            const scoreNum = parseFloat(run.score) || 0;
            let scoreColor = 'var(--status-online)';
            if (scoreNum < 5) scoreColor = 'var(--status-offline)';
            else if (scoreNum < 8) scoreColor = '#f59e0b';
            
            // Format report Markdown to simple HTML elements
            let htmlReport = escapeHtml(run.evaluation)
                .replace(/^### (.*$)/gim, '<h3>$1</h3>')
                .replace(/^#### (.*$)/gim, '<h4>$1</h4>')
                .replace(/^\s*-\s*\*\*(.*?)\*\*:\s*(.*$)/gim, '<li><strong>$1</strong>: $2</li>')
                .replace(/^\s*-\s*(.*$)/gim, '<li>$1</li>');
                
            // Wrap <li> into <ul>
            htmlReport = htmlReport.replace(/(<li>.*<\/li>)/g, '<ul>$1</ul>');
            // Clean consecutive <ul> tags
            htmlReport = htmlReport.replace(/<\/ul>\s*<ul>/g, '');

            detailPane.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:0.75rem; margin-bottom:1rem;">
                    <div>
                        <h2 style="font-size:1.1rem; font-weight:700; color:#f1f5f9;">🔬 Kết Quả Kiểm Thử AI</h2>
                        <p style="font-size:0.75rem; color:var(--text-secondary);">${run.timestamp} | Nguồn: ${run.source}</p>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:1.3rem; font-weight:700; color:${scoreColor};">${run.score}</span>
                        <span style="font-size:0.8rem; color:var(--text-secondary);"> / 10</span>
                    </div>
                </div>
                
                <div class="test-detail-section">
                    <div class="section-title">⚙️ Cấu Hình Chạy Test</div>
                    <div style="font-size:0.8rem; display:grid; grid-template-columns:1fr 1fr; gap:0.5rem; color:#cbd5e1;">
                        <div>Phạm vi quét: <strong>${run.scan_info}</strong></div>
                        <div>Số tin nhắn thực tế: <strong>${run.raw_count} tin nhắn</strong></div>
                        <div>Chế độ tóm tắt: <strong>${run.mode}</strong></div>
                        <div>Từ khóa focus: <strong>${run.focus ? run.focus : 'Không'}</strong></div>
                    </div>
                </div>

                <div class="test-detail-section">
                    <div class="section-title">🤖 AI QA Engineer Đánh Giá (Critique)</div>
                    <div class="markdown-text">${htmlReport}</div>
                </div>

                <div class="test-detail-section">
                    <div class="section-title">📝 Bản Tóm Tắt Được Tạo (Generated Summary)</div>
                    <div class="code-block" style="background:#090d16; color:#f8fafc; border:1px solid rgba(255,255,255,0.05); max-height:400px;">${escapeHtml(run.summary)}</div>
                </div>
            `;
        }

        // Kích hoạt API chạy test từ dashboard
        async function runSelfAuditTest() {
            const btn = document.getElementById('run-test-btn');
            const loading = document.getElementById('test-loading');
            
            btn.disabled = true;
            btn.style.opacity = 0.5;
            loading.style.display = 'block';
            
            try {
                const response = await fetch('/api/test/run', { method: 'POST' });
                const result = await response.json();
                if (result.success) {
                    // Cập nhật dữ liệu dashboard lập tức
                    await updateDashboard();
                    // Chọn phần tử test đầu tiên (vừa mới tạo)
                    selectedTestIndex = 0;
                    renderTestRuns();
                    selectTestRun(0);
                    alert("🎉 Đã chạy xong lượt test tự động! Xem chi tiết đánh giá ở bảng điều khiển.");
                } else {
                    alert("❌ Lỗi kiểm thử: " + result.error);
                }
            } catch (err) {
                console.error("Test error:", err);
                alert("❌ Lỗi kết nối máy chủ khi chạy kiểm thử.");
            } finally {
                btn.disabled = false;
                btn.style.opacity = 1;
                loading.style.display = 'none';
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

                // Cập nhật lịch sử test runs
                if (data.test_runs) {
                    testRunsData = data.test_runs;
                    if (activeTab === 'audit') {
                        renderTestRuns();
                        // Giữ nguyên hiển thị chi tiết test nếu đang chọn
                        if (selectedTestIndex !== null && selectedTestIndex < testRunsData.length) {
                            selectTestRun(selectedTestIndex);
                        }
                    }
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
        "logs": list(config.log_buffer),
        "test_runs": config.test_runs
    })

@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    config.log_buffer.clear()
    print("🧹 Đã xóa toàn bộ logs hệ thống theo yêu cầu từ Dashboard.", flush=True)
    return jsonify({"success": True})

@app.route('/api/test/run', methods=['POST'])
async def api_run_test():
    try:
        import ai_helper
        import config
        from bot_instance import bot
        import discord
        from datetime import timezone, timedelta
        import re
        
        # 1. Thu thập tin nhắn (quét kênh thực tế nếu bot online hoặc dùng Mock Data)
        raw_messages = []
        source_info = "Mock Chat Data (Giả lập)"
        
        if bot.is_ready() and len(bot.guilds) > 0:
            target_channel = None
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    # Kiểm tra quyền đọc tin nhắn
                    permissions = channel.permissions_for(guild.me)
                    if permissions.read_messages and permissions.read_message_history:
                        target_channel = channel
                        break
                if target_channel:
                    break
            
            if target_channel:
                source_info = f"Kênh thực tế: #{target_channel.name} ({target_channel.guild.name})"
                vn_tz = timezone(timedelta(hours=7))
                print(f"🔬 [Test API] Đang lấy tin nhắn test từ kênh Discord {source_info}...", flush=True)
                async for msg in target_channel.history(limit=150):
                    if msg.author.bot:
                        continue
                    local_time = msg.created_at.astimezone(vn_tz).strftime('%d/%m %H:%M')
                    raw_messages.append(f"[{local_time}] {msg.author.display_name}: {msg.content}")
                raw_messages.reverse() # Sắp xếp từ cũ đến mới
        
        if not raw_messages:
            # Fallback sang Mock Data
            print(f"🔬 [Test API] Không có kênh online hoặc bot offline, sử dụng {source_info}...", flush=True)
            raw_messages = ai_helper.MOCK_CHAT_HISTORY
        
        scan_info = "150 tin nhắn thử nghiệm"
        summary_type = "long"
        clean_focus = "bot tóm tắt"  # Thử nghiệm focus vào bot tóm tắt
        
        # 2. Chạy tóm tắt
        print("🔬 [Test API] Đang chạy tóm tắt...", flush=True)
        summary_result = await ai_helper.generate_summary(raw_messages, summary_type, clean_focus, scan_info)
        
        # 3. Chạy đánh giá chất lượng tự động bằng AI QA
        print("🔬 [Test API] Đang gửi kết quả cho AI QA tự động chấm điểm...", flush=True)
        raw_history_text = "\n".join(raw_messages)
        evaluation_report = await ai_helper.evaluate_summary(raw_history_text, summary_result, summary_type, clean_focus)
        
        # Trích xuất điểm số từ báo cáo
        score_val = "N/A"
        score_match = re.search(r"-\s*\*\*Điểm số\*\*:\s*([\d\.\/\s]+)", evaluation_report, re.IGNORECASE)
        if score_match:
            score_val = score_match.group(1).strip()
            
        test_run = {
            "timestamp": datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m %H:%M:%S'),
            "source": source_info,
            "scan_info": scan_info,
            "mode": summary_type,
            "focus": clean_focus,
            "raw_count": len(raw_messages),
            "summary": summary_result,
            "evaluation": evaluation_report,
            "score": score_val
        }
        
        config.test_runs.insert(0, test_run)
        if len(config.test_runs) > 20:
            config.test_runs = config.test_runs[:20]
            
        print(f"🎉 [Test API] Đã chạy xong lượt test. AI QA chấm điểm: {score_val}.", flush=True)
        return jsonify({"success": True, "test_run": test_run})
        
    except Exception as e:
        import traceback
        import sys
        print(f"❌ [Test API] Gặp lỗi khi chạy vòng lặp kiểm thử: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        return jsonify({"success": False, "error": str(e)}), 500
