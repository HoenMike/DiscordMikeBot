"""Read-only Discord Components V2 for the one-card Tarot detail action.

The actual Tarot draw, AI reading and ownership rules remain in the existing
Tarot Views. Never combine LayoutView with content/embed on one message.
"""
from __future__ import annotations

import discord

MAX_VISIBLE_READING = 3700


def build_full_reading_layout(reading: str) -> discord.ui.LayoutView:
    safe = discord.utils.escape_mentions(reading or "Chưa có luận giải.")
    visible = safe[:MAX_VISIBLE_READING].rstrip()
    if len(safe) > MAX_VISIBLE_READING:
        visible += "\n\n*Bản luận giải đầy đủ nằm trong tệp `tarot_reading.txt` đính kèm.*"
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay("### 📖 Luận giải Tarot đầy đủ"),
        discord.ui.Separator(visible=True),
        discord.ui.TextDisplay(visible),
        discord.ui.TextDisplay(
            "-# Asumi Tarot · Quẻ đã rút · Không rút lại lá bài"
        ),
        accent_colour=discord.Colour(0x6D5D8F),
    ))
    return view
