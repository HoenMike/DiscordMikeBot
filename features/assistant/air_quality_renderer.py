"""Deterministic, mobile-legible AQI PNG: only typed public model facts."""
from __future__ import annotations

import io
from PIL import Image, ImageDraw, ImageFont

from features.assistant.providers.air_quality import AirQualityFacts, aqi_label


def _font(size: int, bold: bool = False):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(filename, size)
    except OSError:
        return ImageFont.load_default()


def render_air_quality_png(facts: AirQualityFacts) -> io.BytesIO:
    if facts.status != "ok" or facts.aqi is None or facts.pm25 is None:
        raise ValueError("A verified typed model report is required")

    width, height = 1120, 800
    canvas = Image.new("RGB", (width, height), (19, 24, 35))
    draw = ImageDraw.Draw(canvas)
    fg = (232, 236, 245)
    muted = (164, 174, 193)
    border = (55, 66, 84)
    card = (29, 37, 52)
    accent = (109, 167, 241)
    warn = (
        (66, 188, 129) if facts.aqi <= 50 else
        (228, 192, 79) if facts.aqi <= 100 else
        (240, 145, 91) if facts.aqi <= 150 else
        (233, 99, 91)
    )
    headline = _font(35, True)
    label = _font(23)
    number = _font(62, True)
    small = _font(17)
    biglabel = _font(25, True)

    draw.text((54, 36), "CHẤT LƯỢNG KHÔNG KHÍ · BIÊN HÒA", font=headline, fill=fg)
    draw.text((54, 87), f"Mô hình Open-Meteo · {facts.model_time} (giờ Việt Nam)", font=label, fill=muted)
    for x in (54, 566):
        draw.rounded_rectangle((x, 148, x + 500, 345), radius=20, fill=card, outline=border, width=2)
    draw.text((81, 175), "US AQI · Dữ liệu mô hình", font=label, fill=muted)
    draw.text((81, 213), str(facts.aqi), font=number, fill=warn)
    draw.text((232, 264), aqi_label(facts.aqi), font=small, fill=fg)

    draw.text((594, 175), "Bụi mịn PM2.5 · Mô hình", font=label, fill=muted)
    draw.text((594, 213), f"{facts.pm25:g}", font=number, fill=fg)
    draw.text((790, 270), "µg/m³", font=label, fill=muted)

    draw.rounded_rectangle((54, 366, 1066, 703), radius=22, fill=card, outline=border, width=2)
    draw.text((83, 392), "XU HƯỚNG AQI DỰ BÁO TRONG NGÀY", font=biglabel, fill=fg)

    values = [v for _, v in facts.timeline]
    if len(values) >= 2:
        left, right = 112, 1002
        top, bottom = 476, 630
        upper = max(100, ((max(values) + 49) // 50) * 50)
        for frac in (0, .5, 1):
            y = round(bottom - (bottom - top) * frac)
            draw.line((left, y, right, y), fill=border, width=1)
            draw.text((68, y - 13), str(round(upper * frac)), font=small, fill=muted)
        coords = []
        for i, val in enumerate(values):
            x = left + i * (right - left) / max(1, len(values)-1)
            y = bottom - min(val, upper) / upper * (bottom-top)
            coords.append((round(x), round(y)))
        draw.line(coords, fill=accent, width=5, joint="curve")
        for i, (x, y) in enumerate(coords):
            draw.ellipse((x-5, y-5, x+5, y+5), fill=accent)
            if i in (0, len(coords)//2, len(coords)-1):
                draw.text((x-23, 645), facts.timeline[i][0], font=small, fill=muted)
    else:
        draw.text((86, 523), "Chưa đủ điểm dự báo để dựng biểu đồ.", font=label, fill=muted)

    draw.text((60, 730), "Không phải dữ liệu quan trắc trực tiếp tại trạm.", font=label, fill=(245, 194, 129))
    draw.text((60, 765), "Tham khảo để theo dõi xu hướng; đo tại trạm có thể khác.", font=small, fill=muted)
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
