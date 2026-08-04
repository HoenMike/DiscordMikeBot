import discord
from services.platform_fetchers import PostData
from services.nsfw_filter import NSFWFilterResult
from utils.constants import PLATFORMS, format_count

MAX_TEXT_LENGTH = 1000
MAX_GALLERY_DISPLAY = 4


def build_embed(post: PostData, filter_result: NSFWFilterResult) -> discord.Embed | None:
    if filter_result.is_blocked:
        return None

    platform_info = PLATFORMS.get(post.platform)
    if not platform_info:
        return None

    embed = discord.Embed(
        color=platform_info["color"],
        url=post.url,
    )

    author_kwargs = {"name": post.author}
    if post.author_url:
        author_kwargs["url"] = post.author_url
    if post.author_avatar:
        author_kwargs["icon_url"] = post.author_avatar
    embed.set_author(**author_kwargs)

    description_parts = []
    if filter_result.warning:
        description_parts.append(f"**{filter_result.warning}**\n")

    if post.text:
        text = post.text
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "..."

        if post.is_spoiler and not text.startswith("||"):
            text = f"||{text}||"

        description_parts.append(text)

    if post.media_type == "video":
        description_parts.append("\n**Video**")
    elif post.media_type == "gallery" and len(post.media_urls) > 1:
        description_parts.append(f"\n**{len(post.media_urls)} ảnh**")

    if description_parts:
        embed.description = "\n".join(description_parts)

    if post.media_urls and not filter_result.should_spoiler_media:
        embed.set_image(url=post.media_urls[0])

    stats_parts = []
    if post.likes is not None:
        stats_parts.append(f"Lượt thích: {format_count(post.likes)}")
    if post.comments is not None:
        stats_parts.append(f"Bình luận: {format_count(post.comments)}")
    if post.retweets is not None:
        stats_parts.append(f"Chia sẻ: {format_count(post.retweets)}")

    if stats_parts:
        embed.add_field(
            name="Tương tác",
            value=" | ".join(stats_parts),
            inline=False,
        )

    embed.set_footer(
        text=platform_info["footer_text"],
        icon_url=platform_info.get("icon_url"),
    )

    return embed


def build_gallery_embeds(post: PostData, filter_result: NSFWFilterResult) -> list[discord.Embed]:
    if filter_result.is_blocked or not post.media_urls or filter_result.should_spoiler_media:
        main = build_embed(post, filter_result)
        return [main] if main else []

    platform_info = PLATFORMS.get(post.platform)
    if not platform_info:
        return []

    embeds = []
    main_embed = build_embed(post, filter_result)
    if main_embed:
        embeds.append(main_embed)

    for img_url in post.media_urls[1:MAX_GALLERY_DISPLAY]:
        extra_embed = discord.Embed(url=post.url, color=platform_info["color"])
        extra_embed.set_image(url=img_url)
        embeds.append(extra_embed)

    return embeds
