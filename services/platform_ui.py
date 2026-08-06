import discord
from utils.constants import PLATFORMS


class OriginalLinkView(discord.ui.View):
    """View chứa nút liên kết tới bài viết gốc trên nền tảng tương ứng.

    Sử dụng ButtonStyle.link nên không cần xử lý callback phía bot.
    Timeout được đặt None vì link button không chiếm tài nguyên interaction.
    """

    def __init__(self, platform_key: str, original_url: str):
        super().__init__(timeout=None)

        platform_info = PLATFORMS.get(platform_key)
        if not platform_info:
            return

        label = platform_info.get("button_label", f"Xem b\u1ea3n g\u1ed1c")

        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            label=label,
            url=original_url,
        ))


def create_platform_view(platform_key: str, original_url: str) -> discord.ui.View | None:
    """T\u1ea1o View v\u1edbi n\u00fat li\u00ean k\u1ebft t\u1edbi b\u00e0i vi\u1ebft g\u1ed1c theo n\u1ec1n t\u1ea3ng.

    Tr\u1ea3 v\u1ec1 None n\u1ebfu n\u1ec1n t\u1ea3ng kh\u00f4ng \u0111\u01b0\u1ee3c h\u1ed7 tr\u1ee3 ho\u1eb7c URL kh\u00f4ng h\u1ee3p l\u1ec7.
    """
    if not platform_key or not original_url:
        return None

    platform_info = PLATFORMS.get(platform_key)
    if not platform_info:
        return None

    return OriginalLinkView(platform_key, original_url)
