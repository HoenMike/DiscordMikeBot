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
    """Eligibility is about trustworthy media *or* verified structured text.

    Proxies relying on Discord unfurl stay separate: a LayoutView has no
    message content or native link embed, so V2 cannot replace their player.
    """
    if filter_result.is_blocked:
        return False
    if post.media_type == "text":
        # A plain text social post is real content, not an invented preview.
        return bool(str(post.text or "").strip() and _safe_https(post.url))
    if post.media_type not in ("image", "gallery", "video"):
        return False
    if post.media_type == "video" and file is None:
        # An external video poster is NOT a playable video in MediaGallery.
        return False
    return bool(_media_sources(post, file, filter_result.should_spoiler_media))


def _new_panel(cog, payload: dict, *, colour: int, spoiler: bool = False):
    view = EmbedActionLayoutView(cog, payload)
    # One single compact Discord-native container holds the controls too.
    controls = view.children[0]
    view.remove_item(controls)
    panel = discord.ui.Container(
        accent_colour=discord.Colour(colour), spoiler=spoiler,
    )
    return view, panel, controls


def build_native_social_layout(
    cog, payload: dict, post: PostData, filter_result: NSFWFilterResult,
    *, reply_url: str, reply_author: str, file: discord.File | None = None,
) -> EmbedActionLayoutView:
    """Build the same compact card for media and verified text-only posts.

    File-backed videos retain playable attachments; no proxy link is ever
    copied to a TextDisplay in place of its real native Discord video player.
    LayoutView messages must never include content or embeds.
    """
    if not can_render_native_social(post, filter_result, file):
        raise ValueError("native social layout requires trustworthy post content")
    sources = _media_sources(post, file, filter_result.should_spoiler_media)
    info = PLATFORMS.get(post.platform, {})
    view, panel, controls = _new_panel(
        cog, payload, colour=info.get("color", 0x566477),
        spoiler=bool(filter_result.should_spoiler_media),
    )
    source_author = _plain(reply_author, 80)
    panel.add_item(discord.ui.TextDisplay(
        f"-# [Trả lời]({reply_url}) **{source_author}**"
    ))

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

    if sources:
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


def build_native_social_notice(
    cog, payload: dict, *,
    reply_url: str, reply_author: str, platform: str, hint: str,
) -> EmbedActionLayoutView:
    """One compact action-required notice, never a fake media preview.

    This card is only used when no working proxy/player was sent. If a
    Facebook/other proxy link *was* sent, retain its native video unfurl.
    """
    info = PLATFORMS.get(platform, {})
    view, panel, controls = _new_panel(
        cog, payload, colour=info.get("color", 0x566477),
    )
    panel.add_item(discord.ui.TextDisplay(
        f"-# [Trả lời]({reply_url}) **{_plain(reply_author, 80)}**"
    ))
    panel.add_item(discord.ui.TextDisplay(
        f"**{_plain(info.get('name', platform.capitalize()), 40)}**\n"
        f"{_plain(hint, 250)}"
    ))
    original = _safe_https(payload.get("url"))
    if original:
        panel.add_item(discord.ui.TextDisplay(
            f"-# [Xem liên kết gốc]({original})"
        ))
    panel.add_item(controls)
    view.add_item(panel)
    return view
