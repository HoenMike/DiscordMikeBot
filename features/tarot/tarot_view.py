import asyncio
import time
import io
from typing import List, Optional, Set, Any
import discord

import config
from core import constants as policy
from features.tarot.native_layout import build_full_reading_layout
from features.tarot.deck import (
    DrawnCard,
    get_yes_no_verdict,
    READER_STYLES,
    SPREAD_DEFINITIONS,
    draw_clarifier,
    draw_custom_spread,
    draw_spread
)
from features.tarot.renderer import render_clarifier_board_to_bytes, render_recap_card_to_bytes, render_spread_to_bytes
from features.tarot.ai import generate_clarifier_interpretation, generate_custom_spread_schema, generate_tarot_reading_result, generate_followup_answer, generate_why_explanation, recommend_spread_for_question
from features.tarot.reading.clarifier import resolve_clarifier_suggestions, target_insight
from features.tarot.reading.custom_spread import CustomSpreadSchema
from features.tarot.reading.recommendation import find_similar_recent_question
from features.tarot.reading.recap import build_recap_state
from features.tarot.inline_ui import render_inline_tarot_to_bytes
from features.tarot.reading.schema import TarotReadingResult
from features.tarot.rendering.state import ClarifierBoardState
from features.tarot.reading.followup import TarotSessionState
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


def _unpack_tarot_result(ai_res):
    """Normalize rich V2 and legacy Tarot AI results for existing session code."""
    if isinstance(ai_res, TarotReadingResult):
        return (
            ai_res.full_reading,
            ai_res.topic_tag,
            ai_res.mood_tag,
            ai_res.headline,
            ai_res.is_valid,
            ai_res.key_card.card_id if ai_res.key_card else None,
        )

    if isinstance(ai_res, tuple):
        if len(ai_res) >= 5:
            return ai_res[0], ai_res[1], ai_res[2], ai_res[3], ai_res[4], None
        if len(ai_res) >= 4:
            return ai_res[0], ai_res[1], ai_res[2], ai_res[3], True, None
        if len(ai_res) == 2:
            return ai_res[0], ai_res[1], "", "", True, None
        if ai_res:
            return ai_res[0], "general", "", "", True, None

    return str(ai_res), "general", "", "", True, None


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
        previous_context = self.launcher_view.context

        self.launcher_view.question = clean_q if clean_q else None
        self.launcher_view.context = clean_ctx if clean_ctx else None

        if (
            previous_question != self.launcher_view.question
            or previous_context != self.launcher_view.context
        ):
            if self.launcher_view.selection_source in {"recommendation", "custom"}:
                self.launcher_view.selection_source = "default"
            self.launcher_view.custom_spread_schema = None
            self.launcher_view.custom_spread_notice = None

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
        self.custom_spread_schema: Optional[CustomSpreadSchema] = None
        self.custom_spread_notice: Optional[str] = None
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
        if self.selection_source == "custom":
            return bool(self.question and self.custom_spread_schema)
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
        self.custom_spread_schema = None
        self.custom_spread_notice = None
        return True

    def _check_author(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    def build_launcher_embed(self) -> discord.Embed:
        """Asumi 3 launcher: question-first by default with a one-tap Daily path."""
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
                "**Bạn muốn xem gì hôm nay?**",
                "• Có câu hỏi → bấm **✏️ Nhập câu hỏi**, Asumi sẽ tự đề xuất kiểu trải phù hợp.",
                "• Chỉ muốn năng lượng hôm nay → bấm **☀️ Daily hôm nay** để vào quẻ ngay.",
                "",
                "Bạn vẫn có thể tự chọn spread ở phần **Tuỳ chọn nâng cao** bên dưới.",
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
            selection_text = (
                "*(Chưa chọn — bấm **Trải theo đề xuất**, tạo spread riêng hoặc tự chọn bên dưới)*"
                if self.question
                else "*(Chưa chọn — nhập câu hỏi, dùng **Daily hôm nay** hoặc mở tuỳ chọn nâng cao)*"
            )
        elif self.selection_source == "custom" and self.custom_spread_schema:
            selection_text = f"**{self.custom_spread_schema.title}** · Smart Custom Spread"
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

        if self.custom_spread_schema and self.selection_source == "custom":
            positions = " · ".join(position.title for position in self.custom_spread_schema.positions)
            lines.extend([
                "",
                f"🧩 **Cấu trúc riêng ({self.custom_spread_schema.card_count} lá):** {positions}",
                f"*{self.custom_spread_schema.reason}*",
            ])
        if self.custom_spread_notice:
            lines.extend(["", f"⚠️ *{self.custom_spread_notice}*"])

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
            (
                "💡 **Flow chính:** Nhập câu hỏi → **✨ Trải theo đề xuất**. "
                "Không cần biết tên spread trước."
                if self.question
                else "💡 **Flow chính:** **✏️ Nhập câu hỏi** hoặc **☀️ Daily hôm nay**."
            ),
            "⚙️ Manual spread và phong cách vẫn có ở phần tuỳ chọn nâng cao.",
            "Tarot dùng để tự chiêm nghiệm; Asumi không soi bí mật của người ngoài cuộc hay chốt thay quyết định thực tế.",
        ])

        embed = discord.Embed(
            title="🔮 ASUMI TAROT — BẮT ĐẦU",
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
        spread_name = (
            self.custom_spread_schema.title
            if self.selection_source == "custom" and self.custom_spread_schema
            else SPREAD_DEFINITIONS.get(self.selected_spread, {}).get("name", self.selected_spread)
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

        # Primary actions come first visually. Manual spread/style are deliberately
        # lower in the launcher so new users do not need to know spread names.
        btn_question = discord.ui.Button(
            label="✏️ Sửa câu hỏi" if self.question else "✏️ Nhập câu hỏi",
            style=discord.ButtonStyle.primary,
            custom_id="launcher_btn_question",
            row=0,
        )
        btn_question.callback = self._handle_question_button
        self.add_item(btn_question)

        if not self.question:
            btn_daily = discord.ui.Button(
                label="☀️ Daily hôm nay",
                style=discord.ButtonStyle.success,
                custom_id="launcher_btn_daily",
                row=0,
            )
            btn_daily.callback = self._handle_daily_button
            self.add_item(btn_daily)

        # A generic Start button is only needed after a manual/custom selection.
        # Recommended readings have their own one-click CTA.
        if self.selection_source in {"manual", "custom"}:
            btn_start = discord.ui.Button(
                label="🎴 Bắt đầu",
                style=discord.ButtonStyle.success,
                custom_id="launcher_btn_start",
                row=0 if not self.question else 1,
                disabled=not self._can_start(),
            )
            btn_start.callback = self._handle_start_button
            self.add_item(btn_start)

        btn_history = discord.ui.Button(
            label="📜 Lịch sử",
            style=discord.ButtonStyle.secondary,
            custom_id="launcher_btn_history",
            row=0,
        )
        btn_history.callback = self._handle_history_button
        self.add_item(btn_history)

        btn_cancel = discord.ui.Button(
            label="❌ Đóng",
            style=discord.ButtonStyle.secondary,
            custom_id="launcher_btn_cancel",
            row=0,
        )
        btn_cancel.callback = self._handle_cancel_button
        self.add_item(btn_cancel)

        if self.question and self.recommended_spread:
            btn_recommend = discord.ui.Button(
                label="✨ Trải theo đề xuất",
                style=discord.ButtonStyle.success,
                custom_id="launcher_btn_recommend",
                row=1,
            )
            btn_recommend.callback = self._handle_recommendation_button
            self.add_item(btn_recommend)

        if self.question:
            btn_custom = discord.ui.Button(
                label="✓ Spread riêng" if self.selection_source == "custom" else "🧩 Tạo spread riêng",
                style=discord.ButtonStyle.secondary if self.selection_source == "custom" else discord.ButtonStyle.primary,
                custom_id="launcher_btn_custom",
                row=1,
                disabled=(self.selection_source == "custom"),
            )
            btn_custom.callback = self._handle_custom_spread_button
            self.add_item(btn_custom)

        spread_select = discord.ui.Select(
            placeholder="⚙️ Tuỳ chọn nâng cao · tự chọn spread...",
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
            row=2 if self.question else 1,
            custom_id="launcher_spread_select",
        )
        spread_select.callback = self._handle_spread_select
        self.add_item(spread_select)

        reader_select = discord.ui.Select(
            placeholder="🎭 Tuỳ chọn · đổi phong cách Asumi...",
            options=[
                discord.SelectOption(
                    label=opt.label,
                    value=opt.value,
                    description=opt.description,
                    default=(opt.value == self.selected_reader),
                )
                for opt in READER_SELECT_OPTIONS
            ],
            row=3 if self.question else 2,
            custom_id="launcher_reader_select",
        )
        reader_select.callback = self._handle_reader_select
        self.add_item(reader_select)

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
        self.custom_spread_schema = None
        self.custom_spread_notice = None
        self._build_components()
        await interaction.response.edit_message(embed=self.build_launcher_embed(), view=self)

    async def _handle_recommendation_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return
        previous_state = (
            self.selected_spread,
            self.selection_source,
            self.custom_spread_schema,
            self.custom_spread_notice,
        )
        if not self._use_recommendation():
            await interaction.response.send_message(
                "⚠️ Chưa có đề xuất nào. Hãy nhập câu hỏi trước nhé.",
                ephemeral=True,
            )
            return

        # One-click happy path: the recommendation is already visible in the
        # launcher. If cooldown/validation blocks the start, restore launcher
        # state so the still-visible controls remain semantically accurate.
        started = await self._handle_start_button(interaction)
        if not started:
            (
                self.selected_spread,
                self.selection_source,
                self.custom_spread_schema,
                self.custom_spread_notice,
            ) = previous_state

    async def _handle_daily_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return

        # Daily is the other primary launcher path. It intentionally bypasses
        # question entry and starts immediately after normal cooldown checks.
        previous_state = (
            self.selected_spread,
            self.selection_source,
            self.custom_spread_schema,
            self.custom_spread_notice,
        )
        self.selected_spread = "daily"
        self.selection_source = "manual"
        self.custom_spread_schema = None
        self.custom_spread_notice = None
        started = await self._handle_start_button(interaction)
        if not started:
            (
                self.selected_spread,
                self.selection_source,
                self.custom_spread_schema,
                self.custom_spread_notice,
            ) = previous_state

    async def _handle_custom_spread_button(self, interaction: discord.Interaction):
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return
        if not self.question:
            await interaction.response.send_message("✏️ Hãy nhập câu hỏi trước khi tạo spread riêng.", ephemeral=True)
            return

        await interaction.response.defer()
        bot_user = interaction.client.user if interaction and interaction.client else None
        schema = await generate_custom_spread_schema(
            question=self.question,
            context=self.context,
            user_name=self.author_name,
            user_id=self.author_id,
            guild=interaction.guild if interaction else None,
            bot_id=bot_user.id if bot_user else None,
            bot_name=runtime_bot_name(bot_user),
        )

        if schema:
            self.custom_spread_schema = schema
            self.custom_spread_notice = None
            self.selected_spread = "custom"
            self.selection_source = "custom"
        else:
            self.custom_spread_schema = None
            fallback = self.recommended_spread if self.recommended_spread in SPREAD_DEFINITIONS else "ppf"
            self.selected_spread = fallback
            self.selection_source = "recommendation"
            self.custom_spread_notice = (
                "Asumi chưa tạo được cấu trúc riêng hợp lệ, nên đã fallback sang spread chuẩn phù hợp nhất."
            )

        self._build_components()
        await interaction.edit_original_response(embed=self.build_launcher_embed(), view=self)

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

    async def _handle_start_button(self, interaction: discord.Interaction) -> bool:
        if not self._check_author(interaction):
            await interaction.response.send_message("🔒 Chỉ người mở menu mới có thể tương tác!", ephemeral=True)
            return False

        spread_info = (
            self.custom_spread_schema.as_spread_info()
            if self.selection_source == "custom" and self.custom_spread_schema
            else SPREAD_DEFINITIONS.get(self.selected_spread, SPREAD_DEFINITIONS["daily"])
        )
        if not self._can_start():
            if spread_info.get("requires_question", True) and not self.question:
                await interaction.response.send_modal(TarotQuestionModal(self))
            else:
                await interaction.response.send_message(
                    "✨ Hãy bấm **Trải theo đề xuất**, tạo spread riêng hoặc tự chọn một spread trước khi bắt đầu.",
                    ephemeral=True,
                )
            return False

        # Kiểm tra câu hỏi nếu trải bài yêu cầu
        if spread_info.get("requires_question", True) and not self.question:
            await interaction.response.send_modal(TarotQuestionModal(self))
            return False

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
                    "💡 *Nếu bạn có câu hỏi khác, hãy bấm **Nhập câu hỏi** để Asumi tự gợi ý spread phù hợp.*",
                    ephemeral=True
                )
                return False

        # Kiểm tra Cooldown 1 phút chống spam giữa 2 lần bốc bài
        can_proceed, wait_sec = self.tarot_manager.check_user_cooldown(interaction.user.id, cooldown_seconds=config.COMMAND_COOLDOWN_SECONDS)
        if not can_proceed:
            await interaction.response.send_message(
                f"⏳ **Bạn đang thao tác quá nhanh!** Vui lòng đợi `{int(wait_sec) + 1}s` nữa trước khi bốc quẻ tiếp theo.",
                ephemeral=True
            )
            return False

        # Khởi chạy phiên bốc bài
        await self.start_reading(interaction)
        return True

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

        if self.selection_source == "custom" and self.custom_spread_schema:
            spread_info = self.custom_spread_schema.as_spread_info()
            drawn_cards = draw_custom_spread(
                positions=[
                    (position.title, position.description)
                    for position in self.custom_spread_schema.positions
                ],
                user_id=self.author_id,
                question=self.question,
                schema_title=self.custom_spread_schema.title,
                fatigue_card_ids=fatigue_card_ids,
            )
        else:
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
            generate_tarot_reading_result(
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
                bot_name=runtime_bot_name(bot_user),
                spread_name_override=spread_info["name"] if self.selected_spread == "custom" else None,
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
            set(),
            spread_title=spread_info["name"],
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
            await interaction.response.send_message("⚠️ Câu hỏi bổ sung không hợp lệ hoặc phiên này không thuộc về bạn.", ephemeral=True)
            return
        if self.result_view._followup_in_progress:
            await interaction.response.send_message("⌛ Asumi đang trả lời câu hỏi trước đó.", ephemeral=True)
            return
        if not self.result_view.session_state.can_followup() or self.result_view.is_finished():
            await interaction.response.send_message("Phiên đọc đã hết lượt hỏi thêm hoặc đã hết hạn.", ephemeral=True)
            return

        self.result_view._followup_in_progress = True
        try:
            await interaction.response.defer(ephemeral=False)
        except BaseException:
            self.result_view._followup_in_progress = False
            raise

        bot_user = interaction.client.user if interaction and interaction.client else None
        try:
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
                bot_name=runtime_bot_name(bot_user),
                original_context=self.result_view.context,
                prior_followups=self.result_view.session_state.prompt_history(),
                clarifier_context=self.result_view.session_state.clarifier_summary,
            )
        except BaseException:
            self.result_view._followup_in_progress = False
            raise

        embed = discord.Embed(
            title=f"❓ GIẢI ĐÁP BỔ SUNG CHO {self.user_name.upper()}",
            description=f"**Thắc mắc:** *\"{question_text}\"*\n\n{answer}",
            color=0x8B5CF6
        )
        next_turn = len(self.result_view.session_state.followups) + 1
        embed.set_footer(
            text=f"Phản hồi thêm từ Asumi • {next_turn}/{self.result_view.session_state.max_followups}",
            icon_url=interaction.user.display_avatar.url,
        )
        try:
            await interaction.followup.send(embed=embed)
        except BaseException:
            self.result_view._followup_in_progress = False
            raise

        self.result_view.session_state.record_followup(question_text, answer)
        self.result_view._followup_in_progress = False
        self.result_view._refresh_session_controls()
        if self.message:
            try:
                await self.message.edit(view=self.result_view)
            except Exception:
                pass
        self.result_view._sync_activity_logger()


class TarotClarifierTargetView(discord.ui.View):
    """Ephemeral owner-only picker for the one allowed clarifier target."""

    def __init__(
        self,
        result_view: "TarotResultActionView",
        origin_message: Optional[discord.Message],
        timeout: float = 120.0,
    ):
        super().__init__(timeout=timeout)
        self.result_view = result_view
        self.origin_message = origin_message

        suggestions = resolve_clarifier_suggestions(
            result_view.reading_result,
            result_view.drawn_cards,
        )
        suggested_order = list(suggestions.keys())
        remaining = [
            idx for idx in range(len(result_view.drawn_cards))
            if idx not in suggestions
        ]
        ordered_indices = suggested_order + remaining

        options = []
        for idx in ordered_indices:
            drawn = result_view.drawn_cards[idx]
            position = drawn.position_title
            if position.upper().startswith("LÁ ") and ":" in position:
                position = position.split(":", 1)[1].strip()
            prefix = "✨ " if idx in suggestions else ""
            label = f"{prefix}{idx + 1}. {position}"[:100]
            if idx in suggestions and suggestions[idx]:
                description = f"Asumi gợi ý: {suggestions[idx]}"[:100]
            else:
                orient = "Ngược" if drawn.is_reversed else "Xuôi"
                description = f"{drawn.card.name_vi} · {orient}"[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(idx),
                    description=description,
                )
            )

        self.target_select = discord.ui.Select(
            placeholder="Chọn vị trí muốn làm rõ...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="tarot_clarifier_target",
        )
        self.target_select.callback = self._handle_target
        self.add_item(self.target_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.result_view.author_id:
            return True
        await interaction.response.send_message(
            "🔒 Chỉ người bốc quẻ mới có thể rút clarifier.",
            ephemeral=True,
        )
        return False

    async def _handle_target(self, interaction: discord.Interaction):
        if self.result_view.has_used_clarifier:
            await interaction.response.send_message(
                "✓ Quẻ này đã dùng clarifier rồi.",
                ephemeral=True,
            )
            return
        if self.result_view._clarifier_in_progress:
            await interaction.response.send_message(
                "⌛ Clarifier đang được xử lý, chờ một chút nhé.",
                ephemeral=True,
            )
            return

        try:
            target_index = int(interaction.data["values"][0])
        except (KeyError, IndexError, TypeError, ValueError):
            await interaction.response.send_message(
                "⚠️ Vị trí làm rõ không hợp lệ.",
                ephemeral=True,
            )
            return

        self.target_select.disabled = True
        await interaction.response.edit_message(
            content="🔀 Asumi đang rút đúng **1 lá clarifier** cho vị trí bạn chọn...",
            view=self,
        )

        success = await self.result_view.run_clarifier(
            interaction=interaction,
            target_index=target_index,
            origin_message=self.origin_message,
        )
        try:
            if success:
                await interaction.edit_original_response(
                    content="✅ Clarifier đã được gửi vào kênh. Quẻ gốc vẫn được giữ nguyên.",
                    view=None,
                )
            else:
                self.target_select.disabled = False
                await interaction.edit_original_response(
                    content="❌ Chưa gửi được clarifier. Lượt clarifier **chưa bị dùng**; bạn có thể thử lại.",
                    view=self,
                )
        except Exception:
            pass


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
        channel_id: Optional[int] = None,
        activity_id: Optional[int] = None,
        context: Optional[str] = None,
        reading_result: Optional[TarotReadingResult] = None,
        clarifier_allowed: bool = True,
        spread_title: Optional[str] = None,
        timeout: float = 600.0
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.author_name = author_name
        self.drawn_cards = drawn_cards
        self.question = question
        self.context = context
        self.ai_reading = ai_reading
        self.reader_style = reader_style
        self.spread_key = spread_key
        self.tarot_manager = tarot_manager
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.activity_id = activity_id
        self.reading_result = reading_result
        self.clarifier_allowed = clarifier_allowed
        self.spread_title = spread_title
        self.session_state = TarotSessionState(max_followups=3, timeout_seconds=float(timeout))
        self.has_asked_followup = False  # compatibility: true only when all 3 turns are consumed
        self.has_used_clarifier = False
        self.has_used_why = False
        self.has_generated_recap = False
        self._followup_in_progress = False
        self._why_in_progress = False
        self._recap_in_progress = False
        self.message: Optional[discord.Message] = None
        self._clarifier_in_progress = False
        self.clarifier_target_index: Optional[int] = None
        self.clarifier_card: Optional[DrawnCard] = None
        self.clarifier_reading: Optional[str] = None
        self.liked_user_ids: set[int] = set()
        self.disliked_user_ids: set[int] = set()

        if not clarifier_allowed or not drawn_cards:
            self.clarifier_button.disabled = True
        if len(drawn_cards) != 1:
            # Multi-card spreads already show the full reading inline.
            self.remove_item(self.full_reading_button)

    @discord.ui.button(label="📖 Đọc đầy đủ", style=discord.ButtonStyle.secondary, custom_id="tarot_read_full", row=2)
    async def full_reading_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Before this UI pilot, the full reading was public in the channel.
        # Allow any viewer of this message to open the same text privately,
        # while owner-only Followup / Why / Clarifier remain restricted.
        reading = self.ai_reading or "Chưa có luận giải."
        description = discord.utils.escape_mentions(reading)
        needs_attachment = len(description) > 3900

        def full_file():
            return discord.File(
                io.BytesIO(description.encode("utf-8")),
                filename="tarot_reading.txt",
            )

        # Native V2 is limited to this read-only detail reply, not the
        # interaction lifecycle for Tarot draw/flip/followup/clarifier.
        if policy.ASUMI_TAROT_READING_NATIVE_V2_ENABLED:
            try:
                kwargs = {
                    "view": build_full_reading_layout(reading, with_attachment=needs_attachment),
                    "ephemeral": True,
                    "allowed_mentions": discord.AllowedMentions.none(),
                }
                if needs_attachment:
                    kwargs["file"] = full_file()
                await interaction.response.send_message(**kwargs)
                return
            except discord.HTTPException as exc:
                if exc.status != 400:
                    raise
                # Discord definitively rejected this payload. Only this
                # failure class is safe to retry as an old-style embed.
                # Make a fresh file object since failed sends may close it.
        if needs_attachment:
            visible = description[:3750].rstrip()
            description = visible + "\n\n*Có bản đầy đủ trong tarot_reading.txt*"
        embed = discord.Embed(
            title="📖 Luận giải Tarot đầy đủ",
            description=description[:4096],
            color=0x6D5D8F,
        )
        embed.set_footer(text="Nội dung thuộc quẻ hiện tại · Không rút lại lá bài")
        kwargs = {
            "embed": embed,
            "ephemeral": True,
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        if needs_attachment:
            kwargs["file"] = full_file()
        await interaction.response.send_message(**kwargs)

    @discord.ui.button(label="❓ Hỏi thêm (0/3)", style=discord.ButtonStyle.primary, custom_id="tarot_followup", row=0)
    async def followup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người bốc quẻ mới có thể hỏi thêm về quẻ bài này!", ephemeral=True)
            return

        if not self.session_state.can_followup():
            await interaction.response.send_message("⚠️ Phiên này đã hết lượt hỏi thêm hoặc đã hết hạn.", ephemeral=True)
            return
        if self._followup_in_progress:
            await interaction.response.send_message("⌛ Asumi đang trả lời câu hỏi trước đó.", ephemeral=True)
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

    @discord.ui.button(label="🔍 Vì sao?", style=discord.ButtonStyle.secondary, custom_id="tarot_why", row=0)
    async def why_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người bốc quẻ mới có thể mở giải thích này.", ephemeral=True)
            return
        if self.has_used_why or self.session_state.why_used:
            await interaction.response.send_message("✓ Asumi đã giải thích bằng chứng chính của quẻ này rồi.", ephemeral=True)
            return
        if self._why_in_progress or self.session_state.is_expired():
            await interaction.response.send_message("⌛ Phiên đọc đã hết hạn hoặc đang được xử lý.", ephemeral=True)
            return

        self._why_in_progress = True
        try:
            await interaction.response.defer(ephemeral=True)
            answer = await generate_why_explanation(
                self.drawn_cards,
                self.question,
                self.ai_reading,
                reader_style=self.reader_style,
                user_name=self.author_name,
            )
            embed = discord.Embed(
                title="🔍 VÌ SAO ASUMI ĐỌC QUẺ THEO HƯỚNG NÀY?",
                description=answer,
                color=0x6D5D8F,
            )
            embed.set_footer(text="Chỉ dựa trên lá, vị trí và chiều bài đang hiển thị — không hiển thị suy luận nội bộ.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.session_state.mark_why_used()
            self.has_used_why = True
            self._refresh_session_controls()
            try:
                if interaction.message:
                    self.message = interaction.message
                    await interaction.message.edit(view=self)
            except Exception:
                pass
            self._sync_activity_logger()
        finally:
            self._why_in_progress = False

    @discord.ui.button(label="🃏 Làm rõ", style=discord.ButtonStyle.secondary, custom_id="tarot_clarifier", row=0)
    async def clarifier_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "🔒 Chỉ người bốc quẻ mới có thể rút clarifier.",
                ephemeral=True,
            )
            return
        if not self.clarifier_allowed:
            await interaction.response.send_message(
                "⚠️ Quẻ này không mở clarifier.",
                ephemeral=True,
            )
            return
        if self.has_used_clarifier:
            await interaction.response.send_message(
                "✓ Quẻ này đã dùng clarifier rồi.",
                ephemeral=True,
            )
            return
        if self._clarifier_in_progress:
            await interaction.response.send_message(
                "⌛ Clarifier đang được xử lý.",
                ephemeral=True,
            )
            return

        picker = TarotClarifierTargetView(
            result_view=self,
            origin_message=interaction.message,
        )
        suggestions = resolve_clarifier_suggestions(self.reading_result, self.drawn_cards)
        hint = (
            "Các vị trí có dấu ✨ là nơi Asumi thấy còn đáng làm rõ nhất."
            if suggestions else
            "Chọn đúng **một vị trí** bạn muốn đào sâu. Quẻ gốc sẽ không bị thay đổi."
        )
        await interaction.response.send_message(
            f"🔎 **Chọn vị trí cho clarifier**\n{hint}\n\n"
            "Mỗi quẻ chỉ có **1 clarifier** để tránh biến nó thành reroll.",
            view=picker,
            ephemeral=True,
        )

    async def run_clarifier(
        self,
        interaction: discord.Interaction,
        target_index: int,
        origin_message: Optional[discord.Message],
    ) -> bool:
        """Draw, interpret and deliver one clarifier. Consume only after delivery."""
        if (
            self.has_used_clarifier
            or self._clarifier_in_progress
            or not self.clarifier_allowed
            or not 0 <= target_index < len(self.drawn_cards)
        ):
            return False

        self._clarifier_in_progress = True
        ai_task = None
        image_buffer = None
        try:
            target = self.drawn_cards[target_index]
            try:
                fatigue_card_ids = await self.tarot_manager.get_user_recent_card_ids(self.author_id)
            except Exception:
                fatigue_card_ids = []

            clarifier = draw_clarifier(
                original_cards=self.drawn_cards,
                target_position_index=target_index,
                user_id=self.author_id,
                question=self.question,
                fatigue_card_ids=fatigue_card_ids,
            )
            existing_insight = target_insight(self.reading_result, target)
            key_card_id = None
            if self.reading_result and self.reading_result.key_card:
                key_card_id = self.reading_result.key_card.card_id or None

            board_state = ClarifierBoardState(
                spread_key=self.spread_key,
                drawn_cards=tuple(self.drawn_cards),
                target_position_index=target_index,
                clarifier_card=clarifier,
                key_card_id=key_card_id,
                spread_title=self.spread_title,
            )

            ai_task = self.tarot_manager.create_ai_task(
                generate_clarifier_interpretation(
                    spread_key=self.spread_key,
                    original_question=self.question,
                    context=self.context,
                    original_reading=self.ai_reading,
                    target_card=target,
                    target_insight=existing_insight,
                    clarifier_card=clarifier,
                    reader_style=self.reader_style,
                    user_name=self.author_name,
                )
            )
            render_task = asyncio.to_thread(render_clarifier_board_to_bytes, board_state)
            clarifier_result, image_buffer = await asyncio.gather(ai_task, render_task)

            target_position = target.position_title
            if target_position.upper().startswith("LÁ ") and ":" in target_position:
                target_position = target_position.split(":", 1)[1].strip()

            target_orient = "NGƯỢC" if target.is_reversed else "XUÔI"
            clarifier_orient = "NGƯỢC" if clarifier.is_reversed else "XUÔI"
            embed = discord.Embed(
                title="🔎 TAROT CLARIFIER",
                description=(
                    f"**🎯 Vị trí làm rõ:** {target_index + 1}. {target_position}\n"
                    f"**Lá gốc:** **{target.card.name_vi}** · {target_orient}\n"
                    f"**Lá bổ sung:** **{clarifier.card.name_vi}** (*{clarifier.card.name_en}*) · {clarifier_orient}\n\n"
                    f"{clarifier_result.full_reading}\n\n"
                    "*Clarifier bổ sung ngữ cảnh cho vị trí đã chọn; nó không thay thế hay reroll quẻ gốc.*"
                ),
                color=0x8B5CF6,
            )
            embed.set_image(url="attachment://tarot_clarifier.png")
            embed.set_footer(text=f"Clarifier của {self.author_name} • 1/1")

            file = discord.File(fp=image_buffer, filename="tarot_clarifier.png")
            delivered = False
            try:
                await interaction.followup.send(
                    embed=embed,
                    file=file,
                    ephemeral=False,
                )
                delivered = True
            except Exception:
                # Attachment failure must not mutate the original reading or consume
                # the clarifier. Try a text-only delivery once.
                try:
                    embed.remove_image()
                    await interaction.followup.send(
                        embed=embed,
                        ephemeral=False,
                    )
                    delivered = True
                except Exception:
                    delivered = False

            if not delivered:
                return False

            # Delivery is the commit point. Everything below is best-effort metadata/UI.
            self.has_used_clarifier = True
            self.clarifier_target_index = target_index
            self.clarifier_card = clarifier
            self.clarifier_reading = clarifier_result.full_reading
            self.session_state.set_clarifier(
                f"{target.position_title}: {target.card.name_vi} -> {clarifier.card.name_vi}. "
                f"{clarifier_result.full_reading}"
            )
            self.clarifier_button.disabled = True
            self.clarifier_button.label = "✓ Đã làm rõ"

            try:
                await self.tarot_manager.save_tarot_clarifier(
                    user_id=self.author_id,
                    guild_id=self.guild_id,
                    channel_id=self.channel_id,
                    spread_type=self.spread_key,
                    question=self.question,
                    target_position_index=target_index,
                    target_card=target,
                    clarifier_card=clarifier,
                    interpretation=clarifier_result.full_reading,
                )
            except Exception as exc:
                print(f"⚠️ [TarotClarifier] Không lưu được metadata clarifier: {exc}", flush=True)

            try:
                if origin_message:
                    await origin_message.edit(view=self)
            except Exception:
                pass

            self._sync_activity_logger()
            return True
        except Exception as exc:
            print(f"❌ [TarotClarifier] Lỗi xử lý clarifier: {type(exc).__name__}: {exc}", flush=True)
            if ai_task is not None and not ai_task.done():
                await self.tarot_manager.cancel_ai_task(ai_task)
            return False
        finally:
            self._clarifier_in_progress = False
            try:
                if image_buffer is not None:
                    image_buffer.close()
            except Exception:
                pass

    def _refresh_session_controls(self):
        used = len(self.session_state.followups)
        remaining = self.session_state.remaining_followups
        self.has_asked_followup = remaining <= 0
        self.followup_button.label = f"❓ Hỏi thêm ({used}/{self.session_state.max_followups})"
        self.followup_button.disabled = remaining <= 0 or self.session_state.closed
        if self.has_used_why or self.session_state.why_used:
            self.why_button.label = "✓ Đã giải thích"
            self.why_button.disabled = True

    async def on_timeout(self):
        self.session_state.close()
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="📌 Recap", style=discord.ButtonStyle.secondary, custom_id="tarot_recap", row=1)
    async def recap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "🔒 Chỉ chủ quẻ mới có thể tạo Recap Card.",
                ephemeral=True,
            )
            return
        if self.has_generated_recap:
            await interaction.response.send_message(
                "✓ Recap Card của quẻ này đã được tạo rồi.",
                ephemeral=True,
            )
            return
        if self._recap_in_progress:
            await interaction.response.send_message("⌛ Recap đang được dựng.", ephemeral=True)
            return

        self._recap_in_progress = True
        image_buffer = None
        try:
            await interaction.response.defer(ephemeral=True)
            spread_title = self.spread_title or SPREAD_DEFINITIONS.get(
                self.spread_key, {}
            ).get("name", self.spread_key)
            state = build_recap_state(
                spread_title=spread_title,
                user_name=self.author_name,
                drawn_cards=self.drawn_cards,
                reading_result=self.reading_result,
                ai_reading=self.ai_reading,
            )
            image_buffer = await asyncio.to_thread(render_recap_card_to_bytes, state)
            file = discord.File(fp=image_buffer, filename="tarot_recap.png")
            orientation = "NGƯỢC" if state.hero_card.is_reversed else "XUÔI"
            embed = discord.Embed(
                title="📌 TAROT RECAP",
                description=(
                    "Bản tóm tắt gọn từ **chính quẻ vừa đọc** — không rút thêm lá "
                    "và không gọi AI thêm.\n\n"
                    f"**🃏 Hero:** {state.hero_card.card.name_vi} · {orientation}\n"
                    f"**✨ Headline:** {state.headline}\n"
                    f"**📌 Mang theo:** {state.takeaway}\n"
                    f"**🗂️ Spread:** {state.spread_title} · {state.date_label}"
                ),
                color=0x6D5D8F,
            )
            embed.set_image(url="attachment://tarot_recap.png")
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)

            self.has_generated_recap = True
            self.recap_button.label = "✓ Recap"
            self.recap_button.disabled = True
            if interaction.message:
                self.message = interaction.message
                try:
                    await interaction.message.edit(view=self)
                except Exception:
                    pass
            self._sync_activity_logger()
        except Exception as exc:
            print(f"❌ [TarotRecap] Không tạo/gửi được recap: {type(exc).__name__}: {exc}", flush=True)
            try:
                await interaction.followup.send(
                    "❌ Chưa tạo được Recap Card. Lượt recap **chưa bị khóa**; bạn có thể thử lại.",
                    ephemeral=True,
                )
            except Exception:
                pass
        finally:
            self._recap_in_progress = False
            try:
                if image_buffer is not None:
                    image_buffer.close()
            except Exception:
                pass

    @discord.ui.button(label="👍 Hữu ích", style=discord.ButtonStyle.secondary, custom_id="tarot_rate_pos", row=1)
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

    @discord.ui.button(label="👎 Chưa chuẩn", style=discord.ButtonStyle.secondary, custom_id="tarot_rate_neg", row=1)
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
                details = {
                    "likes": len(self.liked_user_ids),
                    "dislikes": len(self.disliked_user_ids),
                    "clarifier_used": self.has_used_clarifier,
                    "followup_count": len(self.session_state.followups),
                    "why_used": self.has_used_why,
                    "recap_generated": self.has_generated_recap,
                }
                if self.has_used_clarifier and self.clarifier_card is not None:
                    details["clarifier_target_index"] = self.clarifier_target_index
                    details["clarifier_card"] = self.clarifier_card.card.name_vi
                activity_logger.update_activity(self.activity_id, {
                    "details": details
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
        self.spread_title = spread_info.get("name", spread_key)
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

    def build_finalizing_embed(self) -> discord.Embed:
        """Make the waiting state obvious without hiding it below the Reading Board."""
        total = len(self.drawn_cards)
        lines = [
            f"**{self.spread_info['name']}**",
            f"{build_reveal_progress(self.revealed_indices, total)}",
            "",
            "✅ **Phần lật bài đã xong.**",
            "🧠 **Asumi đang viết phần luận giải cuối...**",
        ]

        if total == 1 and self.drawn_cards:
            drawn = self.drawn_cards[0]
            orientation = "NGƯỢC" if drawn.is_reversed else "XUÔI"
            lines.extend([
                f"🃏 **Lá đã mở:** **{drawn.card.name_vi}** (*{drawn.card.name_en}*) · `{orientation}`",
                "",
            ])
        else:
            lines.extend([
                "🃏 Các lá đã được khóa; Asumi đang nối chúng thành phần đọc cuối.",
                "",
            ])

        lines.append("⏳ *Không cần bấm gì thêm — kết quả sẽ tự cập nhật ngay tại tin nhắn này.*")

        embed = discord.Embed(
            title="⏳ ĐANG LUẬN GIẢI — CHƯA XONG",
            description="\n".join(lines),
            color=self.embed_color,
        )
        embed.set_image(url="attachment://tarot_spread.png")
        embed.set_footer(
            text=f"Quẻ bài của {self.author_name} • CHƯA XONG • TỰ CẬP NHẬT",
            icon_url=self.author_avatar_url,
        )
        return embed

    def build_final_payload(
        self,
        embed_cards: discord.Embed,
        ai_reading: str,
        reading_result: Optional[TarotReadingResult] = None,
        *,
        image_filename: str = "tarot_spread.png",
    ):
        """One-card rich UI pilot: answer first, image alongside native actions.

        The full AI reading remains available via the owner's button. Large
        spreads keep their established image and two-embed reading workflow.
        """
        if len(self.drawn_cards) != 1:
            return build_reading_payload(
                embed_cards,
                ai_reading,
                self.style_info.get("embed_title", "Tarot"),
                f"Quẻ bài của {self.author_name}",
                self.author_avatar_url,
            )

        drawn = self.drawn_cards[0]
        orientation = "NGƯỢC" if drawn.is_reversed else "XUÔI"
        position_label = drawn.position_title
        if position_label.upper().startswith("LÁ ") and ":" in position_label:
            position_label = position_label.split(":", 1)[1].strip()

        safe = discord.utils.escape_mentions
        lines = ["✅ **HOÀN TẤT**"]
        if self.question:
            lines.append(f"**Bạn hỏi:** {safe(self.question[:220])}")
        lines.append(
            f"**Lá bài:** {safe(drawn.card.name_vi)} "
            f"(*{safe(drawn.card.name_en)}*) · {orientation}"
        )

        is_valid = reading_result is None or reading_result.is_valid
        if self.spread_key == "yes_no" and is_valid:
            badge, verdict_desc, _ = get_yes_no_verdict(
                drawn.card, drawn.is_reversed
            )
            lines.append(f"**Phán quyết:** {badge}")
            lines.append(f"*{safe(verdict_desc[:220])}*")

        if reading_result and not reading_result.is_valid:
            insight = reading_result.refusal_message or ai_reading
            takeaway = ""
        elif reading_result:
            insight = (
                reading_result.core_message
                or reading_result.dominant_theme
                or ai_reading
            )
            takeaway = (
                reading_result.practical_takeaway[0]
                if reading_result.practical_takeaway else ""
            )
        else:
            insight = ai_reading
            takeaway = ""

        lines.append(f"\n**Thông điệp chính**\n{safe(insight[:800])}")
        if takeaway:
            lines.append(f"\n**Bạn có thể thử**\n{safe(takeaway[:330])}")
        lines.append("\n*Bấm **📖 Đọc đầy đủ** hoặc mở tệp `tarot_reading.txt` bất cứ lúc nào.*")

        reading = discord.Embed(
            title=self.style_info.get("embed_title", "Asumi Tarot")[:256],
            description="\n".join(lines)[:4096],
            color=self.embed_color,
        )
        reading.set_image(url=f"attachment://{image_filename}")
        reading.set_footer(
            text=f"Quẻ bài của {self.author_name} · HOÀN TẤT · UI thử nghiệm",
            icon_url=self.author_avatar_url,
        )
        # Keep the full interpretation durable for anyone with access to the
        # original message, even after the Discord View's 10-minute timeout.
        # It was previously public in the old multi-paragraph embed.
        full_reading_file = discord.File(
            io.BytesIO((ai_reading or "").encode("utf-8")),
            filename="tarot_reading.txt",
        )
        return [reading], full_reading_file

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
            self.revealed_indices,
            just_revealed_indices=(newly_revealed if len(newly_revealed) <= 3 else set()),
            final=is_completed,
            spread_title=self.spread_title,
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

            # If the user finishes revealing before AI is ready, put the
            # processing state ABOVE the board instead of hiding it in a second
            # embed below a tall image.
            if not self.ai_task.done():
                embed_loading = self.build_finalizing_embed()

                try:
                    await interaction.edit_original_response(
                        embed=embed_loading,
                        attachments=[file],
                        view=None,
                    )
                except Exception:
                    if self.message:
                        try:
                            await self.message.edit(
                                embed=embed_loading,
                                attachments=[file],
                                view=None,
                            )
                        except Exception:
                            pass

            # Await bài luận giải thông điệp
            ai_res = await self.ai_task
            reading_result = ai_res if isinstance(ai_res, TarotReadingResult) else None
            (
                ai_reading,
                topic_tag,
                mood_tag,
                summary_headline,
                is_valid_question,
                key_card_id,
            ) = _unpack_tarot_result(ai_res)

            # Re-render the locked final board with the AI-selected key-card emphasis.
            try:
                file.close()
            except Exception:
                pass
            final_image_buffer = await asyncio.to_thread(
                render_spread_to_bytes,
                self.spread_key,
                self.drawn_cards,
                self.revealed_indices,
                key_card_id=key_card_id,
                final=True,
                spread_title=self.spread_title,
            )
            file = discord.File(fp=final_image_buffer, filename="tarot_spread.png")

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

            # The one-card pilot replaces the tall spread image with a compact
            # visual reading. Multi-card boards retain their original layout.
            image_filename = "tarot_spread.png"
            if len(self.drawn_cards) == 1 and is_valid_question:
                try:
                    glance_state = build_recap_state(
                        spread_title=self.spread_title,
                        user_name=self.author_name,
                        drawn_cards=self.drawn_cards,
                        reading_result=reading_result,
                        ai_reading=ai_reading,
                    )
                    glance_buffer = await asyncio.to_thread(
                        render_inline_tarot_to_bytes, glance_state,
                    )
                    old_file = file
                    file = discord.File(
                        fp=glance_buffer, filename="tarot_inline.png"
                    )
                    image_filename = "tarot_inline.png"
                    old_file.close()
                except Exception as exc:
                    print(
                        f"[Tarot Inline UI] Falling back to original board: "
                        f"{type(exc).__name__}", flush=True,
                    )

            final_embeds, reading_file = self.build_final_payload(
                embed_cards,
                ai_reading,
                reading_result=reading_result,
                image_filename=image_filename,
            )

            # View tương tác sau khi hoàn tất quẻ bài (Hỏi thêm AI & Đánh giá)
            action_view = TarotResultActionView(
                author_id=self.author_id,
                author_name=self.author_name,
                drawn_cards=self.drawn_cards,
                question=self.question,
                context=self.context,
                ai_reading=ai_reading,
                reader_style=self.reader_style,
                spread_key=self.spread_key,
                tarot_manager=self.tarot_manager,
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                activity_id=act_id,
                reading_result=reading_result,
                clarifier_allowed=is_valid_question,
                spread_title=self.spread_title,
            )

            action_view.message = self.message or interaction.message
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
                        await self.message.edit(content="⌛ *Phiên đọc đã hết thời gian chờ AI trước khi có luận giải hoàn chỉnh. Bạn có thể bắt đầu lại khi sẵn sàng.*", view=None)
                    except Exception:
                        pass
                return
            reading_result = ai_res if isinstance(ai_res, TarotReadingResult) else None
            (
                ai_reading,
                topic_tag,
                mood_tag,
                summary_headline,
                _is_valid_question,
                key_card_id,
            ) = _unpack_tarot_result(ai_res)

            image_buffer = await asyncio.to_thread(
                render_spread_to_bytes,
                self.spread_key,
                self.drawn_cards,
                self.revealed_indices,
                key_card_id=key_card_id,
                final=True,
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

            # Final one-card readings are intentionally compact: message first,
            # board second. Multi-card spreads keep the richer two-embed layout.
            final_embeds, reading_file = self.build_final_payload(
                embed_cards,
                ai_reading,
            )

            action_view = TarotResultActionView(
                author_id=self.author_id,
                author_name=self.author_name,
                drawn_cards=self.drawn_cards,
                question=self.question,
                context=self.context,
                ai_reading=ai_reading,
                reader_style=self.reader_style,
                spread_key=self.spread_key,
                tarot_manager=self.tarot_manager,
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                activity_id=act_id,
                reading_result=reading_result,
                clarifier_allowed=_is_valid_question,
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
