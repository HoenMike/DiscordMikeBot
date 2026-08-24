import discord
from utils.constants import PLATFORMS


def create_platform_view(platform_key: str, original_url: str) -> discord.ui.View | None:
    """Tạo discord.ui.View chứa button link tới bài viết gốc.

    Button sử dụng nhãn được cấu hình trong PLATFORMS (button_label).
    Nếu platform_key không tồn tại hoặc không có button_label,
    sử dụng nhãn mặc định "Xem bài viết gốc".
    Trả về None nếu không có URL.
    """
    if not original_url:
        return None

    platform_info = PLATFORMS.get(platform_key, {})
    label = platform_info.get("button_label", "Xem bài viết gốc")

    view = discord.ui.View()
    button = discord.ui.Button(
        label=label,
        url=original_url,
        style=discord.ButtonStyle.link,
    )
    view.add_item(button)
    return view
