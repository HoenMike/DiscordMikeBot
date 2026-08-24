import discord
from utils.constants import PLATFORMS, remove_query_params


def create_platform_view(platform_key: str, original_url: str) -> discord.ui.View | None:
    """Tạo discord.ui.View chứa button link tới bài viết gốc.

    Button sử dụng nhãn được cấu hình trong PLATFORMS (button_label).
    Nếu platform_key không tồn tại hoặc không có button_label,
    sử dụng nhãn mặc định "Xem bài viết gốc".
    Tự động làm sạch URL để không vượt quá giới hạn 512 ký tự của Discord button.
    Trả về None nếu không có URL.
    """
    if not original_url:
        return None

    # Làm sạch URL và bỏ query params thừa nếu quá dài
    clean_url = remove_query_params(original_url)
    if len(clean_url) > 512:
        clean_url = original_url.split("?")[0]

    # Discord giới hạn URL trong Link Button tối đa 512 ký tự
    if len(clean_url) > 512 or not clean_url.startswith(("http://", "https://")):
        return None

    platform_info = PLATFORMS.get(platform_key, {})
    label = platform_info.get("button_label", "Xem bài viết gốc")

    view = discord.ui.View()
    button = discord.ui.Button(
        label=label,
        url=clean_url,
        style=discord.ButtonStyle.link,
    )
    view.add_item(button)
    return view

