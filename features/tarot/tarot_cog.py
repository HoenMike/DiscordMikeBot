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
from services.ai_service import split_text


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
        app_commands.Choice(
            name="🌟 Daily Card (Năng lượng & thông điệp ngày - 1 lá)",
            value="daily",
        ),
        app_commands.Choice(
            name="⚡ Yes / No (Trả lời dứt khoát câu hỏi Có/Không - 1 lá)",
            value="yes_no",
        ),
        app_commands.Choice(
            name="🎯 Single Card (Lời khuyên & góc nhìn trọng tâm - 1 lá)",
            value="single",
        ),
        app_commands.Choice(
            name="⏳ Past - Present - Future (Tiến trình sự việc - 3 lá)",
            value="ppf",
        ),
        app_commands.Choice(
            name="⚖️ Two Choices (So sánh nhanh 2 ngả đường A & B - 3 lá)",
            value="choices",
        ),
        app_commands.Choice(
            name="🧘 Mind - Body - Spirit (Định vị bản thân & năng lượng - 3 lá)",
            value="mbs",
        ),
        app_commands.Choice(
            name="🧲 Horseshoe (Toàn cảnh vấn đề & chướng ngại vật - 5 lá)",
            value="horseshoe",
        ),
        app_commands.Choice(
            name="🌿 Two Paths (Phân tích chi tiết rủi ro/lợi ích 2 hướng - 5 lá)",
            value="two_paths",
        ),
        app_commands.Choice(
            name="👑 Celtic Cross (Trải bài chuyên sâu toàn diện 10 góc nhìn - 10 lá)",
            value="celtic",
        ),
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

            # Xây dựng Discord Embed (Sử dụng description để chiếm trọn chiều rộng của Discord)
            embed_color = 0x7851A9  # Tím hoàng gia mặc định
            if spread_key == "yes_no":
                _, _, verdict_color = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
                embed_color = verdict_color

            desc_lines = []
            if clean_question:
                desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{clean_question}*\n")

            if spread_key == "yes_no":
                badge, verdict_desc, _ = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
                desc_lines.append(f"**⚡ Phán Quyết Yes / No:** {badge}\n> *{verdict_desc}*\n")

            # Liệt kê tóm tắt các lá bài
            cards_summary_lines = []
            for drawn in drawn_cards:
                orient = "🔴 `[NGƯỢC]`" if drawn.is_reversed else "🟢 `[XUÔI]`"
                cards_summary_lines.append(
                    f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}"
                )

            desc_lines.append("**🃏 Các Lá Bài Rút Được:**\n" + "\n".join(cards_summary_lines) + "\n")
            desc_lines.append(ai_reading)

            full_description = "\n".join(desc_lines)

            # Chia nhỏ theo đoạn văn an toàn (không bao giờ cắt ngang chữ) nếu vượt quá 4000 ký tự
            chunks = split_text(full_description, limit=4000)
            if not chunks:
                chunks = [full_description]

            embeds = []
            for idx, chunk in enumerate(chunks):
                title = f"🔮 TRẢI BÀI TAROT: {spread_info['name'].upper()}" if idx == 0 else f"🔮 Luận Giải (Tiếp theo - Phần {idx+1})"
                emb = discord.Embed(
                    title=title,
                    description=chunk,
                    color=embed_color
                )
                if idx == len(chunks) - 1:
                    # Gắn footer gọn gàng theo yêu cầu
                    emb.set_footer(
                        text=f"Quẻ bài của {interaction.user.display_name}",
                        icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
                    )
                embeds.append(emb)

            # Đính kèm ảnh trải bài vào embed đầu tiên
            file = discord.File(fp=image_buffer, filename="tarot_spread.png")
            embeds[0].set_image(url="attachment://tarot_spread.png")

            await interaction.followup.send(embeds=embeds, file=file)

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
