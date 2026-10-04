"""Tarot 2.0 Reading Board renderer.

The public `render_spread_to_bytes` signature remains backward-compatible, while the
new `ReadingBoardState` contract carries reveal/final/emphasis state independently
from Discord UI code.
"""

from __future__ import annotations

import io
import pathlib
from typing import List, Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFont

from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, TarotCard, ensure_card_asset
from features.tarot.rendering.state import ReadingBoardState


# Restrained Tarot 2.0 palette: dark celestial, muted violet, warm gold, blue-grey.
COLOR_BG_TOP = (18, 18, 28)
COLOR_BG_BOTTOM = (27, 24, 39)
COLOR_PANEL = (35, 32, 49)
COLOR_PANEL_SOFT = (43, 39, 58)
COLOR_GOLD = (203, 166, 92)
COLOR_GOLD_LIGHT = (236, 211, 151)
COLOR_GOLD_DARK = (115, 91, 50)
COLOR_VIOLET = (132, 111, 171)
COLOR_VIOLET_LIGHT = (183, 166, 215)
COLOR_BLUEGREY = (117, 143, 164)
COLOR_BLUEGREY_LIGHT = (171, 191, 207)
COLOR_TEXT = (244, 241, 247)
COLOR_MUTED = (177, 174, 188)
COLOR_REVERSED = (210, 126, 126)
COLOR_UPRIGHT = (143, 184, 158)
COLOR_SHADOW = (0, 0, 0, 120)

FONTS_DIR = pathlib.Path(__file__).parent / "assets" / "fonts"

_CARD_IMAGE_CACHE: dict[Tuple[str, int, int, bool], Image.Image] = {}
_CARD_BACK_CACHE: dict[Tuple[int, int], Image.Image] = {}


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend([
            FONTS_DIR / "segoeuib.ttf",
            FONTS_DIR / "arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            FONTS_DIR / "segoeui.ttf",
            FONTS_DIR / "arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ])
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _gradient_background(width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), COLOR_BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / max(1, height - 1)
        rgb = tuple(
            int(COLOR_BG_TOP[i] * (1.0 - ratio) + COLOR_BG_BOTTOM[i] * ratio)
            for i in range(3)
        )
        draw.line((0, y, width, y), fill=rgb)

    # Subtle board frame; no heavy gothic ornament.
    margin = max(18, width // 70)
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=max(18, width // 60),
        outline=COLOR_GOLD_DARK,
        width=max(2, width // 500),
    )
    draw.rounded_rectangle(
        (margin + 8, margin + 8, width - margin - 8, height - margin - 8),
        radius=max(15, width // 65),
        outline=(59, 52, 73),
        width=1,
    )

    # Sparse celestial dots for texture, deterministic from canvas size.
    dots = [
        (0.10, 0.12), (0.18, 0.76), (0.29, 0.18), (0.41, 0.88),
        (0.57, 0.13), (0.68, 0.78), (0.81, 0.21), (0.90, 0.70),
        (0.12, 0.46), (0.88, 0.45),
    ]
    dot_r = max(2, width // 650)
    for px, py in dots:
        x, y = int(width * px), int(height * py)
        draw.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=(103, 94, 124))
    return img.convert("RGBA")


def _safe_title(spread_key: str, custom_title: Optional[str] = None) -> str:
    if custom_title:
        title = " ".join(custom_title.split())
        return title if len(title) <= 44 else title[:41].rstrip() + "..."

    compact = {
        "daily": "Daily Card",
        "yes_no": "Yes / No",
        "single": "Single Card",
        "ppf": "Past · Present · Future",
        "choices": "Two Choices",
        "mbs": "Mind · Body · Spirit",
        "horseshoe": "Horseshoe",
        "two_paths": "Two Paths",
        "celtic": "Celtic Cross",
    }
    return compact.get(
        spread_key,
        SPREAD_DEFINITIONS.get(spread_key, {}).get("name", "Tarot Spread"),
    )


def _short_position_title(raw: str, fallback_index: int) -> str:
    title = (raw or "").strip()
    upper = title.upper()
    if upper.startswith("LÁ ") and ":" in title:
        title = title.split(":", 1)[1].strip()
    if upper.startswith("PHÁN QUYẾT"):
        title = "PHÁN QUYẾT"
    title = " ".join(title.split())
    if not title:
        title = f"VỊ TRÍ {fallback_index + 1}"
    if len(title) > 34:
        title = title[:31].rstrip() + "..."
    return title


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((center_x - (bbox[2] - bbox[0]) // 2, y), text, font=font, fill=fill)


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    y: int,
    font: ImageFont.ImageFont,
    *,
    fill=COLOR_PANEL,
    outline=COLOR_GOLD_DARK,
    text_color=COLOR_GOLD_LIGHT,
    pad_x: int = 12,
    pad_y: int = 5,
) -> Tuple[int, int, int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box = (
        center_x - tw // 2 - pad_x,
        y,
        center_x + tw // 2 + pad_x,
        y + th + pad_y * 2,
    )
    draw.rounded_rectangle(box, radius=max(6, pad_y + 2), fill=fill, outline=outline, width=2)
    draw.text((center_x - tw // 2, y + pad_y - bbox[1]), text, font=font, fill=text_color)
    return box


def _draw_header(canvas: Image.Image, state: ReadingBoardState) -> int:
    draw = ImageDraw.Draw(canvas)
    width, _ = canvas.size
    title = _safe_title(state.spread_key, state.spread_title)
    title_font = _get_font(max(28, width // 34), bold=True)
    meta_font = _get_font(max(18, width // 60), bold=True)
    brand_font = _get_font(max(14, width // 82))

    _draw_centered_text(draw, title.upper(), width // 2, max(34, width // 42), title_font, COLOR_GOLD_LIGHT)
    _draw_centered_text(draw, "ASUMI · TAROT", width // 2, max(78, width // 20), brand_font, COLOR_MUTED)

    if state.final:
        _draw_pill(
            draw,
            "FINAL SPREAD",
            width // 2,
            max(112, width // 13),
            meta_font,
            fill=(43, 39, 58),
            outline=COLOR_GOLD_DARK,
            text_color=COLOR_GOLD_LIGHT,
            pad_x=18,
        )
    else:
        progress = f"{state.revealed_count} / {state.total_cards} REVEALED"
        _draw_pill(
            draw,
            progress,
            width // 2,
            max(112, width // 13),
            meta_font,
            fill=(39, 36, 53),
            outline=COLOR_VIOLET,
            text_color=COLOR_TEXT,
            pad_x=18,
        )

        if state.total_cards <= 10:
            dots = "  ".join(
                "●" if idx in state.revealed_indices else "○"
                for idx in range(state.total_cards)
            )
            dots_font = _get_font(max(16, width // 68), bold=True)
            _draw_centered_text(
                draw,
                dots,
                width // 2,
                max(154, width // 9),
                dots_font,
                COLOR_VIOLET_LIGHT,
            )
    return max(190, width // 7)


def _generate_procedural_card(card: TarotCard, target_w: int, target_h: int) -> Image.Image:
    img = Image.new("RGBA", (target_w, target_h), (29, 26, 39, 255))
    draw = ImageDraw.Draw(img)
    border = max(2, target_w // 75)
    draw.rounded_rectangle(
        (border, border, target_w - border - 1, target_h - border - 1),
        radius=max(8, target_w // 14),
        outline=COLOR_GOLD,
        width=border,
        fill=(31, 28, 43, 255),
    )
    draw.ellipse(
        (
            target_w * 0.25,
            target_h * 0.24,
            target_w * 0.75,
            target_h * 0.57,
        ),
        outline=COLOR_VIOLET_LIGHT,
        width=max(2, target_w // 90),
    )
    font_top = _get_font(max(14, target_w // 12), bold=True)
    font_name = _get_font(max(16, target_w // 10), bold=True)
    _draw_centered_text(draw, f"ARCANA {card.number}" if card.arcana == "Major" else card.arcana.upper(), target_w // 2, int(target_h * 0.09), font_top, COLOR_GOLD_LIGHT)
    _draw_centered_text(draw, card.name_vi, target_w // 2, int(target_h * 0.72), font_name, COLOR_TEXT)
    return img


def _generate_card_back(target_w: int, target_h: int) -> Image.Image:
    key = (target_w, target_h)
    if key in _CARD_BACK_CACHE:
        return _CARD_BACK_CACHE[key].copy()

    img = Image.new("RGBA", (target_w, target_h), (29, 26, 43, 255))
    draw = ImageDraw.Draw(img)
    border = max(2, target_w // 65)
    inset = max(8, target_w // 16)
    draw.rounded_rectangle(
        (1, 1, target_w - 2, target_h - 2),
        radius=max(9, target_w // 13),
        outline=COLOR_GOLD,
        width=border,
        fill=(31, 28, 47, 255),
    )
    draw.rounded_rectangle(
        (inset, inset, target_w - inset, target_h - inset),
        radius=max(7, target_w // 16),
        outline=COLOR_VIOLET,
        width=max(1, border - 1),
    )
    cx, cy = target_w // 2, target_h // 2
    r = min(target_w, target_h) // 5
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=COLOR_GOLD_DARK, width=max(2, border - 1))
    draw.line((cx - r, cy, cx + r, cy), fill=COLOR_VIOLET_LIGHT, width=max(1, border - 1))
    draw.line((cx, cy - r, cx, cy + r), fill=COLOR_VIOLET_LIGHT, width=max(1, border - 1))
    _CARD_BACK_CACHE[key] = img.copy()
    return img


def _load_and_prepare_card_image(drawn: DrawnCard, target_w: int, target_h: int) -> Image.Image:
    key = (drawn.card.id, target_w, target_h, drawn.is_reversed)
    if key in _CARD_IMAGE_CACHE:
        return _CARD_IMAGE_CACHE[key].copy()

    card_img: Optional[Image.Image] = None
    asset_path = ensure_card_asset(drawn.card)
    if asset_path and asset_path.exists():
        try:
            with Image.open(asset_path) as raw:
                card_img = raw.convert("RGBA").resize((target_w, target_h), Image.Resampling.LANCZOS)
        except Exception as exc:
            print(f"[TarotRenderer] Failed to read {asset_path}: {exc}", flush=True)

    if card_img is None:
        card_img = _generate_procedural_card(drawn.card, target_w, target_h)

    if drawn.is_reversed:
        card_img = card_img.rotate(180)

    frame = ImageDraw.Draw(card_img)
    frame.rounded_rectangle(
        (1, 1, target_w - 2, target_h - 2),
        radius=max(6, target_w // 24),
        outline=COLOR_GOLD_DARK,
        width=max(2, target_w // 100),
    )
    _CARD_IMAGE_CACHE[key] = card_img.copy()
    return card_img


def _state_accent(state: ReadingBoardState, index: int):
    if state.is_key_card(index):
        return COLOR_GOLD_LIGHT, "KEY"
    if state.is_just_revealed(index):
        return COLOR_VIOLET_LIGHT, "NEW"
    if state.is_target(index):
        return COLOR_BLUEGREY_LIGHT, "TARGET"
    return (77, 70, 92), ""


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    *,
    fill=COLOR_PANEL_SOFT,
    outline=COLOR_GOLD_DARK,
    text_color=COLOR_TEXT,
) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box = (x, y, x + tw + 18, y + th + 10)
    draw.rounded_rectangle(box, radius=7, fill=fill, outline=outline, width=2)
    draw.text((x + 9, y + 5 - bbox[1]), text, font=font, fill=text_color)
    return box[2], box[3]


def _draw_card_slot(
    canvas: Image.Image,
    state: ReadingBoardState,
    index: int,
    center_x: int,
    center_y: int,
    card_w: int,
    card_h: int,
    *,
    position_title: Optional[str] = None,
    rotate_degrees: int = 0,
    show_footer: bool = True,
) -> None:
    if not 0 <= index < len(state.drawn_cards):
        return

    drawn = state.drawn_cards[index]
    revealed = state.is_revealed(index)
    draw = ImageDraw.Draw(canvas)
    label = _short_position_title(position_title or drawn.position_title, index)
    max_label_chars = 16 if card_w < 160 else (20 if card_w < 190 else 25)
    if len(label) > max_label_chars:
        label = label[:max_label_chars - 3].rstrip() + "..."

    label_font = _get_font(max(15, card_w // 10), bold=True)
    name_font = _get_font(max(14, card_w // 11), bold=True)
    meta_font = _get_font(max(12, card_w // 13), bold=True)
    tiny_font = _get_font(max(10, card_w // 16), bold=True)

    img = _load_and_prepare_card_image(drawn, card_w, card_h) if revealed else _generate_card_back(card_w, card_h)
    if rotate_degrees:
        img = img.rotate(rotate_degrees, expand=True)
    img_w, img_h = img.size

    left = center_x - img_w // 2
    top = center_y - img_h // 2

    shadow_pad = max(6, card_w // 30)
    draw.rounded_rectangle(
        (left + shadow_pad, top + shadow_pad, left + img_w + shadow_pad, top + img_h + shadow_pad),
        radius=max(7, card_w // 22),
        fill=COLOR_SHADOW,
    )
    canvas.paste(img, (left, top), img)

    accent, state_tag = _state_accent(state, index)
    border_w = max(3, card_w // 55) if state_tag else max(2, card_w // 95)
    draw.rounded_rectangle(
        (left - 3, top - 3, left + img_w + 3, top + img_h + 3),
        radius=max(8, card_w // 20),
        outline=accent,
        width=border_w,
    )

    # Position title remains visible for face-up and face-down cards.
    label_y = top - max(42, card_w // 4)
    _draw_pill(
        draw,
        f"{index + 1}. {label}",
        center_x,
        label_y,
        label_font,
        fill=COLOR_PANEL,
        outline=accent if state_tag else COLOR_GOLD_DARK,
        text_color=COLOR_TEXT,
        pad_x=max(9, card_w // 18),
        pad_y=max(4, card_w // 55),
    )

    if not revealed:
        number_font = _get_font(max(22, card_w // 6), bold=True)
        _draw_pill(
            draw,
            str(index + 1),
            center_x,
            center_y - max(18, card_w // 9),
            number_font,
            fill=(34, 30, 49),
            outline=COLOR_VIOLET,
            text_color=COLOR_GOLD_LIGHT,
            pad_x=max(14, card_w // 10),
            pad_y=max(6, card_w // 25),
        )
        return

    # Accessible orientation/state badges: important meaning never relies on color alone.
    badge_y = top + max(8, card_w // 25)
    badge_x = left + max(8, card_w // 25)
    if drawn.is_reversed:
        _, badge_bottom = _draw_badge(
            draw,
            "REV",
            badge_x,
            badge_y,
            meta_font,
            fill=(67, 43, 50),
            outline=COLOR_REVERSED,
            text_color=(246, 210, 210),
        )
        badge_y = badge_bottom + 6
    if drawn.card.arcana == "Major":
        _, badge_bottom = _draw_badge(
            draw,
            "MAJOR",
            badge_x,
            badge_y,
            tiny_font,
            fill=(53, 45, 33),
            outline=COLOR_GOLD_DARK,
            text_color=COLOR_GOLD_LIGHT,
        )
        badge_y = badge_bottom + 6
    if state_tag:
        _draw_badge(
            draw,
            state_tag,
            badge_x,
            badge_y,
            tiny_font,
            fill=(49, 42, 65),
            outline=accent,
            text_color=accent,
        )

    if not show_footer:
        return

    footer_y = top + img_h + max(10, card_w // 22)
    name = drawn.card.name_vi
    if len(name) > 24:
        name = name[:21].rstrip() + "..."
    _draw_centered_text(draw, name, center_x, footer_y, name_font, COLOR_TEXT)
    orientation = "NGƯỢC" if drawn.is_reversed else "XUÔI"
    orient_color = COLOR_REVERSED if drawn.is_reversed else COLOR_UPRIGHT
    _draw_centered_text(
        draw,
        orientation,
        center_x,
        footer_y + max(24, card_w // 8),
        meta_font,
        orient_color,
    )


def _layout_1(state: ReadingBoardState) -> Image.Image:
    width, height = 1080, 1350
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    _draw_card_slot(canvas, state, 0, 540, 735, 440, 756)
    return canvas


def _layout_3(state: ReadingBoardState) -> Image.Image:
    width, height = 1400, 900
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    xs = (260, 700, 1140)
    for idx, x in enumerate(xs):
        _draw_card_slot(canvas, state, idx, x, 515, 250, 430)
    return canvas


def _layout_4(state: ReadingBoardState) -> Image.Image:
    width, height = 1300, 1100
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    positions = (
        (650, 420),
        (365, 655),
        (935, 655),
        (650, 875),
    )
    for idx, (x, y) in enumerate(positions):
        _draw_card_slot(canvas, state, idx, x, y, 190, 327)
    return canvas


def _layout_two_paths(state: ReadingBoardState) -> Image.Image:
    width, height = 1400, 1100
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    draw = ImageDraw.Draw(canvas)
    branch_font = _get_font(25, bold=True)

    _draw_card_slot(canvas, state, 0, 700, 385, 190, 327, position_title="BỐI CẢNH CHUNG")

    _draw_pill(draw, "HƯỚNG A", 390, 585, branch_font, fill=(35, 42, 54), outline=COLOR_BLUEGREY, text_color=COLOR_BLUEGREY_LIGHT, pad_x=26)
    _draw_pill(draw, "HƯỚNG B", 1010, 585, branch_font, fill=(43, 36, 54), outline=COLOR_VIOLET, text_color=COLOR_VIOLET_LIGHT, pad_x=26)

    slots = (
        (1, 245, 820, "THUẬN LỢI A"),
        (2, 535, 820, "RỦI RO A"),
        (3, 865, 820, "THUẬN LỢI B"),
        (4, 1155, 820, "RỦI RO B"),
    )
    for idx, x, y, title in slots:
        _draw_card_slot(canvas, state, idx, x, y, 170, 292, position_title=title)
    return canvas


def _layout_horseshoe(state: ReadingBoardState) -> Image.Image:
    width, height = 1500, 1100
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    positions = (
        (210, 410),
        (480, 600),
        (750, 735),
        (1020, 600),
        (1290, 410),
    )
    for idx, (x, y) in enumerate(positions):
        _draw_card_slot(canvas, state, idx, x, y, 200, 344)
    return canvas


def _layout_generic_5(state: ReadingBoardState) -> Image.Image:
    width, height = 1300, 1100
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    positions = (
        (650, 395),
        (370, 625),
        (650, 625),
        (930, 625),
        (650, 875),
    )
    for idx, (x, y) in enumerate(positions):
        _draw_card_slot(canvas, state, idx, x, y, 180, 310)
    return canvas


def _layout_6(state: ReadingBoardState) -> Image.Image:
    width, height = 1500, 1150
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    xs = (300, 750, 1200)
    ys = (410, 830)
    idx = 0
    for y in ys:
        for x in xs:
            _draw_card_slot(canvas, state, idx, x, y, 190, 327)
            idx += 1
    return canvas


def _layout_7(state: ReadingBoardState) -> Image.Image:
    width, height = 1500, 1150
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    positions = (
        (170, 390),
        (365, 565),
        (560, 700),
        (750, 765),
        (940, 700),
        (1135, 565),
        (1330, 390),
    )
    for idx, (x, y) in enumerate(positions):
        _draw_card_slot(canvas, state, idx, x, y, 170, 292)
    return canvas


def _layout_grid(state: ReadingBoardState) -> Image.Image:
    count = state.total_cards
    columns = 3 if count <= 9 else 4
    rows = (count + columns - 1) // columns
    width = 1500
    height = max(1000, 250 + rows * 400)
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)
    card_w, card_h = 190, 327
    x_gap = width // (columns + 1)
    y_start = 360
    y_gap = 400
    for idx in range(count):
        row, col = divmod(idx, columns)
        _draw_card_slot(
            canvas,
            state,
            idx,
            x_gap * (col + 1),
            y_start + row * y_gap,
            card_w,
            card_h,
        )
    return canvas


def _draw_celtic_center(canvas: Image.Image, state: ReadingBoardState) -> None:
    draw = ImageDraw.Draw(canvas)
    center_x, center_y = 610, 710
    card_w, card_h = 170, 292

    # Draw card 1 without its normal footer/position header; card 2 crosses over it.
    for idx, rotation in ((0, 0), (1, 90)):
        drawn = state.drawn_cards[idx]
        revealed = state.is_revealed(idx)
        img = _load_and_prepare_card_image(drawn, card_w, card_h) if revealed else _generate_card_back(card_w, card_h)
        if rotation:
            img = img.rotate(rotation, expand=True)
        iw, ih = img.size
        left, top = center_x - iw // 2, center_y - ih // 2
        draw.rounded_rectangle(
            (left + 8, top + 8, left + iw + 8, top + ih + 8),
            radius=10,
            fill=COLOR_SHADOW,
        )
        canvas.paste(img, (left, top), img)
        accent, tag = _state_accent(state, idx)
        draw.rounded_rectangle(
            (left - 3, top - 3, left + iw + 3, top + ih + 3),
            radius=10,
            outline=accent,
            width=5 if tag else 2,
        )

    central_font = _get_font(20, bold=True)
    _draw_pill(
        draw,
        "1. HIỆN TẠI  ·  2. TRỞ NGẠI",
        center_x,
        500,
        central_font,
        fill=COLOR_PANEL,
        outline=COLOR_GOLD_DARK,
        text_color=COLOR_TEXT,
        pad_x=18,
    )

    detail_font = _get_font(16, bold=True)
    detail_y = 875
    for idx in (0, 1):
        drawn = state.drawn_cards[idx]
        if state.is_revealed(idx):
            orientation = " · REV" if drawn.is_reversed else ""
            _, state_tag = _state_accent(state, idx)
            emphasis = f" · {state_tag}" if state_tag else ""
            text = f"{idx + 1}. {drawn.card.name_vi}{orientation}{emphasis}"
            color = COLOR_REVERSED if drawn.is_reversed else (
                COLOR_GOLD_LIGHT if state.is_key_card(idx) else COLOR_TEXT
            )
        else:
            text = f"{idx + 1}. CHƯA LẬT"
            color = COLOR_MUTED
        _draw_centered_text(draw, text, center_x, detail_y + (idx * 28), detail_font, color)


def _layout_celtic(state: ReadingBoardState) -> Image.Image:
    width, height = 1600, 1350
    canvas = _gradient_background(width, height)
    _draw_header(canvas, state)

    _draw_celtic_center(canvas, state)

    # Traditional cross around the center pair.
    outer = (
        (2, 610, 1090, "GỐC RỄ"),
        (3, 315, 710, "QUÁ KHỨ"),
        (4, 610, 380, "NHẬN THỨC"),
        (5, 905, 710, "TƯƠNG LAI GẦN"),
    )
    for idx, x, y, title in outer:
        _draw_card_slot(canvas, state, idx, x, y, 155, 267, position_title=title)

    # Staff column.
    staff = (
        (6, 1320, 1180, "BẢN THÂN"),
        (7, 1320, 910, "MÔI TRƯỜNG"),
        (8, 1320, 640, "HY VỌNG & NỖI SỢ"),
        (9, 1320, 370, "KẾT QUẢ"),
    )
    for idx, x, y, title in staff:
        _draw_card_slot(canvas, state, idx, x, y, 145, 249, position_title=title)
    return canvas


def render_reading_board(state: ReadingBoardState) -> Image.Image:
    count = state.total_cards
    if count <= 0:
        raise ValueError("ReadingBoardState requires at least one card")
    if count == 1:
        return _layout_1(state)
    if count == 3:
        return _layout_3(state)
    if count == 4:
        return _layout_4(state)
    if count == 5:
        if state.spread_key == "two_paths":
            return _layout_two_paths(state)
        if state.spread_key == "horseshoe":
            return _layout_horseshoe(state)
        return _layout_generic_5(state)
    if count == 6:
        return _layout_6(state)
    if count == 7:
        return _layout_7(state)
    if count == 10 or state.spread_key == "celtic":
        return _layout_celtic(state)
    return _layout_grid(state)


def _render_emergency_board(state: ReadingBoardState, error: Exception) -> Image.Image:
    """Text-first renderer fallback: preserve reading outcome if visual composition fails."""
    width, height = 1200, max(760, 260 + 82 * state.total_cards)
    canvas = _gradient_background(width, height)
    draw = ImageDraw.Draw(canvas)
    title_font = _get_font(34, bold=True)
    row_font = _get_font(24, bold=True)
    small_font = _get_font(18)

    _draw_centered_text(draw, _safe_title(state.spread_key, state.spread_title).upper(), width // 2, 60, title_font, COLOR_GOLD_LIGHT)
    _draw_centered_text(draw, "Visual fallback · cards remain unchanged", width // 2, 110, small_font, COLOR_MUTED)

    y = 190
    for idx, card in enumerate(state.drawn_cards):
        label = _short_position_title(card.position_title, idx)
        if idx in state.revealed_indices:
            orientation = "NGƯỢC" if card.is_reversed else "XUÔI"
            text = f"{idx + 1}. {label} — {card.card.name_vi} · {orientation}"
        else:
            text = f"{idx + 1}. {label} — CHƯA LẬT"
        draw.text((90, y), text, font=row_font, fill=COLOR_TEXT)
        y += 64

    # Keep implementation detail tiny and local; do not expose stack traces.
    err_name = type(error).__name__
    draw.text((90, height - 70), f"Renderer fallback: {err_name}", font=small_font, fill=COLOR_MUTED)
    return canvas


def render_reading_board_to_bytes(state: ReadingBoardState) -> io.BytesIO:
    try:
        image = render_reading_board(state)
    except Exception as exc:
        print(f"[TarotRenderer] Reading Board fallback: {type(exc).__name__}: {exc}", flush=True)
        image = _render_emergency_board(state, exc)

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True, compress_level=6)
    buffer.seek(0)
    return buffer


def render_spread_to_bytes(
    spread_key: str,
    drawn_cards: List[DrawnCard],
    revealed_indices: Optional[Set[int]] = None,
    *,
    just_revealed_indices: Optional[Set[int]] = None,
    key_card_id: Optional[str] = None,
    target_position_index: Optional[int] = None,
    final: bool = False,
    spread_title: Optional[str] = None,
) -> io.BytesIO:
    """Backward-compatible renderer entry point used by current Discord views."""
    state = ReadingBoardState.from_legacy(
        spread_key,
        drawn_cards,
        revealed_indices,
        just_revealed_indices=just_revealed_indices,
        key_card_id=key_card_id,
        target_position_index=target_position_index,
        final=final,
        spread_title=spread_title,
    )
    return render_reading_board_to_bytes(state)


# Compatibility image-returning helpers used by older local tooling.
def render_1_card_spread(spread_key: str, drawn_cards: List[DrawnCard], revealed_indices: Optional[Set[int]] = None) -> Image.Image:
    return render_reading_board(ReadingBoardState.from_legacy(spread_key, drawn_cards, revealed_indices))


def render_3_card_spread(spread_key: str, drawn_cards: List[DrawnCard], revealed_indices: Optional[Set[int]] = None) -> Image.Image:
    return render_reading_board(ReadingBoardState.from_legacy(spread_key, drawn_cards, revealed_indices))


def render_5_card_spread(spread_key: str, drawn_cards: List[DrawnCard], revealed_indices: Optional[Set[int]] = None) -> Image.Image:
    return render_reading_board(ReadingBoardState.from_legacy(spread_key, drawn_cards, revealed_indices))


def render_celtic_cross_spread(drawn_cards: List[DrawnCard], revealed_indices: Optional[Set[int]] = None) -> Image.Image:
    return render_reading_board(ReadingBoardState.from_legacy("celtic", drawn_cards, revealed_indices))
