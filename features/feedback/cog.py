"""Discord feedback wizard: clarify → override → preview → durable submit.

T23.1 intentionally does not auto-approve/reject issues or run Codex.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core import constants as policy
from core.version import CURRENT_VERSION
from features.assistant.trigger import has_explicit_mention, strip_bot_mention
from features.feedback.policy import clarification_text, detect_feedback, FeedbackIntent
from features.feedback.evidence import EvidenceError, evidence_store, UploadedEvidence
from features.feedback.store import FeedbackStorageError, feedback_store


@dataclass
class FeedbackDraft:
    reporter_id: int
    guild_id: int
    channel_id: int
    source_message_id: int
    category: str
    description: str
    attachments: list[tuple[Any, int]] = field(default_factory=list)
    explanation: str = ""
    rule: str = "unknown"
    reply_to_id: int | None = None
    reported_bot_message_id: int | None = None
    created: float = field(default_factory=time.monotonic)
    prompt_message_id: int | None = None


def _safe(value: str, limit: int = 1600) -> str:
    return discord.utils.escape_markdown(
        discord.utils.escape_mentions((value or "").strip())
    )[:limit]


class ExplanationModal(discord.ui.Modal, title="Bổ sung thông tin feedback"):
    explanation = discord.ui.TextInput(
        label="Bạn mong muốn Asumi làm gì?",
        style=discord.TextStyle.paragraph,
        placeholder="Mô tả cách thao tác, điều xảy ra và kết quả mong muốn...",
        required=True,
        max_length=1800,
    )

    def __init__(self, parent: "FeedbackView"):
        super().__init__(timeout=300)
        self.parent_view = parent

    async def on_submit(self, interaction: discord.Interaction):
        draft = self.parent_view.draft
        draft.explanation = str(self.explanation.value).strip()
        await interaction.response.send_message(
            "Đã thêm lời giải thích. Bạn có thể gửi ticket dù đây có thể là "
            "cách dùng chưa đúng. Bấm **Vẫn gửi feedback** trên thẻ ban đầu.",
            ephemeral=True,
        )


class ConfirmView(discord.ui.View):
    def __init__(self, owner: "FeedbackCog", draft: FeedbackDraft):
        super().__init__(timeout=policy.ASUMI_FEEDBACK_DRAFT_TTL_SECONDS)
        self.owner, self.draft = owner, draft
        self.busy = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.draft.reporter_id:
            await interaction.response.send_message(
                "Chỉ người gửi mới được xác nhận ticket này.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Gửi ticket", style=discord.ButtonStyle.success)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.busy:
            await interaction.response.send_message("Ticket đang được xử lý.", ephemeral=True)
            return
        self.busy = True
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            ticket = await self.owner.submit_draft(self.draft)
        except (FeedbackStorageError, EvidenceError) as exc:
            self.busy = False
            await interaction.followup.send(f"❌ {_safe(str(exc), 500)}\nBản nháp vẫn còn, bạn có thể thử lại.", ephemeral=True)
            return
        except Exception as exc:
            self.busy = False
            print(f"[Feedback] Submit failed: {type(exc).__name__}", flush=True)
            await interaction.followup.send(
                "❌ Không thể lưu ticket lúc này. Hãy thử lại sau.", ephemeral=True
            )
            return
        self.owner.discard(self.draft)
        self.stop()
        try:
            await interaction.message.edit(content=f"✅ Đã tiếp nhận feedback **{ticket.id}**. Trạng thái: **{ticket.status}**.", view=None)
        except (discord.HTTPException, AttributeError):
            pass
        await interaction.followup.send(
            f"✅ **{ticket.id}** đã được lưu bền vững. Admin sẽ review thủ công. "
            f"Xem trạng thái bằng `/feedback status` với ID này.",
            ephemeral=True,
        )

    @discord.ui.button(label="Chỉnh sửa / giải thích", style=discord.ButtonStyle.secondary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ExplanationModalForPreview(self))

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.owner.discard(self.draft)
        self.stop()
        await interaction.response.edit_message(content="Đã hủy bản nháp feedback.", embed=None, view=None)


class ExplanationModalForPreview(discord.ui.Modal, title="Chỉnh sửa mô tả feedback"):
    description = discord.ui.TextInput(
        label="Mô tả và điều bạn mong muốn",
        style=discord.TextStyle.paragraph,
        required=True, max_length=1800,
    )

    def __init__(self, view: ConfirmView):
        super().__init__(timeout=300)
        self.view = view
        self.description.default = view.draft.explanation or view.draft.description[:1700]

    async def on_submit(self, interaction: discord.Interaction):
        self.view.draft.explanation = str(self.description.value).strip()
        await interaction.response.send_message(
            "Đã cập nhật lời giải thích. Quay lại thẻ xác nhận để gửi ticket.", ephemeral=True
        )


class FeedbackView(discord.ui.View):
    def __init__(self, owner: "FeedbackCog", draft: FeedbackDraft):
        super().__init__(timeout=policy.ASUMI_FEEDBACK_DRAFT_TTL_SECONDS)
        self.owner, self.draft = owner, draft

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.draft.reporter_id:
            await interaction.response.send_message(
                "Chỉ người gửi feedback được thao tác các nút này.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Đã hiểu, bỏ qua", style=discord.ButtonStyle.secondary)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.owner.discard(self.draft)
        self.stop()
        await interaction.response.edit_message(content="Đã hủy feedback, không tạo ticket.", embed=None, view=None)

    @discord.ui.button(label="Giải thích thêm", style=discord.ButtonStyle.primary)
    async def explain(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ExplanationModal(self))

    @discord.ui.button(label="Vẫn gửi feedback", style=discord.ButtonStyle.success)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = self.draft
        preview = discord.Embed(
            title="📋 Xác nhận gửi feedback",
            description=(
                f"**Loại:** {_safe(draft.category, 30)}\n"
                f"**Asumi:** {CURRENT_VERSION}\n"
                f"**Mô tả:** {_safe(draft.description, 1200)}\n"
                f"**Giải thích:** {_safe(draft.explanation or '(Chưa bổ sung)', 1100)}\n"
                f"**Ảnh đính kèm:** {len(draft.attachments)}\n"
                "Ticket sẽ được review thủ công; Asumi không tự bác bỏ."
            ),
            color=0x648CB0,
        )
        if draft.attachments:
            original, _ = draft.attachments[0]
            if getattr(original, "url", None):
                preview.set_image(url=original.url)
        self.stop()
        await interaction.response.edit_message(content=None, embed=preview, view=ConfirmView(self.owner, draft))


class FeedbackCog(commands.Cog):
    feedback = app_commands.Group(name="feedback", description="Báo lỗi hoặc theo dõi feedback Asumi")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.drafts: dict[tuple[int, int], FeedbackDraft] = {}

    async def cog_load(self):
        ready = await feedback_store.init()
        print(f"[Feedback] Turso ticket schema ready={ready}", flush=True)

    def _key(self, guild_id: int, user_id: int) -> tuple[int, int]:
        return (int(guild_id), int(user_id))

    def discard(self, draft: FeedbackDraft):
        key = self._key(draft.guild_id, draft.reporter_id)
        if self.drafts.get(key) is draft:
            self.drafts.pop(key, None)

    def _active(self, guild_id: int, user_id: int) -> FeedbackDraft | None:
        key = self._key(guild_id, user_id)
        draft = self.drafts.get(key)
        if draft and time.monotonic() - draft.created > policy.ASUMI_FEEDBACK_DRAFT_TTL_SECONDS:
            self.drafts.pop(key, None)
            return None
        return draft

    def _build_draft(
        self, message: discord.Message, intent: FeedbackIntent,
    ) -> FeedbackDraft:
        reference = getattr(message, "reference", None)
        resolved = getattr(reference, "resolved", None)
        referred_bot = resolved if (
            isinstance(resolved, discord.Message)
            and getattr(resolved.author, "id", None) == getattr(self.bot.user, "id", None)
        ) else None
        desc = intent.text.strip()
        explanation, rule = clarification_text(desc, CURRENT_VERSION)
        draft = FeedbackDraft(
            reporter_id=message.author.id,
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            source_message_id=message.id,
            category=intent.category,
            description=desc,
            rule=rule,
            reply_to_id=getattr(reference, "message_id", None),
            reported_bot_message_id=getattr(referred_bot, "id", None),
            attachments=[(a, message.id) for a in list(message.attachments)[:policy.ASUMI_FEEDBACK_MAX_IMAGES]],
        )
        return draft

    def _intro(self, draft: FeedbackDraft) -> str:
        explanation, _ = clarification_text(draft.description, CURRENT_VERSION)
        return (
            "📝 **Asumi Feedback — kiểm tra trước khi gửi**\n"
            + _safe(explanation, 1200) + "\n\n"
            + f"Đã nhận **{len(draft.attachments)} ảnh**. "
            "Nếu Asumi giải thích chưa đúng hoặc bạn vẫn muốn báo lỗi, "
            "hãy chọn **Vẫn gửi feedback**. Admin mới là người xét duyệt."
        )

    async def start_from_message(self, message: discord.Message, intent: FeedbackIntent) -> bool:
        key = self._key(message.guild.id, message.author.id)
        if self._active(*key):
            await message.reply(
                "Bạn đang có bản nháp feedback chưa gửi. Hãy xác nhận/hủy trước khi tạo bản mới.",
                mention_author=False, allowed_mentions=discord.AllowedMentions.none(),
            )
            return True
        if len(message.attachments) > policy.ASUMI_FEEDBACK_MAX_IMAGES:
            await message.reply(
                f"Chỉ nhận tối đa {policy.ASUMI_FEEDBACK_MAX_IMAGES} ảnh cho mỗi ticket.",
                mention_author=False,
            )
            return True
        draft = self._build_draft(message, intent)
        self.drafts[key] = draft
        view = FeedbackView(self, draft)
        result = await message.reply(
            self._intro(draft), view=view, mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        draft.prompt_message_id = result.id
        return True

    async def handle_message(self, message: discord.Message) -> bool:
        if message.guild is None:
            return False
        active = self._active(message.guild.id, message.author.id)
        text = strip_bot_mention(message.content, getattr(self.bot.user, "id", None))
        followup = bool(
            active and message.attachments
            and (getattr(getattr(message, "reference", None), "message_id", None) == active.prompt_message_id
                 or "thêm ảnh feedback" in text.casefold())
        )
        if followup:
            if len(active.attachments) + len(message.attachments) > policy.ASUMI_FEEDBACK_MAX_IMAGES:
                await message.reply("Feedback chỉ nhận tối đa 3 ảnh.", mention_author=False)
                return True
            active.attachments.extend((a, message.id) for a in message.attachments)
            await message.reply(
                f"Đã thêm {len(message.attachments)} ảnh, tổng cộng {len(active.attachments)}. "
                "Quay lại bản nháp và bấm **Vẫn gửi feedback** để tiếp tục.",
                mention_author=False,
            )
            return True

        if not has_explicit_mention(message, getattr(self.bot.user, "id", None)):
            return False
        ref = getattr(getattr(message, "reference", None), "resolved", None)
        replying_to_bot = bool(
            ref and getattr(getattr(ref, "author", None), "id", None) == getattr(self.bot.user, "id", None)
        )
        intent = detect_feedback(text, replying_to_bot=replying_to_bot)
        if not intent:
            return False
        return await self.start_from_message(message, intent)

    async def submit_draft(self, draft: FeedbackDraft):
        if self._active(draft.guild_id, draft.reporter_id) is not draft:
            raise FeedbackStorageError("Bản nháp đã hết hạn. Hãy báo lỗi lại.")
        # Check Turso BEFORE uploading; no irreversible orphan file on known DB outage.
        await feedback_store._require_cloud()
        await feedback_store.init()
        uploaded: list[UploadedEvidence] = []
        try:
            for attachment, message_id in draft.attachments:
                uploaded.append(await evidence_store.put_attachment(
                    attachment, guild_id=draft.guild_id, source_message_id=message_id,
                ))
            ticket = await feedback_store.create(
                guild_id=draft.guild_id, channel_id=draft.channel_id,
                reporter_id=draft.reporter_id, source_message_id=draft.source_message_id,
                bot_version=CURRENT_VERSION, category=draft.category,
                title=draft.description[:110],
                description=draft.description, explanation=draft.explanation,
                design_rule=draft.rule, reply_to_message_id=draft.reply_to_id,
                reported_bot_message_id=draft.reported_bot_message_id,
                evidence=[{
                    "key": x.key, "media_type": x.media_type, "bytes": x.bytes_count,
                    "sha256": x.sha256, "source_message_id": x.source_message_id,
                } for x in uploaded],
            )
            return ticket
        except Exception:
            for item in uploaded:
                await evidence_store.delete(item.key)
            raise

    @feedback.command(name="report", description="Gửi feedback, lỗi hoặc góp ý")
    @app_commands.describe(description="Mô tả lỗi hoặc đề xuất", image="Ảnh chụp màn hình (không bắt buộc)")
    async def report(self, interaction: discord.Interaction, description: str, image: discord.Attachment | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("Chỉ dùng lệnh trong server.", ephemeral=True)
            return
        key = self._key(interaction.guild.id, interaction.user.id)
        if self._active(*key):
            await interaction.response.send_message("Bạn đã có một bản nháp chưa hoàn tất.", ephemeral=True)
            return
        intent = detect_feedback("báo lỗi " + description)
        draft = FeedbackDraft(
            reporter_id=interaction.user.id, guild_id=interaction.guild.id,
            channel_id=interaction.channel_id, source_message_id=interaction.id,
            description=description[:3000], category="bug",
            attachments=[(image, interaction.id)] if image is not None else [],
            rule=clarification_text(description, CURRENT_VERSION)[1],
        )
        self.drafts[key] = draft
        await interaction.response.send_message(
            self._intro(draft), view=FeedbackView(self, draft), ephemeral=True
        )

    @feedback.command(name="status", description="Xem trạng thái ticket feedback của chính bạn")
    @app_commands.describe(ticket_id="Mã ticket, ví dụ FB-000123")
    async def status(self, interaction: discord.Interaction, ticket_id: str):
        try:
            result = await feedback_store.own_ticket(ticket_id, reporter_id=interaction.user.id)
        except FeedbackStorageError:
            await interaction.response.send_message(
                "Chưa thể đọc Turso lúc này, hãy thử lại sau.", ephemeral=True
            )
            return
        if result is None:
            await interaction.response.send_message(
                "Không tìm thấy ticket của bạn với ID này.", ephemeral=True
            )
            return
        reason = f"\n**Lý do:** {_safe(result.reason, 800)}" if result.reason else ""
        await interaction.response.send_message(
            f"**{result.id}** · {_safe(result.title)}\n"
            f"Trạng thái: **{_safe(result.status)}**{reason}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(FeedbackCog(bot))
