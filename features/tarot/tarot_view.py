import asyncio
import io
import os
import random
from typing import List, Optional, Set, Any
import discord

import config
from features.tarot.deck import (
    DrawnCard,
    get_yes_no_verdict,
    READER_STYLES,
    SPREAD_DEFINITIONS,
    draw_spread
)
from features.tarot.renderer import render_spread_to_bytes
from features.tarot.ai import generate_tarot_reading
from features.tarot.voice_reader import play_tarot_voice, auto_play_tarot_voice, generate_tarot_speech
from features.tarot.manager import TarotManager
from core.ai import split_text

WIDE_DIVIDER = "---"

SPREAD_SELECT_OPTIONS = [
    discord.SelectOption(
        label="🌟 Daily Card (Năng lượng ngày - 1 lá)",
        value="daily",
        description="Thông điệp & năng lượng bao quát trong ngày"
    ),
    discord.SelectOption(
        label="⚡ Yes / No (Hỏi nhanh - 1 lá)",
        value="yes_no",
        description="Phán quyết Có/Không kèm phân tích năng lượng"
    ),
    discord.SelectOption(
        label="🎯 Single Card (Lời khuyên - 1 lá)",
        value="single",
        description="Góc nhìn cốt lõi và bài học quan trọng nhất"
    ),
    discord.SelectOption(
        label="⏳ Past - Present - Future (3 lá)",
        value="ppf",
        description="Tiến trình Quá khứ - Hiện tại - Tương lai"
    ),
    discord.SelectOption(
        label="⚖️ Two Choices (2 ngả đường - 3 lá)",
        value="choices",
        description="So sánh nhanh Phương án A & Phương án B"
    ),
    discord.SelectOption(
        label="🧘 Mind - Body - Spirit (3 lá)",
        value="mbs",
        description="Tâm trí - Thể chất - Trực giác nội tâm"
    ),
    discord.SelectOption(
        label="🧲 Horseshoe Spread (5 lá)",
        value="horseshoe",
        description="Toàn cảnh vấn đề & chướng ngại vật"
    ),
    discord.SelectOption(
        label="🌿 Two Paths (So sánh sâu 2 hướng - 5 lá)",
        value="two_paths",
        description="Phân tích chi tiết rủi ro & cơ hội của 2 hướng"
    ),
    discord.SelectOption(
        label="👑 Celtic Cross (Chữ thập - 10 lá)",
        value="celtic",
        description="Trải bài chuyên sâu toàn diện 10 góc nhìn"
    ),
]

READER_SELECT_OPTIONS = [
    discord.SelectOption(
        label="🎲 Ngẫu Nhiên",
        value="random"
    ),
    discord.SelectOption(
        label="⚖️ Orion",
        value="neutral"
    ),
    discord.SelectOption(
        label="🌸 Celeste",
        value="healer"
    ),
    discord.SelectOption(
        label="🃏 Jester",
        value="chaos"
    ),
]


class TarotQuestionModal(discord.ui.Modal, title="🔮 Nhập Câu Hỏi & Bối Cảnh Tarot"):
    """Modal popup cho phép người dùng nhập câu hỏi và bối cảnh trước khi bốc bài."""

    def __init__(self, launcher_view: "TarotLauncherView"):
        super().__init__()
        self.launcher_view = launcher_view

        self.question_input = discord.ui.TextInput(
            label="Câu hỏi / Chủ đề muốn xem",
            style=discord.TextStyle.paragraph,
            placeholder="Ví dụ: Công việc tháng tới của tôi sẽ tiến triển thế nào?",
            default=launcher_view.question or "",
            required=False,
            max_length=500
        )
        self.add_item(self.question_input)

        self.context_input = discord.ui.TextInput(
            label="Bối cảnh thực tế (Không bắt buộc)",
            style=discord.TextStyle.paragraph,
            placeholder="Ví dụ: Đang chuẩn bị chuyển việc hoặc sắp có đợt đánh giá...",
            default=launcher_view.context or "",
            required=False,
            max_length=500
        )
        self.add_item(self.context_input)

    async def on_submit(self, interaction: discord.Interaction):
        clean_q = self.question_input.value.strip() if self.question_input.value else None
        clean_ctx = self.context_input.value.strip() if self.context_input.value else None

        self.launcher_view.question = clean_q if clean_q else None
        self.launcher_view.context = clean_ctx if clean_ctx else None

        embed = self.launcher_view.build_launcher_embed()
        await interaction.response.edit_message(embed=embed, view=self.launcher_view)


class TarotLauncherView(discord.ui.View):
    """
    View Bảng Điều Khiển Tương Tác (Launcher UI):
    Cho phép chọn Kiểu trải bài, Người giải bài, Nhập câu hỏi qua Modal,
    và sau đó gửi quẻ bài ra kênh chat.
    """

    def __init__(
        self,
        author_id: int,
        author_name: str,
        author_avatar_url: Optional[str],
        tarot_manager: TarotManager,
        selected_spread: str = "daily",
        selected_reader: str = "random",
        question: Optional[str] = None,
        context: Optional[str] = None,
        trigger_message: Optional[discord.Message] = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.author_name = author_name
        self.author_avatar_url = author_avatar_url
        self.tarot_manager = tarot_manager
        self.selected_spread = selected_spread
        self.selected_reader = selected_reader
        self.question = question
        self.context = context
        self.trigger_message = trigger_message
        self.message: Optional[discord.Message] = None

        self._build_components()

    def _check_author(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    def build_launcher_embed(self) -> discord.Embed:
        """Xây dựng Embed hiển thị thông tin và trạng thái lựa chọn hiện tại."""
        spread_info = SPREAD_DEFINITIONS.get(self.selected_spread, SPREAD_DEFINITIONS["daily"])
        if self.selected_reader == "random" or self.selected_reader not in READER_STYLES:
            reader_display = "🎲 **Ngẫu Nhiên**"
            embed_color = 0x7851A9
        else:
            reader_info = READER_STYLES[self.selected_reader]
            reader_display = f"**{reader_info['name']}**"
            embed_color = reader_info.get("color", 0x7851A9)

        q_status = f"*{self.question}*" if self.question else ("⚠️ *Chưa nhập (Bắt buộc)*" if spread_info.get("requires_question", True) else "*(Không bắt buộc)*")
        ctx_status = f"*{self.context}*" if self.context else "*(Không có)*"

        lines = [
            f"Chào mừng **{self.author_name}** đến với không gian chiêm tinh học Tarot!\n",
            f"**🔮 THIẾT LẬP QUẺ BÀI:**",
            f"• 🃏 **Kiểu trải bài:** **{spread_info['name']}**",
            f"• 🎭 **Người giải bài:** {reader_display}",
            f"• ❓ **Câu hỏi / Chủ đề:** {q_status}",
            f"• 📝 **Bối cảnh:** {ctx_status}",
            WIDE_DIVIDER,
            "💡 **Hướng dẫn thao tác:**",
            "1. Chọn kiểu trải bài & người giải bài từ **2 Menu thả xuống** bên dưới.",
            "2. Nhấn nút **✏️ Đặt Câu Hỏi** để nhập câu hỏi / bối cảnh cụ thể.",
            "3. Nhấn **🎴 Bắt Đầu Bốc Bài** để trải bài ra kênh chat!"
        ]

        embed = discord.Embed(
            title="🔮 BẢNG THIẾT LẬP TRẢI BÀI TAROT",
            description="\n".join(lines),
            color=embed_color
        )
        embed.set_footer(
            text=f"Quẻ bài của {self.author_name} • MikeBot Tarot",
            icon_url=self.author_avatar_url
        )
        return embed

    def _build_components(self):
        self.clear_items()

        # 1. Select Menu: Chọn kiểu trải bài (Row 0)
        spread_select = discord.ui.Select(
            placeholder="🔮 Chọn kiểu trải bài Tarot...",
            options=[
                discord.SelectOption(
                    label=opt.label,
                    value=opt.value,
                    description=opt.description,
                    default=(opt.value == self.selected_spread)
                )
                for opt in SPREAD_SELECT_OPTIONS
            ],
            row=0,
            custom_id="launcher_spread_select"
        )
        spread_select.callback = self._handle_spread_select
        self.add_item(spread_select)

        # 2. Select Menu: Chọn người giải bài (Row 1)
        reader_select = discord.ui.Select(
            placeholder="🎭 Chọn người giải bài...",
            options=[
                discord.SelectOption(
                    label=opt.label,
                    value=opt.value,
                    description=opt.description,
                    default=(opt.value == self.selected_reader)
                )
                for opt in READER_SELECT_OPTIONS
            ],
            row=1,
            custom_id="launcher_reader_select"
        )
        reader_select.callback = self._handle_reader_select
        self.add_item(reader_select)

        # 3. Action Buttons (Row 2)
        btn_question = discord.ui.Button(
            label="✏️ Đặt Câu Hỏi",
            style=discord.ButtonStyle.primary,
            custom_id="launcher_btn_question",
            row=2
        )
        btn_question.callback = self._handle_question_button
        self.add_item(btn_question)

        btn_start = discord.ui.Button(
            label="🎴 Bắt Đầu Bốc Bài",
            style=discord.ButtonStyle.success,
            custom_id="launcher_btn_start",
            row=2
        )
        btn_start.callback = self._handle_start_button
        self.add_item(btn_start)

        btn_history = discord.ui.Button(
            label="📜 Lịch Sử",
            style=discord.ButtonStyle.secondary,
            custom_id="launcher_btn_history",
            row=2
        )
        btn_history.callback = self._handle_history_button
        self.add_item(btn_history)

        btn_cancel = discord.ui.Button(
            label="❌ Đóng",
            style=discord.ButtonStyle.danger,
            custom_id="launcher_btn_cancel",
            row=2
        )
        btn_cancel.callback = self._handle_cancel_button
        self.add_item(btn_cancel)

    async def _handle_spread_select(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        self.selected_spread = interaction.data["values"][0]
        self._build_components()
        await interaction.response.edit_message(embed=self.build_launcher_embed(), view=self)

    async def _handle_reader_select(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        self.selected_reader = interaction.data["values"][0]
        self._build_components()
        await interaction.response.edit_message(embed=self.build_launcher_embed(), view=self)

    async def _handle_question_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        await interaction.response.send_modal(TarotQuestionModal(self))

    async def _handle_start_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        spread_info = SPREAD_DEFINITIONS.get(self.selected_spread, SPREAD_DEFINITIONS["daily"])

        # Kiểm tra câu hỏi nếu trải bài yêu cầu
        if spread_info.get("requires_question", True) and not self.question:
            await interaction.response.send_modal(TarotQuestionModal(self))
            return

        # Kiểm tra Daily Cooldown
        if self.selected_spread == "daily":
            can_draw, last_draw = await self.tarot_manager.check_daily_cooldown(interaction.user.id)
            if not can_draw and last_draw:
                last_card_str = f"**{last_draw.get('name_vi', 'Bài')}** ({last_draw.get('name_en', '')})"
                orient_str = "[NGƯỢC]" if last_draw.get("is_reversed") else "[XUÔI]"
                drawn_time = last_draw.get("drawn_at", "hôm nay")
                await interaction.response.send_message(
                    f"☀️ **Bạn đã rút Daily Card của ngày hôm nay rồi!**\n\n"
                    f"🃏 Lá bài hôm nay của bạn: {last_card_str} - `{orient_str}` *(Rút lúc {drawn_time})*\n"
                    f"⏰ *Lượt bốc bài sẽ được làm mới vào lúc 00:00 (Giờ VN)!*\n\n"
                    f"💡 *Nếu bạn có câu hỏi khác, hãy chọn `Single Card` hoặc `Yes / No` trong menu nhé!*",
                    ephemeral=True
                )
                return

        # Kiểm tra Cooldown 1 phút chống spam giữa 2 lần bốc bài
        can_proceed, wait_sec = self.tarot_manager.check_user_cooldown(interaction.user.id, cooldown_seconds=config.COMMAND_COOLDOWN_SECONDS)
        if not can_proceed:
            await interaction.response.send_message(
                f"⏳ **Bạn đang thao tác quá nhanh!** Vui lòng đợi `{int(wait_sec) + 1}s` nữa trước khi bốc quẻ tiếp theo.",
                ephemeral=True
            )
            return

        # Khởi chạy phiên bốc bài
        await self.start_reading(interaction)

    async def start_reading(self, interaction: discord.Interaction):
        """Tạo quẻ bài và thay thế / đóng bảng điều khiển thiết lập."""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        self.tarot_manager.record_user_action(self.author_id)

        drawn_cards = draw_spread(
            spread_key=self.selected_spread,
            user_id=self.author_id,
            question=self.question
        )
        spread_info = SPREAD_DEFINITIONS[self.selected_spread]

        # Nếu không chọn hoặc chọn Ngẫu nhiên, tự động random 1 trong 3 Reader
        actual_reader = self.selected_reader
        if actual_reader == "random" or not actual_reader or actual_reader not in READER_STYLES:
            actual_reader = random.choice(["neutral", "healer", "chaos"])

        ai_task = asyncio.create_task(
            generate_tarot_reading(
                spread_key=self.selected_spread,
                drawn_cards=drawn_cards,
                question=self.question,
                context=self.context,
                reader_style=actual_reader,
                user_name=self.author_name
            )
        )

        flip_view = TarotFlipView(
            author_id=self.author_id,
            author_name=self.author_name,
            author_avatar_url=self.author_avatar_url,
            spread_key=self.selected_spread,
            spread_info=spread_info,
            drawn_cards=drawn_cards,
            question=self.question,
            context=self.context,
            reader_style=actual_reader,
            ai_task=ai_task,
            tarot_manager=self.tarot_manager,
            guild_id=interaction.guild.id if interaction.guild else None,
            channel_id=interaction.channel.id if interaction.channel else None
        )

        image_buffer = await asyncio.to_thread(
            render_spread_to_bytes,
            self.selected_spread,
            drawn_cards,
            set()
        )
        file = discord.File(fp=image_buffer, filename="tarot_spread.png")

        desc_lines = []
        if self.question:
            desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")
        if self.context:
            desc_lines.append(f"**📝 Bối cảnh:**\n*{self.context}*\n")
        desc_lines.append(f"**🎭 Người trải bài:** {flip_view.style_info['name']}\n")

        desc_lines.append(WIDE_DIVIDER)

        cards_summary_lines = []
        for drawn in drawn_cards:
            cards_summary_lines.append(f"• **{drawn.position_title}**: ⏳ *(Chờ lật)*")

        desc_lines.append("**🃏 Các Lá Bài:**\n" + "\n".join(cards_summary_lines) + "\n")
        desc_lines.append("⏳ *Hãy bấm vào các nút bên dưới để lật mở từng lá bài...*")

        embed = discord.Embed(
            title=f"🔮 TRẢI BÀI TAROT: {spread_info['name'].upper()}",
            description="\n".join(desc_lines),
            color=flip_view.embed_color
        )
        embed.set_image(url="attachment://tarot_spread.png")
        embed.set_footer(
            text=f"Quẻ bài của {self.author_name} (Đang bốc bài...)",
            icon_url=self.author_avatar_url
        )

        # 1. Nếu mở từ Prefix ($m tarot -> self.message tồn tại): Edit trực tiếp vào tin nhắn đó (mượt mà, 0 tin nhắn thừa)
        if self.message:
            try:
                await self.message.edit(embed=embed, attachments=[file], view=flip_view)
                flip_view.message = self.message
            except Exception:
                if interaction.channel:
                    sent_msg = await interaction.channel.send(embed=embed, file=file, view=flip_view)
                    flip_view.message = sent_msg
        else:
            # 2. Nếu mở từ Slash Command (/tarot -> ephemeral): Gửi quẻ bài ra kênh và xóa sạch bảng ephemeral
            if interaction.channel:
                sent_msg = await interaction.channel.send(embed=embed, file=file, view=flip_view)
                flip_view.message = sent_msg
            try:
                await interaction.delete_original_response()
            except Exception:
                pass

        # 3. Dọn dẹp trigger message nếu có
        if self.trigger_message:
            try:
                await self.trigger_message.delete()
            except Exception:
                pass

        self.stop()

    async def _handle_history_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        history = await self.tarot_manager.get_user_history(interaction.user.id, limit=5)
        if not history:
            await interaction.response.send_message(
                "📜 Bạn chưa có lượt bốc bài Tarot nào được lưu lại.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📜 LỊCH SỬ BỐC BÀI TAROT - {self.author_name.upper()}",
            description="Dưới đây là tối đa 5 lượt bốc bài gần nhất của bạn:",
            color=0xDAA520
        )
        for item in history:
            spread_k = item["spread_type"]
            s_name = SPREAD_DEFINITIONS.get(spread_k, {}).get("name", spread_k)
            q_str = f"**Câu hỏi:** *{item['question']}*\n" if item["question"] else ""
            cards = item["cards"]
            cards_summary = ", ".join([
                f"{c['name_vi']} ({'[NGƯỢC]' if c['is_reversed'] else '[XUÔI]'})"
                for c in cards
            ])
            embed.add_field(
                name=f"🔮 {s_name} • ({item['created_at']})",
                value=f"{q_str}🃏 **Các lá bài:** {cards_summary}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_cancel_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        self.clear_items()
        try:
            if self.message:
                await self.message.delete()
            else:
                await interaction.delete_original_response()
        except Exception:
            pass
        self.stop()

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass


class TarotResultView(discord.ui.View):
    """
    View tương tác sau khi đã luận giải xong quẻ bài:
    - Nếu người bốc bài đang trong Voice: Tự động phát âm thanh, nút hiển thị '🔊 Đang Đọc Trong Voice...'.
    - Nếu người bốc bài KHÔNG trong Voice: Hiển thị nút '🔊 Nghe Đọc Bài' để bấm khi cần.
    """

    def __init__(
        self,
        ai_reading: str,
        reader_style: str,
        author_id: int,
        author_name: str,
        spread_name: str = "",
        preload_task: Optional[asyncio.Task] = None,
        is_auto_playing: bool = False,
        timeout: float = 600.0,
    ):
        super().__init__(timeout=timeout)
        self.ai_reading = ai_reading
        self.reader_style = reader_style
        self.author_id = author_id
        self.author_name = author_name
        self.spread_name = spread_name
        self.preload_task = preload_task
        self.preloaded_audio_path: Optional[str] = None
        self.is_speaking = is_auto_playing
        self.message: Optional[discord.Message] = None

        style_info = READER_STYLES.get(self.reader_style, READER_STYLES["neutral"])
        self.reader_name = style_info.get("name", "Reader")

        # Nút nghe đọc bài qua Voice
        btn_label = "🔊 Đang Đọc Trong Voice..." if is_auto_playing else f"🔊 Nghe {self.reader_name} Đọc Bài"
        self.voice_button = discord.ui.Button(
            label=btn_label,
            style=discord.ButtonStyle.primary,
            custom_id="tarot_listen_voice",
            disabled=is_auto_playing,
            row=0,
        )
        self.voice_button.callback = self._handle_voice_click
        self.add_item(self.voice_button)

    async def on_auto_play_finished(self, failed: bool = False, is_busy: bool = False):
        """Callback khi luồng tự động đọc bài hoàn tất hoặc kết thúc."""
        self.is_speaking = False
        if failed or is_busy:
            self.voice_button.label = f"🔊 Nghe {self.reader_name} Đọc Bài"
        else:
            self.voice_button.label = f"🔊 Nghe {self.reader_name} Đọc Lại"
        self.voice_button.disabled = False
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    async def _handle_voice_click(self, interaction: discord.Interaction):
        # Chỉ cho phép người bốc bài (author) bấm nút
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                f"🔒 **Chỉ người bốc quẻ bài này ({self.author_name}) mới có thể yêu cầu Bot đọc bài!**\n"
                f"💡 Hãy dùng lệnh `/tarot` để tự bốc và nghe trải bài của riêng bạn nhé!",
                ephemeral=True
            )
            return

        if self.is_speaking:
            await interaction.response.send_message(
                "⏳ Reader đang thực hiện đọc bài trong Voice Channel, vui lòng đợi đọc xong nhé!",
                ephemeral=True,
            )
            return

        # Defer ephemeral response để chuẩn bị xử lý
        await interaction.response.defer(ephemeral=True)

        self.is_speaking = True
        self.voice_button.label = "⏳ Đang kết nối & đọc bài..."
        self.voice_button.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
            else:
                await interaction.edit_original_response(view=self)
        except Exception:
            pass

        # Lấy đường dẫn file âm thanh đã preload sẵn nếu có
        preloaded_path = None
        if self.preloaded_audio_path and os.path.exists(self.preloaded_audio_path):
            preloaded_path = self.preloaded_audio_path
        elif self.preload_task:
            try:
                preloaded_path = await asyncio.wait_for(asyncio.shield(self.preload_task), timeout=3.0)
                self.preloaded_audio_path = preloaded_path
            except Exception:
                pass

        try:
            await play_tarot_voice(
                interaction=interaction,
                reading_text=self.ai_reading,
                reader_style=self.reader_style,
                spread_name=self.spread_name,
                preloaded_audio_path=preloaded_path,
            )
            # Sau khi phát xong, file đã được dọn dẹp trong play_tarot_voice
            self.preloaded_audio_path = None
            self.preload_task = None
        finally:
            self.is_speaking = False
            self.voice_button.label = f"🔊 Nghe {self.reader_name} Đọc Lại"
            self.voice_button.disabled = False
            try:
                if self.message:
                    await self.message.edit(view=self)
                else:
                    await interaction.edit_original_response(view=self)
            except Exception:
                pass

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

        # Dọn dẹp file preload nếu người dùng không bấm nghe bài
        try:
            path_to_clean = self.preloaded_audio_path
            if not path_to_clean and self.preload_task and self.preload_task.done():
                path_to_clean = self.preload_task.result()
            if path_to_clean and os.path.exists(path_to_clean):
                os.remove(path_to_clean)
                print(f"🧹 [TarotResultView] Đã dọn dẹp file preload không dùng: {path_to_clean}", flush=True)
        except Exception:
            pass


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
        if reader_style == "random" or not reader_style or reader_style not in READER_STYLES:
            self.reader_style = random.choice(["neutral", "healer", "chaos"])
        else:
            self.reader_style = reader_style
        self.style_info = READER_STYLES.get(self.reader_style, READER_STYLES["neutral"])
        self.ai_task = ai_task
        self.tarot_manager = tarot_manager
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.revealed_indices: Set[int] = set()
        self._has_completed: bool = False
        self.message: Optional[discord.Message] = None

        # Tác vụ Preload âm thanh nền để khi lật xong là có sẵn audio ngay
        self.preload_voice_task: Optional[asyncio.Task] = None
        self._start_voice_preload()

        # Màu embed theo phong cách hoặc Yes/No phán quyết
        self.embed_color = self.style_info.get("color", 0x7851A9)
        if self.spread_key == "yes_no":
            _, _, verdict_color = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
            self.embed_color = verdict_color

        self._build_buttons()

    def _start_voice_preload(self):
        """Khởi chạy preload audio ngay khi AI vừa hoàn tất giải bài (chạy ngầm lúc user lật bài)."""
        async def _worker():
            try:
                ai_reading = await self.ai_task
                if ai_reading and not self._has_completed:
                    self.preload_voice_task = asyncio.create_task(
                        generate_tarot_speech(
                            reading_text=ai_reading,
                            reader_style=self.reader_style,
                            user_name=self.author_name,
                            spread_name=self.spread_info.get("name", "")
                        )
                    )
            except Exception:
                pass

        asyncio.create_task(_worker())

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
                orient = "`[NGƯỢC]`" if drawn.is_reversed else "`[XUÔI]`"
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

            # Kiểm tra xem người bốc bài (author) có đang ở trong Voice Channel không
            author_member = interaction.guild.get_member(self.author_id) if interaction.guild else None
            author_voice = author_member.voice if author_member else getattr(interaction.user, "voice", None)
            voice_channel = author_voice.channel if author_voice else None
            is_in_voice = bool(voice_channel and interaction.guild)

            # Tạo view kết quả có nút Voice Reader (kèm Preloaded Audio Task)
            result_view = TarotResultView(
                ai_reading=ai_reading,
                reader_style=self.reader_style,
                author_id=self.author_id,
                author_name=self.author_name,
                spread_name=self.spread_info.get("name", ""),
                preload_task=self.preload_voice_task,
                is_auto_playing=is_in_voice
            )
            result_view.message = self.message

            # Nếu người bốc bài đang trong Voice -> Tự động kích hoạt flow đọc bài
            if is_in_voice and voice_channel and interaction.guild:
                asyncio.create_task(
                    auto_play_tarot_voice(
                        guild=interaction.guild,
                        voice_channel=voice_channel,
                        reading_text=ai_reading,
                        reader_style=self.reader_style,
                        user_name=self.author_name,
                        spread_name=self.spread_info.get("name", ""),
                        preload_task=self.preload_voice_task,
                        result_view=result_view
                    )
                )

            # Cập nhật kết quả bài giải đầy đủ lên Discord
            try:
                if not sent_image_already:
                    await interaction.edit_original_response(
                        embeds=final_embeds,
                        attachments=[file],
                        view=result_view
                    )
                else:
                    await interaction.edit_original_response(
                        embeds=final_embeds,
                        view=result_view
                    )
            except Exception:
                if self.message:
                    try:
                        if not sent_image_already:
                            await self.message.edit(embeds=final_embeds, attachments=[file], view=result_view)
                        else:
                            await self.message.edit(embeds=final_embeds, view=result_view)
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
                    orient = "`[NGƯỢC]`" if drawn.is_reversed else "`[XUÔI]`"
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
                orient = "`[NGƯỢC]`" if drawn.is_reversed else "`[XUÔI]`"
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

            guild = self.message.guild if self.message else None
            author_member = guild.get_member(self.author_id) if guild else None
            author_voice = author_member.voice if author_member else None
            voice_channel = author_voice.channel if author_voice else None
            is_in_voice = bool(voice_channel and guild)

            result_view = TarotResultView(
                ai_reading=ai_reading,
                reader_style=self.reader_style,
                author_id=self.author_id,
                author_name=self.author_name,
                spread_name=self.spread_info.get("name", ""),
                preload_task=self.preload_voice_task,
                is_auto_playing=is_in_voice
            )
            result_view.message = self.message

            if is_in_voice and voice_channel and guild:
                asyncio.create_task(
                    auto_play_tarot_voice(
                        guild=guild,
                        voice_channel=voice_channel,
                        reading_text=ai_reading,
                        reader_style=self.reader_style,
                        user_name=self.author_name,
                        spread_name=self.spread_info.get("name", ""),
                        preload_task=self.preload_voice_task,
                        result_view=result_view
                    )
                )

            if self.message:
                await self.message.edit(embeds=final_embeds, attachments=[file], view=result_view)
        except Exception as e:
            print(f"[TarotFlipView] Lỗi on_timeout: {e}", flush=True)
