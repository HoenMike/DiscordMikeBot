import os
import math
import platform
import asyncio
import re
import traceback
import sys
from datetime import datetime, timezone, timedelta
import psutil
from flask import Flask, jsonify, render_template

import config
from bot_instance import bot
try:
    from features.summary import ai_summary
except ImportError:
    ai_summary = None

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))


@app.route('/')
def home():
    print("ℹ️ Web server nhận được ping từ UptimeRobot hoặc trình duyệt.", flush=True)
    return render_template('dashboard.html')


@app.route('/api/stats')
def api_stats():
    now = datetime.now(timezone.utc)
    uptime_delta = now - config.start_time

    hours_up, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes_up, seconds_up = divmod(remainder, 60)
    uptime_str = f"{hours_up:02d}h {minutes_up:02d}m {seconds_up:02d}s"

    bot_latency = "N/A"
    bot_status = "Offline"
    guild_count = 0
    total_users = 0
    bot_name = "N/A"

    try:
        ram_usage = psutil.Process().memory_info().rss / (1024 * 1024)
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
        "model": config.GEMINI_SUMMARY_MODEL,
        "logs": list(config.log_buffer),
        "test_runs": config.test_runs
    })


@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    config.log_buffer.clear()
    print("🧹 Đã xóa toàn bộ logs hệ thống theo yêu cầu từ Dashboard.", flush=True)
    return jsonify({"success": True})


@app.route('/api/test/run', methods=['POST'])
def api_run_test():
    if ai_summary is None:
        return jsonify({"success": False, "error": "Tính năng Summary (ai_summary) chưa được cài đặt hoặc đã bị tắt."}), 400

    async def run_test_logic():
        raw_messages = []
        source_info = "Mock Chat Data (Giả lập)"

        if bot.is_ready() and len(bot.guilds) > 0:
            target_channel = None
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    permissions = channel.permissions_for(guild.me)
                    if permissions.read_messages and permissions.read_message_history:
                        target_channel = channel
                        break
                if target_channel:
                    break

            if target_channel:
                source_info = f"Kênh thực tế: #{target_channel.name} ({target_channel.guild.name})"
                vn_tz = timezone(timedelta(hours=7))
                weekday_map = {0: "T2", 1: "T3", 2: "T4", 3: "T5", 4: "T6", 5: "T7", 6: "CN"}
                print(f"🔬 [Test API] Đang lấy tin nhắn test từ kênh Discord {source_info}...", flush=True)
                async for msg in target_channel.history(limit=150):
                    if msg.author.bot:
                        continue
                    local_dt = msg.created_at.astimezone(vn_tz)
                    w_str = weekday_map[local_dt.weekday()]
                    local_time = local_dt.strftime('%d/%m %H:%M')
                    raw_messages.append(f"[{w_str} {local_time}] {msg.author.display_name}: {msg.content}")
                raw_messages.reverse()

        if not raw_messages:
            print(f"🔬 [Test API] Không có kênh online hoặc bot offline, sử dụng {source_info}...", flush=True)
            raw_messages = ai_summary.MOCK_CHAT_HISTORY

        scan_info = "150 tin nhắn thử nghiệm"
        summary_type = "long"
        clean_focus = "bot tóm tắt"

        print("🔬 [Test API] Đang chạy tóm tắt...", flush=True)
        summary_result = await ai_summary.generate_summary(raw_messages, summary_type, clean_focus, scan_info)

        print("🔬 [Test API] Đang gửi kết quả cho AI QA tự động chấm điểm...", flush=True)
        raw_history_text = "\n".join(raw_messages)
        evaluation_report = await ai_summary.evaluate_summary(raw_history_text, summary_result, summary_type, clean_focus)

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
        return test_run

    try:
        if bot.is_ready() and bot.loop and bot.loop.is_running():
            print("🔬 [Test API] Chạy test bằng loop của Discord Bot (threadsafe)...", flush=True)
            future = asyncio.run_coroutine_threadsafe(run_test_logic(), bot.loop)
            test_run = future.result(timeout=120)
        else:
            print("🔬 [Test API] Chạy test bằng loop mới (bot offline)...", flush=True)
            test_run = asyncio.run(run_test_logic())

        return jsonify({"success": True, "test_run": test_run})

    except Exception as e:
        print(f"❌ [Test API] Gặp lỗi khi chạy vòng lặp kiểm thử: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        return jsonify({"success": False, "error": str(e)}), 500
