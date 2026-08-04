import discord
from services.platform_fetchers import PostData


class NSFWFilterResult:
    def __init__(self, post: PostData | None, should_spoiler_media: bool = False, warning: str | None = None):
        self.post = post
        self.should_spoiler_media = should_spoiler_media
        self.warning = warning

    @property
    def is_blocked(self) -> bool:
        return self.post is None


class NSFWFilter:
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
