import asyncio
import traceback
import discord
from discord import app_commands
from discord.ext import commands

from features.tarot.deck import (
    SPREAD_DEFINITIONS,
    draw_spread,
    get_yes_no_verdict
)
from features.tarot.renderer import render_spread_to_bytes
from features.tarot.ai import generate_tarot_reading
from features.tarot.manager import TarotManager


class TarotCog(commands.Cog):
    """Cog xử lý toàn bộ các Slash Command liên quan đến Bốc và Luận giải Tarot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tarot_manager = TarotManager()

    async def cog_load(self):
        """Khởi tạo SQLite database cho Tarot khi nạp cog."""
        await self.tarot_manager.init_db()

    async def cog_unload(self):
        """Đóng kết nối database khi hủy nạp cog."""
        await self.tarot_manager.close()

    @app_commands.command(
        name="tarot",
        description="Bốc và luận giải bài Tarot huyền bí bằng AI với ảnh trải bài trực quan"
    )
    @app_commands.describe(
        spread="Chọn kiểu trải bài phù hợp với nhu cầu",
        question="Câu hỏi hoặc chủ đề muốn xem (Bắt buộc cho mọi kiểu trải bài trừ Daily Card)"
    )
    @app_commands.choices(spread=[
        app_commands.Choice(name="🌟 Daily Card (Năng lượng ngày - 1 lần/ngày)", value="daily"),
        app_commands.Choice(name="⚡ Yes / No (Hỏi nhanh dứt khoát - 1 lá)", value="yes_no"),
        app_commands.Choice(name="🎯 Single Card (Góc nhìn sâu / Lời khuyên - 1 lá)", value="single"),
        app_commands.Choice(name="⚖️ Two Choices (So sánh nhanh 2 Hướng - 3 lá)", value="choices"),
        app_commands.Choice(name="🌿 Two Paths (So sánh chuyên sâu 2 Hướng - 5 lá)", value="two_paths"),
        app_commands.Choice(name="🧲 Horseshoe (Trải bài Móng ngựa - 5 lá)", value="horseshoe"),
        app_commands.Choice(name="⏳ Past - Present - Future (Tiến trình thời gian - 3 lá)", value="ppf"),
        app_commands.Choice(name="🧘 Mind - Body - Spirit (Định vị bản thân - 3 lá)", value="mbs"),
        app_commands.Choice(name="👑 Celtic Cross (Trải bài chữ thập chuyên sâu - 10 lá)", value="celtic"),
    ])
    async def tarot(
        self,
        interaction: discord.Interaction,
        spread: app_commands.Choice[str],
        question: str | None = None
    ):
        spread_key = spread.value
        spread_info = SPREAD_DEFINITIONS.get(spread_key)
        if not spread_info:
            await interaction.response.send_message(
                "❌ Kiểu trải bài không hợp lệ!",
                ephemeral=True
            )
            return

        # 1. Kiểm tra điều kiện bắt buộc nhập câu hỏi
        clean_question = question.strip() if question else ""
        if spread_info.get("requires_question", True) and not clean_question:
            await interaction.response.send_message(
                f"❌ Với kiểu trải bài **{spread_info['name']}**, bạn **bắt buộc** phải nhập câu hỏi hoặc chủ đề cần xem vào ô `question`!\n"
                f"💡 *Ví dụ: `/tarot spread:{spread.name} question:Công việc tháng tới của tôi sẽ tiến triển thế nào?`*",
                ephemeral=True
            )
            return

        # 2. Kiểm tra Daily Cooldown (Chỉ áp dụng cho 'daily')
        if spread_key == "daily":
            can_draw, last_draw = await self.tarot_manager.check_daily_cooldown(interaction.user.id)
            if not can_draw and last_draw:
                last_card_str = f"**{last_draw.get('name_vi', 'Bài')}** ({last_draw.get('name_en', '')})"
                orient_str = "[NGƯỢC]" if last_draw.get("is_reversed") else "[XUÔI]"
                drawn_time = last_draw.get("drawn_at", "hôm nay")
                await interaction.response.send_message(
                    f"☀️ **Bạn đã rút Daily Card của ngày hôm nay rồi!**\n\n"
                    f"🃏 Lá bài hôm nay của bạn: {last_card_str} - `{orient_str}` *(Rút lúc {drawn_time})*\n"
                    f"⏰ *Mỗi người chỉ nên nhận 1 thông điệp năng lượng mỗi ngày. Lượt bốc bài sẽ được làm mới vào lúc 00:00 (Giờ VN)!*\n\n"
                    f"💡 *Nếu bạn có câu hỏi cụ thể khác, hãy dùng `/tarot spread:Single Card` hoặc `/tarot spread:Yes / No` nhé!*",
                    ephemeral=True
                )
                return

        # 3. Defer response để bot có thời gian ghép ảnh và gọi AI
        await interaction.response.defer(thinking=True)

        try:
            # Rút bài ngẫu nhiên
            drawn_cards = draw_spread(spread_key)

            # Ghép ảnh trải bài bằng Pillow trên thread riêng
            image_buffer = await asyncio.to_thread(render_spread_to_bytes, spread_key, drawn_cards)

            # Gọi Gemini AI tạo bài luận giải
            ai_reading = await generate_tarot_reading(
                spread_key=spread_key,
                drawn_cards=drawn_cards,
                question=clean_question if clean_question else None,
                user_name=interaction.user.display_name
            )

            # Lưu vào database
            if spread_key == "daily":
                await self.tarot_manager.record_daily_draw(interaction.user.id, drawn_cards[0])

            await self.tarot_manager.save_tarot_history(
                user_id=interaction.user.id,
                guild_id=interaction.guild.id if interaction.guild else None,
                channel_id=interaction.channel.id if interaction.channel else None,
                spread_type=spread_key,
                question=clean_question if clean_question else None,
                drawn_cards=drawn_cards,
                ai_reading=ai_reading
            )

            # Xây dựng Discord Embed
            embed_color = 0x7851A9  # Tím hoàng gia mặc định
            if spread_key == "yes_no":
                _, _, verdict_color = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
                embed_color = verdict_color

            embed = discord.Embed(
                title=f"🔮 TRẢI BÀI TAROT: {spread_info['name'].upper()}",
                color=embed_color
            )

            if clean_question:
                embed.add_field(name="❓ Câu hỏi / Chủ đề", value=f"*{clean_question}*", inline=False)

            if spread_key == "yes_no":
                badge, verdict_desc, _ = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
                embed.add_field(
                    name="⚡ Phán Quyết Yes / No",
                    value=f"### {badge}\n> *{verdict_desc}*",
                    inline=False
                )

            # Liệt kê tóm tắt các lá bài
            cards_summary_lines = []
            for drawn in drawn_cards:
                orient = "🔴 [NGƯỢC]" if drawn.is_reversed else "🟢 [XUÔI]"
                cards_summary_lines.append(
                    f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}"
                )

            embed.add_field(
                name="🃏 Các Lá Bài Rút Được",
                value="\n".join(cards_summary_lines),
                inline=False
            )

            # Thêm nội dung luận giải từ AI (chia nhỏ nếu quá dài)
            if len(ai_reading) <= 1024:
                embed.add_field(name="📖 Luận Giải Từ Vũ Trụ", value=ai_reading, inline=False)
            else:
                # Cắt gọn theo từng phần
                reading_chunks = [ai_reading[i:i+1020] for i in range(0, len(ai_reading), 1020)]
                for idx, chunk in enumerate(reading_chunks):
                    field_title = "📖 Luận Giải Từ Vũ Trụ" if idx == 0 else f"📖 Luận Giải (Tiếp theo - Phần {idx+1})"
                    embed.add_field(name=field_title, value=chunk, inline=False)

            # Đính kèm ảnh trải bài
            file = discord.File(fp=image_buffer, filename="tarot_spread.png")
            embed.set_image(url="attachment://tarot_spread.png")
            embed.set_footer(
                text=f"Quẻ bài của {interaction.user.display_name} • DiscordMikeBot Tarot",
                icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
            )

            await interaction.followup.send(embed=embed, file=file)

        except Exception as e:
            print(f"❌ [TarotCog] Lỗi trong quá trình bốc bài: {e}", flush=True)
            traceback.print_exc()
            await interaction.followup.send(
                "❌ Đã xảy ra lỗi trong quá trình bốc và giải bài Tarot. Vui lòng thử lại sau!",
                ephemeral=True
            )

    @app_commands.command(
        name="tarot_history",
        description="Xem lại các lượt bốc bài Tarot gần nhất của bạn"
    )
    async def tarot_history(self, interaction: discord.Interaction):
        history = await self.tarot_manager.get_user_history(interaction.user.id, limit=5)
        if not history:
            await interaction.response.send_message(
                "📜 Bạn chưa có lượt bốc bài Tarot nào được lưu lại. Hãy dùng `/tarot` để bốc quẻ đầu tiên nhé!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📜 LỊCH SỬ BỐC BÀI TAROT - {interaction.user.display_name.upper()}",
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

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TarotCog(bot))
