import io
import math
import pathlib
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from features.tarot.deck import (
    DrawnCard,
    TarotCard,
    SPREAD_DEFINITIONS,
    ensure_card_asset,
    CARDS_DIR
)

# Màu sắc chủ đạo phong cách Tarot huyền bí
COLOR_BG_DARK = (16, 12, 26)        # #100C1A - Tím đêm thẳm
COLOR_BG_BANNER = (28, 20, 48, 230) # Nền banner tiêu đề
COLOR_GOLD_PRIMARY = (218, 165, 32) # #DAA520 - Vàng kim hoàng gia
COLOR_GOLD_LIGHT = (245, 215, 110)  # #F5D76E - Vàng kim sáng
COLOR_GOLD_DARK = (140, 100, 20)    # Vàng kim trầm
COLOR_WHITE = (245, 245, 250)
COLOR_MUTED = (175, 165, 200)
COLOR_UPRIGHT = (46, 204, 113)      # #2ECC71 - Xanh ngọc
COLOR_REVERSED = (231, 76, 60)      # #E74C3C - Đỏ hồng
COLOR_BRANCH_A = (52, 152, 219)     # #3498DB - Xanh biển cho Nhánh A
COLOR_BRANCH_B = (155, 89, 182)     # #9B59B6 - Tím pastel cho Nhánh B


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Tải font hỗ trợ Tiếng Việt an toàn trên mọi hệ điều hành."""
    font_names = ["segoeui.ttf", "arial.ttf", "calibri.ttf"]
    if bold:
        font_names = ["segouib.ttf", "arialbd.ttf", "calibrib.ttf"] + font_names

    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_sparkle_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int = 10, color=COLOR_GOLD_LIGHT):
    """Vẽ ngôi sao 4 cánh lấp lánh (thay cho ký tự unicode lỗi font)."""
    points = [
        (cx, cy - size),
        (cx + size // 4, cy - size // 4),
        (cx + size, cy),
        (cx + size // 4, cy + size // 4),
        (cx, cy + size),
        (cx - size // 4, cy + size // 4),
        (cx - size, cy),
        (cx - size // 4, cy - size // 4),
    ]
    draw.polygon(points, fill=color, outline=COLOR_GOLD_PRIMARY)
    draw.ellipse([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=COLOR_WHITE)


def _draw_ornate_corner(draw: ImageDraw.ImageDraw, x: int, y: int, radius: int = 24, quadrant: int = 1):
    """Vẽ hoa văn góc vàng kim ma thuật."""
    if quadrant == 1:
        draw.line([(x, y + radius), (x, y), (x + radius, y)], fill=COLOR_GOLD_PRIMARY, width=2)
        draw.line([(x + 6, y + radius - 6), (x + 6, y + 6), (x + radius - 6, y + 6)], fill=COLOR_GOLD_DARK, width=1)
        draw.ellipse([(x + 3, y + 3), (x + 9, y + 9)], fill=COLOR_GOLD_LIGHT)
    elif quadrant == 2:
        draw.line([(x, y + radius), (x, y), (x - radius, y)], fill=COLOR_GOLD_PRIMARY, width=2)
        draw.line([(x - 6, y + radius - 6), (x - 6, y + 6), (x - radius + 6, y + 6)], fill=COLOR_GOLD_DARK, width=1)
        draw.ellipse([(x - 9, y + 3), (x - 3, y + 9)], fill=COLOR_GOLD_LIGHT)
    elif quadrant == 3:
        draw.line([(x, y - radius), (x, y), (x + radius, y)], fill=COLOR_GOLD_PRIMARY, width=2)
        draw.line([(x + 6, y - radius + 6), (x + 6, y - 6), (x + radius - 6, y - 6)], fill=COLOR_GOLD_DARK, width=1)
        draw.ellipse([(x + 3, y - 9), (x + 9, y - 3)], fill=COLOR_GOLD_LIGHT)
    elif quadrant == 4:
        draw.line([(x, y - radius), (x, y), (x - radius, y)], fill=COLOR_GOLD_PRIMARY, width=2)
        draw.line([(x - 6, y - radius + 6), (x - 6, y - 6), (x - radius + 6, y - 6)], fill=COLOR_GOLD_DARK, width=1)
        draw.ellipse([(x - 9, y - 9), (x - 3, y - 3)], fill=COLOR_GOLD_LIGHT)


def _draw_mystic_background(width: int, height: int, title: str) -> Image.Image:
    """Tạo canvas nền tối sang trọng với hoa văn và banner tiêu đề Tarot."""
    img = Image.new("RGBA", (width, height), COLOR_BG_DARK)
    draw = ImageDraw.Draw(img)

    margin = 12
    draw.rectangle([(margin, margin), (width - margin, height - margin)], outline=COLOR_GOLD_PRIMARY, width=2)
    draw.rectangle([(margin + 5, margin + 5), (width - margin - 5, height - margin - 5)], outline=COLOR_GOLD_DARK, width=1)

    _draw_ornate_corner(draw, margin, margin, radius=28, quadrant=1)
    _draw_ornate_corner(draw, width - margin, margin, radius=28, quadrant=2)
    _draw_ornate_corner(draw, margin, height - margin, radius=28, quadrant=3)
    _draw_ornate_corner(draw, width - margin, height - margin, radius=28, quadrant=4)

    # Tiêu đề trải bài ở đỉnh
    font_title = _get_font(19, bold=True)
    title_text = title.upper()
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    t_w = bbox[2] - bbox[0]
    title_x = (width - t_w) // 2
    title_y = 22

    banner_pad_x = 42
    banner_pad_y = 5
    draw.rectangle(
        [(title_x - banner_pad_x, title_y - banner_pad_y), (title_x + t_w + banner_pad_x, title_y + 25)],
        fill=COLOR_BG_BANNER,
        outline=COLOR_GOLD_PRIMARY,
        width=1
    )

    _draw_sparkle_star(draw, title_x - 20, title_y + 10, size=8)
    _draw_sparkle_star(draw, title_x + t_w + 20, title_y + 10, size=8)

    draw.text((title_x, title_y), title_text, fill=COLOR_GOLD_LIGHT, font=font_title)

    return img


def _generate_procedural_card(card: TarotCard, target_w: int, target_h: int) -> Image.Image:
    """Vẽ lá bài nghệ thuật dự phòng nếu chưa có file ảnh gốc."""
    img = Image.new("RGBA", (target_w, target_h), (24, 18, 38))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(4, 4), (target_w - 4, target_h - 4)], outline=COLOR_GOLD_PRIMARY, width=2)
    draw.rectangle([(7, 7), (target_w - 7, target_h - 7)], outline=COLOR_GOLD_DARK, width=1)

    _draw_ornate_corner(draw, 7, 7, radius=10, quadrant=1)
    _draw_ornate_corner(draw, target_w - 7, 7, radius=10, quadrant=2)
    _draw_ornate_corner(draw, 7, target_h - 7, radius=10, quadrant=3)
    _draw_ornate_corner(draw, target_w - 7, target_h - 7, radius=10, quadrant=4)

    _draw_sparkle_star(draw, target_w // 2, int(target_h * 0.40), size=int(target_w * 0.20))

    font_roman = _get_font(max(9, int(target_h * 0.062)), bold=True)
    font_vi = _get_font(max(10, int(target_w * 0.078)), bold=True)
    font_en = _get_font(max(8, int(target_w * 0.062)))

    num_str = f"NO. {card.number}" if card.arcana != "Major" else f"ARCANA {card.number}"
    bbox_num = draw.textbbox((0, 0), num_str, font=font_roman)
    draw.text(((target_w - (bbox_num[2] - bbox_num[0])) // 2, int(target_h * 0.08)), num_str, fill=COLOR_GOLD_LIGHT, font=font_roman)

    bbox_vi = draw.textbbox((0, 0), card.name_vi, font=font_vi)
    draw.text(((target_w - (bbox_vi[2] - bbox_vi[0])) // 2, int(target_h * 0.70)), card.name_vi, fill=COLOR_GOLD_LIGHT, font=font_vi)

    bbox_en = draw.textbbox((0, 0), card.name_en, font=font_en)
    draw.text(((target_w - (bbox_en[2] - bbox_en[0])) // 2, int(target_h * 0.82)), card.name_en, fill=COLOR_MUTED, font=font_en)

    return img


def _load_and_prepare_card_image(drawn: DrawnCard, target_w: int, target_h: int) -> Image.Image:
    """Tải ảnh lá bài từ assets hoặc tạo procedural, xoay 180° nếu reversed."""
    card = drawn.card
    asset_path = ensure_card_asset(card)

    card_img = None
    if asset_path and asset_path.exists():
        try:
            with Image.open(asset_path) as raw_img:
                raw_rgb = raw_img.convert("RGBA")
                card_img = raw_rgb.resize((target_w, target_h), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"[TarotRenderer] Lỗi mở ảnh {asset_path}: {e}", flush=True)

    if card_img is None:
        card_img = _generate_procedural_card(card, target_w, target_h)

    if drawn.is_reversed:
        card_img = card_img.rotate(180)

    draw_c = ImageDraw.Draw(card_img)
    draw_c.rectangle([(0, 0), (target_w - 1, target_h - 1)], outline=COLOR_GOLD_PRIMARY, width=2)

    return card_img


def _draw_card_with_meta(
    canvas: Image.Image,
    drawn: DrawnCard,
    center_x: int,
    center_y: int,
    card_w: int,
    card_h: int,
    custom_pos_title: Optional[str] = None,
    font_size_scale: float = 1.0,
    wrap_name: bool = False
):
    """Vẽ 1 lá bài hoàn chỉnh kèm nhãn vị trí và tên lá bài trên canvas."""
    draw = ImageDraw.Draw(canvas)

    card_img = _load_and_prepare_card_image(drawn, card_w, card_h)
    top_left_x = center_x - card_w // 2
    top_left_y = center_y - card_h // 2

    # Drop shadow
    shadow = Image.new("RGBA", (card_w + 10, card_h + 10), (0, 0, 0, 150))
    canvas.paste(shadow, (top_left_x - 5, top_left_y - 2), shadow)

    canvas.paste(card_img, (top_left_x, top_left_y), card_img)

    # Position Header
    pos_title = custom_pos_title or drawn.position_title
    pos_font_size = max(10, int(12 * font_size_scale))
    font_pos = _get_font(pos_font_size, bold=True)
    bbox_pos = draw.textbbox((0, 0), pos_title, font=font_pos)
    pos_w = bbox_pos[2] - bbox_pos[0]
    pos_y = top_left_y - (pos_font_size + 9)

    draw.rectangle(
        [(center_x - pos_w // 2 - 5, pos_y - 2), (center_x + pos_w // 2 + 5, pos_y + pos_font_size + 3)],
        fill=(32, 24, 52, 230),
        outline=COLOR_GOLD_PRIMARY,
        width=1
    )
    draw.text((center_x - pos_w // 2, pos_y), pos_title, fill=COLOR_GOLD_LIGHT, font=font_pos)

    # Footer
    name_font_size = max(10, int(12 * font_size_scale))
    orient_font_size = max(9, int(10 * font_size_scale))
    font_name = _get_font(name_font_size, bold=True)
    font_orient = _get_font(orient_font_size, bold=True)

    orient_str = "[NGƯỢC]" if drawn.is_reversed else "[XUÔI]"
    orient_color = COLOR_REVERSED if drawn.is_reversed else COLOR_UPRIGHT
    bbox_orient = draw.textbbox((0, 0), orient_str, font=font_orient)
    orient_w = bbox_orient[2] - bbox_orient[0]

    footer_y = top_left_y + card_h + 4

    if wrap_name:
        vi_name = drawn.card.name_vi
        en_name = f"({drawn.card.name_en})"
        bbox_vi = draw.textbbox((0, 0), vi_name, font=font_name)
        bbox_en = draw.textbbox((0, 0), en_name, font=_get_font(max(8, int(10 * font_size_scale))))

        draw.text((center_x - (bbox_vi[2] - bbox_vi[0]) // 2, footer_y), vi_name, fill=COLOR_WHITE, font=font_name)
        draw.text((center_x - (bbox_en[2] - bbox_en[0]) // 2, footer_y + name_font_size + 1), en_name, fill=COLOR_MUTED, font=_get_font(max(8, int(10 * font_size_scale))))
        draw.text((center_x - orient_w // 2, footer_y + 2 * name_font_size + 2), orient_str, fill=orient_color, font=font_orient)
    else:
        card_name_str = f"{drawn.card.name_vi} ({drawn.card.name_en})"
        bbox_name = draw.textbbox((0, 0), card_name_str, font=font_name)
        name_w = bbox_name[2] - bbox_name[0]

        draw.text((center_x - name_w // 2, footer_y), card_name_str, fill=COLOR_WHITE, font=font_name)
        draw.text((center_x - orient_w // 2, footer_y + name_font_size + 2), orient_str, fill=orient_color, font=font_orient)


def render_1_card_spread(spread_key: str, drawn_cards: List[DrawnCard]) -> Image.Image:
    """Render layout cho trải bài 1 lá (daily, yes_no, single)."""
    spread_name = SPREAD_DEFINITIONS[spread_key]["name"]
    width = 520
    height = 760
    canvas = _draw_mystic_background(width, height, spread_name)

    card_w = 320
    card_h = 550
    center_x = width // 2
    center_y = 395

    _draw_card_with_meta(canvas, drawn_cards[0], center_x, center_y, card_w, card_h, font_size_scale=1.1)
    return canvas


def render_3_card_spread(spread_key: str, drawn_cards: List[DrawnCard]) -> Image.Image:
    """Render layout cho trải bài 3 lá hàng ngang (choices, ppf, mbs)."""
    spread_name = SPREAD_DEFINITIONS[spread_key]["name"]
    width = 980
    height = 640
    canvas = _draw_mystic_background(width, height, spread_name)

    card_w = 260
    card_h = 450
    spacing = 35
    start_x = (width - (3 * card_w + 2 * spacing)) // 2 + card_w // 2
    center_y = 345

    for i, drawn in enumerate(drawn_cards):
        cx = start_x + i * (card_w + spacing)
        _draw_card_with_meta(canvas, drawn, cx, center_y, card_w, card_h)

    return canvas


def render_5_card_spread(spread_key: str, drawn_cards: List[DrawnCard]) -> Image.Image:
    """
    Render layout cho trải bài 5 lá:
    - Nếu là 'two_paths': Cây phân nhánh (Decision Tree) với Lá 1 ở trên, 2 lá Nhánh A bên trái, 2 lá Nhánh B bên phải.
    - Nếu là 'horseshoe' hoặc khác: Cánh cung móng ngựa (Horseshoe arc).
    """
    spread_name = SPREAD_DEFINITIONS.get(spread_key, {}).get("name", "TRẢI BÀI 5 LÁ")

    if spread_key == "two_paths":
        width = 1140
        height = 840
        canvas = _draw_mystic_background(width, height, "TWO PATHS (SO SÁNH 2 LỰA CHỌN)")
        draw = ImageDraw.Draw(canvas)

        card_w = 150
        card_h = 258

        # 1. Lá 1: Bối cảnh (Ở đỉnh chính giữa)
        _draw_card_with_meta(canvas, drawn_cards[0], width // 2, 235, card_w, card_h, "LÁ 1: BỐI CẢNH", font_size_scale=1.0)

        # Hàm vẽ Banner nhánh cân đối tuyệt đối theo tọa độ tâm
        def _draw_branch_header(center_x: int, top_y: int, text: str, border_color, text_color):
            font_branch = _get_font(13, bold=True)
            bbox = draw.textbbox((0, 0), text, font=font_branch)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            pad_x = 26
            pad_y = 5
            box_left = center_x - text_w // 2 - pad_x
            box_right = center_x + text_w // 2 + pad_x
            box_top = top_y
            box_bottom = top_y + text_h + 2 * pad_y

            draw.rectangle([(box_left, box_top), (box_right, box_bottom)], fill=(22, 26, 48, 230), outline=border_color, width=2)
            star_y = (box_top + box_bottom) // 2
            _draw_sparkle_star(draw, box_left + 12, star_y, size=5, color=text_color)
            _draw_sparkle_star(draw, box_right - 12, star_y, size=5, color=text_color)

            text_x = center_x - text_w // 2
            text_y = box_top + pad_y - 1
            draw.text((text_x, text_y), text, fill=text_color, font=font_branch)

        # Nhánh A (Trái): Tâm giữa 2 lá là cx = 295
        center_a = 295
        _draw_branch_header(center_a, 405, "HƯỚNG ĐI A", COLOR_BRANCH_A, (130, 200, 255))
        _draw_card_with_meta(canvas, drawn_cards[1], 200, 580, card_w, card_h, "LÁ 2: THUẬN LỢI", font_size_scale=0.9, wrap_name=True)
        _draw_card_with_meta(canvas, drawn_cards[2], 390, 580, card_w, card_h, "LÁ 3: RỦI RO", font_size_scale=0.9, wrap_name=True)

        # Nhánh B (Phải): Tâm giữa 2 lá là cx = 845
        center_b = 845
        _draw_branch_header(center_b, 405, "HƯỚNG ĐI B", COLOR_BRANCH_B, (225, 160, 255))
        _draw_card_with_meta(canvas, drawn_cards[3], 750, 580, card_w, card_h, "LÁ 4: THUẬN LỢI", font_size_scale=0.9, wrap_name=True)
        _draw_card_with_meta(canvas, drawn_cards[4], 940, 580, card_w, card_h, "LÁ 5: RỦI RO", font_size_scale=0.9, wrap_name=True)

        return canvas

    else:
        # Layout Móng Ngựa (Horseshoe) hoặc 5 lá hình cánh cung
        width = 1200
        height = 700
        canvas = _draw_mystic_background(width, height, spread_name)

        card_w = 160
        card_h = 275

        positions = [
            (drawn_cards[0], 160, 290, "LÁ 1: QUÁ KHỨ"),
            (drawn_cards[1], 380, 385, "LÁ 2: HIỆN TẠI"),
            (drawn_cards[2], 600, 445, "LÁ 3: TÁC ĐỘNG ẨN"),
            (drawn_cards[3], 820, 385, "LÁ 4: TRỞ NGẠI"),
            (drawn_cards[4], 1040, 290, "LÁ 5: KẾT QUẢ"),
        ]

        for card, cx, cy, pos_title in positions:
            _draw_card_with_meta(canvas, card, cx, cy, card_w, card_h, pos_title, font_size_scale=0.95, wrap_name=True)

        return canvas


def render_celtic_cross_spread(drawn_cards: List[DrawnCard]) -> Image.Image:
    """
    Render layout Celtic Cross 10 lá chuẩn truyền thống với không gian chặt chẽ,
    cân đối hài hòa giữa Cụm Chữ Thập và Cột Quyền Trượng, không có khoảng trống thừa.
    """
    width = 1140
    height = 1000
    canvas = _draw_mystic_background(width, height, "CELTIC CROSS (TRẢI BÀI 10 LÁ)")

    # Kích thước từng lá bài: Tỷ lệ chuẩn Tarot
    card_w = 96
    card_h = 164

    # Cross Area (Bên trái): Tâm cx = 410, cy = 500
    cross_cx = 410
    cross_cy = 500

    # 1. Lá 1: Hiện tại (Trung tâm bên trái)
    _draw_card_with_meta(canvas, drawn_cards[0], cross_cx - 55, cross_cy, card_w, card_h, "LÁ 1: HIỆN TẠI", font_size_scale=0.85, wrap_name=True)

    # 2. Lá 2: Thách thức / Trở ngại (Đặt cạnh song song trung tâm bên phải)
    _draw_card_with_meta(canvas, drawn_cards[1], cross_cx + 55, cross_cy, card_w, card_h, "LÁ 2: THÁCH THỨC", font_size_scale=0.85, wrap_name=True)

    # 3. Lá 4: Quá khứ gần (Bên trái của Cross)
    _draw_card_with_meta(canvas, drawn_cards[3], cross_cx - 230, cross_cy, card_w, card_h, "LÁ 4: QUÁ KHỨ", font_size_scale=0.85, wrap_name=True)

    # 4. Lá 6: Tương lai gần (Bên phải của Cross)
    _draw_card_with_meta(canvas, drawn_cards[5], cross_cx + 230, cross_cy, card_w, card_h, "LÁ 6: TƯƠNG LAI", font_size_scale=0.85, wrap_name=True)

    # 5. Lá 5: Mục tiêu / Ý thức (Trên đỉnh của Cross)
    _draw_card_with_meta(canvas, drawn_cards[4], cross_cx, cross_cy - 245, card_w, card_h, "LÁ 5: Ý THỨC", font_size_scale=0.85, wrap_name=True)

    # 6. Lá 3: Căn nguyên / Tiềm thức (Dưới đáy của Cross)
    _draw_card_with_meta(canvas, drawn_cards[2], cross_cx, cross_cy + 245, card_w, card_h, "LÁ 3: TIỀM THỨC", font_size_scale=0.85, wrap_name=True)

    # Staff Area (Cột 4 lá bên phải): staff_x = 960
    staff_x = 960
    staff_positions = [
        (drawn_cards[9], 140, "LÁ 10: KẾT QUẢ"),
        (drawn_cards[8], 380, "LÁ 9: HY VỌNG & SỢ"),
        (drawn_cards[7], 620, "LÁ 8: MÔI TRƯỜNG"),
        (drawn_cards[6], 860, "LÁ 7: THÁI ĐỘ"),
    ]

    for card, sy, custom_title in staff_positions:
        _draw_card_with_meta(canvas, card, staff_x, sy, card_w, card_h, custom_title, font_size_scale=0.85, wrap_name=True)

    return canvas


def render_spread_to_bytes(spread_key: str, drawn_cards: List[DrawnCard]) -> io.BytesIO:
    """Tạo ảnh trải bài và đóng gói vào io.BytesIO gửi thẳng lên Discord."""
    count = len(drawn_cards)
    if count == 1:
        img = render_1_card_spread(spread_key, drawn_cards)
    elif count == 3:
        img = render_3_card_spread(spread_key, drawn_cards)
    elif count == 5:
        img = render_5_card_spread(spread_key, drawn_cards)
    elif count == 10 or spread_key == "celtic":
        img = render_celtic_cross_spread(drawn_cards)
    else:
        if count <= 2:
            img = render_1_card_spread(spread_key, drawn_cards)
        elif count <= 4:
            img = render_3_card_spread(spread_key, drawn_cards)
        elif count <= 6:
            img = render_5_card_spread(spread_key, drawn_cards)
        else:
            img = render_celtic_cross_spread(drawn_cards)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer
