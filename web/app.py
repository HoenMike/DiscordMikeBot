import os
import math
import hmac
import hashlib
import asyncio
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

    bot_id = ""
    invite_url = ""
    if bot.is_ready() and bot.user:
        bot_id = str(bot.user.id)
        # Quyền tối thiểu: Send Messages, Read Messages/History, Embed Links, Attach Files, Manage Messages (để xóa tin gốc/ẩn embed), Manage Webhooks + Slash Commands
        invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions=275414838784&scope=bot%20applications.commands"

    activities_overview = activity_logger.get_activities(limit=1)

    return jsonify({
        "bot_status": bot_status,
        "bot_id": bot_id,
        "bot_name": bot_name,
        "bot_avatar": bot_avatar,
        "invite_url": invite_url,
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


# ==========================================
# 5. GUILDS / SERVERS MANAGEMENT APIS
# ==========================================
@app.route('/api/guilds')
@login_required
def api_guilds():
    guild_list = []
    if bot.is_ready():
        for g in bot.guilds:
            is_susp = bot.config_manager.is_guild_suspended(g.id)
            guild_list.append({
                "id": str(g.id),
                "name": g.name,
                "icon": g.icon.url if g.icon else "",
                "member_count": g.member_count or len(g.members),
                "owner_id": str(g.owner_id) if g.owner_id else "",
                "is_suspended": is_susp,
                "created_at": g.created_at.strftime("%d/%m/%Y") if g.created_at else "",
                "joined_at": g.me.joined_at.strftime("%d/%m/%Y") if (g.me and g.me.joined_at) else ""
            })
    return jsonify({
        "total": len(guild_list),
        "guilds": guild_list
    })


def run_coroutine_safe(coro):
    """Chạy an toàn một coroutine bất kể bot đang chạy trong event loop hay bot đang offline."""
    loop = None
    try:
        if bot.is_ready():
            loop = bot.loop
    except Exception:
        loop = None

    if loop and loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=15)
    else:
        return asyncio.run(coro)


@app.route('/api/guilds/suspend', methods=['POST'])
@login_required
def api_suspend_guild():
    data = request.get_json(silent=True) or {}
    guild_id = int(data.get("guild_id", 0))
    reason = data.get("reason", "Admin tạm ngưng hoạt động").strip()

    if not guild_id:
        return jsonify({"success": False, "error": "Thiếu guild_id"}), 400

    guild_name = ""
    target_guild = bot.get_guild(guild_id) if bot.is_ready() else None
    if target_guild:
        guild_name = target_guild.name

    try:
        run_coroutine_safe(bot.config_manager.suspend_guild(guild_id, guild_name=guild_name, reason=reason))
        print(f"⛔ [Admin Console] Đã tạm ngưng (Suspend) server: {guild_name} ({guild_id}). Lý do: {reason}", flush=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/guilds/unsuspend', methods=['POST'])
@login_required
def api_unsuspend_guild():
    data = request.get_json(silent=True) or {}
    guild_id = int(data.get("guild_id", 0))

    if not guild_id:
        return jsonify({"success": False, "error": "Thiếu guild_id"}), 400

    try:
        run_coroutine_safe(bot.config_manager.unsuspend_guild(guild_id))
        print(f"✅ [Admin Console] Đã gỡ tạm ngưng (Unsuspend) cho server: {guild_id}.", flush=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/guilds/leave', methods=['POST'])
@login_required
def api_leave_guild():
    data = request.get_json(silent=True) or {}
    guild_id = int(data.get("guild_id", 0))

    if not guild_id:
        return jsonify({"success": False, "error": "Thiếu guild_id"}), 400

    target_guild = bot.get_guild(guild_id) if bot.is_ready() else None
    if not target_guild:
        return jsonify({"success": False, "error": "Bot không còn ở trong server này."}), 404

    guild_name = target_guild.name

    async def do_leave():
        await target_guild.leave()

    try:
        run_coroutine_safe(do_leave())
        print(f"👋 [Admin Console] Bot đã rời khỏi server: {guild_name} ({guild_id}) theo yêu cầu của Admin.", flush=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

