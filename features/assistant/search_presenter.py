"""Compact, source-grounded Discord presentation for public Brave search.

Rendering is intentionally separated from provider/quota logic; snippets are
untrusted external text and must not act as Discord markup or mentions.
"""
from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import urlsplit

import discord
from core import constants as policy


def _plain(value: str, maximum: int) -> str:
    """Strip HTML formatting and normalize untrusted provider/LLM snippets."""
    clean = html.unescape(re.sub(r"</?[a-z][^>]*>", " ", str(value or ""), flags=re.I))
    clean = " ".join(clean.replace("\u200b", "").split())
    return clean[:maximum].rstrip()


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", (value or "").casefold())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").replace("đ", "d")


def _fuel_query(query: str) -> bool:
    folded = _fold(query)
    return "gia xang" in folded


def prioritize_sources(query: str, hits, maximum: int | None = None):
    """Order fuel answers toward the original publisher, not aggregators.

    This is a presentation preference, *not* a statement that any page contains
    today's verified price. The original Brave order is preserved for ties.
    """
    if maximum is None:
        maximum = policy.ASUMI_WEB_SEARCH_DISPLAY_SOURCES
    options = list(hits)
    if _fuel_query(query):
        primary = ("petrolimex.com.vn", "pvoil.com.vn", "moit.gov.vn")
        trusted = ("congthuong.vn", "topi.vn", "vietnamnet.vn")
        secondary = ("baomoi.com", "pricedancing.com")
        def order(hit):
            host = (urlsplit(hit.url).hostname or "").lower()
            def match(domain):
                return host == domain or host.endswith("." + domain)
            if any(match(d) for d in primary):
                return 0
            if any(match(d) for d in trusted):
                return 1
            if any(match(d) for d in secondary):
                return 3
            return 2
        options.sort(key=order)
    return tuple(options[:max(1, min(int(maximum), 3))])


def build_search_embed(query: str, hits, summary: str = "") -> discord.Embed:
    """One short answer followed by a maximum of three clearly linked sources."""
    title = _plain(query, 115) or "Tra cứu web"
    # Model citation indices are not Discord links. Sources are clickable below;
    # never leave unlinked [1]/[2]/[3] references in the answer.
    answer = re.sub(r"\[(?:[1-9]|10)\]", "", _plain(summary, 620))
    answer = " ".join(answer.split())
    if not answer:
        answer = (
            "Mình tìm được các nguồn tham khảo bên dưới, nhưng trích đoạn "
            "chưa đủ để xác minh một câu trả lời chính xác."
        )
    embed = discord.Embed(
        title=f"🔎 {title}",
        description=discord.utils.escape_mentions(answer)[:700],
        color=0x5888A8,
    )
    lines: list[str] = []
    for i, item in enumerate(prioritize_sources(query, hits), 1):
        label = discord.utils.escape_markdown(
            discord.utils.escape_mentions(_plain(item.title, 96))
        )
        domain = (urlsplit(item.url).hostname or "Nguồn web").removeprefix("www.")
        excerpt = discord.utils.escape_markdown(
            discord.utils.escape_mentions(_plain(item.description, 135))
        )
        entry = f"**{i}. [{label}]({item.url})** · `{domain}`"
        if excerpt:
            entry += f"\n{excerpt}"
        if len("\n\n".join([*lines, entry])) > 1010:
            break
        lines.append(entry)
    if lines:
        embed.add_field(name="Nguồn tham khảo", value="\n\n".join(lines), inline=False)
    note = "Brave Search · Mở link để xác minh nội dung gốc"
    if any(x in _fold(query) for x in ("hom nay", "moi nhat", "hien tai", "bay gio")):
        note = "Brave Search · Trích đoạn có thể chưa cập nhật tức thời"
    embed.set_footer(text=note)
    return embed


def build_verified_fuel_embed(query: str, report) -> discord.Embed:
    """Show actual dated first-party prices, not search-result excerpts.

    The date is an *effective-from* timestamp, not a claim that a future
    adjustment cannot exist. Only call for parser-validated official pages.
    """
    if report.status != "ok" or not report.effective_at or not report.rows:
        raise ValueError("Verified source prices required")
    effective = report.effective_at.strftime("%H:%M ngày %d/%m/%Y")
    heading = f"**Bảng giá PVOIL công bố — hiệu lực từ {effective}**"
    embed = discord.Embed(
        title=f"⛽ {_plain(query, 105) or 'Giá xăng dầu'}",
        description=heading + "\n"
        + "\n".join(
            f"• {discord.utils.escape_markdown(row.label)}: "
            f"**{row.vnd_per_liter:,} đ/lít**".replace(",", ".")
            for row in report.rows
        ),
        color=0x4685A1,
    )
    embed.add_field(
        name="Nguồn xác minh",
        value=f"[PVOIL — Bảng giá xăng dầu]({report.source_url})",
        inline=False,
    )
    embed.set_footer(
        text="Đã đọc bảng giá PVOIL trực tiếp · Ngày hiệu lực không phải ngày truy vấn"
    )
    return embed


def build_weather_embed(query: str, report) -> discord.Embed:
    """Current temperature + today's forecast; keep AQI out of weather."""
    if report.status != "ok" or report.temp_c is None:
        raise ValueError("Current weather facts required")

    def temp(v):
        return f"{v:.0f}°C" if v is not None else "Chưa có"
    answer = f"**{temp(report.temp_c)} · {report.condition}**"
    if report.feels_c is not None:
        answer += f"\nCảm giác như **{temp(report.feels_c)}**"
    if report.humidity_pct is not None:
        answer += f" · Độ ẩm **{report.humidity_pct}%**"
    embed = discord.Embed(
        title=f"🌤️ Thời tiết {report.place} — hôm nay",
        description=answer,
        color=0x4A91AE,
    )
    embed.add_field(
        name="Trong ngày",
        value=f"Cao nhất **{temp(report.high_c)}** · "
              f"Thấp nhất **{temp(report.low_c)}**",
        inline=False,
    )
    if report.rain_probability_pct is not None:
        rain = f"Xác suất mưa cao nhất **{report.rain_probability_pct}%**"
        if report.rain_mm is not None:
            rain += f" · Lượng mưa dự báo **{report.rain_mm:g} mm**"
        embed.add_field(name="Mưa", value=rain, inline=False)
    embed.add_field(
        name="Nguồn dự báo",
        value="[Open-Meteo](https://open-meteo.com/)",
        inline=False,
    )
    embed.set_footer(
        text=f"Thời điểm dữ liệu: {report.measured_at.replace('T', ' ')} (giờ VN) · Dự báo có thể thay đổi"
    )
    return embed


def build_aggregated_fuel_embed(query: str, report) -> discord.Embed:
    """Community-source facts, prominently labeled as independently unverified.

    These are structured figures with an explicit price date from a third-party
    aggregator, NOT a copy of an official PVOIL page or the live price at a pump.
    """
    if report.status != "ok" or not report.effective_date or not report.rows:
        raise ValueError("Dated aggregated fuel prices required")
    from datetime import date
    date_label = date.fromisoformat(report.effective_date).strftime("%d/%m/%Y")
    embed = discord.Embed(
        title=f"⛽ {_plain(query, 105) or 'Giá xăng dầu'}",
        description=(
            f"**Bảng giá tham khảo (Vùng 1) · kỳ {date_label}**\n"
            + "\n".join(
                f"• {discord.utils.escape_markdown(label)}: "
                f"**{value:,} đ/lít**".replace(",", ".")
                for label, value in report.rows
            )
        ),
        color=0x6985AA,
    )
    embed.add_field(
        name="Nguồn dữ liệu",
        value=f"[{discord.utils.escape_markdown(report.provider)} — dữ liệu tổng hợp]({report.source_url})",
        inline=False,
    )
    embed.set_footer(
        text=(
            "Nguồn tổng hợp, chưa kiểm chứng trực tiếp với PVOIL · "
            "Ngày kỳ giá không phải giờ cập nhật trực tiếp"
        )
    )
    return embed
