"""T25 Tarot rich reply pilot: static, answer-first visual inside Discord.

A regular Discord message cannot run React/OpenUI. Render trusted structured
Tarot data into one compact image; native buttons handle actual interactions.
No additional model call or separate dashboard/Activity is involved.
"""
from __future__ import annotations

import io

from PIL import ImageDraw

from features.tarot.rendering.state import RecapCardState
from features.tarot.renderer import (
    COLOR_BG_TOP, COLOR_BLUEGREY_LIGHT, COLOR_GOLD, COLOR_GOLD_DARK,
    COLOR_GOLD_LIGHT, COLOR_MUTED, COLOR_PANEL, COLOR_TEXT, COLOR_VIOLET,
    COLOR_VIOLET_LIGHT, _get_font, _gradient_background,
    _load_and_prepare_card_image, _wrap_recap_text,
)


def render_inline_tarot_to_bytes(state: RecapCardState) -> io.BytesIO:
    """Compact 1200×760 shareable rich card for a one-card Tarot reading.

    Content is derived from an existing reading: neither invented nor re-rolled.
    Text remains in the companion Discord embed for accessibility.
    """
    width, height = 1200, 760
    canvas = _gradient_background(width, height)
    draw = ImageDraw.Draw(canvas)
    label_font = _get_font(19, bold=True)
    heading_font = _get_font(31, bold=True)
    body_font = _get_font(25)
    card_font = _get_font(23, bold=True)
    meta_font = _get_font(19)

    # The actual card artwork is the hero, not an AI-generated substitute.
    hero = _load_and_prepare_card_image(state.hero_card, 340, 554).convert("RGBA")
    draw.rounded_rectangle(
        (62, 101, 440, 671), radius=28,
        fill=(33, 30, 45), outline=COLOR_GOLD_DARK, width=2,
    )
    canvas.alpha_composite(hero, (80, 108))
    orient = "NGƯỢC" if state.hero_card.is_reversed else "XUÔI"
    card_name = state.hero_card.card.name_vi[:32]
    draw.text((84, 669), f"{card_name} · {orient}", font=card_font, fill=COLOR_GOLD_LIGHT)

    # Short text-first visual: headline + action are scan-friendly on mobile.
    draw.rounded_rectangle(
        (475, 100, 1143, 672), radius=28,
        fill=COLOR_PANEL, outline=COLOR_VIOLET, width=2,
    )
    draw.text((514, 135), "ASUMI · TAROT INSIGHT", font=label_font, fill=COLOR_VIOLET_LIGHT)
    draw.text((514, 179), state.spread_title[:47], font=meta_font, fill=COLOR_MUTED)

    y = 235
    for line in _wrap_recap_text(draw, state.headline, heading_font, 580, 3):
        draw.text((514, y), line, font=heading_font, fill=COLOR_GOLD_LIGHT)
        y += 45

    y = max(405, y + 34)
    draw.line((514, y, 1098, y), fill=COLOR_GOLD_DARK, width=2)
    y += 26
    draw.text((514, y), "GỢI Ý ĐỂ CHIÊM NGHIỆM", font=label_font, fill=COLOR_BLUEGREY_LIGHT)
    y += 42
    for line in _wrap_recap_text(draw, state.takeaway, body_font, 580, 4):
        draw.text((514, y), line, font=body_font, fill=COLOR_TEXT)
        y += 39

    draw.text(
        (67, 716), f"{state.user_name[:28]} · {state.date_label}",
        font=meta_font, fill=COLOR_MUTED,
    )
    draw.text(
        (735, 716), "Góc nhìn tham khảo, không phải định mệnh",
        font=meta_font, fill=COLOR_MUTED,
    )

    output = io.BytesIO()
    canvas.convert("RGB").save(output, "PNG", optimize=True, compress_level=6)
    output.seek(0)
    return output
