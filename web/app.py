import os
import math
import hmac
import hashlib
import platform
import psutil
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request, session, redirect, url_for

import config
from bot_instance import bot
from core.activity_logger import activity_logger

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
app.secret_key = config.FLASK_SECRET_KEY


def check_password_hash(provided_password: str) -> bool:
    """Kiểm tra mật khẩu bảo mật bằng HMAC SHA-256 an toàn chống timing attack."""
    expected_pw = getattr(config, "ADMIN_PASSWORD", "Crtm123123@")
    provided_hash = hashlib.sha256(provided_password.encode("utf-8")).hexdigest()
    expected_hash = hashlib.sha256(expected_pw.encode("utf-8")).hexdigest()
    return hmac.compare_digest(provided_hash, expected_hash)


def login_required(f):
    """Decorator bảo vệ các Route và API yêu cầu đăng nhập hợp lệ."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            # Nếu là request API -> trả về JSON 401
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized", "authenticated": False}), 401
            # Nếu là request trang HTML -> chuyển hướng về /login
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# 1. AUTHENTICATION ROUTES
# ==========================================
@app.route('/login', methods=['GET'])
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("home"))
    return render_template('login.html')


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")

    if not password:
        return jsonify({"success": False, "error": "Vui lòng nhập mật khẩu quản trị!"}), 400

    if check_password_hash(password):
        session["logged_in"] = True
        session.permanent = True
        print("🔐 [Auth] Đăng nhập Admin Web Console thành công.", flush=True)
        return jsonify({"success": True})
    else:
        print("⚠️ [Auth] Phát hiện lượt đăng nhập Admin Web Console thất bại.", flush=True)
        return jsonify({"success": False, "error": "Mật khẩu quản trị không chính xác!"}), 401


@app.route('/api/auth/logout', methods=['POST', 'GET'])
def api_logout():
    session.clear()
    if request.path.startswith("/api/"):
        return jsonify({"success": True})
    return redirect(url_for("login_page"))


# ==========================================
# 2. MAIN DASHBOARD ROUTE
# ==========================================
@app.route('/')
@login_required
def home():
    return render_template('dashboard.html')


# ==========================================
# 3. STATS & SYSTEM APIS
# ==========================================
@app.route('/api/stats')
@login_required
def api_stats():
    now = datetime.now(timezone.utc)
    uptime_delta = now - config.start_time

    hours_up, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes_up, seconds_up = divmod(remainder, 60)
    uptime_str = f"{hours_up:02d}h {minutes_up:02d}m {seconds_up:02d}s"

    bot_latency = "N/A"
    bot_latency_raw = 0
    bot_status = "Offline"
    guild_count = 0
    total_users = 0
    bot_name = "N/A"
    bot_avatar = ""

    try:
        ram_usage = psutil.Process().memory_info().rss / (1024 * 1024)
        ram_str = f"{ram_usage:.1f} MB"
        ram_raw = round(ram_usage, 1)
    except Exception:
        ram_str = "N/A"
        ram_raw = 0

    if bot.is_ready():
        bot_status = "Online"
        try:
            latency = bot.latency
            if latency is not None and not math.isnan(latency):
                bot_latency_raw = round(latency * 1000)
                bot_latency = f"{bot_latency_raw}ms"
            else:
                bot_latency = "N/A"
        except Exception:
            bot_latency = "N/A"

        guild_count = len(bot.guilds)
        total_users = sum(g.member_count for g in bot.guilds if g.member_count)
        if bot.user:
            bot_name = bot.user.name
            bot_avatar = bot.user.display_avatar.url if bot.user.display_avatar else ""

    activities_overview = activity_logger.get_activities(limit=1)

    return jsonify({
        "bot_status": bot_status,
        "bot_name": bot_name,
        "bot_avatar": bot_avatar,
        "uptime": uptime_str,
        "uptime_seconds": int(uptime_delta.total_seconds()),
        "latency": bot_latency,
        "latency_raw": bot_latency_raw,
        "guilds": guild_count,
        "total_users": total_users,
        "ram_usage": ram_str,
        "ram_raw": ram_raw,
        "os_info": f"{platform.system()} ({platform.release()})",
        "python_version": platform.python_version(),
        "summaries_count": config.summary_count,
        "models": {
            "summary": config.GEMINI_SUMMARY_MODEL,
            "tarot": config.GEMINI_TAROT_MODEL,
            "data": config.GEMINI_DATA_MODEL
        },
        "activity_counts": activities_overview["counts"],
        "logs": list(config.log_buffer)
    })


# ==========================================
# 4. ACTIVITY TRACE APIS
# ==========================================
@app.route('/api/activities')
@login_required
def api_activities():
    action_type = request.args.get("type", "all")
    search = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    result = activity_logger.get_activities(
        action_type=action_type,
        search=search,
        limit=min(limit, 200),
        offset=offset
    )
    return jsonify(result)


@app.route('/api/activities/clear', methods=['POST'])
@login_required
def api_clear_activities():
    activity_logger.clear()
    print("🧹 Đã xóa toàn bộ lịch sử tương tác từ Web Console.", flush=True)
    return jsonify({"success": True})


@app.route('/api/logs/clear', methods=['POST'])
@login_required
def api_clear_logs():
    config.log_buffer.clear()
    print("🧹 Đã xóa toàn bộ logs hệ thống theo yêu cầu từ Web Console.", flush=True)
    return jsonify({"success": True})
