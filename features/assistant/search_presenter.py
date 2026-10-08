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


def prioritize_sources(query: str, hits, maximum: int = 3):
    """Order fuel answers toward the original publisher, not aggregators.

    This is a presentation preference, *not* a statement that any page contains
    today's verified price. The original Brave order is preserved for ties.
    """
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
