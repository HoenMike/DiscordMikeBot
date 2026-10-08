import os
import math
import hmac
import hashlib
import asyncio
import platform
import psutil
from functools import wraps
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import config
from bot_instance import bot
from core.activity_logger import activity_logger
from core.presence_manager import presence_manager
from core.version import CURRENT_VERSION, get_version_info, get_changelog
from features.cabin.manager import cabin_manager

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
app.secret_key = config.FLASK_SECRET_KEY
# Admin OAuth consent cookie must never travel over plaintext HTTP.
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)




ADMIN_MUTATION_PATHS = frozenset({
    '/api/activities/clear', '/api/logs/clear',
    '/api/guilds/suspend', '/api/guilds/unsuspend', '/api/guilds/leave',
    '/api/tarot/reset-cooldown', '/api/tarot/reset-all-cooldowns',
    '/api/cabin/shields/toggle', '/api/cabin/sessions/stop', '/api/presence',
})


@app.before_request
def guard_admin_mutations():
    """Require anti-CSRF for all legacy dashboard writes as well as T24 pages.

    Connector OAuth/API endpoints have separate authentication and are not covered
    here; per-feedback review APIs keep their own existing CSRF checks.
    """
    if request.method != 'POST' or request.path not in ADMIN_MUTATION_PATHS:
        return None
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    token = session.get('feedback_csrf')
    if not token or not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), token):
        return jsonify({"error": "Invalid CSRF token"}), 403
    if request.mimetype != 'application/json':
        return jsonify({"error": "JSON required"}), 415
    return None

@app.context_processor
def release_template_context():
    from core.version import RELEASE_DATE, CODENAME, CHANGELOG
    latest_type = CHANGELOG[0].get("type", "minor") if CHANGELOG else "minor"
    return {
        "release_version": CURRENT_VERSION,
        "release_date": RELEASE_DATE,
        "release_codename": CODENAME,
        "release_type": latest_type,
    }


def check_password_hash(provided_password: str) -> bool:
    """Kiểm tra mật khẩu bảo mật bằng HMAC SHA-256 an toàn chống timing attack."""
    expected_pw = getattr(config, "ADMIN_PASSWORD", "")
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
            # Nếu là request trang HTML -> chuyển hướng về /login kèm tham số next
            return redirect(url_for("login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# 0. SYSTEM HEALTH CHECK ROUTES (PUBLIC)
# ==========================================
@app.route('/healthz', methods=['GET'])
@app.route('/ping', methods=['GET'])
def health_check():
    """Endpoint kiểm tra sức khỏe hệ thống (không yêu cầu login) phục vụ Render Port Scanner & Uptime Monitors."""
    bot_ready = False
    try:
        bot_ready = bot.is_ready()
    except Exception:
        bot_ready = False

    return jsonify({
        "status": "ok",
        "bot_online": bot_ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": CURRENT_VERSION
    }), 200


# ==========================================
# 1. AUTHENTICATION ROUTES
# ==========================================
@app.route('/login', methods=['GET'])
def login_page():
    next_url = request.args.get("next", "/admin")
    if session.get("logged_in"):
        return redirect(next_url if next_url.startswith("/") else url_for("admin_dashboard"))
    return render_template('login.html', next=next_url)


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    next_url = data.get("next", "/admin")
    if not next_url.startswith("/"):
        next_url = "/admin"

    if not password:
        return jsonify({"success": False, "error": "Vui lòng nhập mật khẩu quản trị!"}), 400

    if check_password_hash(password):
        session["logged_in"] = True
        session.permanent = True
        print("🔐 [Auth] Đăng nhập Admin Web Console thành công.", flush=True)
        return jsonify({"success": True, "redirect": next_url})
    else:
        print("⚠️ [Auth] Phát hiện lượt đăng nhập Admin Web Console thất bại.", flush=True)
        return jsonify({"success": False, "error": "Mật khẩu quản trị không chính xác!"}), 401


@app.route('/api/auth/logout', methods=['POST', 'GET'])
def api_logout():
    session.clear()
    if request.path.startswith("/api/"):
        return jsonify({"success": True, "redirect": "/"})
    return redirect(url_for("guest_home"))


# ==========================================
# 2. GUEST & ADMIN PAGE ROUTES
# ==========================================
@app.route('/')
def guest_home():
    """Trang chủ công khai (Guest Page) - Giới thiệu bot, thông số trực tiếp và Changelog."""
    return render_template('guest.html')


ADMIN_PAGES = {
    "overview": "Tổng quan",
    "activity": "Tương tác",
    "monitoring": "Sức khỏe & Logs",
    "assistant": "AI & Search",
    "tarot": "Tarot",
    "cabin": "Cabin",
    "guilds": "Máy chủ",
    "presence": "Trạng thái Bot",
    "releases": "Phiên bản & Kết nối",
}


def admin_csrf_token():
    import secrets
    if not session.get("feedback_csrf"):
        session["feedback_csrf"] = secrets.token_urlsafe(32)
    return session["feedback_csrf"]


@app.route('/admin')
@login_required
def admin_dashboard():
    return render_template('admin_console.html', page="overview",
                           page_title=ADMIN_PAGES["overview"],
                           feedback_csrf=admin_csrf_token())


@app.route('/admin/<page>')
@login_required
def admin_page(page):
    if page not in ADMIN_PAGES or page == "overview":
        from flask import abort
        abort(404)
    return render_template('admin_console.html', page=page,
                           page_title=ADMIN_PAGES[page],
                           feedback_csrf=admin_csrf_token())


@app.route('/admin/legacy')
@login_required
def admin_legacy():
    """Temporary fallback during phased migration, not part of navigation."""
    return render_template('dashboard.html', feedback_csrf=admin_csrf_token())


@app.route('/home')
def legacy_home():
    """Chuyển hướng tương thích cho các liên kết cũ."""
    if session.get("logged_in"):
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("guest_home"))


# ==========================================
# 2.1 PUBLIC STATS API FOR GUEST PAGE
# ==========================================
@app.route('/api/public/stats', methods=['GET'])
def api_public_stats():
    """API công khai cung cấp thông số cơ bản phục vụ Trang Khách (không yêu cầu login)."""
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
    from core.branding import BOT_BRAND_NAME, runtime_bot_name
    bot_name = BOT_BRAND_NAME
    bot_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"
    bot_id = ""
    invite_url = ""

    if bot.is_ready():
        bot_status = "Online"
        try:
            latency = bot.latency
            if latency is not None and not math.isnan(latency):
                bot_latency_raw = round(latency * 1000)
                bot_latency = f"{bot_latency_raw}ms"
        except Exception:
            pass

        guild_count = len(bot.guilds)
        total_users = sum(g.member_count for g in bot.guilds if g.member_count)
        if bot.user:
            bot_name = runtime_bot_name(bot.user)
            bot_avatar = bot.user.display_avatar.url if bot.user.display_avatar else bot_avatar
            bot_id = str(bot.user.id)
            invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions=275414838784&scope=bot%20applications.commands"

    from core.version import CODENAME, RELEASE_DATE

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
        "prefix": ".m",
        "version": CURRENT_VERSION,
        "codename": CODENAME,
        "release_date": RELEASE_DATE,
        "presence": presence_manager.get_info()
    })


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
        "version": CURRENT_VERSION,
        "version_info": get_version_info(),
        "presence": presence_manager.get_info(),
        "summaries_count": config.summary_count,
        "models": {
            "summary": config.GEMINI_SUMMARY_MODEL,
            "tarot": config.GEMINI_TAROT_MODEL,
            "data": config.GEMINI_DATA_MODEL,
            "cabin": config.GEMINI_CABIN_MODEL
        },
        "activity_counts": activities_overview["counts"],
        "cabin_stats": {
            "active_sessions": len(cabin_manager._sessions),
            "active_shields": len(cabin_manager._shields)
        },
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
    try:
        run_coroutine_safe(activity_logger.clear_db())
        print("🧹 Đã xóa toàn bộ lịch sử tương tác từ Web Console.", flush=True)
        return jsonify({"success": True})
    except Exception as e:
        activity_logger.clear()
        return jsonify({"success": True})


@app.route('/api/logs/clear', methods=['POST'])
@login_required
def api_clear_logs():
    try:
        run_coroutine_safe(activity_logger.clear_console_logs_db())
        print("🧹 Đã xóa toàn bộ logs hệ thống theo yêu cầu từ Web Console.", flush=True)
        return jsonify({"success": True})
    except Exception as e:
        config.log_buffer.clear()
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
    """Chạy an toàn một coroutine trên event loop của Discord bot hoặc fallback sang event loop mới nếu bot đang dừng."""
    loop = None
    try:
        if hasattr(bot, "loop") and bot.loop and bot.loop.is_running():
            loop = bot.loop
    except Exception:
        loop = None

    if loop and loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=15)
    else:
        async def _run_and_cleanup():
            try:
                return await coro
            finally:
                try:
                    from core.db import db_client
                    await db_client.close()
                except Exception:
                    pass
        return asyncio.run(_run_and_cleanup())


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
        print(f"⛔ [Admin Console] Đã tạm ngừng máy chủ: {guild_name} ({guild_id}). Lý do: {reason}", flush=True)
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
        print(f"✅ [Admin Console] Đã gỡ tạm ngừng cho máy chủ: {guild_id}.", flush=True)
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


# ==========================================
# 6. TAROT COOLDOWNS MANAGEMENT APIS
# ==========================================
@app.route('/api/tarot/cooldowns')
@login_required
def api_tarot_cooldowns():
    from features.tarot.manager import TarotManager
    from core.activity_logger import activity_logger
    tm = TarotManager()
    try:
        items = run_coroutine_safe(tm.get_active_daily_cooldowns())
        enriched = []

        # Tạo map user_id -> (user_name, user_avatar) từ Activity Logger
        activity_user_map = {}
        act_res = activity_logger.get_activities(limit=1000)
        for act in act_res.get("items", []):
            uid_str = str(act.get("user_id", ""))
            if uid_str and uid_str not in activity_user_map:
                activity_user_map[uid_str] = {
                    "name": act.get("user_name"),
                    "avatar": act.get("user_avatar")
                }

        for item in items:
            uid = item["user_id"]
            uid_str = str(uid)
            card = item.get("card_data", {})
            name_vi = card.get("name_vi", "Lá bài")
            name_en = card.get("name_en", "")
            is_rev = card.get("is_reversed", False)
            drawn_at = card.get("drawn_at", "")

            # 1. Tìm thông tin user theo thứ tự ưu tiên:
            # - card_data đã lưu lúc bốc bài
            # - Activity Logger map
            # - Discord bot cache / fetch_user
            username = card.get("user_name")
            display_name = card.get("user_name")
            avatar_url = card.get("user_avatar")

            if not avatar_url and uid_str in activity_user_map:
                if not username:
                    username = activity_user_map[uid_str]["name"]
                    display_name = activity_user_map[uid_str]["name"]
                if activity_user_map[uid_str]["avatar"]:
                    avatar_url = activity_user_map[uid_str]["avatar"]

            if (not avatar_url or not username) and bot.is_ready():
                u = bot.get_user(uid)
                if u:
                    username = username or u.name
                    display_name = display_name or u.display_name
                    avatar_url = avatar_url or (u.display_avatar.url if u.display_avatar else None)
                else:
                    try:
                        fetched_u = run_coroutine_safe(bot.fetch_user(uid))
                        if fetched_u:
                            username = username or fetched_u.name
                            display_name = display_name or fetched_u.display_name
                            avatar_url = avatar_url or (fetched_u.display_avatar.url if fetched_u.display_avatar else None)
                    except Exception:
                        pass

            username = username or f"User {uid}"
            display_name = display_name or f"User {uid}"
            if not avatar_url:
                avatar_url = f"https://ui-avatars.com/api/?name={display_name}&background=8b5cf6&color=fff"

            enriched.append({
                "user_id": str(uid),
                "username": username,
                "display_name": display_name,
                "avatar_url": avatar_url,
                "card_title": f"{name_vi} ({'[NGƯỢC]' if is_rev else '[XUÔI]'})" if name_vi else "Đã bốc bài",
                "card_name_en": name_en,
                "drawn_at": drawn_at,
                "last_daily_date": item["last_daily_date"],
                "updated_at": item["updated_at"]
            })
        return jsonify({"total": len(enriched), "cooldowns": enriched})
    except Exception as e:
        return jsonify({"total": 0, "cooldowns": [], "error": str(e)}), 500


@app.route('/api/tarot/reset-cooldown', methods=['POST'])
@login_required
def api_tarot_reset_cooldown():
    data = request.get_json(silent=True) or {}
    try:
        user_id = int(data.get("user_id", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "User ID không hợp lệ! Vui lòng chỉ nhập các chữ số."}), 400

    if not user_id:
        return jsonify({"success": False, "error": "Vui lòng nhập User ID!"}), 400

    from features.tarot.manager import TarotManager
    tm = TarotManager()
    try:
        run_coroutine_safe(tm.reset_daily_cooldown(user_id))
        print(f"✨ [Admin Console] Đã gỡ Daily Cooldown cho User ID: {user_id}", flush=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/tarot/reset-all-cooldowns', methods=['POST'])
@login_required
def api_tarot_reset_all_cooldowns():
    from features.tarot.manager import TarotManager
    tm = TarotManager()
    try:
        run_coroutine_safe(tm.reset_all_daily_cooldowns())
        print("✨ [Admin Console] Đã xóa sạch toàn bộ Cooldown Tarot trong ngày!", flush=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# 7. TAROT RATINGS & DATASET EXPORT APIS
# ==========================================
@app.route('/api/tarot/ratings/stats', methods=['GET'])
@login_required
def api_tarot_ratings_stats():
    from features.tarot.manager import TarotManager
    tm = TarotManager()
    try:
        stats = run_coroutine_safe(tm.get_rating_stats())
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tarot/ratings/export', methods=['GET'])
@login_required
def api_tarot_ratings_export():
    import io
    import csv
    import json
    from flask import Response
    from features.tarot.manager import TarotManager
    tm = TarotManager()
    export_format = request.args.get("format", "json").lower()

    try:
        ratings = run_coroutine_safe(tm.get_all_ratings_detailed())
        stats = run_coroutine_safe(tm.get_rating_stats())

        if export_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Rating ID", "User ID", "Guild ID", "Spread Type", "Reader Style", "Rating", "Is Positive", "Created At"])
            for r in ratings:
                writer.writerow([
                    r["rating_id"], r["user_id"], r["guild_id"] or "", r["spread_type"],
                    r["reader_style"], r["rating"], r["is_positive"], r["created_at"]
                ])
            response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
            response.headers["Content-Disposition"] = "attachment; filename=tarot_ratings_dataset.csv"
            return response
        else:
            export_payload = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "summary": stats,
                "dataset": ratings
            }
            response = Response(
                json.dumps(export_payload, ensure_ascii=False, indent=2),
                mimetype="application/json; charset=utf-8"
            )
            response.headers["Content-Disposition"] = "attachment; filename=tarot_ratings_dataset.json"
            return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# 8. DỊCH CABIN & KHIÊN CHỐNG CABIN APIS
# ==========================================
@app.route('/api/cabin/shields', methods=['GET'])
@login_required
def api_cabin_shields():
    from features.cabin.manager import cabin_manager
    try:
        raw_shields = run_coroutine_safe(cabin_manager.list_all_shields())
        enriched = []
        for s in raw_shields:
            uid = s["user_id"]
            gid = s["guild_id"]
            user_name = s.get("user_name") or f"User {uid}"
            avatar_url = ""
            guild_name = f"Server {gid}"

            if bot.is_ready():
                g = bot.get_guild(gid)
                if g:
                    guild_name = g.name
                    member = g.get_member(uid)
                    if member:
                        user_name = member.display_name
                        avatar_url = member.display_avatar.url if member.display_avatar else ""

                if not avatar_url:
                    u = bot.get_user(uid)
                    if u:
                        user_name = user_name or u.display_name
                        avatar_url = u.display_avatar.url if u.display_avatar else ""

            if not avatar_url:
                avatar_url = f"https://ui-avatars.com/api/?name={user_name}&background=3b82f6&color=fff"

            created_at_str = ""
            if s.get("created_at"):
                try:
                    dt = datetime.fromtimestamp(s["created_at"], timezone.utc)
                    created_at_str = dt.strftime("%d/%m/%Y %H:%M")
                except Exception:
                    created_at_str = str(s["created_at"])

            enriched.append({
                "guild_id": str(gid),
                "guild_name": guild_name,
                "user_id": str(uid),
                "user_name": user_name,
                "avatar_url": avatar_url,
                "created_at": created_at_str,
                "created_at_raw": s.get("created_at", 0)
            })

        return jsonify({"total": len(enriched), "shields": enriched})
    except Exception as e:
        return jsonify({"total": 0, "shields": [], "error": str(e)}), 500


@app.route('/api/cabin/shields/toggle', methods=['POST'])
@login_required
def api_cabin_shields_toggle():
    from features.cabin.manager import cabin_manager
    data = request.get_json(silent=True) or {}
    try:
        guild_id = int(data.get("guild_id", 0))
        user_id = int(data.get("user_id", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "ID máy chủ hoặc ID người dùng không hợp lệ!"}), 400

    if not guild_id or not user_id:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ Guild ID và User ID!"}), 400

    user_name = data.get("user_name", "").strip()
    enable = data.get("enable")

    if bot.is_ready() and not user_name:
        u = bot.get_user(user_id)
        if u:
            user_name = u.display_name

    try:
        is_shielded = run_coroutine_safe(
            cabin_manager.toggle_shield(
                guild_id=guild_id,
                user_id=user_id,
                user_name=user_name or f"User {user_id}",
                enable=enable
            )
        )
        action_str = "kích hoạt" if is_shielded else "gỡ bỏ"
        print(f"🛡️ [Admin Console] Đã {action_str} Khiên Chống Cabin cho user {user_id} tại guild {guild_id}.", flush=True)
        return jsonify({"success": True, "is_shielded": is_shielded})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/cabin/sessions', methods=['GET'])
@login_required
def api_cabin_sessions():
    from features.cabin.manager import cabin_manager
    from features.cabin.constants import format_duration
    try:
        sessions = cabin_manager.list_all_sessions()
        result = []
        for s in sessions:
            g_name = f"Server {s.guild_id}"
            c_name = f"Channel {s.channel_id}"
            target_avatar = ""
            creator_avatar = ""

            if bot.is_ready():
                g = bot.get_guild(s.guild_id)
                if g:
                    g_name = g.name
                    ch = g.get_channel(s.channel_id)
                    if ch:
                        c_name = f"#{ch.name}"
                    t_member = g.get_member(s.target_id)
                    if t_member and t_member.display_avatar:
                        target_avatar = t_member.display_avatar.url
                    c_member = g.get_member(s.creator_id)
                    if c_member and c_member.display_avatar:
                        creator_avatar = c_member.display_avatar.url

            if not target_avatar:
                target_avatar = f"https://ui-avatars.com/api/?name={s.target_name}&background=f97316&color=fff"
            if not creator_avatar:
                creator_avatar = f"https://ui-avatars.com/api/?name={s.creator_name}&background=8b5cf6&color=fff"

            rem_sec = s.remaining_seconds
            rem_str = format_duration(rem_sec)

            result.append({
                "guild_id": str(s.guild_id),
                "guild_name": g_name,
                "channel_id": str(s.channel_id),
                "channel_name": c_name,
                "target_id": str(s.target_id),
                "target_name": s.target_name,
                "target_avatar": target_avatar,
                "creator_id": str(s.creator_id),
                "creator_name": s.creator_name,
                "creator_avatar": creator_avatar,
                "remaining_seconds": rem_sec,
                "remaining_str": rem_str,
                "translated_count": s.translated_count,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
            })
        return jsonify({"total": len(result), "sessions": result})
    except Exception as e:
        return jsonify({"total": 0, "sessions": [], "error": str(e)}), 500


@app.route('/api/cabin/sessions/stop', methods=['POST'])
@login_required
def api_cabin_sessions_stop():
    from features.cabin.manager import cabin_manager
    data = request.get_json(silent=True) or {}
    try:
        guild_id = int(data.get("guild_id", 0))
        target_id = int(data.get("target_id", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "ID không hợp lệ!"}), 400

    if not guild_id or not target_id:
        return jsonify({"success": False, "error": "Thiếu guild_id hoặc target_id!"}), 400

    try:
        stopped = run_coroutine_safe(cabin_manager.stop_session(guild_id, target_id))
        print(f"🛑 [Admin Console] Đã dừng phiên Dịch Cabin của user {target_id} tại guild {guild_id}.", flush=True)
        return jsonify({"success": True, "stopped": stopped})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# 10. PRESENCE & STATUS CONTROL APIS
# ==========================================
@app.route('/api/presence', methods=['GET'])
@login_required
def api_get_presence():
    return jsonify(presence_manager.get_info())


@app.route('/api/presence', methods=['POST'])
@login_required
def api_update_presence():
    data = request.get_json(silent=True) or {}
    status = data.get("status", "online")
    activity_type = data.get("activity_type", "custom")
    activity_text = data.get("activity_text", "").strip()
    is_rotating = bool(data.get("is_rotating", False))

    success = run_coroutine_safe(
        presence_manager.apply_presence(
            bot=bot,
            status=status,
            activity_type=activity_type,
            text=activity_text,
            is_rotating=is_rotating,
            save_db=True
        )
    )
    if success:
        return jsonify({"success": True, "presence": presence_manager.get_info()})
    return jsonify({"success": False, "error": "Bot chưa kết nối Discord hoặc xảy ra lỗi."}), 500


# ==========================================
# 11. VERSION & CHANGELOG APIS (PUBLIC)
# ==========================================
@app.route('/api/version', methods=['GET'])
def api_version():
    """API công khai cung cấp thông tin phiên bản và toàn bộ Changelog."""
    return jsonify({
        "info": get_version_info(),
        "changelog": get_changelog()
    })





# T23.2 — Authentication is inherited from the existing admin session.
@app.route('/api/admin/feedback', methods=['GET'])
@login_required
def feedback_inbox():
    from features.feedback.store import feedback_store, FeedbackStorageError
    status = (request.args.get("status") or "").strip()[:30]
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(50, limit))
    view = (request.args.get("view") or "").strip()[:20]
    query = (request.args.get("q") or "").strip()[:100]
    try:
        fetched = asyncio.run(feedback_store.admin_list(
            status=status, limit=limit + 1, offset=offset, view=view, query=query))
        tickets = fetched[:limit]
        return jsonify({"tickets": tickets, "count": len(tickets),
                        "has_more": len(fetched) > limit, "offset": offset})
    except FeedbackStorageError:
        return jsonify({"error": "Không thể kết nối Turso"}), 503




@app.route('/api/admin/feedback/<ticket_id>', methods=['GET'])
@login_required
def feedback_ticket_detail(ticket_id):
    from features.feedback.store import feedback_store, FeedbackStorageError
    try:
        ticket = asyncio.run(feedback_store.admin_detail(ticket_id))
        if ticket is None:
            return jsonify({"error": "Ticket not found"}), 404
        return jsonify({"ticket": ticket})
    except FeedbackStorageError:
        return jsonify({"error": "Turso unavailable"}), 503

@app.route('/api/admin/feedback/<ticket_id>/events', methods=['GET'])
@login_required
def feedback_admin_events(ticket_id: str):
    from features.feedback.store import feedback_store, FeedbackStorageError
    try:
        return jsonify({"events": asyncio.run(feedback_store.admin_events(ticket_id=ticket_id))})
    except FeedbackStorageError:
        return jsonify({"error": "Turso unavailable"}), 503


@app.route('/api/admin/feedback/<ticket_id>/review', methods=['POST'])
@login_required
def feedback_review(ticket_id: str):
    from features.feedback.store import feedback_store, FeedbackStorageError
    if not (ticket_id.startswith("FB-") and len(ticket_id) <= 30):
        return jsonify({"error": "Ticket không hợp lệ"}), 400
    if (request.headers.get('X-CSRF-Token') or '') != session.get('feedback_csrf'):
        return jsonify({"error": "Invalid CSRF token"}), 403
    if request.mimetype != 'application/json':
        return jsonify({"error": "JSON required"}), 415
    payload = request.get_json(silent=True) or {}
    try:
        asyncio.run(feedback_store.review(
            ticket_id=ticket_id, status=str(payload.get("status", "")),
            reason=str(payload.get("reason", "")), actor_id="dashboard-admin",
            verified_version=str(payload.get("verified_version", "")),
        ))
        return jsonify({"ok": True, "ticket_id": ticket_id})
    except FeedbackStorageError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route('/admin/feedback', methods=['GET'])
@login_required
def feedback_dashboard():
    return render_template('feedback.html', feedback_csrf=admin_csrf_token(),
                           page="feedback", selected_ticket="")


@app.route('/admin/feedback/<ticket_id>', methods=['GET'])
@login_required
def feedback_ticket_page(ticket_id):
    return render_template('feedback.html', feedback_csrf=admin_csrf_token(),
                           page="feedback", selected_ticket=ticket_id)


@app.route('/api/admin/feedback/<ticket_id>/evidence/<int:index>', methods=['GET'])
@login_required
def feedback_evidence(ticket_id: str, index: int):
    from flask import Response
    from features.feedback.store import feedback_store, FeedbackStorageError
    from features.feedback.evidence import evidence_store
    if not ticket_id.startswith('FB-') or not 0 <= index <= 2:
        return jsonify({"error": "Not found"}), 404
    try:
        ticket = asyncio.run(feedback_store.admin_detail(ticket_id))
        if ticket is None or index >= len(ticket['evidence']):
            return jsonify({"error": "Not found"}), 404
        key = ticket['evidence'][index].get('key', '')
        if not key.startswith('feedback/') or '..' in key:
            return jsonify({"error": "Invalid evidence"}), 404
        obj = evidence_store._s3().get_object(Bucket=evidence_store.bucket, Key=key)
        raw = obj['Body'].read(8388609)
        if len(raw) > 8388608:
            return jsonify({"error": "File too large"}), 413
        return Response(raw, content_type='image/png', headers={
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; sandbox",
        })
    except Exception:
        return jsonify({"error": "Private evidence currently unavailable"}), 503


# T23.3 — Private ChatGPT/plugin bridge. Disabled until a scoped token is set.
def feedback_connector_required(fn):
    @wraps(fn)
    def checked(*args, **kwargs):
        configured = os.environ.get("ASUMI_FEEDBACK_CONNECTOR_TOKEN", "")
        supplied = (request.headers.get("Authorization", "") or "")
        expected = "Bearer " + configured
        if len(configured) < 32 or not hmac.compare_digest(supplied, expected):
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return checked


@app.route('/api/feedback-connector/v1/tickets', methods=['GET'])
@feedback_connector_required
def connector_feedback_list():
    from features.feedback.store import feedback_store, FeedbackStorageError
    try:
        limit = min(100, max(1, int(request.args.get('limit', '25'))))
        records = asyncio.run(feedback_store.admin_list(
            status=(request.args.get('status') or '')[:30], limit=limit
        ))
        # Send metadata and text, not raw screenshots or S3 object keys.
        for ticket in records:
            ticket['evidence_count'] = len(ticket.pop('evidence', []))
        return jsonify({"tickets": records})
    except (FeedbackStorageError, ValueError):
        return jsonify({"error": "Unavailable"}), 503


@app.route('/api/feedback-connector/v1/tickets/<ticket_id>/review', methods=['POST'])
@feedback_connector_required
def connector_feedback_review(ticket_id):
    # Read-only until owner identity and per-decision approval are cryptographically bound.
    return jsonify({"error":"Review writes disabled pending owner-authenticated approval"}), 403

@app.route('/api/admin/feedback/<ticket_id>/links', methods=['POST'])
@login_required
def feedback_implementation_links(ticket_id):
    from features.feedback.store import feedback_store, FeedbackStorageError
    if request.mimetype != 'application/json':
        return jsonify({"error":"JSON required"}), 415
    if (request.headers.get('X-CSRF-Token') or '') != session.get('feedback_csrf'):
        return jsonify({"error":"Invalid CSRF token"}), 403
    data = request.get_json(silent=True) or {}
    try:
        asyncio.run(feedback_store.link_delivery(
            ticket_id=ticket_id,
            issue_url=str(data.get('issue_url') or ''),
            pr_url=str(data.get('pr_url') or ''),
            version=str(data.get('version') or ''),
        ))
        return jsonify({"ok":True})
    except FeedbackStorageError as exc:
        return jsonify({"error":str(exc)}), 400


@app.route('/api/feedback-connector/v1/tickets/<ticket_id>', methods=['GET'])
@feedback_connector_required
def connector_feedback_detail(ticket_id):
    from features.feedback.store import feedback_store, FeedbackStorageError
    try:
        data = asyncio.run(feedback_store.admin_detail(ticket_id))
        if data is None:
            return jsonify({"error":"Ticket not found"}), 404
        data['evidence_count'] = len(data.pop('evidence',[]))
        return jsonify({"ticket":data})
    except FeedbackStorageError:
        return jsonify({"error":"Unavailable"}), 503


@app.route('/api/admin/feedback/metrics', methods=['GET'])
@login_required
def feedback_metrics():
    from features.feedback.store import feedback_store, FeedbackStorageError
    try:
        return jsonify(asyncio.run(feedback_store.review_metrics()))
    except FeedbackStorageError:
        return jsonify({"error": "Turso unavailable"}), 503


@app.route('/api/feedback-connector/v1/tickets/<ticket_id>/links', methods=['POST'])
@feedback_connector_required
def connector_feedback_links(ticket_id):
    # Read-only until owner identity and per-decision approval are cryptographically bound.
    return jsonify({"error":"Review writes disabled pending owner-authenticated approval"}), 403


# T23.3 — AI can PROPOSE, but only a logged-in owner can APPLY the decision.
@app.route('/api/feedback-connector/v1/tickets/<ticket_id>/proposals', methods=['POST'])
@feedback_connector_required
def connector_propose_feedback_review(ticket_id: str):
    from features.feedback.store import feedback_store, FeedbackStorageError
    if request.mimetype != 'application/json':
        return jsonify({"error": "JSON required"}), 415
    data = request.get_json(silent=True) or {}
    try:
        proposal_id = asyncio.run(feedback_store.propose_review(
            ticket_id=ticket_id, target_status=str(data.get('status') or ''),
            reason=str(data.get('reason') or ''), source='chatgpt',
        ))
        return jsonify({"proposal_id": proposal_id, "ticket_id": ticket_id,
                        "state": "pending_owner_review"}), 202
    except FeedbackStorageError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route('/api/admin/feedback/<ticket_id>/proposals', methods=['GET'])
@login_required
def admin_feedback_proposals(ticket_id: str):
    from features.feedback.store import feedback_store, FeedbackStorageError
    try:
        items = asyncio.run(feedback_store.list_proposals(ticket_id=ticket_id))
        return jsonify({"proposals": items})
    except FeedbackStorageError:
        return jsonify({"error": "Turso unavailable"}), 503


@app.route('/api/admin/feedback/proposals/<proposal_id>/decision', methods=['POST'])
@login_required
def admin_feedback_proposal_decision(proposal_id: str):
    from features.feedback.store import feedback_store, FeedbackStorageError
    if request.mimetype != 'application/json':
        return jsonify({"error": "JSON required"}), 415
    if not session.get('feedback_csrf') or not hmac.compare_digest(
        request.headers.get('X-CSRF-Token', ''), session['feedback_csrf']
    ):
        return jsonify({"error": "CSRF invalid"}), 403
    data = request.get_json(silent=True) or {}
    if type(data.get('accept')) is not bool:
        return jsonify({"error": "Boolean accept required"}), 400
    try:
        ticket_id = asyncio.run(feedback_store.decide_proposal(
            proposal_id=proposal_id, accept=data['accept'], actor_id='owner-dashboard',
        ))
        return jsonify({"ok": True, "ticket_id": ticket_id,
                        "decision": "accepted" if data['accept'] else "dismissed"})
    except FeedbackStorageError as exc:
        return jsonify({"error": str(exc)}), 400


# The ChatGPT MCP host cannot read server-side Render env values. OAuth
# binds a short-lived access token to the admin who explicitly consented.
def feedback_mcp_oauth_required(fn):
    @wraps(fn)
    def checked(*args, **kwargs):
        from features.feedback.oauth import authorize_bearer, CHALLENGE_METADATA, OAuthError
        try:
            authorized = asyncio.run(authorize_bearer(
                request.headers.get('Authorization', '')
            ))
        except (OAuthError, Exception):
            authorized = False
        if not authorized:
            response = jsonify({"error": "OAuth authorization required"})
            response.status_code = 401
            response.headers['WWW-Authenticate'] = (
                'Bearer resource_metadata="' + CHALLENGE_METADATA
                + '", scope="feedback:read feedback:propose"'
            )
            response.headers['Cache-Control'] = 'no-store'
            return response
        return fn(*args, **kwargs)
    return checked


# MCP Streamable HTTP JSON-RPC endpoint for the private ChatGPT plugin.
# Only read and propose tools exist; approval always requires owner Dashboard.
@app.route('/api/feedback-connector/mcp', methods=['GET', 'POST'])
@feedback_mcp_oauth_required
def feedback_mcp_http():
    from features.feedback.mcp_bridge import handle_mcp
    if request.method == 'GET':
        return jsonify({"error": "SSE not supported; use Streamable HTTP POST"}), 405
    if request.content_length is not None and request.content_length > 16384:
        return jsonify({"error": "Payload too large"}), 413
    if request.mimetype != 'application/json':
        return jsonify({"error": "JSON-RPC JSON body required"}), 415
    payload = request.get_json(silent=True)
    if payload is None or isinstance(payload, list):
        return jsonify({
            "jsonrpc": "2.0", "id": None,
            "error": {"code": -32600, "message": "Single JSON-RPC request required"}
        }), 400
    try:
        result = asyncio.run(handle_mcp(payload))
    except Exception as exc:
        print("[Feedback MCP] RPC error: " + type(exc).__name__, flush=True)
        return jsonify({
            "jsonrpc": "2.0", "id": payload.get("id"),
            "error": {"code": -32603, "message": "Internal server error"}
        }), 500
    if result is None:
        return "", 202
    return jsonify(result), 200


# T23 OAuth 2.1 authorization server for owner-only ChatGPT MCP access.
# Separate from the legacy static REST connector token used for internal callers.
@app.route('/.well-known/oauth-protected-resource', methods=['GET'])
@app.route('/.well-known/oauth-protected-resource/api/feedback-connector/mcp', methods=['GET'])
def asumi_mcp_protected_resource_metadata():
    from features.feedback.oauth import ISSUER, RESOURCE, SCOPE
    return jsonify({
        "resource": RESOURCE, "authorization_servers": [ISSUER],
        "scopes_supported": SCOPE.split(),
        "resource_documentation": ISSUER + "/admin/feedback",
    })


@app.route('/.well-known/oauth-authorization-server', methods=['GET'])
def asumi_mcp_authorization_server_metadata():
    from features.feedback.oauth import ISSUER, SCOPE
    return jsonify({
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/oauth/authorize",
        "token_endpoint": ISSUER + "/oauth/token",
        "registration_endpoint": ISSUER + "/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": SCOPE.split(),
    })


@app.route('/oauth/register', methods=['POST'])
def asumi_mcp_oauth_register():
    from features.feedback.oauth import register_chatgpt_client, OAuthError
    if request.mimetype != 'application/json':
        return jsonify({"error": "invalid_client_metadata"}), 415
    if request.content_length is not None and request.content_length > 4096:
        return jsonify({"error": "invalid_client_metadata"}), 413
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "invalid_client_metadata"}), 400
    # Reject clients that can bypass public-client PKCE or redirect outside ChatGPT.
    if data.get("token_endpoint_auth_method", "none") != "none":
        return jsonify({"error": "invalid_client_metadata"}), 400
    grants = data.get("grant_types", ["authorization_code"])
    if not isinstance(grants, list) or "authorization_code" not in grants:
        return jsonify({"error": "invalid_client_metadata"}), 400
    try:
        record = asyncio.run(register_chatgpt_client(data.get("redirect_uris")))
        response = jsonify(record)
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response
    except OAuthError as exc:
        return jsonify({"error": exc.error, "error_description": exc.description}), exc.status


@app.route('/oauth/authorize', methods=['GET', 'POST'])
def asumi_mcp_oauth_authorize():
    from features.feedback.oauth import (
        validate_auth_request, issue_code, OAuthError, ISSUER
    )
    from flask import render_template_string
    from urllib.parse import urlencode

    # No consent through ChatGPT tool calls: user must sign in and click approve.
    if not session.get("logged_in"):
        return redirect(url_for("login_page", next=request.full_path if request.method == "GET" else "/admin"))

    if request.method == "GET":
        try:
            pending = asyncio.run(validate_auth_request(dict(request.args)))
        except OAuthError as exc:
            return jsonify({"error": exc.error, "error_description": exc.description}), exc.status
        import secrets
        session["asumi_mcp_oauth_pending"] = pending
        session["asumi_mcp_oauth_csrf"] = secrets.token_urlsafe(32)
        session.modified = True
        return render_template_string(
            """<!doctype html><html lang="vi"><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Asumi Feedback — ChatGPT access</title>
            <style>body{max-width:510px;margin:8vh auto;font:16px/1.6 system-ui;padding:20px}
            main{border:1px solid #bbb;border-radius:14px;padding:25px}
            button{padding:12px 20px;margin-right:12px;cursor:pointer}</style></head>
            <body><main><h2>Cho phép ChatGPT truy cập Asumi Feedback?</h2>
            <p>Bạn đang đăng nhập với quyền quản trị Asumi.</p>
            <p>ChatGPT được <strong>đọc ticket</strong> và <strong>đề xuất review</strong>.
            ChatGPT <strong>không được tự duyệt/từ chối</strong>.
            Quyết định vẫn cần bạn bấm xác nhận trong Feedback Inbox.</p>
            <form method="POST" action="/oauth/authorize">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <button name="decision" value="allow">Cho phép kết nối</button>
            <button name="decision" value="deny">Từ chối</button>
            </form></main></body></html>""",
            csrf=session["asumi_mcp_oauth_csrf"],
        )

    pending = session.get("asumi_mcp_oauth_pending")
    secret = session.get("asumi_mcp_oauth_csrf", "")
    session.pop("asumi_mcp_oauth_pending", None)
    session.pop("asumi_mcp_oauth_csrf", None)
    if not isinstance(pending, dict) or not secret or not hmac.compare_digest(
        str(request.form.get("csrf", "")), secret
    ):
        return jsonify({"error": "access_denied", "error_description": "Invalid consent session"}), 403
    if request.form.get("decision") != "allow":
        return redirect(pending["redirect_uri"] + "?" + urlencode({
            "error": "access_denied", "state": pending["state"]
        }), code=302)
    try:
        code = asyncio.run(issue_code(pending))
    except OAuthError as exc:
        return jsonify({"error": exc.error, "error_description": exc.description}), exc.status
    return redirect(pending["redirect_uri"] + "?" + urlencode({
        "code": code, "state": pending["state"], "iss": ISSUER,
    }), code=302)


@app.route('/oauth/token', methods=['POST'])
def asumi_mcp_oauth_token():
    from features.feedback.oauth import (
        exchange_code, refresh_access_token, OAuthError
    )
    if request.mimetype != "application/x-www-form-urlencoded":
        return jsonify({"error": "invalid_request"}), 415
    grant = request.form.get("grant_type")
    params = dict(request.form)
    try:
        if grant == "authorization_code":
            result = asyncio.run(exchange_code(params))
        elif grant == "refresh_token":
            result = asyncio.run(refresh_access_token(params))
        else:
            return jsonify({"error": "unsupported_grant_type"}), 400
    except OAuthError as exc:
        result = jsonify({"error": exc.error, "error_description": exc.description})
        result.status_code = exc.status
        result.headers["Cache-Control"] = "no-store"
        return result
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route('/api/admin/feedback/oauth/revoke', methods=['POST'])
@login_required
def asumi_mcp_owner_revoke_tokens():
    from features.feedback.oauth import revoke_all_owner_tokens, OAuthError
    token = request.headers.get('X-CSRF-Token', '')
    expected = session.get('feedback_csrf', '')
    if not expected or not hmac.compare_digest(token, expected):
        return jsonify({"error": "Invalid CSRF token"}), 403
    try:
        count = asyncio.run(revoke_all_owner_tokens())
        return jsonify({"revoked": count, "ok": True})
    except OAuthError as exc:
        return jsonify({"error": exc.error}), exc.status
