"""Historical read-only native Tarot V2 view.

The legacy Discord embed is again the public reading UI. This helper is kept
for compatibility only and must never upload or reference a TXT attachment.
Long readings now use features.tarot.reading.pagination in the live callback.
"""
from __future__ import annotations

import discord

MAX_VISIBLE_READING = 3500


def build_full_reading_layout(reading: str, *, with_attachment: bool = False) -> discord.ui.LayoutView:
    """Short read-only compatibility view; the attachment flag is ignored."""
    safe = discord.utils.escape_mentions(reading or "Chưa có luận giải.")
    visible = safe[:MAX_VISIBLE_READING].rstrip()
    if len(safe) > MAX_VISIBLE_READING:
        visible += "\n\n*Để xem trọn nội dung, dùng tính năng đọc nhiều trang trong Discord.*"
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("### 📖 Luận giải Tarot"),
        discord.ui.Separator(visible=True),
        discord.ui.TextDisplay(visible),
        discord.ui.TextDisplay("-# Asumi Tarot · Không rút lại lá bài"),
        accent_colour=discord.Colour(0x6D5D8F),
    ))
    return view
