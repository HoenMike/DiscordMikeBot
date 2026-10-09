"""Discord-only pages for full Tarot reading, without txt attachments.

A read-only ephemeral view: no redraw, AI request, or mutations to the source
reading. The public Discord message retains the original summary/board.
"""
from __future__ import annotations

import discord

PAGE_LENGTH = 3400


def split_reading_pages(reading: str, *, page_length: int = PAGE_LENGTH) -> list[str]:
    """Split on natural boundaries without discarding reading content."""
    if page_length < 100:
        raise ValueError("page_length must be at least 100")
    text = discord.utils.escape_mentions(reading or "Chưa có luận giải.")
    pages: list[str] = []
    while len(text) > page_length:
        cut = text.rfind("\n\n", 0, page_length)
        if cut < page_length // 3:
            cut = text.rfind("\n", 0, page_length)
        if cut < page_length // 3:
            cut = text.rfind(" ", 0, page_length)
        if cut < page_length // 3:
            cut = page_length
        pages.append(text[:cut])
        text = text[cut:]
    pages.append(text)
    return pages


class TarotReadingPagesView(discord.ui.View):
    """Ephemeral prev/next controls for one existing, immutable interpretation."""

    def __init__(self, reading: str, *, viewer_id: int):
        super().__init__(timeout=900)
        self.viewer_id = viewer_id
        self.pages = split_reading_pages(reading)
        self.page_index = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.previous_button.disabled = self.page_index == 0
        self.next_button.disabled = self.page_index >= len(self.pages) - 1

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📖 LUẬN GIẢI TAROT",
            description=self.pages[self.page_index],
            color=0x7851A9,
        )
        embed.set_footer(
            text=f"Trang {self.page_index + 1}/{len(self.pages)} · Quẻ đã rút · Không rút thêm lá"
        )
        return embed

    async def _turn(self, interaction: discord.Interaction, delta: int) -> None:
        if interaction.user.id != self.viewer_id:
            await interaction.response.send_message(
                "Chỉ người mở bản đọc này mới có thể chuyển trang.", ephemeral=True
            )
            return
        self.page_index = max(0, min(len(self.pages) - 1, self.page_index + delta))
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="◀ Trước", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._turn(interaction, -1)

    @discord.ui.button(label="Tiếp ▶", style=discord.ButtonStyle.primary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._turn(interaction, 1)
