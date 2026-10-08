"""Private Discord ticket history, revision and soft-delete interfaces.

All surfaces are ephemeral and owner-gated; no ticket content from other
Discord users can be accessed with these UI components.
"""
from __future__ import annotations

import discord

from core.version import CURRENT_VERSION
from features.feedback.store import FeedbackStorageError, feedback_store

PAGE_SIZE = 8

STATUS_VI = {
    "submitted": "Chờ xem xét", "triage": "Đang phân loại",
    "needs_info": "Cần bổ sung", "approved": "Đã duyệt",
    "rejected": "Không duyệt", "duplicate": "Trùng",
    "deferred": "Tạm hoãn", "planned": "Đã lên kế hoạch",
    "in_progress": "Đang sửa", "in_review": "Đang review",
    "deployed": "Đã triển khai", "verified": "Đã xác minh sửa xong",
    "closed": "Đã đóng", "reopened": "Mở lại", "deleted": "Đã xóa",
}


EDITABLE = set(STATUS_VI) - {"deleted"}

def safe(value: str, limit: int = 1300) -> str:
    return discord.utils.escape_mentions(str(value or ""))[:limit]


class OwnerView(discord.ui.View):
    def __init__(self, *, owner_id: int, guild_id: int):
        super().__init__(timeout=280)
        self.owner_id = owner_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (interaction.user.id != self.owner_id or interaction.guild is None
                or interaction.guild.id != self.guild_id):
            await interaction.response.send_message(
                "Chỉ người gửi ticket trong server này mới được thao tác.", ephemeral=True
            )
            return False
        return True


class TicketSelection(discord.ui.Select):
    def __init__(self, parent: "MyFeedbackView", tickets: list[dict]):
        options = [
            discord.SelectOption(
                label=f"#{t['number']} · {safe(t['title'], 67)}"[:100],
                value=t["id"],
                description=f"{STATUS_VI.get(t['status'], t['status'])} · {t['category']}"[:100],
            )
            for t in tickets
        ]
        super().__init__(placeholder="Chọn ticket để xem chi tiết...", options=options)
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction):
        ticket = next((t for t in self.parent_view.tickets if t["id"] == self.values[0]), None)
        if ticket is None:
            await interaction.response.send_message("Không tìm thấy ticket.", ephemeral=True)
            return
        view = TicketDetailView(
            owner_id=self.parent_view.owner_id, guild_id=self.parent_view.guild_id,
            ticket=ticket, include_deleted=self.parent_view.include_deleted,
            offset=self.parent_view.offset,
        )
        await interaction.response.edit_message(embed=view.embed(), view=view)


class MyFeedbackView(OwnerView):
    def __init__(self, *, owner_id: int, guild_id: int,
                 tickets: list[dict], offset: int, include_deleted: bool):
        super().__init__(owner_id=owner_id, guild_id=guild_id)
        self.tickets = tickets
        self.offset = offset
        self.include_deleted = include_deleted
        if tickets:
            self.add_item(TicketSelection(self, tickets))
        self.prev_page.disabled = offset == 0
        self.next_page.disabled = len(tickets) < PAGE_SIZE
        self.deleted_toggle.label = (
            "Ẩn ticket đã xóa" if include_deleted else "Hiện ticket đã xóa"
        )

    @classmethod
    async def load(cls, *, owner_id: int, guild_id: int,
                   offset: int = 0, include_deleted: bool = False):
        tickets = await feedback_store.own_list(
            reporter_id=owner_id, guild_id=guild_id,
            limit=PAGE_SIZE, offset=offset, include_deleted=include_deleted,
        )
        return cls(owner_id=owner_id, guild_id=guild_id,
                   tickets=tickets, offset=offset,
                   include_deleted=include_deleted)

    def embed(self):
        e = discord.Embed(
            title="📮 Feedback của bạn",
            description="Chỉ bạn thấy danh sách này. Chọn một ticket để xem trạng thái, "
                        "lý do hoặc thao tác sửa/xóa.",
            color=0x688ED4,
        )
        if not self.tickets:
            e.add_field(name="Chưa có ticket", value="Dùng `/feedback report` hoặc tag Asumi để báo lỗi.", inline=False)
        else:
            for t in self.tickets:
                label = STATUS_VI.get(t["status"], t["status"])
                desc = safe(t["title"], 140)
                extra = f" → ticket #{t['replacement_number']}" if t["replacement_number"] else ""
                e.add_field(
                    name=f"#{t['number']}  ·  {label}",
                    value=f"{desc}{extra}",
                    inline=False,
                )
        e.set_footer(text=f"Trang {self.offset // PAGE_SIZE + 1} · Ticket mới nhất ở trên")
        return e

    async def change(self, interaction: discord.Interaction, offset: int, show_deleted: bool):
        try:
            page = await MyFeedbackView.load(
                owner_id=self.owner_id, guild_id=self.guild_id,
                offset=offset, include_deleted=show_deleted,
            )
        except FeedbackStorageError:
            await interaction.response.send_message("Không đọc được Turso, thử lại sau.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=page.embed(), view=page)

    @discord.ui.button(label="Trước", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.change(interaction, max(0, self.offset-PAGE_SIZE), self.include_deleted)

    @discord.ui.button(label="Sau", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.change(interaction, self.offset+PAGE_SIZE, self.include_deleted)

    @discord.ui.button(label="Hiện ticket đã xóa", style=discord.ButtonStyle.secondary, row=1)
    async def deleted_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.change(interaction, 0, not self.include_deleted)


class TicketDetailView(OwnerView):
    def __init__(self, *, owner_id: int, guild_id: int,
                 ticket: dict, offset: int = 0, include_deleted: bool = False):
        super().__init__(owner_id=owner_id, guild_id=guild_id)
        self.ticket = ticket
        self.offset = offset
        self.include_deleted = include_deleted
        self.revise.disabled = ticket["status"] not in EDITABLE
        self.delete.disabled = ticket["status"] == "deleted"

    def embed(self):
        t = self.ticket
        e = discord.Embed(
            title=f"Ticket #{t['number']}",
            description=safe(t["description"], 2200),
            color=0x8B9DBF if t["status"] == "deleted" else 0x6797DF,
        )
        e.add_field(name="Trạng thái", value=STATUS_VI.get(t["status"], t["status"]))
        e.add_field(name="Loại", value=t["category"])
        if t["reason"]:
            e.add_field(name="Lý do / phản hồi từ admin", value=safe(t["reason"], 1000), inline=False)
        if t["explanation"]:
            e.add_field(name="Giải thích đã gửi", value=safe(t["explanation"], 900), inline=False)
        if t["replacement_number"]:
            e.add_field(name="Đã thay thế bằng", value=f"Ticket #{t['replacement_number']}", inline=False)
        if t["status"] in EDITABLE:
            e.set_footer(text="Sửa tạo ticket mới; ticket cũ và quyết định trước đây vẫn được lưu trong lịch sử audit.")
        else:
            e.set_footer(text="Ticket đã xử lý hoặc xóa: lưu lịch sử, không chỉnh sửa trực tiếp.")
        return e

    @discord.ui.button(label="← Danh sách", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            page = await MyFeedbackView.load(
                owner_id=self.owner_id, guild_id=self.guild_id,
                offset=self.offset, include_deleted=self.include_deleted,
            )
        except FeedbackStorageError:
            await interaction.response.send_message("Turso tạm thời không khả dụng.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=page.embed(), view=page)

    @discord.ui.button(label="Sửa → Ticket mới", style=discord.ButtonStyle.primary)
    async def revise(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.ticket["status"] not in EDITABLE:
            await interaction.response.send_message("Ticket này không thể sửa; hãy gửi báo cáo mới.", ephemeral=True)
            return
        await interaction.response.send_modal(ReviseModal(self))

    @discord.ui.button(label="Xóa ticket", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.ticket["status"] == "deleted":
            await interaction.response.send_message("Ticket đã được xóa.", ephemeral=True)
            return
        view = DeleteConfirmView(
            owner_id=self.owner_id, guild_id=self.guild_id,
            ticket=self.ticket,
        )
        await interaction.response.edit_message(embed=view.embed(), view=view)


class ReviseModal(discord.ui.Modal, title="Sửa feedback → tạo ticket mới"):
    description = discord.ui.TextInput(
        label="Mô tả mới", style=discord.TextStyle.paragraph,
        required=True, max_length=3000,
    )
    explanation = discord.ui.TextInput(
        label="Giải thích thêm (tùy chọn)", style=discord.TextStyle.paragraph,
        required=False, max_length=1800,
    )

    def __init__(self, parent: TicketDetailView):
        super().__init__(timeout=300)
        self.parent_view=parent
        self.description.default=parent.ticket["description"][:3000]
        self.explanation.default=(parent.ticket["explanation"] or "")[:1800]

    async def on_submit(self, interaction: discord.Interaction):
        if (interaction.user.id != self.parent_view.owner_id or interaction.guild is None
                or interaction.guild.id != self.parent_view.guild_id):
            await interaction.response.send_message("Bạn không có quyền sửa ticket này.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            new_ticket = await feedback_store.replace_own(
                ticket_id=self.parent_view.ticket["id"],
                reporter_id=interaction.user.id,
                guild_id=interaction.guild.id,
                source_message_id=interaction.id,
                bot_version=CURRENT_VERSION,
                description=str(self.description.value),
                explanation=str(self.explanation.value or ""),
            )
        except FeedbackStorageError as exc:
            await interaction.followup.send(safe(str(exc), 400), ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ Đã tạo **ticket {new_ticket.label}**. "
            f"Ticket #{self.parent_view.ticket['number']} được đánh dấu **đã xóa / thay thế**. "
            "Ảnh cũ được giữ trên ticket mới. Xem trong `/feedback mine`.",
            ephemeral=True,
        )


class DeleteConfirmView(OwnerView):
    def __init__(self, *, owner_id: int, guild_id: int, ticket: dict):
        super().__init__(owner_id=owner_id, guild_id=guild_id)
        self.ticket=ticket

    def embed(self):
        return discord.Embed(
            title=f"Xóa ticket #{self.ticket['number']}?",
            description="Ticket sẽ chuyển thành **Đã xóa** và ẩn khỏi danh sách mặc định. "
                        "Lịch sử và ảnh vẫn được lưu để đối chiếu, không xóa khỏi Turso/R2.",
            color=0xD37B69,
        )

    @discord.ui.button(label="Giữ ticket", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        page = await MyFeedbackView.load(
            owner_id=self.owner_id, guild_id=self.guild_id,
            offset=0, include_deleted=False,
        )
        await interaction.response.edit_message(embed=page.embed(), view=page)

    @discord.ui.button(label="Xác nhận xóa", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            number = await feedback_store.soft_delete_own(
                ticket_id=self.ticket["id"], reporter_id=interaction.user.id,
                guild_id=interaction.guild.id,
            )
            page = await MyFeedbackView.load(
                owner_id=self.owner_id, guild_id=self.guild_id,
                offset=0, include_deleted=False,
            )
        except FeedbackStorageError as exc:
            await interaction.response.send_message(safe(str(exc), 400), ephemeral=True)
            return
        await interaction.response.edit_message(embed=page.embed(), view=page)
        await interaction.followup.send(
            f"Đã đánh dấu ticket **#{number}** là **Đã xóa**. Có thể xem lại bằng nút **Hiện ticket đã xóa**.",
            ephemeral=True,
        )
