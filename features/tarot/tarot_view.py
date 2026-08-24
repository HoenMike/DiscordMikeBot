import asyncio
import io
from typing import List, Optional, Set
import discord

from features.tarot.deck import DrawnCard, get_yes_no_verdict
from features.tarot.renderer import render_spread_to_bytes
from features.tarot.manager import TarotManager
from services.ai_service import split_text

WIDE_DIVIDER = "──────────────────────────────────────────"


class TarotFlipView(discord.ui.View):
    """
    View tương tác Gamification: Cho phép người dùng bấm từng nút để lật mở từng lá bài,
    cập nhật Realtime cho cả kênh chat cùng theo dõi trước khi bung bài giải từ AI.
    """

    def __init__(
        self,
        author_id: int,
        author_name: str,
        author_avatar_url: Optional[str],
        spread_key: str,
        spread_info: dict,
        drawn_cards: List[DrawnCard],
        question: Optional[str],
        ai_task: asyncio.Task,
        tarot_manager: TarotManager,
        guild_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.author_name = author_name
        self.author_avatar_url = author_avatar_url
        self.spread_key = spread_key
        self.spread_info = spread_info
        self.drawn_cards = drawn_cards
        self.question = question
        self.ai_task = ai_task
        self.tarot_manager = tarot_manager
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.revealed_indices: Set[int] = set()
        self._has_completed: bool = False
        self.message: Optional[discord.Message] = None

        # Màu embed
        self.embed_color = 0x7851A9
        if self.spread_key == "yes_no":
            _, _, verdict_color = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
            self.embed_color = verdict_color

        self._build_buttons()

    def _build_buttons(self):
        """Khởi tạo và cập nhật trạng thái các nút bấm lật bài."""
        self.clear_items()
        card_count = len(self.drawn_cards)

        if card_count == 1:
            is_opened = 0 in self.revealed_indices
            label = "✅ Đã Lật Bài" if is_opened else "🎴 Lật Mở Quẻ Bài"
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.success if is_opened else discord.ButtonStyle.primary,
                custom_id="flip_0",
                disabled=is_opened,
                row=0
            )
            btn.callback = self._handle_button_click
            self.add_item(btn)
            return

        # Với 3, 5, 10 lá: Tạo nút cho từng lá + nút Lật Tất Cả
        for idx, card in enumerate(self.drawn_cards):
            is_opened = idx in self.revealed_indices
            pos_title = card.position_title

            # Rút ngắn nhãn nút để vừa giao diện Discord
            short_label = pos_title.split(":")[0].strip() if ":" in pos_title else f"Lá {idx + 1}"
            if is_opened:
                btn_label = f"✅ {short_label}"
                btn_style = discord.ButtonStyle.secondary
            else:
                btn_label = f"🎴 {short_label}"
                btn_style = discord.ButtonStyle.primary

            # Tính row: tối đa 5 nút / hàng
            row = idx // 5

            btn = discord.ui.Button(
                label=btn_label,
                style=btn_style,
                custom_id=f"flip_{idx}",
                disabled=is_opened,
                row=row
            )
            btn.callback = self._handle_button_click
            self.add_item(btn)

        # Nút "Lật Tất Cả"
        all_opened = len(self.revealed_indices) == card_count
        row_for_all = (card_count // 5) if (card_count % 5 != 0) else (card_count // 5)
        btn_all = discord.ui.Button(
            label="✨ Lật Tất Cả",
            style=discord.ButtonStyle.success if not all_opened else discord.ButtonStyle.secondary,
            custom_id="flip_all",
            disabled=all_opened,
            row=min(4, row_for_all)
        )
        btn_all.callback = self._handle_button_click
        self.add_item(btn_all)

    async def _handle_button_click(self, interaction: discord.Interaction):
        """Xử lý khi người dùng bấm nút lật bài."""
        # 1. Kiểm tra phân quyền: Chỉ người bốc bài mới được lật
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "🔒 Chỉ người bốc quẻ mới có thể bấm lật bài!",
                ephemeral=True
            )
            return

        custom_id = interaction.data.get("custom_id", "")
        if custom_id == "flip_all":
            self.revealed_indices = set(range(len(self.drawn_cards)))
        elif custom_id.startswith("flip_"):
            idx = int(custom_id.split("_")[1])
            self.revealed_indices.add(idx)

        # 2. Kiểm tra xem đã lật hết chưa
        is_completed = len(self.revealed_indices) == len(self.drawn_cards)

        # 3. Cập nhật nút bấm
        self._build_buttons()

        # 4. Render lại ảnh Canvas với trạng thái lật hiện tại
        image_buffer = await asyncio.to_thread(
            render_spread_to_bytes,
            self.spread_key,
            self.drawn_cards,
            self.revealed_indices
        )
        file = discord.File(fp=image_buffer, filename="tarot_spread.png")

        # 5. Xây dựng Embed tương ứng
        if is_completed:
            self._has_completed = True
            # Await bài luận giải AI chạy ngầm
            ai_reading = await self.ai_task

            # Lưu vào Database
            if self.spread_key == "daily":
                await self.tarot_manager.record_daily_draw(self.author_id, self.drawn_cards[0])

            await self.tarot_manager.save_tarot_history(
                user_id=self.author_id,
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                spread_type=self.spread_key,
                question=self.question,
                drawn_cards=self.drawn_cards,
                ai_reading=ai_reading
            )

            # Xây dựng Embed hoàn chỉnh (Full-width description)
            desc_lines = []
            if self.question:
                desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")

            if self.spread_key == "yes_no":
                badge, verdict_desc, _ = get_yes_no_verdict(self.drawn_cards[0].card, self.drawn_cards[0].is_reversed)
                desc_lines.append(f"**⚡ Phán Quyết Yes / No:** {badge}\n> *{verdict_desc}*\n")

            desc_lines.append(WIDE_DIVIDER)

            cards_summary_lines = []
            for drawn in self.drawn_cards:
                orient = "🔴 `[NGƯỢC]`" if drawn.is_reversed else "🟢 `[XUÔI]`"
                cards_summary_lines.append(
                    f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}"
                )

            desc_lines.append("**🃏 Các Lá Bài Rút Được:**\n" + "\n".join(cards_summary_lines) + "\n")
            desc_lines.append(WIDE_DIVIDER)
            desc_lines.append(ai_reading)

            full_description = "\n".join(desc_lines)
            chunks = split_text(full_description, limit=4000)
            if not chunks:
                chunks = [full_description]

            embeds = []
            for idx_chunk, chunk in enumerate(chunks):
                title = (
                    f"🔮 TRẢI BÀI TAROT: {self.spread_info['name'].upper()}"
                    if idx_chunk == 0
                    else f"🔮 Luận Giải (Tiếp theo - Phần {idx_chunk + 1})"
                )
                emb = discord.Embed(title=title, description=chunk, color=self.embed_color)
                if idx_chunk == len(chunks) - 1:
                    emb.set_footer(
                        text=f"Quẻ bài của {self.author_name}",
                        icon_url=self.author_avatar_url
                    )
                embeds.append(emb)

            embeds[0].set_image(url="attachment://tarot_spread.png")

            # Khi đã lật xong, disable hoặc dọn dẹp các nút bấm
            for item in self.children:
                item.disabled = True

            await interaction.response.edit_message(
                embeds=embeds,
                attachments=[file],
                view=self
            )
            self.stop()

        else:
            # Chưa lật hết: Hiển thị giao diện chờ lật bài
            desc_lines = []
            if self.question:
                desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")

            desc_lines.append(WIDE_DIVIDER)

            cards_summary_lines = []
            for idx, drawn in enumerate(self.drawn_cards):
                if idx in self.revealed_indices:
                    orient = "🔴 `[NGƯỢC]`" if drawn.is_reversed else "🟢 `[XUÔI]`"
                    cards_summary_lines.append(
                        f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}"
                    )
                else:
                    cards_summary_lines.append(
                        f"• **{drawn.position_title}**: ⏳ *(Chờ lật)*"
                    )

            desc_lines.append("**🃏 Các Lá Bài:**\n" + "\n".join(cards_summary_lines) + "\n")
            desc_lines.append("⏳ *Hãy bấm vào các nút bên dưới để lật mở từng lá bài...*")

            emb = discord.Embed(
                title=f"🔮 TRẢI BÀI TAROT: {self.spread_info['name'].upper()}",
                description="\n".join(desc_lines),
                color=self.embed_color
            )
            emb.set_image(url="attachment://tarot_spread.png")
            emb.set_footer(
                text=f"Quẻ bài của {self.author_name} (Đang bốc bài...)",
                icon_url=self.author_avatar_url
            )

            await interaction.response.edit_message(
                embed=emb,
                attachments=[file],
                view=self
            )

    async def on_timeout(self):
        """Nếu sau 5 phút người dùng không lật hết, tự động lật toàn bộ."""
        if self._has_completed:
            return

        try:
            self.revealed_indices = set(range(len(self.drawn_cards)))
            self._build_buttons()
            for item in self.children:
                item.disabled = True

            ai_reading = await self.ai_task
            image_buffer = await asyncio.to_thread(
                render_spread_to_bytes,
                self.spread_key,
                self.drawn_cards,
                self.revealed_indices
            )
            file = discord.File(fp=image_buffer, filename="tarot_spread.png")

            desc_lines = []
            if self.question:
                desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")

            cards_summary_lines = []
            for drawn in self.drawn_cards:
                orient = "🔴 `[NGƯỢC]`" if drawn.is_reversed else "🟢 `[XUÔI]`"
                cards_summary_lines.append(
                    f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}"
                )

            desc_lines.append("**🃏 Các Lá Bài Rút Được:**\n" + "\n".join(cards_summary_lines) + "\n")
            desc_lines.append(ai_reading)

            emb = discord.Embed(
                title=f"🔮 TRẢI BÀI TAROT: {self.spread_info['name'].upper()}",
                description="\n".join(desc_lines),
                color=self.embed_color
            )
            emb.set_image(url="attachment://tarot_spread.png")
            emb.set_footer(
                text=f"Quẻ bài của {self.author_name}",
                icon_url=self.author_avatar_url
            )

            if self.message:
                await self.message.edit(embed=emb, attachments=[file], view=self)
        except Exception as e:
            print(f"[TarotFlipView] Lỗi on_timeout: {e}", flush=True)
