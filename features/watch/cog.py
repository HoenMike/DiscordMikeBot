"""
features/watch/cog.py - Discord Slash Commands & Cog interface for Asumi Watch Engine.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

import config
from core.activity_logger import activity_logger
from core.branding import BOT_BRAND_NAME
from features.watch.constants import (
    CADENCE_PRESETS,
    CONDITION_MAX_LEN,
    MSG_NOT_CONFIGURED,
    QUERY_MAX_LEN,
    TITLE_MAX_LEN,
    VALID_CADENCE_HOURS,
    WATCH_EMBED_COLOR,
)
from features.watch.manager import watch_manager
from features.watch.models import WatchDefinition, WatchStatus
from features.watch.scheduler import WatchScheduler
from features.watch.search import (
    BraveSearchProvider,
    get_current_month_key,
    get_remaining_days_in_month,
)


def _format_utc_to_vn(iso_utc: Optional[str]) -> str:
    if not iso_utc:
        return "Chưa có"
    try:
        dt = datetime.fromisoformat(iso_utc)
        vn_dt = dt.astimezone(timezone(timedelta(hours=7)))
        return vn_dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso_utc)[:16]


class WatchCreateModal(discord.ui.Modal, title="🔭 Tạo Asumi Watch Mới"):
    watch_title = discord.ui.TextInput(
        label="Tiêu đề theo dõi",
        placeholder="VD: PUBG VN Krafton, Petit Planet Release...",
        max_length=TITLE_MAX_LEN,
        required=True,
    )
    search_query = discord.ui.TextInput(
        label="Từ khóa tìm kiếm Web",
        placeholder="VD: PUBG Vietnam Krafton GAM All Gamers",
        max_length=QUERY_MAX_LEN,
        required=True,
    )
    condition_prompt = discord.ui.TextInput(
        label="Điều kiện cần báo (tùy chọn)",
        placeholder="VD: Chỉ báo khi có phản hồi chính thức hoặc thông báo ngày phát hành...",
        style=discord.TextStyle.paragraph,
        max_length=CONDITION_MAX_LEN,
        required=False,
    )

    def __init__(self, cadence_hours: int = 24, stop_after_trigger: bool = False):
        super().__init__()
        self.cadence_hours = cadence_hours
        self.stop_after_trigger = stop_after_trigger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        channel_id = interaction.channel_id or 0
        guild_id = interaction.guild_id

        try:
            watch = await watch_manager.create_watch(
                owner_user_id=user.id,
                channel_id=channel_id,
                title=self.watch_title.value,
                search_query=self.search_query.value,
                guild_id=guild_id,
                condition_prompt=self.condition_prompt.value or None,
                cadence_hours=self.cadence_hours,
                stop_after_trigger=self.stop_after_trigger,
            )

            embed = discord.Embed(
                title=f"✨ ĐÃ TẠO WATCH #{watch.id} THÀNH CÔNG!",
                description=(
                    f"**Tiêu đề:** {watch.title}\n"
                    f"**Từ khóa:** `{watch.search_query}`\n"
                    f"**Điều kiện:** {watch.condition_prompt or '*Bất kỳ diễn biến mới nào*'}\n"
                    f"**Tần suất kiểm tra:** Mỗi {watch.cadence_hours} giờ\n"
                    f"**Kênh nhận báo:** <#{watch.channel_id}>\n"
                    f"**Tự dừng khi đạt:** {'Có' if watch.stop_after_trigger else 'Không'}\n\n"
                    f"💡 *Lần kiểm tra đầu tiên sẽ thiết lập mốc so sánh (baseline) trong nền "
                    f"và sẽ chỉ gửi thông báo khi phát hiện thay đổi thực sự có ý nghĩa!*"
                ),
                color=WATCH_EMBED_COLOR,
            )
            embed.set_footer(text=f"Asumi Watch Engine • ID #{watch.id}")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ **Không thể tạo Watch:** {e}", ephemeral=True)


class WatchGroup(app_commands.Group):
    """Nhóm lệnh /watch điều khiển tính năng theo dõi Web."""

    def __init__(self):
        super().__init__(name="watch", description="Theo dõi thông tin Web và cảnh báo diễn biến mới")


class WatchCog(commands.Cog, name="Watch"):
    """Cog quản lý tính năng Persistent Web Monitoring (Watch Engine)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.search_provider = BraveSearchProvider()
        self.scheduler = WatchScheduler(bot=bot, search_provider=self.search_provider)
        self._run_now_cooldowns: dict = {}  # user_id -> monotonic timestamp

    async def cog_load(self):
        """Khởi tạo database và scheduler an toàn."""
        try:
            await watch_manager.init_db()
            print("✅ [Watch] Đã khởi tạo cơ sở dữ liệu Watch Engine thành công.", flush=True)
        except Exception as e:
            print(f"❌ [Watch] Lỗi khởi tạo DB Watch: {e}", flush=True)

        self.scheduler.start()
        print("✅ [Watch] WatchScheduler heartbeat loop đã khởi động.", flush=True)

    async def cog_unload(self):
        """Dọn dẹp scheduler và các tài nguyên in-flight."""
        await self.scheduler.stop()
        print("🛑 [Watch] WatchScheduler đã dừng và giải phóng toàn bộ tác vụ nền.", flush=True)

    # =========================================================================
    # SLASH COMMANDS (/watch ...)
    # =========================================================================

    watch_group = WatchGroup()

    @watch_group.command(name="create", description="Tạo một mục theo dõi Web mới (Asumi Watch)")
    @app_commands.describe(
        cadence="Tần suất kiểm tra thông tin định kỳ",
        stop_after_trigger="Tự động hoàn tất và dừng Watch khi điều kiện đã được thỏa mãn",
    )
    @app_commands.choices(
        cadence=[
            app_commands.Choice(name="Nhanh (mỗi 6 giờ)", value=6),
            app_commands.Choice(name="Hàng ngày (mỗi 24 giờ - Mặc định)", value=24),
            app_commands.Choice(name="Thư thả (mỗi 3 ngày / 72 giờ)", value=72),
            app_commands.Choice(name="Hàng tuần (mỗi 7 ngày / 168 giờ)", value=168),
        ]
    )
    async def watch_create_slash(
        self,
        interaction: discord.Interaction,
        cadence: Optional[app_commands.Choice[int]] = None,
        stop_after_trigger: Optional[bool] = False,
    ):
        chosen_cadence = cadence.value if cadence else 24
        modal = WatchCreateModal(
            cadence_hours=chosen_cadence,
            stop_after_trigger=bool(stop_after_trigger),
        )
        await interaction.response.send_modal(modal)

    @watch_group.command(name="list", description="Xem danh sách các Watch bạn đang theo dõi")
    async def watch_list_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        watches = await watch_manager.list_user_watches(user.id)

        if not watches:
            await interaction.followup.send(
                "📭 **Bạn chưa có mục Watch nào!** Dùng lệnh `/watch create` để bắt đầu theo dõi một chủ đề.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🔭 DANH SÁCH WATCH CỦA BẠN ({len(watches)} mục)",
            color=WATCH_EMBED_COLOR,
        )

        status_emoji = {
            WatchStatus.ACTIVE.value: "🟢 Đang chạy",
            WatchStatus.PAUSED.value: "⏸️ Tạm dừng",
            WatchStatus.COMPLETED.value: "✅ Hoàn tất",
            WatchStatus.CONFIG_ERROR.value: "⚠️ Lỗi cấu hình",
            WatchStatus.DISABLED.value: "⛔ Đã tắt",
        }

        for w in watches[:10]:
            st = status_emoji.get(w.status, w.status)
            last_checked = _format_utc_to_vn(w.last_checked_at)
            next_run = _format_utc_to_vn(w.next_run_at)
            cond = f"\n• *Điều kiện:* {w.condition_prompt[:60]}..." if w.condition_prompt else ""
            embed.add_field(
                name=f"#{w.id} — {w.title}",
                value=(
                    f"• *Trạng thái:* {st}\n"
                    f"• *Tần suất:* Mỗi {w.cadence_hours}h | *Kênh:* <#{w.channel_id}>\n"
                    f"• *Kiểm tra gần nhất:* {last_checked} | *Kế tiếp:* {next_run}{cond}"
                ),
                inline=False,
            )

        if len(watches) > 10:
            embed.set_footer(text=f"Hiển thị 10/{len(watches)} mục • Dùng /watch view [id] để xem chi tiết.")
        else:
            embed.set_footer(text="Dùng /watch view [id] để xem chi tiết hoặc /watch pause/resume/delete.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @watch_group.command(name="view", description="Xem chi tiết trạng thái và diễn biến của một Watch")
    @app_commands.describe(watch_id="ID của Watch cần xem (VD: 1, 2, 3...)")
    async def watch_view_slash(self, interaction: discord.Interaction, watch_id: int):
        await interaction.response.defer(ephemeral=True)
        watch = await watch_manager.get_watch(watch_id)

        if not watch:
            await interaction.followup.send("❌ **Không tìm thấy Watch với ID này!**", ephemeral=True)
            return

        is_owner = (watch.owner_user_id == interaction.user.id)
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator

        if not (is_owner or is_admin):
            await interaction.followup.send("🔒 **Bạn không có quyền xem thông tin chi tiết Watch này!**", ephemeral=True)
            return

        state = watch.get_state()
        summary = state.get("summary", "Chưa có tóm tắt dữ liệu.")
        last_change = state.get("last_major_change", "Chưa phát hiện thay đổi lớn.")
        known_facts = state.get("known_facts", [])

        embed = discord.Embed(
            title=f"🔭 CHI TIẾT WATCH #{watch.id}: {watch.title}",
            color=WATCH_EMBED_COLOR,
        )
        embed.add_field(name="🔎 Từ khóa tìm kiếm", value=f"`{watch.search_query}`", inline=False)
        if watch.condition_prompt:
            embed.add_field(name="🎯 Điều kiện cảnh báo", value=watch.condition_prompt, inline=False)

        embed.add_field(name="📊 Trạng thái", value=watch.status.upper(), inline=True)
        embed.add_field(name="⏳ Chu kỳ", value=f"Mỗi {watch.cadence_hours}h", inline=True)
        embed.add_field(name="📢 Kênh nhận", value=f"<#{watch.channel_id}>", inline=True)

        embed.add_field(name="🕒 Lần kiểm tra gần nhất", value=_format_utc_to_vn(watch.last_checked_at), inline=True)
        embed.add_field(name="🔔 Lần báo gần nhất", value=_format_utc_to_vn(watch.last_notified_at), inline=True)
        embed.add_field(name="⏭️ Lần chạy kế tiếp", value=_format_utc_to_vn(watch.next_run_at), inline=True)

        embed.add_field(name="📝 Tóm tắt bối cảnh hiện tại", value=summary[:1000], inline=False)
        embed.add_field(name="⚡ Diễn biến đáng chú ý gần nhất", value=last_change[:500], inline=False)

        if known_facts:
            facts_text = "\n".join([f"• {f}" for f in known_facts[:5]])
            embed.add_field(name="📌 Dữ kiện đã ghi nhận", value=facts_text[:1000], inline=False)

        if watch.last_error:
            embed.add_field(name="⚠️ Lỗi gần nhất", value=f"`{watch.last_error[:200]}`", inline=False)

        embed.set_footer(text=f"Tạo lúc {_format_utc_to_vn(watch.created_at)} • Chủ sở hữu: <@{watch.owner_user_id}>")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @watch_group.command(name="pause", description="Tạm dừng một Watch đang hoạt động")
    @app_commands.describe(watch_id="ID của Watch cần tạm dừng")
    async def watch_pause_slash(self, interaction: discord.Interaction, watch_id: int):
        await interaction.response.defer(ephemeral=True)
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator

        try:
            success = await watch_manager.pause_watch(watch_id, interaction.user.id, is_admin=is_admin)
            if success:
                await interaction.followup.send(f"⏸️ **Đã tạm dừng Watch #{watch_id} thành công!**", ephemeral=True)
            else:
                await interaction.followup.send("❌ Không tìm thấy Watch với ID này!", ephemeral=True)
        except PermissionError as pe:
            await interaction.followup.send(f"⛔ {pe}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi: {e}", ephemeral=True)

    @watch_group.command(name="resume", description="Kích hoạt lại một Watch đang tạm dừng")
    @app_commands.describe(watch_id="ID của Watch cần kích hoạt lại")
    async def watch_resume_slash(self, interaction: discord.Interaction, watch_id: int):
        await interaction.response.defer(ephemeral=True)
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator

        try:
            success = await watch_manager.resume_watch(watch_id, interaction.user.id, is_admin=is_admin)
            if success:
                await interaction.followup.send(f"▶️ **Đã kích hoạt lại Watch #{watch_id}!** Lịch kiểm tra được kích hoạt ngay.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Không tìm thấy Watch với ID này!", ephemeral=True)
        except (PermissionError, ValueError) as err:
            await interaction.followup.send(f"⛔ {err}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi: {e}", ephemeral=True)

    @watch_group.command(name="delete", description="Xóa vĩnh viễn một Watch và toàn bộ dữ liệu lịch sử")
    @app_commands.describe(watch_id="ID của Watch cần xóa")
    async def watch_delete_slash(self, interaction: discord.Interaction, watch_id: int):
        await interaction.response.defer(ephemeral=True)
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator

        try:
            success = await watch_manager.delete_watch(watch_id, interaction.user.id, is_admin=is_admin)
            if success:
                await interaction.followup.send(f"🗑️ **Đã xóa vĩnh viễn Watch #{watch_id} và dữ liệu liên quan.**", ephemeral=True)
            else:
                await interaction.followup.send("❌ Không tìm thấy Watch với ID này!", ephemeral=True)
        except PermissionError as pe:
            await interaction.followup.send(f"⛔ {pe}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi: {e}", ephemeral=True)

    @watch_group.command(name="run-now", description="Thực hiện kiểm tra thủ công Watch ngay lập tức (Áp dụng Cooldown)")
    @app_commands.describe(watch_id="ID của Watch cần kiểm tra ngay")
    async def watch_run_now_slash(self, interaction: discord.Interaction, watch_id: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        # Cooldown per user: 60s
        now_mono = time.monotonic()
        last_call = self._run_now_cooldowns.get(user_id, 0.0)
        if now_mono - last_call < 60.0:
            remaining = int(60.0 - (now_mono - last_call)) + 1
            await interaction.followup.send(
                f"⏳ **Bạn đang thao tác quá nhanh!** Vui lòng đợi `{remaining}s` trước khi gọi lại run-now.",
                ephemeral=True,
            )
            return

        watch = await watch_manager.get_watch(watch_id)
        if not watch:
            await interaction.followup.send("❌ **Không tìm thấy Watch với ID này!**", ephemeral=True)
            return

        is_owner = (watch.owner_user_id == user_id)
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator

        if not (is_owner or is_admin):
            await interaction.followup.send("🔒 **Bạn không có quyền thực thi Watch này!**", ephemeral=True)
            return

        self._run_now_cooldowns[user_id] = now_mono

        try:
            run = await self.scheduler.execute_watch(watch, is_manual=True)
            msg_status = {
                "no_change": "Đã kiểm tra xong: Không phát hiện thay đổi mới nào (kênh chat giữ yên lặng).",
                "baseline": f"Đã thiết lập mốc so sánh ban đầu với {run.new_result_count} kết quả hiện có.",
                "success": "Đã kiểm tra xong và cập nhật trạng thái Watch!",
                "budget_exhausted": "Hạn ngạch tìm kiếm tháng này đã đạt giới hạn.",
                "ai_failed": "Phát hiện kết quả mới nhưng AI tạm thời gặp lỗi; ứng viên đã được lưu lại để thử lại sau.",
                "search_failed": f"Tìm kiếm thất bại: {run.error_text}",
            }.get(run.status, f"Hoàn tất với trạng thái: {run.status}")

            notif_str = "\n🔔 **Đã phát hiện diễn biến đáng chú ý và gửi thông báo tới kênh!**" if run.notification_sent else ""
            await interaction.followup.send(
                f"✨ **Kết quả kiểm tra thủ công Watch #{watch.id}:**\n• {msg_status}{notif_str}\n• Thời gian thực thi: `{run.duration_ms}ms`",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi khi thực thi Watch: {e}", ephemeral=True)

    @watch_group.command(name="budget", description="Xem hạn ngạch tìm kiếm Web và thống kê sử dụng")
    async def watch_budget_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        stats = await watch_manager.get_dashboard_stats()

        embed = discord.Embed(
            title="📊 HẠN NGẠCH & THỐNG KÊ TÌM KIẾM WEB (ASUMI WATCH)",
            color=WATCH_EMBED_COLOR,
        )

        brave_status = "🟢 Đã kết nối" if stats["brave_configured"] else "⚪ Chưa cấu hình (Chế độ chờ)"
        embed.add_field(name="Brave Search Provider", value=brave_status, inline=True)
        embed.add_field(name="Mục Watch Đang Chạy", value=f"**{stats['active_watches']}** mục", inline=True)
        embed.add_field(name="Kiểm Tra Hôm Nay", value=f"**{stats['checks_today']}** lượt", inline=True)

        embed.add_field(
            name="Hạn Ngạch Tìm Kiếm Tháng",
            value=f"**{stats['monthly_searches']}** / **{stats['monthly_limit']}** lượt",
            inline=True,
        )
        embed.add_field(
            name="Còn Lại Trong Tháng",
            value=f"**{stats['budget_remaining']}** lượt",
            inline=True,
        )
        embed.add_field(
            name="Gợi Ý Dùng Hàng Ngày",
            value=f"~**{stats['daily_allowance']}** lượt/ngày ({stats['days_left']} ngày còn lại)",
            inline=True,
        )

        embed.add_field(name="Bộ Đệm Tiết Kiệm (Cache Hits)", value=f"**{stats['cache_hits']}** lượt", inline=True)
        embed.add_field(name="Đánh Giá AI (Gemini)", value=f"**{stats['ai_evaluations']}** lượt", inline=True)
        embed.add_field(name="Thông Báo Đã Gửi", value=f"**{stats['notifications_sent']}** thông báo", inline=True)

        embed.set_footer(text="Hạn ngạch tìm kiếm được quản lý bền vững và tự động làm mới vào đầu mỗi tháng.")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Entry point when extension is loaded via bot.load_extension('features.watch.cog')."""
    cog = WatchCog(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.watch_group)
