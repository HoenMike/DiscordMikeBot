import asyncio
from datetime import datetime, timezone, timedelta
import random
import traceback
from typing import Optional, Union
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from features.tarot.deck import (
    SPREAD_DEFINITIONS,
    draw_spread,
    get_yes_no_verdict,
    READER_STYLES
)
from features.tarot.renderer import render_spread_to_bytes
from features.tarot.ai import generate_tarot_reading, recommend_spread_for_question
from features.tarot.manager import TarotManager
from features.tarot.tarot_view import (
    TarotFlipView,
    TarotLauncherView,
    WIDE_DIVIDER
)
from core.ai import split_text

VN_TZ = timezone(timedelta(hours=7))


SPREAD_ALIASES = {
    "daily": "daily",
    "ngay": "daily",
    "ngaymoi": "daily",
    "d": "daily",
    "day": "daily",

    "yes_no": "yes_no",
    "yesno": "yes_no",
    "yn": "yes_no",
    "yes": "yes_no",
    "no": "yes_no",
    "conenkhong": "yes_no",

    "single": "single",
    "motla": "single",
    "1la": "single",
    "s": "single",
    "one": "single",

    "ppf": "ppf",
    "past_present_future": "ppf",
    "pastpresentfuture": "ppf",
    "quakhutuonglai": "ppf",
    "3la": "ppf",

    "choices": "choices",
    "choice": "choices",
    "two_choices": "choices",
    "twochoices": "choices",
    "2ngaduong": "choices",
    "2luachon": "choices",

    "mbs": "mbs",
    "mind_body_spirit": "mbs",
    "mindbodyspirit": "mbs",
    "tamtri": "mbs",

    "horseshoe": "horseshoe",
    "mongngua": "horseshoe",
    "5la": "horseshoe",
    "horse": "horseshoe",

    "two_paths": "two_paths",
    "twopaths": "two_paths",
    "twopath": "two_paths",
    "2huong": "two_paths",
    "2conduong": "two_paths",

    "celtic": "celtic",
    "celtic_cross": "celtic",
    "celticcross": "celtic",
    "chuthap": "celtic",
    "10la": "celtic",
}


class TarotCog(commands.Cog):
    """Cog xử lý toàn bộ các Slash Command và Prefix Command liên quan đến Tarot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tarot_manager = TarotManager()

    async def cog_load(self):
        """Khởi tạo SQLite database cho Tarot khi nạp cog."""
        await self.tarot_manager.init_db()
        self.weekly_card_loop.start()

    async def cog_unload(self):
        """Đóng kết nối database khi hủy nạp cog."""
        self.weekly_card_loop.cancel()
        await self.tarot_manager.close()

    async def _show_history(
        self,
        target_user: Union[discord.User, discord.Member],
        sender: callable,
        is_ephemeral: bool = True
    ):
        """Hiển thị lịch sử bốc bài gần nhất của user."""
        history = await self.tarot_manager.get_user_history(target_user.id, limit=5)
        if not history:
            await sender(
                "📜 Bạn chưa có lượt bốc bài Tarot nào được lưu lại. Hãy dùng `/tarot` hoặc `.m tarot` để bốc quẻ đầu tiên nhé!",
                ephemeral=is_ephemeral
            )
            return

        embed = discord.Embed(
            title=f"📜 LỊCH SỬ BỐC BÀI TAROT - {target_user.display_name.upper()}",
            description="Dưới đây là tối đa 5 lượt bốc bài gần nhất của bạn:",
            color=0xDAA520
        )

        for item in history:
            spread_key = item["spread_type"]
            spread_name = SPREAD_DEFINITIONS.get(spread_key, {}).get("name", spread_key)
            question_str = f"**Câu hỏi:** *{item['question']}*\n" if item["question"] else ""

            cards = item["cards"]
            cards_summary = ", ".join([
                f"{c['name_vi']} ({'[NGƯỢC]' if c['is_reversed'] else '[XUÔI]'})"
                for c in cards
            ])

            embed.add_field(
                name=f"🔮 {spread_name} • ({item['created_at']})",
                value=f"{question_str}🃏 **Các lá bài:** {cards_summary}",
                inline=False
            )

        embed.set_footer(
            text=f"Yêu cầu bởi {target_user.display_name}",
            icon_url=target_user.display_avatar.url if target_user.display_avatar else None
        )
        await sender(embed=embed, ephemeral=is_ephemeral)

    async def _execute_tarot_flow(
        self,
        user: Union[discord.User, discord.Member],
        spread_key: str,
        question: Optional[str] = None,
        context: Optional[str] = None,
        reader_key: str = "random",
        interaction: Optional[discord.Interaction] = None,
        ctx: Optional[commands.Context] = None
    ):
        """Hàm dùng chung xử lý quy trình bốc bài cho cả Slash Command và Prefix Command."""
        spread_info = SPREAD_DEFINITIONS.get(spread_key)
        if not spread_info:
            err = "❌ Kiểu trải bài không hợp lệ! Hãy dùng `.m tarot` hoặc `/tarot` để xem danh sách."
            if interaction:
                await interaction.response.send_message(err, ephemeral=True)
            elif ctx:
                await ctx.reply(err, mention_author=False)
            return

        clean_question = question.strip() if question else ""
        clean_context = context.strip() if context else ""

        # Nếu không chọn Reader hoặc chọn Ngẫu Nhiên, random 1 trong 3 tính cách
        if not reader_key or reader_key == "random" or reader_key not in READER_STYLES:
            reader_key = random.choice(["neutral", "healer", "chaos"])

        # 1. Kiểm tra điều kiện bắt buộc nhập câu hỏi
        if spread_info.get("requires_question", True) and not clean_question:
            err = (
                f"❌ Với kiểu trải bài **{spread_info['name']}**, bạn **bắt buộc** phải nhập câu hỏi hoặc chủ đề cần xem!\n"
                f"💡 *Ví dụ cú pháp: `.m tarot {spread_key} Công việc tháng tới của tôi sẽ tiến triển thế nào?`*\n"
                f"💡 *Hoặc gõ `.m tarot` để mở giao diện nhập câu hỏi trực quan.*"
            )
            if interaction:
                await interaction.response.send_message(err, ephemeral=True)
            elif ctx:
                await ctx.reply(err, mention_author=False)
            return

        # 2. Kiểm tra Daily Cooldown
        if spread_key == "daily":
            can_draw, last_draw = await self.tarot_manager.check_daily_cooldown(user.id)
            if not can_draw and last_draw:
                last_card_str = f"**{last_draw.get('name_vi', 'Bài')}** ({last_draw.get('name_en', '')})"
                orient_str = "[NGƯỢC]" if last_draw.get("is_reversed") else "[XUÔI]"
                drawn_time = last_draw.get("drawn_at", "hôm nay")
                cooldown_msg = (
                    f"☀️ **Bạn đã rút Daily Card của ngày hôm nay rồi!**\n\n"
                    f"🃏 Lá bài hôm nay của bạn: {last_card_str} - `{orient_str}` *(Rút lúc {drawn_time})*\n"
                    f"⏰ *Mỗi người chỉ nên nhận 1 thông điệp năng lượng mỗi ngày. Lượt bốc bài sẽ được làm mới vào lúc 00:00 (Giờ VN)!*\n\n"
                    f"💡 *Nếu bạn có câu hỏi cụ thể khác, hãy dùng `.m tarot single` hoặc `.m tarot yes_no` nhé!*"
                )
                if interaction:
                    await interaction.response.send_message(cooldown_msg, ephemeral=True)
                elif ctx:
                    await ctx.reply(cooldown_msg, mention_author=False)
                return

        # 3. Kiểm tra Cooldown 30s chống spam giữa 2 lần bốc bài liên tiếp của 1 người
        can_proceed, wait_sec = self.tarot_manager.check_user_cooldown(
            user.id,
            cooldown_seconds=config.COMMAND_COOLDOWN_SECONDS
        )
        if not can_proceed:
            cd_msg = f"⏳ **Bạn đang thao tác quá nhanh!** Vui lòng tĩnh tâm và chờ thêm `{int(wait_sec) + 1}s` nữa trước khi bốc quẻ tiếp theo nhé."
            if interaction:
                await interaction.response.send_message(cd_msg, ephemeral=True)
            elif ctx:
                await ctx.reply(cd_msg, mention_author=False)
            return

        # 4. Phản hồi ban đầu
        initial_msg = None
        if interaction:
            await interaction.response.defer(thinking=True)
        elif ctx:
            initial_msg = await ctx.reply("🔮 Đang kết nối năng lượng và trải bài Tarot...", mention_author=False)

        try:
            # Lấy ngữ cảnh cũ (Trí nhớ bạn cũ) và danh sách lá bốc gần đây (Card Fatigue)
            recent_ctx = await self.tarot_manager.get_user_recent_context(user.id)
            fatigue_card_ids = await self.tarot_manager.get_user_recent_card_ids(user.id)

            # 1. Rút bài theo seed năng lượng vũ trụ theo khung giờ (kèm Card Fatigue)
            drawn_cards = draw_spread(
                spread_key=spread_key,
                user_id=user.id,
                question=clean_question if clean_question else None,
                fatigue_card_ids=fatigue_card_ids
            )

            # 2. Zero-Latency Pre-fetch (kèm Trí nhớ bạn cũ & Nhận thức đối tượng @mention)
            bot_user = self.bot.user or (interaction.client.user if interaction and interaction.client else None)
            guild_obj = interaction.guild if interaction else (ctx.guild if ctx else None)
            ai_task = asyncio.create_task(
                generate_tarot_reading(
                    spread_key=spread_key,
                    drawn_cards=drawn_cards,
                    question=clean_question if clean_question else None,
                    context=clean_context if clean_context else None,
                    reader_style=reader_key,
                    user_name=user.display_name,
                    recent_context=recent_ctx,
                    user_id=user.id,
                    guild=guild_obj,
                    bot_id=bot_user.id if bot_user else None,
                    bot_name=bot_user.display_name if bot_user else "MikeDaBot"
                )
            )

            # 3. Khởi tạo View lật bài
            user_avatar = user.display_avatar.url if user.display_avatar else None
            guild_id = (interaction.guild.id if interaction and interaction.guild else (ctx.guild.id if ctx and ctx.guild else None))
            channel_id = (interaction.channel.id if interaction and interaction.channel else (ctx.channel.id if ctx and ctx.channel else None))

            view = TarotFlipView(
                author_id=user.id,
                author_name=user.display_name,
                author_avatar_url=user_avatar,
                spread_key=spread_key,
                spread_info=spread_info,
                drawn_cards=drawn_cards,
                question=clean_question if clean_question else None,
                context=clean_context if clean_context else None,
                reader_style=reader_key,
                ai_task=ai_task,
                tarot_manager=self.tarot_manager,
                guild_id=guild_id,
                channel_id=channel_id
            )

            # 4. Render Canvas ban đầu
            image_buffer = await asyncio.to_thread(
                render_spread_to_bytes,
                spread_key,
                drawn_cards,
                set()
            )
            file = discord.File(fp=image_buffer, filename="tarot_spread.png")

            # 5. Xây dựng Embed
            desc_lines = []
            if clean_question:
                desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{clean_question}*\n")
            if clean_context:
                desc_lines.append(f"**📝 Bối cảnh:**\n*{clean_context}*\n")
            desc_lines.append(f"**🎭 Người trải bài:** {view.style_info['name']}\n")

            desc_lines.append(WIDE_DIVIDER)

            cards_summary_lines = []
            for drawn in drawn_cards:
                cards_summary_lines.append(f"• **{drawn.position_title}**: ⏳ *(Chờ lật)*")

            desc_lines.append("**🃏 Các Lá Bài:**\n" + "\n".join(cards_summary_lines) + "\n")
            desc_lines.append("⏳ *Hãy bấm vào các nút bên dưới để lật mở từng lá bài...*")

            embed = discord.Embed(
                title=f"🔮 TRẢI BÀI TAROT: {spread_info['name'].upper()}",
                description="\n".join(desc_lines),
                color=view.embed_color
            )
            embed.set_image(url="attachment://tarot_spread.png")
            embed.set_footer(
                text=f"Quẻ bài của {user.display_name} (Đang bốc bài...)",
                icon_url=user_avatar
            )

            if interaction:
                sent_msg = await interaction.followup.send(embed=embed, file=file, view=view)
                view.message = sent_msg
            elif ctx and initial_msg:
                await initial_msg.edit(content=None, embed=embed, attachments=[file], view=view)
                view.message = initial_msg

            # Chỉ ghi nhận cooldown sau khi gửi bài thành công
            self.tarot_manager.record_user_action(user.id)

        except Exception as e:
            print(f"❌ [TarotCog] Lỗi trong quá trình bốc bài: {e}", flush=True)
            traceback.print_exc()
            if isinstance(e, discord.Forbidden):
                err_text = (
                    "⚠️ **Bot thiếu quyền gửi tin nhắn hoặc đính kèm ảnh (Send Messages / Attach Files) trong kênh này!**\n"
                    "Vui lòng kiểm tra và cấp quyền cho Bot trong cài đặt kênh."
                )
            else:
                err_text = "❌ Đã xảy ra lỗi trong quá trình bốc và giải bài Tarot. Vui lòng thử lại sau!"

            if interaction:
                try:
                    await interaction.followup.send(err_text, ephemeral=True)
                except Exception:
                    pass
            elif ctx:
                if initial_msg:
                    try:
                        await initial_msg.edit(content=err_text)
                    except Exception:
                        pass
                else:
                    try:
                        await ctx.reply(err_text, mention_author=False)
                    except Exception:
                        pass

    # =========================================================================
    # 1. SLASH COMMANDS
    # =========================================================================
    @app_commands.command(
        name="tarot",
        description="Bốc và luận giải bài Tarot huyền bí bằng AI với ảnh trải bài trực quan"
    )
    @app_commands.describe(
        spread="Kiểu trải bài Tarot bạn muốn thực hiện",
        question="Câu hỏi hoặc chủ đề bạn muốn hỏi bài (Bắt buộc với hầu hết các trải bài)",
        context="Bối cảnh/hoàn cảnh hiện tại (Ví dụ: đang có crush, sắp chuyển việc...) để bài giải chuẩn xác hơn",
        reader="Người giải bài bạn muốn tham vấn (Orion, Celeste, Jester hoặc để ngẫu nhiên)"
    )
    @app_commands.choices(spread=[
        app_commands.Choice(name="🌟 Daily Card (Năng lượng & thông điệp ngày - 1 lá)", value="daily"),
        app_commands.Choice(name="⚡ Yes / No (Trả lời dứt khoát câu hỏi Có/Không - 1 lá)", value="yes_no"),
        app_commands.Choice(name="🎯 Single Card (Lời khuyên & góc nhìn trọng tâm - 1 lá)", value="single"),
        app_commands.Choice(name="⏳ Past - Present - Future (Tiến trình sự việc - 3 lá)", value="ppf"),
        app_commands.Choice(name="⚖️ Two Choices (So sánh nhanh 2 ngả đường A & B - 3 lá)", value="choices"),
        app_commands.Choice(name="🧘 Mind - Body - Spirit (Định vị bản thân & năng lượng - 3 lá)", value="mbs"),
        app_commands.Choice(name="🧲 Horseshoe (Toàn cảnh vấn đề & chướng ngại vật - 5 lá)", value="horseshoe"),
        app_commands.Choice(name="🌿 Two Paths (Phân tích chi tiết rủi ro/lợi ích 2 hướng - 5 lá)", value="two_paths"),
        app_commands.Choice(name="👑 Celtic Cross (Trải bài chuyên sâu toàn diện 10 góc nhìn - 10 lá)", value="celtic"),
    ])
    @app_commands.choices(reader=[
        app_commands.Choice(name="🎲 Ngẫu Nhiên", value="random"),
        app_commands.Choice(name="⚖️ Orion", value="neutral"),
        app_commands.Choice(name="🌸 Celeste", value="healer"),
        app_commands.Choice(name="🃏 Jester", value="chaos"),
    ])
    @app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
    async def tarot_slash(
        self,
        interaction: discord.Interaction,
        spread: app_commands.Choice[str] | None = None,
        question: str | None = None,
        context: str | None = None,
        reader: app_commands.Choice[str] | None = None
    ):
        reader_key = reader.value if reader else "random"
        if not spread:
            # Mở launcher riêng tư (Ephemeral) trực tiếp 100%
            user_avatar = interaction.user.display_avatar.url if interaction.user.display_avatar else None
            launcher = TarotLauncherView(
                author_id=interaction.user.id,
                author_name=interaction.user.display_name,
                author_avatar_url=user_avatar,
                tarot_manager=self.tarot_manager,
                selected_spread="daily",
                selected_reader=reader_key,
                question=question,
                context=context
            )
            embed = launcher.build_launcher_embed()
            await interaction.response.send_message(embed=embed, view=launcher, ephemeral=True)
            return

        spread_key = spread.value
        await self._execute_tarot_flow(
            user=interaction.user,
            spread_key=spread_key,
            question=question,
            context=context,
            reader_key=reader_key,
            interaction=interaction
        )

    @app_commands.command(
        name="tarot_history",
        description="Xem lại các lượt bốc bài Tarot gần nhất của bạn"
    )
    @app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
    async def tarot_history_slash(self, interaction: discord.Interaction):
        async def send_response(*args, **kwargs):
            await interaction.response.send_message(*args, **kwargs)
        await self._show_history(interaction.user, send_response, is_ephemeral=True)

    @app_commands.command(
        name="tarot_recommend",
        description="Gợi ý kiểu trải bài phù hợp nhất dựa trên câu hỏi của bạn"
    )
    @app_commands.describe(question="Nhập câu hỏi hoặc vấn đề bạn đang băn khoăn")
    async def tarot_recommend_slash(self, interaction: discord.Interaction, question: str):
        spread_key, spread_name, reason = recommend_spread_for_question(question)
        embed = discord.Embed(
            title="🧭 GỢI Ý KIỂU TRẢI BÀI TAROT",
            description=f"**❓ Câu hỏi của bạn:**\n*{question}*\n\n"
                        f"✨ **Kiểu trải bài đề xuất:** **{spread_name}** (`{spread_key}`)\n\n"
                        f"💡 **Lý do gợi ý:**\n{reason}\n\n"
                        f"👉 *Bạn có thể gõ `/tarot` hoặc `.m tarot {spread_key} {question}` để bắt đầu ngay!*",
            color=0x8B5CF6
        )
        embed.set_footer(text="Gợi ý chiêm tinh thông minh MikeDaBot", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tarot_memory",
        description="Bật hoặc tắt tính năng AI nhớ ngữ cảnh các lần đọc trước (Trí nhớ bạn cũ)"
    )
    @app_commands.describe(status="Chọn bật hoặc tắt trí nhớ ngữ cảnh")
    @app_commands.choices(status=[
        app_commands.Choice(name="🟢 Bật trí nhớ (Nhớ mang máng chủ đề cũ)", value="on"),
        app_commands.Choice(name="🔴 Tắt trí nhớ (Xem như người mới hoàn toàn)", value="off"),
    ])
    async def tarot_memory_slash(self, interaction: discord.Interaction, status: app_commands.Choice[str]):
        is_on = (status.value == "on")
        await self.tarot_manager.set_user_memory_preference(interaction.user.id, is_on)
        if is_on:
            msg = "🟢 **Đã BẬT trí nhớ bạn cũ:** Bot sẽ nhớ mang máng chủ đề và lá bài gần nhất để tạo cảm giác liên tục thân thiện."
        else:
            msg = "🔴 **Đã TẮT trí nhớ bạn cũ:** Bot sẽ không liên kết bất kỳ thông tin nào từ các quẻ bài trước đó của bạn."
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(
        name="tarot_forget",
        description="Xóa sạch toàn bộ lịch sử bốc bài và dữ liệu ngữ cảnh của bạn khỏi hệ thống"
    )
    async def tarot_forget_slash(self, interaction: discord.Interaction):
        await self.tarot_manager.clear_user_history(interaction.user.id)
        await interaction.response.send_message(
            "🧹 **Đã xóa sạch lịch sử:** Toàn bộ dữ liệu bốc bài và ngữ cảnh của bạn đã được xóa khỏi hệ thống!",
            ephemeral=True
        )

    @app_commands.command(
        name="tarot_weekly_setup",
        description="Cài đặt kênh nhận Lá Bài Tuần của Server vào sáng Thứ Hai (Quản trị viên)"
    )
    @app_commands.describe(channel="Kênh text muốn nhận thông điệp tuần")
    @app_commands.default_permissions(manage_guild=True)
    async def tarot_weekly_setup_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            await interaction.response.send_message("❌ Lệnh này chỉ dùng trong Server!", ephemeral=True)
            return
        await self.tarot_manager.set_weekly_guild_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✨ **Cài đặt thành công:** Kênh {channel.mention} sẽ nhận **Lá Bài Năng Lượng Tuần Mới** vào mỗi sáng Thứ Hai (08:00 GMT+7)!",
            ephemeral=True
        )

    @app_commands.command(
        name="tarot_help",
        description="Xem hướng dẫn chi tiết về 9 kiểu trải bài, 3 Reader và cách bốc bài Tarot"
    )
    async def tarot_help_slash(self, interaction: discord.Interaction):
        from bot_instance import send_bot_help
        await send_bot_help(interaction, feature="tarot", ephemeral=True)

    # =========================================================================
    # 2. PREFIX COMMANDS (.m tarot ...)
    # =========================================================================
    @commands.command(
        name="tarot",
        aliases=["tr", "bocbai", "tarotcard"],
        help="Bốc bài Tarot với menu tương tác trực quan hoặc bốc nhanh qua cú pháp"
    )
    @commands.cooldown(1, 30.0, commands.BucketType.user)
    async def tarot_prefix(
        self,
        ctx: commands.Context,
        spread_arg: Optional[str] = None,
        *,
        rest: Optional[str] = None
    ):
        # 1. Trường hợp không truyền tham số hoặc yêu cầu mở menu tương tác (UI)
        if spread_arg is None or spread_arg.lower() in ["ui", "menu", "panel", "chon", "open", "launcher"]:
            user_avatar = ctx.author.display_avatar.url if ctx.author.display_avatar else None
            launcher = TarotLauncherView(
                author_id=ctx.author.id,
                author_name=ctx.author.display_name,
                author_avatar_url=user_avatar,
                tarot_manager=self.tarot_manager,
                selected_spread="daily",
                selected_reader="random",
                question=None
            )
            embed = launcher.build_launcher_embed()
            sent_msg = await ctx.reply(
                embed=embed,
                view=launcher,
                mention_author=False
            )
            launcher.message = sent_msg
            return

        # 2. Xem lịch sử
        if spread_arg.lower() in ["history", "his", "lichsu", "ls"]:
            async def send_reply(*args, **kwargs):
                kwargs.pop("ephemeral", None)
                await ctx.reply(*args, mention_author=False, **kwargs)
            await self._show_history(ctx.author, send_reply, is_ephemeral=False)
            return

        # 3. Gợi ý trải bài
        if spread_arg.lower() in ["recommend", "rec", "goiy", "tuvan"]:
            if not rest:
                await ctx.reply("❓ Vui lòng nhập câu hỏi để bot gợi ý trải bài! Ví dụ: `.m tarot recommend Tôi có nên chuyển việc không?`", mention_author=False)
                return
            s_key, s_name, reason = recommend_spread_for_question(rest)
            embed = discord.Embed(
                title="🧭 GỢI Ý KIỂU TRẢI BÀI TAROT",
                description=f"**❓ Câu hỏi:** *{rest}*\n\n✨ **Đề xuất:** **{s_name}** (`{s_key}`)\n💡 **Lý do:** {reason}",
                color=0x8B5CF6
            )
            await ctx.reply(embed=embed, mention_author=False)
            return

        # 4. Bật/Tắt Memory
        if spread_arg.lower() in ["memory", "bonho"]:
            is_on = rest and rest.lower() in ["on", "bat", "true", "1"]
            await self.tarot_manager.set_user_memory_preference(ctx.author.id, is_on)
            state_text = "🟢 Đã BẬT" if is_on else "🔴 Đã TẮT"
            await ctx.reply(f"{state_text} tính năng trí nhớ bạn cũ.", mention_author=False)
            return

        # 5. Xóa lịch sử
        if spread_arg.lower() in ["forget", "xoa", "clear"]:
            await self.tarot_manager.clear_user_history(ctx.author.id)
            await ctx.reply("🧹 Đã xóa sạch toàn bộ lịch sử bốc bài của bạn khỏi hệ thống!", mention_author=False)
            return

        # 6. Cài đặt kênh nhận bài tuần cho server
        if spread_arg.lower() in ["weekly_setup", "weekly", "setup_weekly", "baituan"]:
            if not ctx.guild:
                await ctx.reply("❌ Lệnh này chỉ dùng được trong Server!", mention_author=False)
                return
            if not ctx.author.guild_permissions.manage_guild:
                await ctx.reply("❌ Bạn cần có quyền `Manage Server` để cài đặt tính năng này!", mention_author=False)
                return
            target_channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
            await self.tarot_manager.set_weekly_guild_channel(ctx.guild.id, target_channel.id)
            await ctx.reply(f"✨ Đã cài đặt kênh {target_channel.mention} nhận **Lá Bài Tuần Mới** vào 08:00 sáng Thứ Hai hàng tuần!", mention_author=False)
            return

        # 7. Xem hướng dẫn
        if spread_arg.lower() in ["help", "huongdan", "h"]:
            from bot_instance import send_bot_help
            await send_bot_help(ctx, feature="tarot")
            return

        # 7. Kiểm tra xem spread_arg có khớp với kiểu trải bài nào không
        spread_lower = spread_arg.lower()
        if spread_lower in SPREAD_ALIASES:
            spread_key = SPREAD_ALIASES[spread_lower]
            question = rest.strip() if rest else None
            await self._execute_tarot_flow(
                user=ctx.author,
                spread_key=spread_key,
                question=question,
                context=None,
                reader_key="random",
                ctx=ctx
            )
            return

        # 8. Nếu spread_arg không khớp kiểu trải bài nào -> Người dùng có thể đã nhập thẳng câu hỏi
        full_query = f"{spread_arg} {rest or ''}".strip()
        user_avatar = ctx.author.display_avatar.url if ctx.author.display_avatar else None
        launcher = TarotLauncherView(
            author_id=ctx.author.id,
            author_name=ctx.author.display_name,
            author_avatar_url=user_avatar,
            tarot_manager=self.tarot_manager,
            selected_spread="single",
            selected_reader="random",
            question=full_query
        )
        embed = launcher.build_launcher_embed()
        sent_msg = await ctx.reply(
            embed=embed,
            view=launcher,
            mention_author=False
        )
        launcher.message = sent_msg

    @commands.command(
        name="tarot_history",
        aliases=["thistory", "t_history", "lichsutarot"]
    )
    @commands.cooldown(1, 30.0, commands.BucketType.user)
    async def tarot_history_prefix(self, ctx: commands.Context):
        async def send_reply(*args, **kwargs):
            kwargs.pop("ephemeral", None)
            await ctx.reply(*args, mention_author=False, **kwargs)
        await self._show_history(ctx.author, send_reply, is_ephemeral=False)

    # =========================================================================
    # 3. BACKGROUND TASKS (Lá bài tuần của Server)
    # =========================================================================
    @tasks.loop(minutes=30)
    async def weekly_card_loop(self):
        """Kiểm tra và gửi lá bài tuần cho các server vào 08:00 sáng Thứ Hai (GMT+7)."""
        now_vn = datetime.now(VN_TZ)
        if now_vn.weekday() != 0 or now_vn.hour < 8:
            return

        current_week_str = now_vn.strftime("%Y-W%W")
        configs = await self.tarot_manager.get_weekly_guild_configs()
        for cfg in configs:
            guild_id = cfg["guild_id"]
            channel_id = cfg["channel_id"]
            last_sent = cfg.get("last_sent_week", "")

            if last_sent == current_week_str:
                continue

            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            try:
                drawn_cards = draw_spread("daily", user_id=guild_id, question="Năng lượng tuần mới của máy chủ")
                ai_res = await generate_tarot_reading(
                    spread_key="daily",
                    drawn_cards=drawn_cards,
                    question="Năng lượng và thông điệp tuần mới cho toàn thể cộng đồng máy chủ",
                    reader_style="neutral",
                    user_name="Cộng Đồng Server"
                )
                ai_reading = ai_res[0] if isinstance(ai_res, tuple) else ai_res

                img_bytes = await asyncio.to_thread(render_spread_to_bytes, "daily", drawn_cards, {0})
                file = discord.File(fp=img_bytes, filename="weekly_tarot.png")

                embed = discord.Embed(
                    title=f"🌟 LÁ BÀI TUẦN MỚI CHO MÁY CHỦ ({now_vn.strftime('%d/%m/%Y')})",
                    description=f"**🎴 Lá Bài Đại Diện:** **{drawn_cards[0].card.name_vi}** (*{drawn_cards[0].card.name_en}*)\n\n{ai_reading}",
                    color=0xDAA520
                )
                embed.set_image(url="attachment://weekly_tarot.png")
                embed.set_footer(text="Năng lượng chiêm tinh tuần mới • Chúc cả server một tuần ngập tràn may mắn!")

                await channel.send(embed=embed, file=file)
                await self.tarot_manager.update_weekly_guild_sent(guild_id, current_week_str)
                print(f"✅ [Weekly Tarot] Đã gửi bài tuần cho server ID: {guild_id}", flush=True)
            except Exception as e:
                print(f"⚠️ [Weekly Tarot] Lỗi gửi bài tuần cho server {guild_id}: {e}", flush=True)

    @weekly_card_loop.before_loop
    async def before_weekly_card_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TarotCog(bot))

