"""Optional compact Components V2 presentation for media-backed social previews.

This is a *renderer*, not a new scraping/proxy provider. In particular, native
Facebook proxy URLs must remain ordinary message content to let Discord unfurl
them. Never substitute a Facebook thumbnail for a playable video.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import discord

from features.embed.builder import PostData, NSFWFilterResult
from features.embed.constants import PLATFORMS, format_count
from features.embed.ui import EmbedActionLayoutView

MAX_MEDIA_ITEMS = 4


def _safe_https(value: str | None) -> str | None:
    url = str(value or "").strip()
    if len(url) > 1600 or any(ch in url for ch in "<>()[]\r\n\t "):
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    return url


def _plain(value: str | None, maximum: int) -> str:
    # Providers are untrusted; they must not supply markdown or ping anyone.
    normalized = " ".join(str(value or "").split())
    normalized = discord.utils.escape_mentions(normalized)
    return discord.utils.escape_markdown(normalized[:maximum])


def _media_sources(post: PostData, file: discord.File | None, spoiler: bool) -> list[str]:
    if file is not None:
        # Discord will own the attachment. Do not point a V2 gallery at an
        # unauthenticated video CDN or render a poster as though it were video.
        if post.media_type == "video" and not file.filename.lower().endswith((".mp4", ".webm", ".mov")):
            return []
        return [f"attachment://{file.filename}"]

    if spoiler or post.media_type not in ("image", "gallery"):
        return []
    return [url for raw in post.media_urls[:MAX_MEDIA_ITEMS]
            if (url := _safe_https(raw)) is not None]


def can_render_native_social(
    post: PostData, filter_result: NSFWFilterResult, file: discord.File | None,
) -> bool:
    """The new layout is eligible only when its media is not merely a poster."""
    if filter_result.is_blocked or post.media_type not in ("image", "gallery", "video"):
        return False
    if post.media_type == "video" and file is None:
        return False
    return bool(_media_sources(post, file, filter_result.should_spoiler_media))


def build_native_social_layout(
    cog, payload: dict, post: PostData, filter_result: NSFWFilterResult,
    *, reply_url: str, reply_author: str, file: discord.File | None = None,
) -> EmbedActionLayoutView:
    """Construct a compact Discord-native card and reuse legacy owner actions.

    Call only after can_render_native_social has accepted the media.
    A LayoutView message must be sent with view (+ optional file) and NEVER
    with content/embeds.
    """
    sources = _media_sources(post, file, filter_result.should_spoiler_media)
    if not sources:
        raise ValueError("native social layout requires renderable media")

    view = EmbedActionLayoutView(cog, payload)
    # The controls are constructed first by the shared action mixin. Move their
    # ActionRow into the container so the entire preview occupies one card.
    controls = view.children[0]
    view.remove_item(controls)

    info = PLATFORMS.get(post.platform, {})
    panel = discord.ui.Container(
        accent_colour=discord.Colour(info.get("color", 0x566477)),
        spoiler=bool(filter_result.should_spoiler_media),
    )
    source_author = _plain(reply_author, 80)
    header = f"-# [Trả lời]({reply_url}) **{source_author}**"
    panel.add_item(discord.ui.TextDisplay(header))

    heading = f"**{_plain(post.author or info.get('name', 'Bài viết'), 150)}**"
    description = _plain(post.text, 600)
    if description:
        heading += "\n" + description
    avatar = _safe_https(post.author_avatar)
    if avatar and not filter_result.should_spoiler_media:
        panel.add_item(discord.ui.Section(
            discord.ui.TextDisplay(heading),
            accessory=discord.ui.Thumbnail(avatar),
        ))
    else:
        panel.add_item(discord.ui.TextDisplay(heading))

    panel.add_item(discord.ui.MediaGallery(*[
        discord.MediaGalleryItem(
            media=source, spoiler=bool(filter_result.should_spoiler_media),
            description=_plain(post.text or post.author, 200) or None,
        ) for source in sources
    ]))

    stats = []
    if post.likes is not None:
        stats.append(f"👍 {format_count(post.likes)}")
    if post.comments is not None:
        stats.append(f"💬 {format_count(post.comments)}")
    if post.retweets is not None:
        stats.append(f"↗ {format_count(post.retweets)}")
    if stats:
        panel.add_item(discord.ui.TextDisplay("-# " + "  ·  ".join(stats)))

    original = _safe_https(payload.get("url")) or _safe_https(post.url)
    footer = _plain(info.get("name", post.platform.capitalize()), 35)
    panel.add_item(discord.ui.TextDisplay(
        f"-# {footer}" + (f" · [Xem bài gốc]({original})" if original else "")
    ))
    panel.add_item(controls)
    view.add_item(panel)
    return view
