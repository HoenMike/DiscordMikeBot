import asyncio
import io
from typing import List, Optional, Set
import discord

from features.tarot.deck import DrawnCard, get_yes_no_verdict, READER_STYLES
from features.tarot.renderer import render_spread_to_bytes
from features.tarot.manager import TarotManager
from core.ai import split_text

WIDE_DIVIDER = "---"


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
        context: Optional[str] = None,
        reader_style: str = "neutral",
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
        self.context = context
        self.reader_style = reader_style
        self.style_info = READER_STYLES.get(reader_style, READER_STYLES["neutral"])
        self.ai_task = ai_task
        self.tarot_manager = tarot_manager
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.revealed_indices: Set[int] = set()
        self._has_completed: bool = False
        self.message: Optional[discord.Message] = None

        # Màu embed theo phong cách hoặc Yes/No phán quyết
        self.embed_color = self.style_info.get("color", 0x7851A9)
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

        # 2. Defer interaction an toàn để tránh lỗi 3 giây timeout
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception as e:
            print(f"⚠️ [TarotFlipView] Lỗi defer interaction: {e}", flush=True)

        custom_id = interaction.data.get("custom_id", "")
        if custom_id == "flip_all":
            self.revealed_indices = set(range(len(self.drawn_cards)))
        elif custom_id.startswith("flip_"):
            idx = int(custom_id.split("_")[1])
            self.revealed_indices.add(idx)

        # 3. Kiểm tra xem đã lật hết chưa
        is_completed = len(self.revealed_indices) == len(self.drawn_cards)

        # 4. Cập nhật nút bấm
        self._build_buttons()

        # 5. Render lại ảnh Canvas với trạng thái lật hiện tại
        image_buffer = await asyncio.to_thread(
            render_spread_to_bytes,
            self.spread_key,
            self.drawn_cards,
            self.revealed_indices
        )
        file = discord.File(fp=image_buffer, filename="tarot_spread.png")

        # 6. Xây dựng Embed tương ứng
        if is_completed:
            self._has_completed = True

            # Xây dựng danh sách lá bài rút được
            cards_summary_lines = []
            for drawn in self.drawn_cards:
                orient = "🔴 `[NGƯỢC]`" if drawn.is_reversed else "🟢 `[XUÔI]`"
                cards_summary_lines.append(
                    f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}"
                )

            # --- EMBED 1: QUẺ RÚT & HÌNH ẢNH TRẢI BÀI ---
            desc_cards = []
            if self.question:
                desc_cards.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")
            if self.context:
                desc_cards.append(f"**📝 Bối cảnh:**\n*{self.context}*\n")
            if self.reader_style != "neutral":
                desc_cards.append(f"**🎭 Người trải bài:** {self.style_info['name']}\n")
            if self.spread_key == "yes_no":
                badge, verdict_desc, _ = get_yes_no_verdict(self.drawn_cards[0].card, self.drawn_cards[0].is_reversed)
                desc_cards.append(f"**⚡ Phán Quyết Yes / No:** {badge}\n> *{verdict_desc}*\n")
            desc_cards.append(WIDE_DIVIDER)
            desc_cards.append("**🃏 Các Lá Bài Rút Được:**\n" + "\n".join(cards_summary_lines))

            embed_cards = discord.Embed(
                title=f"🔮 TRẢI BÀI TAROT: {self.spread_info['name'].upper()}",
                description="\n".join(desc_cards),
                color=self.embed_color
            )
            embed_cards.set_image(url="attachment://tarot_spread.png")

            sent_image_already = False
            # Nếu luận giải chưa sẵn sàng: CẬP NHẬT NGAY để người dùng thấy ảnh bài đã lật tức thì (Instant Visual Flip)
            if not self.ai_task.done():
                embed_loading = discord.Embed(
                    title=self.style_info.get("loading_title", "✨ ĐANG ĐÓN NHẬN THÔNG ĐIỆP..."),
                    description=self.style_info.get("loading_desc", "🌌 *Đang kết nối năng lượng và giải mã tín hiệu từ vũ trụ, xin chờ trong giây lát...*"),
                    color=self.embed_color
                )
                embed_loading.set_footer(
                    text=f"Quẻ bài của {self.author_name}",
                    icon_url=self.author_avatar_url
                )

                try:
                    await interaction.edit_original_response(
                        embeds=[embed_cards, embed_loading],
                        attachments=[file],
                        view=None
                    )
                    sent_image_already = True
                except Exception:
                    if self.message:
                        try:
                            await self.message.edit(embeds=[embed_cards, embed_loading], attachments=[file], view=None)
                            sent_image_already = True
                        except Exception:
                            pass

            # Await bài luận giải thông điệp
            ai_reading = await self.ai_task

            # Lưu vào Database
            if self.spread_key == "daily":
                await self.tarot_manager.record_daily_draw(self.author_id, self.drawn_cards[0])

            saved_q = f"{self.question} (Bối cảnh: {self.context})" if self.question and self.context else (self.question or (f"Bối cảnh: {self.context}" if self.context else None))
            await self.tarot_manager.save_tarot_history(
                user_id=self.author_id,
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                spread_type=self.spread_key,
                question=saved_q,
                drawn_cards=self.drawn_cards,
                ai_reading=ai_reading
            )

            # --- EMBED 2: THÔNG ĐIỆP TỪ VŨ TRỤ ---
            chunks = split_text(ai_reading, limit=4000)
            if not chunks:
                chunks = [ai_reading]

            final_embeds = [embed_cards]
            for idx_chunk, chunk in enumerate(chunks):
                title = (
                    self.style_info.get("embed_title", "📖 THÔNG ĐIỆP TỪ VŨ TRỤ")
                    if idx_chunk == 0
                    else f"{self.style_info.get('embed_title', '📖 Thông Điệp')} (Tiếp theo - Phần {idx_chunk + 1})"
                )
                emb_reading = discord.Embed(
                    title=title,
                    description=chunk,
                    color=self.embed_color
                )
                if idx_chunk == len(chunks) - 1:
                    emb_reading.set_footer(
                        text=f"Quẻ bài của {self.author_name}",
                        icon_url=self.author_avatar_url
                    )
                final_embeds.append(emb_reading)

            # Cập nhật kết quả bài giải đầy đủ lên Discord
            try:
                if not sent_image_already:
                    await interaction.edit_original_response(
                        embeds=final_embeds,
                        attachments=[file],
                        view=None
                    )
                else:
                    await interaction.edit_original_response(
                        embeds=final_embeds,
                        view=None
                    )
            except Exception:
                if self.message:
                    try:
                        if not sent_image_already:
                            await self.message.edit(embeds=final_embeds, attachments=[file], view=None)
                        else:
                            await self.message.edit(embeds=final_embeds, view=None)
                    except Exception as ex:
                        print(f"⚠️ [TarotFlipView] Message edit fallback lỗi: {ex}", flush=True)
            self.stop()

        else:
            # Chưa lật hết: Hiển thị giao diện chờ lật bài
            desc_lines = []
            if self.question:
                desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")
            if self.context:
                desc_lines.append(f"**📝 Bối cảnh:**\n*{self.context}*\n")

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

            try:
                await interaction.edit_original_response(
                    embed=emb,
                    attachments=[file],
                    view=self
                )
            except Exception:
                if self.message:
                    try:
                        await self.message.edit(embed=emb, attachments=[file], view=self)
                    except Exception as ex:
                        print(f"⚠️ [TarotFlipView] Message edit fallback lỗi: {ex}", flush=True)

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

            # Xây dựng danh sách lá bài rút được
            cards_summary_lines = []
            for drawn in self.drawn_cards:
                orient = "🔴 `[NGƯỢC]`" if drawn.is_reversed else "🟢 `[XUÔI]`"
                cards_summary_lines.append(
                    f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}"
                )

            # --- EMBED 1: QUẺ RÚT & HÌNH ẢNH TRẢI BÀI ---
            desc_cards = []
            if self.question:
                desc_cards.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")
            if self.context:
                desc_cards.append(f"**📝 Bối cảnh:**\n*{self.context}*\n")
            if self.reader_style != "neutral":
                desc_cards.append(f"**🎭 Người trải bài:** {self.style_info['name']}\n")
            if self.spread_key == "yes_no":
                badge, verdict_desc, _ = get_yes_no_verdict(self.drawn_cards[0].card, self.drawn_cards[0].is_reversed)
                desc_cards.append(f"**⚡ Phán Quyết Yes / No:** {badge}\n> *{verdict_desc}*\n")
            desc_cards.append(WIDE_DIVIDER)
            desc_cards.append("**🃏 Các Lá Bài Rút Được:**\n" + "\n".join(cards_summary_lines))

            embed_cards = discord.Embed(
                title=f"🔮 TRẢI BÀI TAROT: {self.spread_info['name'].upper()}",
                description="\n".join(desc_cards),
                color=self.embed_color
            )
            embed_cards.set_image(url="attachment://tarot_spread.png")

            # --- EMBED 2: THÔNG ĐIỆP TỪ VŨ TRỤ ---
            chunks = split_text(ai_reading, limit=4000)
            if not chunks:
                chunks = [ai_reading]

            final_embeds = [embed_cards]
            for idx_chunk, chunk in enumerate(chunks):
                title = (
                    self.style_info.get("embed_title", "📖 THÔNG ĐIỆP TỪ VŨ TRỤ")
                    if idx_chunk == 0
                    else f"{self.style_info.get('embed_title', '📖 Thông Điệp')} (Tiếp theo - Phần {idx_chunk + 1})"
                )
                emb_reading = discord.Embed(
                    title=title,
                    description=chunk,
                    color=self.embed_color
                )
                if idx_chunk == len(chunks) - 1:
                    emb_reading.set_footer(
                        text=f"Quẻ bài của {self.author_name}",
                        icon_url=self.author_avatar_url
                    )
                final_embeds.append(emb_reading)

            if self.message:
                await self.message.edit(embeds=final_embeds, attachments=[file], view=None)
        except Exception as e:
            print(f"[TarotFlipView] Lỗi on_timeout: {e}", flush=True)
