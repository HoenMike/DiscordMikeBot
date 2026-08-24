import discord
from services.platform_fetchers import PostData
from utils.constants import PLATFORMS, format_count

MAX_TEXT_LENGTH = 1000
MAX_GALLERY_DISPLAY = 4


class NSFWFilterResult:
    def __init__(self, post: PostData | None, should_spoiler_media: bool = False, warning: str | None = None):
        self.post = post
        self.should_spoiler_media = should_spoiler_media
        self.warning = warning

    @property
    def is_blocked(self) -> bool:
        return self.post is None


class NSFWFilter:
    """Bộ lọc nội dung nhạy cảm (NSFW) dựa trên cấu hình máy chủ/kênh Discord."""
    def process(self, post: PostData, channel: discord.TextChannel | discord.Thread, config: dict) -> NSFWFilterResult:
        nsfw_mode = config.get("nsfw_mode", "spoiler")

        is_nsfw_channel = getattr(channel, "is_nsfw", lambda: False)() if callable(getattr(channel, "is_nsfw", None)) else getattr(channel, "is_nsfw", False)

        if is_nsfw_channel or (not post.is_nsfw and not post.is_spoiler):
            return NSFWFilterResult(post=post, should_spoiler_media=False)

        if post.is_spoiler and post.text:
            post.text = f"||{post.text}||"

        if post.is_nsfw:
            if nsfw_mode == "block":
                return NSFWFilterResult(post=None, warning="Nội dung NSFW đã bị chặn theo cài đặt máy chủ.")
            elif nsfw_mode == "spoiler":
                return NSFWFilterResult(
                    post=post,
                    should_spoiler_media=True,
                    warning="Nội dung nhạy cảm (NSFW)"
                )
            else:
                return NSFWFilterResult(post=post, should_spoiler_media=False)

        return NSFWFilterResult(post=post, should_spoiler_media=False)


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

    # Đặt ảnh xem trước (ưu tiên thumbnail_url cho video vì Discord embed không nhận link video MP4 trong set_image)
    image_url_to_set = post.thumbnail_url if post.media_type == "video" else (post.media_urls[0] if post.media_urls else None)
    if not image_url_to_set and post.media_urls and not post.media_urls[0].lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
        image_url_to_set = post.media_urls[0]

    if image_url_to_set and not filter_result.should_spoiler_media:
        embed.set_image(url=image_url_to_set)

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
