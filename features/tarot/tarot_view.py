import asyncio
import time
import io
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
from features.tarot.ai import generate_tarot_reading, generate_followup_answer
from features.tarot.flavor import detect_spread_flavor
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
            placeholder="Ví dụ: Công việc tháng tới của tôi ra sao? (Chỉ hỏi cho bản thân hoặc mối quan hệ bạn là người trong cuộc)",
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
            "3. Nhấn **🎴 Bắt Đầu Bốc Bài** để trải bài ra kênh chat!",
            "⚠️ *Lưu ý: Tarot chỉ giải quẻ cho chính bạn hoặc mối quan hệ bạn là người trong cuộc cần lời khuyên. Câu hỏi bốc bài thay/soi mói đời tư người thứ ba sẽ bị từ chối.*"
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

        # Lấy ngữ cảnh cũ (Trí nhớ bạn cũ) và danh sách lá bốc gần đây (Card Fatigue)
        recent_ctx = await self.tarot_manager.get_user_recent_context(self.author_id)
        fatigue_card_ids = await self.tarot_manager.get_user_recent_card_ids(self.author_id)

        drawn_cards = draw_spread(
            spread_key=self.selected_spread,
            user_id=self.author_id,
            question=self.question,
            fatigue_card_ids=fatigue_card_ids
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
                user_name=self.author_name,
                recent_context=recent_ctx
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

        sent_msg = None
        # 1. Nếu mở từ Prefix ($m tarot -> self.message tồn tại): Edit trực tiếp vào tin nhắn đó
        if self.message:
            try:
                await self.message.edit(embed=embed, attachments=[file], view=flip_view)
                sent_msg = self.message
            except Exception as e:
                print(f"⚠️ [TarotLauncherView] Không thể edit tin nhắn gốc ({e}), thử gửi mới...", flush=True)
                if interaction.channel:
                    try:
                        sent_msg = await interaction.channel.send(embed=embed, file=file, view=flip_view)
                    except Exception:
                        pass
                if not sent_msg:
                    try:
                        sent_msg = await interaction.followup.send(embed=embed, file=file, view=flip_view)
                    except Exception:
                        pass
        else:
            # 2. Nếu mở từ Slash Command (/tarot -> ephemeral): Gửi quẻ bài ra kênh và xóa sạch bảng ephemeral
            if interaction.channel:
                try:
                    sent_msg = await interaction.channel.send(embed=embed, file=file, view=flip_view)
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"⚠️ [TarotLauncherView] channel.send bị chặn ({e}), fallback sang interaction.followup.send...", flush=True)
                except Exception as e:
                    print(f"⚠️ [TarotLauncherView] Lỗi channel.send: {e}", flush=True)

            if not sent_msg:
                try:
                    sent_msg = await interaction.followup.send(embed=embed, file=file, view=flip_view)
                except Exception as ex:
                    print(f"❌ [TarotLauncherView] Không thể gửi quẻ bài ra kênh: {ex}", flush=True)

            try:
                await interaction.delete_original_response()
            except Exception:
                pass

        if not sent_msg:
            # Nếu cả 2 phương thức đều thất bại do bot thiếu quyền Attach Files / Send Messages
            ai_task.cancel()
            err_text = (
                "⚠️ **Bot không thể gửi quẻ bài ra kênh do thiếu quyền hạn!**\n"
                "Vui lòng đảm bảo Bot có các quyền sau trong kênh chat này:\n"
                "• `Xem kênh (View Channel)`\n"
                "• `Gửi tin nhắn (Send Messages)`\n"
                "• `Đính kèm tệp / ảnh (Attach Files)`\n"
                "• `Nhúng liên kết (Embed Links)`"
            )
            try:
                await interaction.followup.send(err_text, ephemeral=True)
            except Exception:
                pass
            return

        flip_view.message = sent_msg
        self.tarot_manager.record_user_action(self.author_id)

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

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        print(f"❌ [TarotLauncherView] Lỗi tương tác ({type(error).__name__}): {error}", flush=True)
        err_msg = "❌ Đã xảy ra lỗi khi xử lý thao tác bốc bài."
        if isinstance(error, discord.Forbidden):
            err_msg = (
                "⚠️ **Bot thiếu quyền hạn trong kênh này!**\n"
                "Vui lòng đảm bảo Bot có quyền `Send Messages`, `Embed Links` và `Attach Files` trong kênh."
            )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(err_msg, ephemeral=True)
            else:
                await interaction.followup.send(err_msg, ephemeral=True)
        except Exception:
            pass


class TarotFollowupModal(discord.ui.Modal, title="❓ Hỏi Thêm Ý Nghĩa Quẻ Bài"):
    """Modal Discord cho phép người dùng hỏi thêm 1 câu đào sâu về quẻ bài vừa rút."""

    def __init__(
        self,
        author_id: int,
        drawn_cards: List[DrawnCard],
        original_question: Optional[str],
        original_reading: str,
        reader_style: str,
        user_name: str
    ):
        super().__init__()
        self.author_id = author_id
        self.drawn_cards = drawn_cards
        self.original_question = original_question
        self.original_reading = original_reading
        self.reader_style = reader_style
        self.user_name = user_name

        self.followup_input = discord.ui.TextInput(
            label="Điều bạn muốn làm rõ thêm về quẻ bài này",
            style=discord.TextStyle.paragraph,
            placeholder="Ví dụ: Lá bài này có ý nghĩa gì với kế hoạch tháng tới của mình?",
            required=True,
            max_length=250
        )
        self.add_item(self.followup_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        question_text = self.followup_input.value.strip()

        answer = await generate_followup_answer(
            drawn_cards=self.drawn_cards,
            original_question=self.original_question,
            original_reading=self.original_reading,
            user_followup_question=question_text,
            reader_style=self.reader_style,
            user_name=self.user_name
        )

        embed = discord.Embed(
            title=f"❓ GIẢI ĐÁP BỔ SUNG CHO {self.user_name.upper()}",
            description=f"**Thắc mắc:** *\"{question_text}\"*\n\n{answer}",
            color=0x8B5CF6
        )
        embed.set_footer(text="Phản hồi bổ sung từ Tarot Reader", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed)


class TarotResultActionView(discord.ui.View):
    """View tương tác sau khi hoàn tất quẻ bài: Nút Hỏi Thêm AI & Nút Đánh Giá Luận Giải 👍/👎 cộng dồn nhiều người."""

    def __init__(
        self,
        author_id: int,
        author_name: str,
        drawn_cards: List[DrawnCard],
        question: Optional[str],
        ai_reading: str,
        reader_style: str,
        spread_key: str,
        tarot_manager: TarotManager,
        guild_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        timeout: float = 600.0
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.author_name = author_name
        self.drawn_cards = drawn_cards
        self.question = question
        self.ai_reading = ai_reading
        self.reader_style = reader_style
        self.spread_key = spread_key
        self.tarot_manager = tarot_manager
        self.guild_id = guild_id
        self.activity_id = activity_id
        self.has_asked_followup = False
        self.liked_user_ids: set[int] = set()
        self.disliked_user_ids: set[int] = set()

    @discord.ui.button(label="❓ Hỏi Thêm Ý Nghĩa", style=discord.ButtonStyle.primary, custom_id="tarot_followup", row=0)
    async def followup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người bốc quẻ mới có thể hỏi thêm về quẻ bài này!", ephemeral=True)
            return

        if self.has_asked_followup:
            await interaction.response.send_message("⚠️ Bạn đã sử dụng lượt hỏi thêm cho quẻ bài này rồi!", ephemeral=True)
            return

        modal = TarotFollowupModal(
            author_id=self.author_id,
            drawn_cards=self.drawn_cards,
            original_question=self.question,
            original_reading=self.ai_reading,
            reader_style=self.reader_style,
            user_name=self.author_name
        )
        await interaction.response.send_modal(modal)
        self.has_asked_followup = True
        button.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="👍 Hữu ích", style=discord.ButtonStyle.secondary, custom_id="tarot_rate_pos", row=0)
    async def rate_pos_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid in self.liked_user_ids:
            self.liked_user_ids.remove(uid)
            msg = "🔄 Bạn đã bỏ thích quẻ bài này."
        else:
            self.liked_user_ids.add(uid)
            self.disliked_user_ids.discard(uid)
            msg = "💖 Cảm ơn bạn đã đánh giá hữu ích!"
            await self.tarot_manager.save_rating(uid, self.guild_id, self.spread_key, self.reader_style, is_positive=True)

        self._update_rating_button_labels()
        self._sync_activity_logger()

        await interaction.response.send_message(msg, ephemeral=True)
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="👎 Chưa chuẩn", style=discord.ButtonStyle.secondary, custom_id="tarot_rate_neg", row=0)
    async def rate_neg_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid in self.disliked_user_ids:
            self.disliked_user_ids.remove(uid)
            msg = "🔄 Bạn đã bỏ đánh giá chưa chuẩn."
        else:
            self.disliked_user_ids.add(uid)
            self.liked_user_ids.discard(uid)
            msg = "📝 Đã ghi nhận phản hồi của bạn để cải thiện luận giải tốt hơn!"
            await self.tarot_manager.save_rating(uid, self.guild_id, self.spread_key, self.reader_style, is_positive=False)

        self._update_rating_button_labels()
        self._sync_activity_logger()

        await interaction.response.send_message(msg, ephemeral=True)
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    def _update_rating_button_labels(self):
        likes_count = len(self.liked_user_ids)
        dislikes_count = len(self.disliked_user_ids)
        for item in self.children:
            cid = getattr(item, "custom_id", "")
            if cid == "tarot_rate_pos":
                item.label = f"👍 Hữu ích ({likes_count})" if likes_count > 0 else "👍 Hữu ích"
                item.style = discord.ButtonStyle.success if likes_count > 0 else discord.ButtonStyle.secondary
            elif cid == "tarot_rate_neg":
                item.label = f"👎 Chưa chuẩn ({dislikes_count})" if dislikes_count > 0 else "👎 Chưa chuẩn"
                item.style = discord.ButtonStyle.danger if dislikes_count > 0 else discord.ButtonStyle.secondary

    def _sync_activity_logger(self):
        if self.activity_id:
            try:
                from core.activity_logger import activity_logger
                activity_logger.update_activity(self.activity_id, {
                    "details": {
                        "likes": len(self.liked_user_ids),
                        "dislikes": len(self.disliked_user_ids)
                    }
                })
            except Exception as e:
                print(f"⚠️ [TarotResultActionView] Lỗi đồng bộ rating vào ActivityLogger: {e}", flush=True)


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

        # Màu embed theo phong cách hoặc Yes/No phán quyết
        self.embed_color = self.style_info.get("color", 0x7851A9)
        if self.spread_key == "yes_no":
            _, _, verdict_color = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
            self.embed_color = verdict_color

        self.start_time = time.monotonic()
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
            desc_cards.append(f"**🎭 Người trải bài:** {self.style_info['name']}\n")
            if self.spread_key == "yes_no":
                badge, verdict_desc, _ = get_yes_no_verdict(self.drawn_cards[0].card, self.drawn_cards[0].is_reversed)
                desc_cards.append(f"**⚡ Phán Quyết Yes / No:** {badge}\n> *{verdict_desc}*\n")
            desc_cards.append(WIDE_DIVIDER)
            desc_cards.append("**🃏 Các Lá Bài Rút Được:**\n" + "\n".join(cards_summary_lines))

            # Phát hiện Flavor Text / Easter Egg combo hiếm
            flavor_text = detect_spread_flavor(self.drawn_cards)
            if flavor_text:
                desc_cards.append(f"\n{WIDE_DIVIDER}\n{flavor_text}")

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
            ai_res = await self.ai_task
            is_valid_question = True
            if isinstance(ai_res, tuple):
                if len(ai_res) >= 5:
                    ai_reading, topic_tag, mood_tag, summary_headline, is_valid_question = ai_res[0], ai_res[1], ai_res[2], ai_res[3], ai_res[4]
                elif len(ai_res) >= 4:
                    ai_reading, topic_tag, mood_tag, summary_headline = ai_res[0], ai_res[1], ai_res[2], ai_res[3]
                elif len(ai_res) == 2:
                    ai_reading, topic_tag = ai_res[0], ai_res[1]
                    mood_tag, summary_headline = "", ""
                else:
                    ai_reading, topic_tag, mood_tag, summary_headline = ai_res[0], "general", "", ""
            else:
                ai_reading, topic_tag, mood_tag, summary_headline = str(ai_res), "general", "", ""

            # Nếu câu hỏi không hợp lệ (hỏi cho người thứ ba B và C), cập nhật Embed 1 nếu là Yes/No
            if not is_valid_question and self.spread_key == "yes_no":
                if embed_cards.description:
                    lines = embed_cards.description.split("\n")
                    new_lines = []
                    for line in lines:
                        if "**⚡ Phán Quyết Yes / No:**" in line:
                            new_lines.append("**⚡ Phán Quyết Yes / No:** 🚫 **KHÔNG HỢP LỆ (VI PHẠM NGUYÊN TẮC)**")
                        elif line.strip().startswith("> *") and any(w in line for w in ["thành công", "Năng lượng", "tiềm năng", "Rủi ro", "phụ thuộc", "bất lợi", "trở ngại"]):
                            new_lines.append("> *Câu hỏi vi phạm quy tắc đạo đức Tarot: Không thể phán quyết Yes/No cho đời tư người thứ ba khi bạn không phải người nhận lời khuyên!*")
                        else:
                            new_lines.append(line)
                    embed_cards.description = "\n".join(new_lines)

            act_id = None
            # Ghi nhận hoạt động vào Live Activity Logger
            try:
                from core.activity_logger import activity_logger
                elapsed_ms = round((time.monotonic() - getattr(self, 'start_time', time.monotonic())) * 1000, 1)
                cards_summary = ", ".join([f"{c.card.name_vi} ({'[NGƯỢC]' if c.is_reversed else '[XUÔI]'})" for c in self.drawn_cards])
                guild_name_str = interaction.guild.name if interaction.guild else "Direct Message"
                channel_name_str = interaction.channel.name if (interaction.channel and hasattr(interaction.channel, 'name')) else "Direct Message"
                act_entry = activity_logger.log(
                    action_type="tarot",
                    action_name=f"Tarot: {self.spread_info['name']}",
                    user_id=self.author_id,
                    user_name=self.author_name,
                    user_avatar=self.author_avatar_url,
                    guild_name=guild_name_str,
                    guild_id=self.guild_id,
                    channel_name=channel_name_str,
                    channel_id=self.channel_id,
                    prompt=f"Câu hỏi: {self.question or '(Không)'} | Bối cảnh: {self.context or '(Không)'}",
                    response=f"Lá bài: {cards_summary}\n\nThông điệp: {ai_reading}",
                    status="success",
                    duration_ms=elapsed_ms,
                    details={
                        "spread": self.spread_key,
                        "reader": self.reader_style,
                        "topic_tag": topic_tag,
                        "mood_tag": mood_tag,
                        "summary_headline": summary_headline,
                        "cards": [c.card.name_vi for c in self.drawn_cards],
                        "likes": 0,
                        "dislikes": 0
                    }
                )
                if act_entry:
                    act_id = act_entry.get("id")
            except Exception as act_err:
                print(f"⚠️ [ActivityLogger] Lỗi ghi nhận Tarot: {act_err}", flush=True)

            # Lưu vào Database
            if self.spread_key == "daily":
                await self.tarot_manager.record_daily_draw(
                    self.author_id,
                    self.drawn_cards[0],
                    user_name=self.author_name,
                    user_avatar=self.author_avatar_url
                )

            saved_q = f"{self.question} (Bối cảnh: {self.context})" if self.question and self.context else (self.question or (f"Bối cảnh: {self.context}" if self.context else None))
            await self.tarot_manager.save_tarot_history(
                user_id=self.author_id,
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                spread_type=self.spread_key,
                question=saved_q,
                drawn_cards=self.drawn_cards,
                ai_reading=ai_reading,
                topic_tag=topic_tag,
                mood_tag=mood_tag
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

            # View tương tác sau khi hoàn tất quẻ bài (Hỏi thêm AI & Đánh giá)
            action_view = TarotResultActionView(
                author_id=self.author_id,
                author_name=self.author_name,
                drawn_cards=self.drawn_cards,
                question=self.question,
                ai_reading=ai_reading,
                reader_style=self.reader_style,
                spread_key=self.spread_key,
                tarot_manager=self.tarot_manager,
                guild_id=self.guild_id,
                activity_id=act_id
            )

            # Cập nhật kết quả bài giải đầy đủ lên Discord kèm Action View
            try:
                if not sent_image_already:
                    await interaction.edit_original_response(
                        embeds=final_embeds,
                        attachments=[file],
                        view=action_view
                    )
                else:
                    await interaction.edit_original_response(
                        embeds=final_embeds,
                        view=action_view
                    )
            except Exception:
                if self.message:
                    try:
                        if not sent_image_already:
                            await self.message.edit(embeds=final_embeds, attachments=[file], view=action_view)
                        else:
                            await self.message.edit(embeds=final_embeds, view=action_view)
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
                    kw = drawn.card.keywords_reversed if drawn.is_reversed else drawn.card.keywords_upright
                    kw_text = ", ".join(kw[:3]) if kw else ""
                    kw_part = f"\n  ↳ ✨ *Từ khóa:* `{kw_text}`" if kw_text else ""
                    cards_summary_lines.append(
                        f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}{kw_part}"
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

            ai_res = await self.ai_task
            if isinstance(ai_res, tuple):
                if len(ai_res) >= 4:
                    ai_reading, topic_tag, mood_tag, summary_headline = ai_res[0], ai_res[1], ai_res[2], ai_res[3]
                elif len(ai_res) == 2:
                    ai_reading, topic_tag = ai_res[0], ai_res[1]
                    mood_tag, summary_headline = "", ""
                else:
                    ai_reading, topic_tag, mood_tag, summary_headline = ai_res[0], "general", "", ""
            else:
                ai_reading, topic_tag, mood_tag, summary_headline = str(ai_res), "general", "", ""

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
                kw = drawn.card.keywords_reversed if drawn.is_reversed else drawn.card.keywords_upright
                kw_text = ", ".join(kw[:3]) if kw else ""
                kw_part = f"\n  ↳ ✨ *Từ khóa:* `{kw_text}`" if kw_text else ""
                cards_summary_lines.append(
                    f"• **{drawn.position_title}**: **{drawn.card.name_vi}** (*{drawn.card.name_en}*) {orient}{kw_part}"
                )

            # --- EMBED 1: QUẺ RÚT & HÌNH ẢNH TRẢI BÀI ---
            desc_cards = []
            if self.question:
                desc_cards.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")
            if self.context:
                desc_cards.append(f"**📝 Bối cảnh:**\n*{self.context}*\n")
            desc_cards.append(f"**🎭 Người trải bài:** {self.style_info['name']}\n")
            if self.spread_key == "yes_no":
                badge, verdict_desc, _ = get_yes_no_verdict(self.drawn_cards[0].card, self.drawn_cards[0].is_reversed)
                desc_cards.append(f"**⚡ Phán Quyết Yes / No:** {badge}\n> *{verdict_desc}*\n")
            desc_cards.append(WIDE_DIVIDER)
            desc_cards.append("**🃏 Các Lá Bài Rút Được:**\n" + "\n".join(cards_summary_lines))

            flavor_text = detect_spread_flavor(self.drawn_cards)
            if flavor_text:
                desc_cards.append(f"\n{WIDE_DIVIDER}\n{flavor_text}")

            embed_cards = discord.Embed(
                title=f"🔮 TRẢI BÀI TAROT: {self.spread_info['name'].upper()}",
                description="\n".join(desc_cards),
                color=self.embed_color
            )
            embed_cards.set_image(url="attachment://tarot_spread.png")

            act_id = None
            # Ghi nhận hoạt động vào Live Activity Logger
            try:
                from core.activity_logger import activity_logger
                elapsed_ms = round((time.monotonic() - getattr(self, 'start_time', time.monotonic())) * 1000, 1)
                cards_summary = ", ".join([f"{c.card.name_vi} ({'[NGƯỢC]' if c.is_reversed else '[XUÔI]'})" for c in self.drawn_cards])
                guild_name_str = self.message.guild.name if (self.message and self.message.guild) else "Direct Message"
                channel_name_str = self.message.channel.name if (self.message and self.message.channel and hasattr(self.message.channel, 'name')) else "Direct Message"
                act_entry = activity_logger.log(
                    action_type="tarot",
                    action_name=f"Tarot: {self.spread_info['name']}",
                    user_id=self.author_id,
                    user_name=self.author_name,
                    user_avatar=self.author_avatar_url,
                    guild_name=guild_name_str,
                    guild_id=self.guild_id,
                    channel_name=channel_name_str,
                    channel_id=self.channel_id,
                    prompt=f"Câu hỏi: {self.question or '(Không)'} | Bối cảnh: {self.context or '(Không)'}",
                    response=f"Lá bài: {cards_summary}\n\nThông điệp: {ai_reading}",
                    status="success",
                    duration_ms=elapsed_ms,
                    details={
                        "spread": self.spread_key,
                        "reader": self.reader_style,
                        "topic_tag": topic_tag,
                        "mood_tag": mood_tag,
                        "summary_headline": summary_headline,
                        "cards": [c.card.name_vi for c in self.drawn_cards],
                        "likes": 0,
                        "dislikes": 0
                    }
                )
                if act_entry:
                    act_id = act_entry.get("id")
            except Exception as act_err:
                print(f"⚠️ [ActivityLogger] Lỗi ghi nhận Tarot (timeout): {act_err}", flush=True)

            # Lưu vào Database
            if self.spread_key == "daily":
                await self.tarot_manager.record_daily_draw(
                    self.author_id,
                    self.drawn_cards[0],
                    user_name=self.author_name,
                    user_avatar=self.author_avatar_url
                )

            saved_q = f"{self.question} (Bối cảnh: {self.context})" if self.question and self.context else (self.question or (f"Bối cảnh: {self.context}" if self.context else None))
            await self.tarot_manager.save_tarot_history(
                user_id=self.author_id,
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                spread_type=self.spread_key,
                question=saved_q,
                drawn_cards=self.drawn_cards,
                ai_reading=ai_reading,
                topic_tag=topic_tag,
                mood_tag=mood_tag
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

            action_view = TarotResultActionView(
                author_id=self.author_id,
                author_name=self.author_name,
                drawn_cards=self.drawn_cards,
                question=self.question,
                ai_reading=ai_reading,
                reader_style=self.reader_style,
                spread_key=self.spread_key,
                tarot_manager=self.tarot_manager,
                guild_id=self.guild_id,
                activity_id=act_id
            )

            if self.message:
                await self.message.edit(embeds=final_embeds, attachments=[file], view=action_view)
        except Exception as e:
            print(f"[TarotFlipView] Lỗi on_timeout: {e}", flush=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        print(f"❌ [TarotFlipView] Lỗi tương tác ({type(error).__name__}): {error}", flush=True)
        err_msg = "❌ Đã xảy ra lỗi khi lật mở lá bài."
        if isinstance(error, discord.Forbidden):
            err_msg = (
                "⚠️ **Bot thiếu quyền chỉnh sửa hoặc gửi hình ảnh trong kênh này!**\n"
                "Vui lòng đảm bảo Bot có quyền `Send Messages`, `Embed Links` và `Attach Files`."
            )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(err_msg, ephemeral=True)
            else:
                await interaction.followup.send(err_msg, ephemeral=True)
        except Exception:
            pass
