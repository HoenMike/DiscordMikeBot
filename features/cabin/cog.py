"""
features/cabin/cog.py - Cog điều khiển Slash Command, Prefix Command và Listener cho tính năng Dịch Cabin AI.
"""

import asyncio
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.activity_logger import activity_logger
from features.cabin.ai import generate_cabin_interpretation, generate_cabin_interpretation_batch
from features.cabin.constants import (
    CABIN_EMBED_COLOR,
    CONTEXT_HISTORY_MINUTES,
    CONTEXT_MAX_MESSAGES,
    DEFAULT_DURATION_SECONDS,
    format_duration,
    parse_duration,
)
from features.cabin.manager import cabin_manager


class CabinStopView(discord.ui.View):
    """View tương tác chứa nút Dừng Cabin 1-chạm."""

    def __init__(self, guild_id: int, target_id: int, creator_id: int, timeout: Optional[float] = 10800):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.target_id = target_id
        self.creator_id = creator_id

    @discord.ui.button(label="Dừng Cabin", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        # Kiểm tra quyền: Nạn nhân, Người tạo ban đầu, Người điều khiển hiện tại (nếu bị đè quyền), hoặc Quản trị viên
        is_target = (user.id == self.target_id)
        session = cabin_manager.get_session(self.guild_id, self.target_id)
        is_creator = (user.id == self.creator_id) or (session and user.id == session.creator_id)
        is_admin = False
        if isinstance(user, discord.Member):
            is_admin = user.guild_permissions.manage_messages or user.guild_permissions.administrator

        if not (is_target or is_creator or is_admin):
            await interaction.response.send_message(
                "⛔ **Bạn không có quyền dừng phiên cabin này!** Chỉ nạn nhân, người bật hoặc Quản trị viên mới có thể bấm dừng.",
                ephemeral=True
            )
            return

        # Thực hiện dừng session
        stopped = await cabin_manager.stop_session(self.guild_id, self.target_id)
        button.disabled = True
        button.label = "Đã Dừng Cabin"

        if stopped:
            stop_embed = discord.Embed(
                title="🛑 ĐÃ DỪNG CHẾ ĐỘ DỊCH CABIN",
                description=(
                    f"Phiên Dịch Cabin cho <@{self.target_id}> đã được dừng bởi {user.mention}.\n"
                    f"🕊️ Thành viên này giờ đã có thể thoải mái trò chuyện bình thường!"
                ),
                color=0x95A5A6
            )
            await interaction.response.edit_message(embed=stop_embed, view=self)
        else:
            await interaction.response.edit_message(
                content="ℹ️ Phiên Dịch Cabin này đã kết thúc hoặc không còn tồn tại.",
                view=self
            )


class CabinCog(commands.Cog, name="Cabin"):
    """Cog xử lý toàn bộ logic tính năng Dịch Cabin AI troll trực tiếp."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Debounce buffers: (guild_id, author_id) -> list of (text, discord.Message)
        self._msg_buffers: Dict = defaultdict(list)
        # Debounce tasks: (guild_id, author_id) -> asyncio.Task
        self._debounce_tasks: Dict = {}

    async def cog_load(self):
        """Khởi tạo database khi nạp Cog."""
        try:
            await cabin_manager.init_db()
            print("✅ [Cabin] Đã khởi tạo cơ sở dữ liệu và nạp các phiên cabin còn hiệu lực thành công.", flush=True)
        except Exception as e:
            print(f"❌ [Cabin] Lỗi khởi tạo DB cabin: {e}", flush=True)
        if not self.cleanup_task.is_running():
            self.cleanup_task.start()

    def cog_unload(self):
        if self.cleanup_task.is_running():
            self.cleanup_task.cancel()
        for task in self._debounce_tasks.values():
            task.cancel()
        self._debounce_tasks.clear()
        self._msg_buffers.clear()

    @tasks.loop(seconds=60.0)
    async def cleanup_task(self):
        """Tự động dọn dẹp các phiên cabin đã hết hạn định kỳ mỗi 60 giây."""
        try:
            cleaned = await cabin_manager.cleanup_expired()
            if cleaned > 0:
                print(f"🧹 [Cabin] Đã tự động dọn dẹp {cleaned} phiên cabin đã hết hạn.", flush=True)
        except Exception as e:
            print(f"⚠️ [Cabin] Lỗi dọn dẹp session hết hạn: {e}", flush=True)

    @cleanup_task.before_loop
    async def before_cleanup(self):
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            pass

    # =========================================================================
    # 🌟 SLASH COMMAND: /cabin @user [thoi_gian]
    # =========================================================================

    @app_commands.command(
        name="cabin",
        description="Bật hoặc tắt chế độ Dịch Cabin AI troll trực tiếp cho một người dùng"
    )
    @app_commands.describe(
        user="Người bạn muốn đưa vào buồng dịch cabin (hoặc tự tắt nếu đang chạy)",
        thoi_gian="Thời lượng dịch cabin (ví dụ: 10m, 30m, 1h - Mặc định 30 phút, tối đa 3 giờ)"
    )
    async def slash_cabin(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        thoi_gian: Optional[str] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Lệnh này chỉ có thể sử dụng trong máy chủ Discord!", ephemeral=True)
            return

        guild = interaction.guild

        # 1. Kiểm tra không cho phép cabin Bot
        if user.bot:
            await interaction.response.send_message(
                "🤖 **Không thể dịch cabin cho Bot!** Bot luôn nói thật lòng và không có gì để phiên dịch cả.",
                ephemeral=True
            )
            return

        # 2. Kiểm tra Khiên Chống Cabin của người mục tiêu (Được cấp từ Admin Dashboard)
        if cabin_manager.has_shield(guild.id, user.id):
            embed = discord.Embed(
                title="🛡️ KHIÊN BẢO VỆ!",
                description=f"**{user.mention} hiện đang được bảo vệ bởi Khiên Chống Cabin!**",
                color=0x3498DB
            )
            await interaction.response.send_message(embed=embed)
            return

        # 3. Cơ chế TOGGLE thông minh: Nếu chính nạn nhân hoặc chính người tạo muốn dừng -> TẮT NGAY
        active_session = cabin_manager.get_session(guild.id, user.id)
        if active_session:
            is_target = (interaction.user.id == user.id)
            is_creator = (active_session.creator_id == interaction.user.id)

            if is_target or is_creator:
                await cabin_manager.stop_session(guild.id, user.id)
                embed = discord.Embed(
                    title="🛑 ĐÃ TẮT CHẾ ĐỘ DỊCH CABIN",
                    description=(
                        f"Đã giải thoát thành công cho {user.mention} theo yêu cầu của {interaction.user.mention}!\n\n"
                        f"🕊️ Kể từ giờ, {user.display_name} có thể trò chuyện bình thường mà không bị bot bẻ lái nữa."
                    ),
                    color=0x95A5A6
                )
                await interaction.response.send_message(embed=embed)
                return

            # Nếu là người khác (C != target và C != creator cũ):
            # C sẽ ĐÈ QUYỀN của người tạo trước (A), gỡ phiên của A ra và tính vào cooldown/session limit của C!

        # 4. Kiểm tra giới hạn: C chỉ được tạo tối đa 1 phiên cabin cùng lúc (không được troll 2 người khác nhau)
        existing_session = cabin_manager.get_active_session_by_creator(guild.id, interaction.user.id)
        if existing_session and existing_session.target_id != user.id:
            rem_str = format_duration(existing_session.remaining_seconds)
            await interaction.response.send_message(
                f"⏳ **Bạn đang có một phiên Dịch Cabin đang hoạt động!**\n"
                f"• **Nạn nhân hiện tại:** <@{existing_session.target_id}>\n"
                f"• **Thời gian còn lại:** `{rem_str}`\n\n"
                f"💡 *Mỗi người chỉ được quản lý tối đa **1 phiên cabin** cùng lúc. "
                f"Hãy dừng phiên cũ trước (bằng nút 🛑 hoặc `/cabinstop`) nếu muốn troll người khác!*",
                ephemeral=True
            )
            return

        # 5. Phân tích thời gian hợp lệ
        duration_seconds = parse_duration(thoi_gian)
        if duration_seconds is None:
            await interaction.response.send_message(
                "❌ **Thời gian không hợp lệ!**\n"
                "👉 Bạn có thể nhập: `10m`, `30m`, `45p`, `1h`, `2h` (Mặc định: `30m`, tối thiểu 1 phút, tối đa 3 giờ).",
                ephemeral=True
            )
            return

        old_creator_id = active_session.creator_id if active_session else None

        session = await cabin_manager.start_session(
            guild_id=guild.id,
            channel_id=interaction.channel_id,
            target_id=user.id,
            target_name=user.display_name,
            creator_id=interaction.user.id,
            creator_name=interaction.user.display_name,
            duration_seconds=duration_seconds,
        )

        formatted_time = format_duration(duration_seconds)
        if active_session:
            embed = discord.Embed(
                title="🎙️ ĐÃ ĐÈ QUYỀN DỊCH CABIN!",
                description=(
                    f"🎯 **Nạn nhân:** {user.mention}\n"
                    f"👑 **Người điều khiển mới:** {interaction.user.mention}\n"
                    f"🔄 **Đã gỡ quyền của:** <@{old_creator_id}>\n"
                    f"⏳ **Thời lượng mới:** `{formatted_time}`\n\n"
                    f"⚡ *Phiên cabin của <@{old_creator_id}> đã được gỡ bỏ hoàn toàn và chuyển sang cho {interaction.user.mention}. "
                    f"Cooldown dịch của {user.display_name} đã được reset về 0 để tiếp tục troll ngay lập tức!* 😂\n\n"
                    f"🛑 *Nạn nhân, người điều khiển mới hoặc Quản trị viên có thể bấm nút bên dưới để dừng bất kỳ lúc nào.*"
                ),
                color=CABIN_EMBED_COLOR
            )
        else:
            embed = discord.Embed(
                title="🎙️ ĐÃ BẬT CHẾ ĐỘ DỊCH CABIN TRỰC TIẾP!",
                description=(
                    f"🎯 **Đối tượng được 'chăm sóc':** {user.mention}\n"
                    f"⏳ **Thời lượng:** `{formatted_time}`\n"
                    f"👤 **Người yêu cầu:** {interaction.user.mention}\n\n"
                    f"💡 *Kể từ giờ, mỗi khi {user.display_name} gửi tin nhắn trong server, "
                    f"bot sẽ quét ngữ cảnh cuộc trò chuyện và 'phiên dịch cabin' trực tiếp câu nói đó sang tầng ý nghĩa sâu xa!* 😂\n\n"
                    f"🛑 *Nạn nhân hoặc Quản trị viên có thể bấm nút bên dưới để dừng bất kỳ lúc nào.*"
                ),
                color=CABIN_EMBED_COLOR
            )

        embed.set_footer(text="MikeDaBot Cabin Engine • Powered by Gemini 3.8 Flash")

        view = CabinStopView(
            guild_id=guild.id,
            target_id=user.id,
            creator_id=interaction.user.id,
            timeout=float(duration_seconds + 300)
        )

        await interaction.response.send_message(embed=embed, view=view)

    # =========================================================================
    # 🛑 SLASH COMMAND: /cabinstop [user]
    # =========================================================================

    @app_commands.command(
        name="cabinstop",
        description="Dừng nhanh phiên Dịch Cabin (dành cho người tạo, nạn nhân hoặc Quản trị viên)"
    )
    @app_commands.describe(
        user="Người dùng cần dừng phiên cabin (để trống nếu muốn dừng phiên của chính bạn)"
    )
    async def slash_cabinstop(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ Lệnh này chỉ có thể sử dụng trong máy chủ Discord!", ephemeral=True)
            return

        guild = interaction.guild
        author = interaction.user

        target_user = user
        if target_user is None:
            # 1. Nếu bản thân đang là nạn nhân
            if cabin_manager.is_active(guild.id, author.id):
                target_user = author
            else:
                # 2. Nếu bản thân là người tạo phiên dịch cho ai đó
                creator_session = cabin_manager.get_active_session_by_creator(guild.id, author.id)
                if creator_session:
                    target_user = guild.get_member(creator_session.target_id)
                    if not target_user:
                        await cabin_manager.stop_session(guild.id, creator_session.target_id)
                        await interaction.response.send_message("🛑 Đã dừng phiên Dịch Cabin bạn đã tạo thành công!")
                        return

        if not target_user or not cabin_manager.is_active(guild.id, target_user.id):
            await interaction.response.send_message(
                "ℹ️ Không tìm thấy phiên Dịch Cabin nào đang chạy liên quan đến bạn hoặc người được chọn.",
                ephemeral=True
            )
            return

        is_target = (author.id == target_user.id)
        is_admin = False
        if isinstance(author, discord.Member):
            is_admin = author.guild_permissions.manage_messages or author.guild_permissions.administrator
        session = cabin_manager.get_session(guild.id, target_user.id)
        is_creator = session and (session.creator_id == author.id)

        if not (is_target or is_creator or is_admin):
            await interaction.response.send_message(
                f"⛔ Bạn không có quyền dừng phiên cabin của {target_user.display_name}!",
                ephemeral=True
            )
            return

        await cabin_manager.stop_session(guild.id, target_user.id)
        await interaction.response.send_message(
            f"🛑 Đã dừng thành công phiên Dịch Cabin cho {target_user.mention}!"
        )

    # =========================================================================
    # 💬 PREFIX COMMANDS: .m cabin @user [thời_gian], .m cabinstop, .m cabinlist
    # =========================================================================

    @commands.group(name="cabin", invoke_without_command=True)
    async def prefix_cabin(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.Member, str]] = None,
        *,
        thoi_gian: Optional[str] = None
    ):
        """Lệnh tiền tố điều khiển Dịch Cabin: .m cabin @user [thời_gian]"""
        if not ctx.guild:
            await ctx.reply("❌ Lệnh này chỉ có thể sử dụng trong máy chủ Discord!", mention_author=False)
            return

        # Nếu người dùng chỉ gõ ".m cabin" không kèm tham số -> hiển thị hướng dẫn & danh sách đang chạy
        if target is None:
            active_sessions = cabin_manager.list_guild_sessions(ctx.guild.id)
            if not active_sessions:
                await ctx.reply(
                    "🎙️ **HƯỚNG DẪN DỊCH CABIN TROLL AI**\n\n"
                    "👉 **Bật/Tắt cabin:** `.m cabin @người_dùng [thời_gian]` hoặc `/cabin @người_dùng`\n"
                    "👉 **Dừng nhanh:** `.m cabinstop @người_dùng`\n"
                    "👉 **Xem danh sách:** `.m cabinlist`\n\n"
                    "*(Ví dụ: `.m cabin @Mike 30m` hoặc `.m cabin @Mike 1h`)*",
                    mention_author=False
                )
            else:
                lines = []
                for s in active_sessions:
                    rem = format_duration(s.remaining_seconds)
                    lines.append(f"• <@{s.target_id}>: còn `{rem}` (đã dịch `{s.translated_count}` câu)")
                await ctx.reply(
                    "🎙️ **DANH SÁCH ĐANG BỊ DỊCH CABIN TRONG SERVER:**\n" + "\n".join(lines) +
                    "\n\n👉 Dùng `.m cabinstop @người_dùng` để dừng.",
                    mention_author=False
                )
            return

        # Nếu truyền vào chuỗi không phải Member
        if isinstance(target, str):
            await ctx.reply("❌ Vui lòng tag đúng người dùng cần dịch cabin (ví dụ: `.m cabin @User 30m`).", mention_author=False)
            return

        if target.bot:
            await ctx.reply("🤖 Không thể dịch cabin cho Bot!", mention_author=False)
            return

        # Kiểm tra Khiên Chống Cabin của người mục tiêu (Được cấp từ Admin Dashboard)
        if cabin_manager.has_shield(ctx.guild.id, target.id):
            embed = discord.Embed(
                title="🛡️ KHIÊN BẢO VỆ!",
                description=f"**{target.mention} hiện đang được bảo vệ bởi Khiên Chống Cabin!**",
                color=0x3498DB
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        # 3. Cơ chế TOGGLE thông minh: Nếu chính nạn nhân hoặc chính người tạo muốn dừng -> TẮT NGAY
        active_session = cabin_manager.get_session(ctx.guild.id, target.id)
        if active_session:
            is_target = (ctx.author.id == target.id)
            is_creator = (active_session.creator_id == ctx.author.id)

            if is_target or is_creator:
                await cabin_manager.stop_session(ctx.guild.id, target.id)
                await ctx.reply(
                    f"🛑 **Đã dừng Dịch Cabin cho {target.mention}!** Người này giờ đã có thể trò chuyện bình thường.",
                    mention_author=False
                )
                return

            # Nếu là người khác (C != target và C != creator cũ): C sẽ đè quyền của người trước (A)!

        # 4. Kiểm tra giới hạn: C chỉ được tạo tối đa 1 phiên cabin cùng lúc (không được troll 2 người khác nhau)
        existing_session = cabin_manager.get_active_session_by_creator(ctx.guild.id, ctx.author.id)
        if existing_session and existing_session.target_id != target.id:
            rem_str = format_duration(existing_session.remaining_seconds)
            await ctx.reply(
                f"⏳ **Bạn đang có một phiên Dịch Cabin đang chạy!**\n"
                f"• **Nạn nhân hiện tại:** <@{existing_session.target_id}> (còn `{rem_str}`)\n"
                f"💡 *Mỗi người chỉ được tạo tối đa 1 phiên cabin cùng lúc. "
                f"Hãy dừng phiên cũ trước bằng `.m cabin @{existing_session.target_name}` hoặc `.m cabinstop` nhé!*",
                mention_author=False
            )
            return

        # 5. Phân tích thời gian hợp lệ
        duration_seconds = parse_duration(thoi_gian)
        if duration_seconds is None:
            await ctx.reply("❌ Thời gian không hợp lệ! Hãy nhập ví dụ: `15m`, `30m`, `1h` (Tối đa 3 giờ).", mention_author=False)
            return

        old_creator_id = active_session.creator_id if active_session else None

        await cabin_manager.start_session(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            target_id=target.id,
            target_name=target.display_name,
            creator_id=ctx.author.id,
            creator_name=ctx.author.display_name,
            duration_seconds=duration_seconds,
        )

        formatted_time = format_duration(duration_seconds)
        if active_session:
            embed = discord.Embed(
                title="🎙️ ĐÃ ĐÈ QUYỀN DỊCH CABIN!",
                description=(
                    f"🎯 **Nạn nhân:** {target.mention}\n"
                    f"👑 **Người điều khiển mới:** {ctx.author.mention}\n"
                    f"🔄 **Đã gỡ quyền của:** <@{old_creator_id}>\n"
                    f"⏳ **Thời lượng mới:** `{formatted_time}`\n\n"
                    f"⚡ *Phiên cabin của <@{old_creator_id}> đã được gỡ bỏ hoàn toàn và chuyển sang cho {ctx.author.mention}. "
                    f"Cooldown dịch của {target.display_name} đã được reset về 0 để tiếp tục troll ngay lập tức!* 😂\n\n"
                    f"🛑 *Nạn nhân, người điều khiển mới hoặc Quản trị viên có thể bấm nút bên dưới để dừng bất kỳ lúc nào.*"
                ),
                color=CABIN_EMBED_COLOR
            )
        else:
            embed = discord.Embed(
                title="🎙️ ĐÃ BẬT CHẾ ĐỘ DỊCH CABIN TRỰC TIẾP!",
                description=(
                    f"🎯 **Đối tượng:** {target.mention}\n"
                    f"⏳ **Thời lượng:** `{formatted_time}`\n"
                    f"👤 **Người yêu cầu:** {ctx.author.mention}\n\n"
                    f"💡 *Kể từ giờ, mỗi khi {target.display_name} nhắn tin, bot sẽ quét context cuộc trò chuyện và dịch trực tiếp sang tầng ý nghĩa sâu xa!* 😂\n\n"
                    f"🛑 *Nạn nhân hoặc Quản trị viên có thể bấm nút bên dưới để dừng bất kỳ lúc nào.*"
                ),
                color=CABIN_EMBED_COLOR
            )

        embed.set_footer(text="MikeDaBot Cabin Engine • Powered by Gemini 3.8 Flash")
        view = CabinStopView(
            guild_id=ctx.guild.id,
            target_id=target.id,
            creator_id=ctx.author.id,
            timeout=float(duration_seconds + 300)
        )
        await ctx.reply(embed=embed, view=view, mention_author=False)

    @prefix_cabin.command(name="stop", aliases=["tat", "dung", "cancel", "huy"])
    async def prefix_cabin_stop_sub(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """Lệnh con: .m cabin stop [@user]"""
        if not ctx.guild:
            return

        target_user = target
        if target_user is None:
            # Tự động nhận diện mục tiêu:
            # 1. Nạn nhân muốn tự tắt cho bản thân
            if cabin_manager.is_active(ctx.guild.id, ctx.author.id):
                target_user = ctx.author
            else:
                # 2. Người tạo muốn dừng phiên mà mình đang chạy cho người khác
                creator_session = cabin_manager.get_active_session_by_creator(ctx.guild.id, ctx.author.id)
                if creator_session:
                    target_user = ctx.guild.get_member(creator_session.target_id)
                    if not target_user:
                        await cabin_manager.stop_session(ctx.guild.id, creator_session.target_id)
                        await ctx.reply("🛑 Đã dừng phiên Dịch Cabin bạn đã tạo thành công!", mention_author=False)
                        return

        if not target_user or not cabin_manager.is_active(ctx.guild.id, target_user.id):
            await ctx.reply("ℹ️ Bạn hoặc người được chỉ định hiện không có phiên Dịch Cabin nào đang chạy.", mention_author=False)
            return

        is_target = (ctx.author.id == target_user.id)
        is_admin = ctx.author.guild_permissions.manage_messages or ctx.author.guild_permissions.administrator
        session = cabin_manager.get_session(ctx.guild.id, target_user.id)
        is_creator = session and (session.creator_id == ctx.author.id)

        if not (is_target or is_creator or is_admin):
            await ctx.reply("⛔ Bạn không có quyền dừng phiên cabin này.", mention_author=False)
            return

        await cabin_manager.stop_session(ctx.guild.id, target_user.id)
        await ctx.reply(f"🛑 Đã dừng phiên Dịch Cabin cho {target_user.mention}!", mention_author=False)

    @prefix_cabin.command(name="list", aliases=["status", "danhsach"])
    async def prefix_cabin_list_sub(self, ctx: commands.Context):
        """Lệnh con: .m cabin list"""
        if not ctx.guild:
            return
        active_sessions = cabin_manager.list_guild_sessions(ctx.guild.id)
        if not active_sessions:
            await ctx.reply("🎙️ Hiện không có ai trong máy chủ đang bị dịch cabin.", mention_author=False)
            return

        lines = []
        for s in active_sessions:
            rem = format_duration(s.remaining_seconds)
            lines.append(f"• <@{s.target_id}>: còn `{rem}` (đã dịch `{s.translated_count}` câu)")
        await ctx.reply("🎙️ **DANH SÁCH ĐANG BỊ DỊCH CABIN TRONG SERVER:**\n" + "\n".join(lines) + "\n\n👉 Dùng `.m cabinstop @người_dùng` để dừng.", mention_author=False)

    @commands.command(name="cabinstop", aliases=["uncabin"])
    async def prefix_cabinstop_alias(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """Lệnh độc lập: .m cabinstop [@user]"""
        await self.prefix_cabin_stop_sub(ctx, target)

    @commands.command(name="cabinlist")
    async def prefix_cabinlist_alias(self, ctx: commands.Context):
        """Lệnh độc lập: .m cabinlist"""
        await self.prefix_cabin_list_sub(ctx)

    # =========================================================================
    # 🎧 LISTENER: on_message -> Debounce Buffer -> Dịch Cabin Batch
    # =========================================================================

    # Thời gian chờ để gom tin nhắn trước khi gọi AI (giây)
    BATCH_DEBOUNCE_SECONDS = 3.0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Bo qua tin nhan tu bot hoac ngoai guild hoac khong co noi dung
        if message.author.bot or not message.guild or not message.content:
            return

        guild_id = message.guild.id
        author_id = message.author.id
        raw_text = message.content.strip()

        # Kiem tra neu la tin nhan lenh bot (.m, .M, /, !, ?, ;, ~, $)
        is_bot_cmd = raw_text.startswith((".m", ".M", "/", "!", "?", ";", "~", "$"))

        # Ghi nhan vao RAM rolling cache neu khong phai lenh bot (<0.001ms)
        if not is_bot_cmd:
            cabin_manager.record_channel_message(
                guild_id=guild_id,
                channel_id=message.channel.id,
                author_name=message.author.display_name,
                content=message.clean_content
            )

        # 2. Kiem tra xem tac gia co dang trong phien cabin cua guild nay khong
        session = cabin_manager.get_session(guild_id, author_id)
        if not session:
            return

        # 3. Loc bo cac tin nhan khong phu hop de dich
        if is_bot_cmd or len(raw_text) < 2:
            return

        # Bo qua neu chi chua link URL thuan tuy
        if raw_text.startswith(("http://", "https://")) and " " not in raw_text:
            return

        # 4. Kiem tra Cooldown nhanh (check-only, khong update - update that su khi AI xong)
        if not cabin_manager.check_cooldown(guild_id, author_id, update=False):
            return

        # 5. Buffer tin nhan vao debounce window
        buf_key = (guild_id, author_id)
        self._msg_buffers[buf_key].append((message.clean_content.strip(), message))

        # Huy debounce task cu neu dang cho
        existing_task = self._debounce_tasks.get(buf_key)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        # Tao debounce task moi - sau BATCH_DEBOUNCE_SECONDS se thuc hien dich tong hop
        task = asyncio.create_task(
            self._process_cabin_batch(buf_key, guild_id, author_id, message)
        )
        self._debounce_tasks[buf_key] = task

    async def _process_cabin_batch(
        self,
        buf_key: tuple,
        guild_id: int,
        author_id: int,
        trigger_message: discord.Message,
    ):
        """
        Cho BATCH_DEBOUNCE_SECONDS roi xu ly toan bo tin nhan da gom trong buffer.
        Neu nhieu tin nhan duoc gom lai, goi AI 1 lan duy nhat voi batch prompt de giam RPM.
        """
        try:
            await asyncio.sleep(self.BATCH_DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            # Task bi huy do co tin nhan moi den - task moi se xu ly
            return

        # Lay va xoa buffer
        batch_entries = self._msg_buffers.pop(buf_key, [])
        self._debounce_tasks.pop(buf_key, None)

        if not batch_entries:
            return

        # Kiem tra lai cooldown (lock that su ngay truoc khi goi AI)
        if not cabin_manager.check_cooldown(guild_id, author_id, update=True):
            return

        # Kiem tra lai session van con hieu luc
        session = cabin_manager.get_session(guild_id, author_id)
        if not session:
            cabin_manager.reset_cooldown(guild_id, author_id)
            return

        start_time = time.time()
        target_name = trigger_message.author.display_name

        # Gom danh sach text va lay tin nhan gan nhat de reply vao
        texts = [text for text, _ in batch_entries]
        reply_target = batch_entries[-1][1]  # Reply vao tin nhan cuoi cung trong batch
        count = len(texts)
        log_label = f"batch {count} tin" if count > 1 else "1 tin"

        # Lay boi canh kenh
        context_tuples = await cabin_manager.get_channel_context(
            channel=trigger_message.channel,
            window_minutes=CONTEXT_HISTORY_MINUTES,
            max_messages=CONTEXT_MAX_MESSAGES
        )
        # Loc bo cac tin nhan trong batch khoi context (tranh lap lai)
        batch_texts_set = set(texts)
        context_tuples = [c for c in context_tuples if c[1].strip() not in batch_texts_set]

        try:
            async with trigger_message.channel.typing():
                interpretation = await generate_cabin_interpretation_batch(
                    target_name=target_name,
                    messages=texts,
                    context_messages=context_tuples,
                )

                if interpretation:
                    reply_content = f"🎙️ **Dịch cabin:** {interpretation}"
                    await reply_target.reply(reply_content, mention_author=False)

                    cabin_manager.update_cooldown(guild_id, author_id)
                    await cabin_manager.increment_translated_count(guild_id, author_id)

                    duration_ms = round((time.time() - start_time) * 1000, 2)
                    activity_logger.log(
                        action_type="cabin",
                        action_name="Dịch Cabin AI",
                        user_id=author_id,
                        user_name=target_name,
                        user_avatar=str(trigger_message.author.display_avatar.url) if trigger_message.author.display_avatar else None,
                        guild_name=trigger_message.guild.name,
                        guild_id=guild_id,
                        channel_name=trigger_message.channel.name if hasattr(trigger_message.channel, "name") else "unknown",
                        channel_id=trigger_message.channel.id,
                        prompt=" | ".join(texts)[:150],
                        response=interpretation[:200],
                        status="success",
                        duration_ms=duration_ms,
                    )
                    print(f"🎙️ [Cabin] Dịch {log_label} của [{target_name}] xong trong {duration_ms:.0f}ms.", flush=True)
                else:
                    # AI khong sinh duoc ket qua, reset cooldown de tin tiep theo khong bi chan
                    cabin_manager.reset_cooldown(guild_id, author_id)
        except discord.Forbidden:
            cabin_manager.reset_cooldown(guild_id, author_id)
            print(f"[Cabin] Bot thieu quyen gui tin nhan tai channel {trigger_message.channel.id}", flush=True)
        except Exception as err:
            cabin_manager.reset_cooldown(guild_id, author_id)
            print(f"[Cabin] Loi trong qua trinh dich {log_label}: {err}", flush=True)
            import traceback as _tb
            _tb.print_exc()



async def setup(bot: commands.Bot):
    await bot.add_cog(CabinCog(bot))
