import asyncio
import time
import io
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
from features.tarot.ai import generate_tarot_reading, generate_followup_answer, recommend_spread_for_question
from features.tarot.reading.recommendation import find_similar_recent_question
from features.tarot.reading.session import (
    build_ai_ready_status,
    build_micro_reveal,
    build_reveal_progress,
    compact_flip_label,
)
from features.tarot.flavor import detect_spread_flavor
from features.tarot.manager import TarotManager
from core.branding import BOT_BRAND_NAME, runtime_bot_name

WIDE_DIVIDER = "---"


def build_reading_payload(embed_cards, ai_reading, title, footer, avatar_url=None):
    card_text = embed_cards.description or ""
    embed_cards.title = (embed_cards.title or "")[:256]
    embed_cards.description = card_text[:3500]
    title = title[:256]
    footer = footer[:256]
    budget = min(4096, 6000 - len(embed_cards) - len(title) - len(footer))
    notice = "\n\nFull reading: tarot_reading.txt"
    attachment = None
    if len(ai_reading) > budget or len(card_text) > 3500:
        description = ai_reading[:max(0, budget - len(notice))] + notice
        attachment = discord.File(
            io.BytesIO((card_text + "\n\n" + ai_reading).encode("utf-8")),
            filename="tarot_reading.txt"
        )
    else:
        description = ai_reading
    reading = discord.Embed(title=title, description=description, color=embed_cards.color)
    reading.set_footer(text=footer, icon_url=avatar_url)
    return [embed_cards, reading], attachment

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
        label="✨ Tự động",
        value="auto",
        description="Asumi tự bắt nhịp với câu hỏi của bạn"
    ),
    discord.SelectOption(
        label="🌙 Tĩnh",
        description="Điềm đạm, sâu sắc và trực diện",
        value="neutral"
    ),
    discord.SelectOption(
        label="🌸 Dịu",
        description="Ấm áp, tinh tế và nhẹ nhàng",
        value="healer"
    ),
    discord.SelectOption(
        label="🃏 Tinh quái",
        description="Lém lỉnh, vui vẻ và cà khịa đúng lúc",
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
            placeholder="Ví dụ: Công việc tháng tới của tôi ra sao? (Chỉ hỏi cho bản thân)",
            default=(launcher_view.question or "")[:500],
            required=False,
            max_length=500
        )
        self.add_item(self.question_input)

        self.context_input = discord.ui.TextInput(
            label="Bối cảnh thực tế (Không bắt buộc)",
            style=discord.TextStyle.paragraph,
            placeholder="Ví dụ: Đang chuẩn bị chuyển việc hoặc sắp có đợt đánh giá...",
            default=(launcher_view.context or "")[:500],
            required=False,
            max_length=500
        )
        self.add_item(self.context_input)

    async def on_submit(self, interaction: discord.Interaction):
        clean_q = self.question_input.value.strip() if self.question_input.value else None
        clean_ctx = self.context_input.value.strip() if self.context_input.value else None
        previous_question = self.launcher_view.question

        self.launcher_view.question = clean_q if clean_q else None
        self.launcher_view.context = clean_ctx if clean_ctx else None

        if previous_question != self.launcher_view.question and self.launcher_view.selection_source == "recommendation":
            self.launcher_view.selection_source = "default"

        self.launcher_view.refresh_recommendation()
        await self.launcher_view.refresh_similar_question_hint()
        self.launcher_view._build_components()

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
        selected_reader: str = "auto",
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
        self.selected_spread = selected_spread if selected_spread in SPREAD_DEFINITIONS else "daily"
        self.selected_reader = selected_reader if selected_reader in READER_STYLES else "auto"
        self.question = question.strip() if question else None
        self.context = context.strip() if context else None
        self.trigger_message = trigger_message

        # T20.2 launcher state. "default" means the user has not accepted or
        # manually chosen a spread yet; this prevents the old Daily default
        # from looking like a recommendation.
        self.selection_source = "default"
        self.recommended_spread: Optional[str] = None
        self.recommended_name: Optional[str] = None
        self.recommendation_reason: Optional[str] = None
        self.similar_question_hint: Optional[dict] = None
        self.reading_context_mode = "current"

        self._starting = False
        self._pending_ai_task = None
        self._pending_flip = None
        self.message: Optional[discord.Message] = None

        self.refresh_recommendation()
        self._build_components()

    def refresh_recommendation(self) -> None:
        """Refresh the zero-latency spread recommendation from current question/context."""
        if not self.question:
            self.recommended_spread = None
            self.recommended_name = None
            self.recommendation_reason = None
            if self.selection_source == "recommendation":
                self.selection_source = "default"
            return

        query = self.question
        if self.context:
            query = f"{query} {self.context}"
        spread_key, spread_name, reason = recommend_spread_for_question(query)
        new_recommendation = spread_key if spread_key in SPREAD_DEFINITIONS else "ppf"
        if (
            self.selection_source == "recommendation"
            and self.selected_spread != new_recommendation
        ):
            # Question/context changed enough that the previously accepted
            # recommendation is no longer the current recommendation.
            self.selection_source = "default"
        self.recommended_spread = new_recommendation
        self.recommended_name = spread_name
        self.recommendation_reason = reason

    async def refresh_similar_question_hint(self) -> None:
        """Detect a similar recent reading without blocking or forcing the user."""
        self.similar_question_hint = None
        if not self.question:
            self.reading_context_mode = "current"
            return
        try:
            memory_enabled = await self.tarot_manager.is_user_memory_enabled(self.author_id)
            if not memory_enabled:
                self.reading_context_mode = "current"
                return
            history = await self.tarot_manager.get_user_history(self.author_id, limit=5)
        except Exception:
            self.reading_context_mode = "current"
            return
        self.similar_question_hint = find_similar_recent_question(history, self.question)
        if not self.similar_question_hint:
            self.reading_context_mode = "current"

    async def prepare(self) -> "TarotLauncherView":
        """Async preparation hook used before the launcher is first shown."""
        self.refresh_recommendation()
        await self.refresh_similar_question_hint()
        self._build_components()
        return self

    def _can_start(self) -> bool:
        if self.selection_source == "default":
            return False
        spread_info = SPREAD_DEFINITIONS.get(self.selected_spread)
        if not spread_info:
            return False
        if spread_info.get("requires_question", True) and not self.question:
            return False
        return True

    def _use_recommendation(self) -> bool:
        if not self.recommended_spread:
            return False
        self.selected_spread = self.recommended_spread
        self.selection_source = "recommendation"
        return True

    def _check_author(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    def build_launcher_embed(self) -> discord.Embed:
        """Question-first Tarot 2.0 launcher."""
        if self.selected_reader == "random" or self.selected_reader not in READER_STYLES:
            reader_display = "✨ **Tự động**"
            embed_color = 0x7851A9
        else:
            reader_info = READER_STYLES[self.selected_reader]
            reader_display = f"**{reader_info['name']}**"
            embed_color = reader_info.get("color", 0x7851A9)

        lines = []
        if not self.question:
            lines.extend([
                "**Bạn đang muốn hỏi điều gì?**",
                "Nhập câu hỏi trước; Asumi sẽ đề xuất kiểu trải phù hợp để bạn không cần biết tên các spread.",
                "",
                "Nếu chỉ muốn xem năng lượng hôm nay, bạn có thể tự chọn **Daily Card** ở menu bên dưới.",
            ])
        else:
            lines.extend([
                "**❓ Câu hỏi của bạn**",
                f"*{self.question}*",
            ])
            if self.context:
                lines.extend(["", f"**📝 Bối cảnh:** *{self.context}*"])

            if self.recommended_spread:
                canonical_name = SPREAD_DEFINITIONS.get(self.recommended_spread, {}).get(
                    "name", self.recommended_name or self.recommended_spread
                )
                lines.extend([
                    "",
                    f"✨ **Asumi đề xuất: {canonical_name}**",
                    self.recommendation_reason or "Kiểu trải này phù hợp nhất với cách câu hỏi đang được đặt.",
                ])

        lines.append("")
        lines.append(WIDE_DIVIDER)

        if self.selection_source == "default":
            selection_text = "*(Chưa chọn — dùng đề xuất hoặc tự chọn spread bên dưới)*"
        else:
            spread_name = SPREAD_DEFINITIONS.get(self.selected_spread, {}).get(
                "name", self.selected_spread
            )
            source_label = "đề xuất của Asumi" if self.selection_source == "recommendation" else "tự chọn"
            selection_text = f"**{spread_name}** · {source_label}"

        lines.extend([
            f"🃏 **Trải bài sẽ dùng:** {selection_text}",
            f"🎭 **Phong cách Asumi:** {reader_display}",
        ])

        if self.similar_question_hint:
            old_question = str(self.similar_question_hint.get("question") or "").strip()
            created_at = str(self.similar_question_hint.get("created_at") or "").strip()
            score = float(self.similar_question_hint.get("similarity") or 0.0)
            suffix = f" · {created_at}" if created_at else ""
            lines.extend([
                "",
                "↩️ **Có vẻ bạn từng hỏi một câu khá gần đây**",
                f"*{old_question[:220]}*{suffix}",
                (
                    "Mặc định Asumi sẽ xem đây là **tình hình hiện tại** và chỉ dùng quẻ cũ như ngữ cảnh nhẹ. "
                    "Bạn có thể đổi sang **xem như câu hỏi mới** ở menu bên dưới."
                ),
            ])
            if score >= 0.75:
                lines.append("*Độ giống khá cao; nếu vẫn là cùng tình huống, hãy xem quẻ mới như một snapshot mới thay vì một cách reset câu trả lời.*")

        lines.extend([
            "",
            "💡 **Flow mới:** Nhập câu hỏi → dùng đề xuất hoặc tự chọn → bắt đầu trải bài.",
            "Tarot dùng để tự chiêm nghiệm; Asumi không soi bí mật của người ngoài cuộc hay chốt thay quyết định thực tế.",
        ])

        embed = discord.Embed(
            title="🔮 ASUMI TAROT — BẮT ĐẦU TỪ CÂU HỎI",
            description="\n".join(lines),
            color=embed_color,
        )
        embed.set_footer(
            text=f"Quẻ bài của {self.author_name} • {BOT_BRAND_NAME} Tarot",
            icon_url=self.author_avatar_url,
        )
        return embed

    def build_shuffling_embed(self) -> discord.Embed:
        """Short transition state between launcher setup and the face-down reading board."""
        spread_name = SPREAD_DEFINITIONS.get(self.selected_spread, {}).get(
            "name", self.selected_spread
        )
        lines = [
            f"**{spread_name}**",
            "🔀 *Asumi đang xáo bài và khóa thứ tự lá cho phiên này...*",
        ]
        if self.question:
            lines.extend(["", f"**❓ {self.question}**"])
        lines.extend([
            "",
            "✨ *Luận giải bắt đầu chạy nền ngay khi bộ bài được rút, nên bạn có thể lật bài mà không phải chờ AI trước.*",
        ])
        embed = discord.Embed(
            title="🔮 ĐANG CHUẨN BỊ TRẢI BÀI",
            description="\n".join(lines),
            color=READER_STYLES.get(self.selected_reader, READER_STYLES["auto"]).get("color", 0x7851A9),
        )
        embed.set_footer(
            text=f"{self.author_name} • Đang xáo bài",
            icon_url=self.author_avatar_url,
        )
        return embed

    def _build_components(self):
        self.clear_items()

        # Manual spread override remains available, but is visually secondary to question-first.
        spread_select = discord.ui.Select(
            placeholder="🃏 Tự chọn kiểu trải bài...",
            options=[
                discord.SelectOption(
                    label=opt.label,
                    value=opt.value,
                    description=opt.description,
                    default=(
                        self.selection_source != "default"
                        and opt.value == self.selected_spread
                    ),
                )
                for opt in SPREAD_SELECT_OPTIONS
            ],
            row=0,
            custom_id="launcher_spread_select",
        )
        spread_select.callback = self._handle_spread_select
        self.add_item(spread_select)

        reader_select = discord.ui.Select(
            placeholder="🎭 Phong cách Asumi (tuỳ chọn)...",
            options=[
                discord.SelectOption(
                    label=opt.label,
                    value=opt.value,
                    description=opt.description,
                    default=(opt.value == self.selected_reader),
                )
                for opt in READER_SELECT_OPTIONS
            ],
            row=1,
            custom_id="launcher_reader_select",
        )
        reader_select.callback = self._handle_reader_select
        self.add_item(reader_select)

        btn_question = discord.ui.Button(
            label="✏️ Sửa câu hỏi" if self.question else "✏️ Nhập câu hỏi",
            style=discord.ButtonStyle.primary,
            custom_id="launcher_btn_question",
            row=2,
        )
        btn_question.callback = self._handle_question_button
        self.add_item(btn_question)

        if self.recommended_spread:
            recommendation_active = (
                self.selection_source == "recommendation"
                and self.selected_spread == self.recommended_spread
            )
            btn_recommend = discord.ui.Button(
                label="✓ Đang dùng đề xuất" if recommendation_active else "✨ Dùng đề xuất",
                style=discord.ButtonStyle.secondary if recommendation_active else discord.ButtonStyle.primary,
                custom_id="launcher_btn_recommend",
                row=2,
                disabled=recommendation_active,
            )
            btn_recommend.callback = self._handle_recommendation_button
            self.add_item(btn_recommend)

        btn_start = discord.ui.Button(
            label="🎴 Bắt đầu",
            style=discord.ButtonStyle.success,
            custom_id="launcher_btn_start",
            row=2,
            disabled=not self._can_start(),
        )
        btn_start.callback = self._handle_start_button
        self.add_item(btn_start)

        btn_history = discord.ui.Button(
            label="📜 Lịch sử",
            style=discord.ButtonStyle.secondary,
            custom_id="launcher_btn_history",
            row=2,
        )
        btn_history.callback = self._handle_history_button
        self.add_item(btn_history)

        # Discord allows max 5 components per row. When recommendation is present,
        # close moves to its own compact row with same-question controls.
        close_row = 3 if self.recommended_spread else 2
        btn_cancel = discord.ui.Button(
            label="❌ Đóng",
            style=discord.ButtonStyle.danger,
            custom_id="launcher_btn_cancel",
            row=close_row,
        )
        btn_cancel.callback = self._handle_cancel_button
        self.add_item(btn_cancel)

        if self.similar_question_hint:
            context_select = discord.ui.Select(
                placeholder="↩️ Cách dùng quẻ gần đây...",
                options=[
                    discord.SelectOption(
                        label="🔄 Xem tình hình hiện tại",
                        value="current",
                        description="Cho phép Asumi dùng quẻ gần đây như ngữ cảnh nhẹ",
                        default=(self.reading_context_mode == "current"),
                    ),
                    discord.SelectOption(
                        label="🆕 Xem như câu hỏi mới",
                        value="fresh",
                        description="Không đưa ngữ cảnh Tarot cũ vào bài đọc lần này",
                        default=(self.reading_context_mode == "fresh"),
                    ),
                ],
                row=4,
                custom_id="launcher_context_mode_select",
            )
            context_select.callback = self._handle_context_mode_select
            self.add_item(context_select)

    async def _handle_spread_select(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        self.selected_spread = interaction.data["values"][0]
        self.selection_source = "manual"
        self._build_components()
        await interaction.response.edit_message(embed=self.build_launcher_embed(), view=self)

    async def _handle_recommendation_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return
        if not self._use_recommendation():
            await interaction.response.send_message(
                "⚠️ Chưa có đề xuất nào. Hãy nhập câu hỏi trước nhé.",
                ephemeral=True,
            )
            return

        self._build_components()
        await interaction.response.edit_message(embed=self.build_launcher_embed(), view=self)

    async def _handle_context_mode_select(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        value = interaction.data["values"][0]
        self.reading_context_mode = "fresh" if value == "fresh" else "current"
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
        if not self._can_start():
            if spread_info.get("requires_question", True) and not self.question:
                await interaction.response.send_modal(TarotQuestionModal(self))
            else:
                await interaction.response.send_message(
                    "✨ Hãy dùng đề xuất của Asumi hoặc tự chọn một kiểu trải bài trước khi bắt đầu.",
                    ephemeral=True,
                )
            return

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
        if self._starting or self.is_finished():
            if not interaction.response.is_done():
                await interaction.response.defer()
            return
        self._starting = True
        try:
            await self._start_reading(interaction)
        finally:
            if self._pending_ai_task is not None:
                await self.tarot_manager.cancel_ai_task(self._pending_ai_task)
                self._pending_ai_task = None
            if self._pending_flip is not None:
                self._pending_flip.stop()
                self._pending_flip = None
            self._starting = False

    async def _start_reading(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        # T20.3: give the launcher a visible lifecycle transition instead of
        # leaving users on a static setup screen while draw/render work starts.
        try:
            shuffling_embed = self.build_shuffling_embed()
            if self.message:
                await self.message.edit(embed=shuffling_embed, view=None)
            else:
                await interaction.edit_original_response(embed=shuffling_embed, view=None)
        except Exception:
            pass

        # T20.2: when a repeated question is detected, the user can explicitly
        # choose a fresh read that does not inject prior Tarot context.
        recent_ctx = None
        if self.reading_context_mode != "fresh":
            recent_ctx = await self.tarot_manager.get_user_recent_context(self.author_id)
        fatigue_card_ids = await self.tarot_manager.get_user_recent_card_ids(self.author_id)

        drawn_cards = draw_spread(
            spread_key=self.selected_spread,
            user_id=self.author_id,
            question=self.question,
            fatigue_card_ids=fatigue_card_ids
        )
        spread_info = SPREAD_DEFINITIONS[self.selected_spread]

        # Legacy random choice now resolves to Asumi's adaptive mood.
        actual_reader = self.selected_reader
        if actual_reader == "random" or not actual_reader or actual_reader not in READER_STYLES:
            actual_reader = "auto"

        bot_user = interaction.client.user if interaction and interaction.client else None
        ai_task = self.tarot_manager.create_ai_task(
            generate_tarot_reading(
                spread_key=self.selected_spread,
                drawn_cards=drawn_cards,
                question=self.question,
                context=self.context,
                reader_style=actual_reader,
                user_name=self.author_name,
                recent_context=recent_ctx,
                user_id=self.author_id,
                guild=interaction.guild if interaction else None,
                bot_id=bot_user.id if bot_user else None,
                bot_name=runtime_bot_name(bot_user)
            )
        )

        self._pending_ai_task = ai_task
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

        self._pending_flip = flip_view
        image_buffer = await asyncio.to_thread(
            render_spread_to_bytes,
            self.selected_spread,
            drawn_cards,
            set()
        )
        file = discord.File(fp=image_buffer, filename="tarot_spread.png")

        embed = flip_view.build_session_embed()

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

        await flip_view.attach_message(sent_msg)
        self._pending_ai_task = None
        self._pending_flip = None
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
        user_name: str,
        result_view: "TarotResultActionView",
        message: Optional[discord.Message] = None
    ):
        super().__init__()
        self.result_view = result_view
        self.message = message
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
        question_text = self.followup_input.value.strip()
        if interaction.user.id != self.author_id or not question_text:
            await interaction.response.send_message("Invalid followup submission.", ephemeral=True)
            return
        if self.result_view.has_asked_followup or self.result_view.is_finished():
            await interaction.response.send_message("Followup already submitted or expired.", ephemeral=True)
            return
        self.result_view.has_asked_followup = True
        try:
            await interaction.response.defer(ephemeral=False)
        except BaseException:
            self.result_view.has_asked_followup = False
            raise
        self.result_view.followup_button.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self.result_view)
            except Exception:
                pass

        bot_user = interaction.client.user if interaction and interaction.client else None
        answer = await generate_followup_answer(
            drawn_cards=self.drawn_cards,
            original_question=self.original_question,
            original_reading=self.original_reading,
            user_followup_question=question_text,
            reader_style=self.reader_style,
            user_name=self.user_name,
            user_id=interaction.user.id if interaction and interaction.user else None,
            guild=interaction.guild if interaction else None,
            bot_id=bot_user.id if bot_user else None,
            bot_name=runtime_bot_name(bot_user)
        )

        embed = discord.Embed(
            title=f"❓ GIẢI ĐÁP BỔ SUNG CHO {self.user_name.upper()}",
            description=f"**Thắc mắc:** *\"{question_text}\"*\n\n{answer}",
            color=0x8B5CF6
        )
        embed.set_footer(text="Phản hồi thêm từ Asumi", icon_url=interaction.user.display_avatar.url)
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
            user_name=self.author_name,
            result_view=self,
            message=interaction.message
        )
        await interaction.response.send_modal(modal)

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
        reader_style: str = "auto",
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
            self.reader_style = "auto"
        else:
            self.reader_style = reader_style
        self.style_info = READER_STYLES.get(self.reader_style, READER_STYLES["auto"])
        self.ai_task = ai_task
        self.tarot_manager = tarot_manager
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.revealed_indices: Set[int] = set()
        self._last_revealed_indices: Set[int] = set()
        self._has_completed: bool = False
        self._flip_lock = asyncio.Lock()
        self._ai_cancelled = False
        self._ai_ready_callback_attached = False
        self.message: Optional[discord.Message] = None

        # Màu embed theo phong cách hoặc Yes/No phán quyết
        self.embed_color = self.style_info.get("color", 0x7851A9)
        if self.spread_key == "yes_no":
            _, _, verdict_color = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
            self.embed_color = verdict_color

        self.start_time = time.monotonic()
        self._build_buttons()

    async def cancel_ai_task(self) -> None:
        if self._ai_cancelled:
            return
        self._ai_cancelled = True
        await self.tarot_manager.cancel_ai_task(self.ai_task)

    def _is_ai_ready(self) -> bool:
        if not self.ai_task.done() or self.ai_task.cancelled():
            return False
        try:
            return self.ai_task.exception() is None
        except (asyncio.CancelledError, Exception):
            return False

    async def attach_message(self, message: Optional[discord.Message]) -> None:
        """Attach the live Discord message and enable zero-extra-call AI-ready updates."""
        self.message = message
        if not message or self._ai_ready_callback_attached:
            return

        self._ai_ready_callback_attached = True
        if self.ai_task.done():
            await self._refresh_ai_ready_indicator()
            return

        def _done_callback(task: asyncio.Task) -> None:
            if task.cancelled() or self._has_completed or self.is_finished():
                return
            try:
                asyncio.get_running_loop().create_task(self._refresh_ai_ready_indicator())
            except RuntimeError:
                pass

        self.ai_task.add_done_callback(_done_callback)

    async def _refresh_ai_ready_indicator(self) -> None:
        """Refresh only text/view state; preserve the already-rendered attachment."""
        if not self.message or self._has_completed or self.is_finished() or not self._is_ai_ready():
            return
        async with self._flip_lock:
            if not self.message or self._has_completed or self.is_finished():
                return
            try:
                await self.message.edit(
                    embed=self.build_session_embed(),
                    view=self,
                )
            except Exception:
                pass

    def build_session_embed(self, last_revealed_indices: Optional[Set[int]] = None) -> discord.Embed:
        """Build the FACE_DOWN/REVEALING session state for the single live message."""
        last_revealed = (
            set(last_revealed_indices)
            if last_revealed_indices is not None
            else set(self._last_revealed_indices)
        )
        total = len(self.drawn_cards)

        desc_lines = []
        if self.question:
            desc_lines.append(f"**❓ Câu hỏi / Chủ đề:**\n*{self.question}*\n")
        if self.context:
            desc_lines.append(f"**📝 Bối cảnh:**\n*{self.context}*\n")
        desc_lines.append(f"**🎭 Phong cách Asumi:** {self.style_info['name']}")
        desc_lines.append("")
        desc_lines.append(build_reveal_progress(self.revealed_indices, total))
        desc_lines.append(build_ai_ready_status(self._is_ai_ready()))

        if last_revealed:
            if len(last_revealed) <= 3:
                reveal_lines = [
                    build_micro_reveal(self.drawn_cards[idx], idx + 1)
                    for idx in sorted(last_revealed)
                    if 0 <= idx < total
                ]
                if reveal_lines:
                    desc_lines.extend([
                        "",
                        "**✨ Vừa lật**",
                        "\n".join(reveal_lines),
                    ])
            else:
                desc_lines.extend([
                    "",
                    f"✨ **Đã lật {len(last_revealed)} lá cùng lúc.**",
                ])

        desc_lines.extend(["", WIDE_DIVIDER])

        cards_summary_lines = []
        for idx, drawn in enumerate(self.drawn_cards):
            position_label = drawn.position_title
            if position_label.upper().startswith("LÁ ") and ":" in position_label:
                position_label = position_label.split(":", 1)[1].strip()

            if idx in self.revealed_indices:
                orient = "[NGƯỢC]" if drawn.is_reversed else "[XUÔI]"
                cards_summary_lines.append(
                    f"• **{idx + 1}. {position_label}** — **{drawn.card.name_vi}** {orient}"
                )
            else:
                cards_summary_lines.append(
                    f"• **{idx + 1}. {position_label}** — ▫️ *Chưa lật*"
                )

        desc_lines.append("**🃏 Trải bài:**\n" + "\n".join(cards_summary_lines))
        if len(self.revealed_indices) < total:
            desc_lines.append("\n*Chọn số lá bên dưới hoặc dùng **Lật hết**.*")

        state = "CHỜ LẬT" if not self.revealed_indices else "ĐANG LẬT"
        embed = discord.Embed(
            title=f"🔮 {self.spread_info['name'].upper()}",
            description="\n".join(desc_lines),
            color=self.embed_color,
        )
        embed.set_image(url="attachment://tarot_spread.png")
        embed.set_footer(
            text=f"Quẻ bài của {self.author_name} • {state} • {len(self.revealed_indices)}/{total}",
            icon_url=self.author_avatar_url,
        )
        return embed

    def _build_buttons(self):
        """Build compact mobile-friendly reveal controls."""
        self.clear_items()
        card_count = len(self.drawn_cards)

        if card_count == 1:
            is_opened = 0 in self.revealed_indices
            btn = discord.ui.Button(
                label="✓ Đã lật" if is_opened else "🎴 Lật lá",
                style=discord.ButtonStyle.success if is_opened else discord.ButtonStyle.primary,
                custom_id="flip_0",
                disabled=is_opened,
                row=0,
            )
            btn.callback = self._handle_button_click
            self.add_item(btn)
            return

        for idx, _card in enumerate(self.drawn_cards):
            is_opened = idx in self.revealed_indices
            btn = discord.ui.Button(
                label=compact_flip_label(idx, is_opened),
                style=discord.ButtonStyle.secondary if is_opened else discord.ButtonStyle.primary,
                custom_id=f"flip_{idx}",
                disabled=is_opened,
                row=idx // 5,
            )
            btn.callback = self._handle_button_click
            self.add_item(btn)

        all_opened = len(self.revealed_indices) == card_count
        row_for_all = (card_count + 4) // 5
        btn_all = discord.ui.Button(
            label="✓ Đã lật hết" if all_opened else "✨ Lật hết",
            style=discord.ButtonStyle.secondary if all_opened else discord.ButtonStyle.success,
            custom_id="flip_all",
            disabled=all_opened,
            row=min(4, row_for_all),
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

        async with self._flip_lock:
            if self._has_completed or self.is_finished():
                return
            try:
                await self._process_flip(interaction)
            except BaseException:
                if self._has_completed:
                    await self.tarot_manager.cancel_ai_task(self.ai_task)
                    self.stop()
                raise

    async def _process_flip(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id", "")
        newly_revealed: Set[int] = set()

        if custom_id == "flip_all":
            all_indices = set(range(len(self.drawn_cards)))
            newly_revealed = all_indices - self.revealed_indices
            self.revealed_indices = all_indices
        elif custom_id.startswith("flip_"):
            try:
                idx = int(custom_id.split("_")[1])
            except (ValueError, IndexError):
                return
            if not 0 <= idx < len(self.drawn_cards) or idx in self.revealed_indices:
                return
            newly_revealed = {idx}
            self.revealed_indices.add(idx)
        else:
            return

        self._last_revealed_indices = newly_revealed
        is_completed = len(self.revealed_indices) == len(self.drawn_cards)
        if is_completed:
            self._has_completed = True

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
            desc_cards.append(f"**🎭 Phong cách Asumi:** {self.style_info['name']}\n")
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

            # If the user finishes revealing before AI is ready, keep the same
            # session message and show a clear finalizing state.
            if not self.ai_task.done():
                embed_loading = discord.Embed(
                    title="✨ TẤT CẢ LÁ ĐÃ LẬT",
                    description=(
                        f"{build_reveal_progress(self.revealed_indices, len(self.drawn_cards))}\n\n"
                        "Asumi đang hoàn tất việc nối các lá thành một câu chuyện. "
                        "Ảnh trải bài đã được khóa, chỉ còn chờ phần luận giải."
                    ),
                    color=self.embed_color,
                )
                embed_loading.set_footer(
                    text=f"Quẻ bài của {self.author_name} • ĐANG LUẬN GIẢI",
                    icon_url=self.author_avatar_url,
                )

                try:
                    await interaction.edit_original_response(
                        embeds=[embed_cards, embed_loading],
                        attachments=[file],
                        view=None,
                    )
                except Exception:
                    if self.message:
                        try:
                            await self.message.edit(
                                embeds=[embed_cards, embed_loading],
                                attachments=[file],
                                view=None,
                            )
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
            final_embeds, reading_file = build_reading_payload(
                embed_cards, ai_reading,
                self.style_info.get("embed_title", "Tarot"),
                f"Quẻ bài của {self.author_name}", self.author_avatar_url
            )

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

            file.reset()
            attachments = [file] + ([reading_file] if reading_file else [])
            try:
                await interaction.edit_original_response(
                    embeds=final_embeds, attachments=attachments, view=action_view
                )
            except Exception:
                if self.message:
                    for attachment in attachments:
                        attachment.reset()
                    await self.message.edit(
                        embeds=final_embeds, attachments=attachments, view=action_view
                    )
            self.stop()

        else:
            # Still revealing: edit the same session message with progress,
            # micro-reveal and current AI readiness.
            emb = self.build_session_embed(self._last_revealed_indices)

            try:
                await interaction.edit_original_response(
                    embed=emb,
                    attachments=[file],
                    view=self,
                )
            except Exception:
                if self.message:
                    try:
                        await self.message.edit(
                            embed=emb,
                            attachments=[file],
                            view=self,
                        )
                    except Exception as ex:
                        print(f"⚠️ [TarotFlipView] Message edit fallback lỗi: {ex}", flush=True)

    async def on_timeout(self):
        async with self._flip_lock:
            if self._has_completed:
                return
            self._has_completed = True
            try:
                await asyncio.wait_for(self._complete_timeout(), timeout=20.0)
            except Exception as e:
                print(f"[TarotFlipView] Lỗi on_timeout: {e}", flush=True)
            finally:
                await self.cancel_ai_task()
                self.stop()

    async def _complete_timeout(self):
        try:
            self.revealed_indices = set(range(len(self.drawn_cards)))
            self._build_buttons()
            for item in self.children:
                item.disabled = True

            try:
                ai_res = await asyncio.wait_for(asyncio.shield(self.ai_task), timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if self.message:
                    try:
                        await self.message.edit(content="⌛ *Quá lâu không nhận được luận giải từ AI. Quẻ bài của bạn đã được lưu nhưng không hiển thị bài giải đầy đủ.*", view=None)
                    except Exception:
                        pass
                return
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
            desc_cards.append(f"**🎭 Phong cách Asumi:** {self.style_info['name']}\n")
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
            final_embeds, reading_file = build_reading_payload(
                embed_cards, ai_reading,
                self.style_info.get("embed_title", "Tarot"),
                f"Quẻ bài của {self.author_name}", self.author_avatar_url
            )

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
                await self.message.edit(
                    embeds=final_embeds,
                    attachments=[file] + ([reading_file] if reading_file else []),
                    view=action_view
                )
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
