import re
import discord

# Cache webhook theo channel ID để tránh tạo lại mỗi lần gửi.
_webhook_cache: dict[int, discord.Webhook] = {}

WEBHOOK_NAME = "MikeDaBot Proxy"

# Giới hạn ký tự tối đa cho content gửi qua Discord API
_MAX_CONTENT_LENGTH = 2000


def sanitize_username(display_name: str) -> str:
    """Thay thế 'discord' trong tên hiển thị để tránh API từ chối webhook.

    Discord API từ chối webhook message khi username chứa từ 'discord'
    (không phân biệt hoa thường). Thay thế bằng ký tự tương tự về hình thức
    (U+0257, Latin small letter d with hook) để giữ nguyên giao diện.
    """
    if not display_name:
        return "User"
    sanitized = re.sub(r"(?i)discord", "discor\u0257", display_name)
    sanitized = sanitized.strip()
    if not sanitized:
        return "User"
    return sanitized[:80]


def _truncate_content(content: str) -> str:
    """Cắt ngắn content nếu vượt quá giới hạn 2000 ký tự của Discord."""
    if len(content) <= _MAX_CONTENT_LENGTH:
        return content
    return content[:_MAX_CONTENT_LENGTH - 3] + "..."


async def get_or_create_webhook(channel: discord.TextChannel) -> discord.Webhook | None:
    """Tìm hoặc tạo webhook thuộc bot trong kênh.

    Ưu tiên sử dụng webhook đã cache. Nếu chưa có, tìm trong danh sách webhook
    của kênh. Nếu không tìm thấy, tạo mới.
    Trả về None nếu không có quyền manage_webhooks hoặc kênh không hỗ trợ.
    """
    if not hasattr(channel, "webhooks") or not hasattr(channel, "create_webhook"):
        return None

    channel_id = channel.id

    # Kiểm tra cache trước, không gọi fetch() xác nhận để giảm request thừa
    cached = _webhook_cache.get(channel_id)
    if cached is not None:
        return cached

    try:
        webhooks = await channel.webhooks()
    except discord.Forbidden:
        print(
            f"[WebhookSender] Không có quyền manage_webhooks trong kênh #{getattr(channel, 'name', channel_id)} "
            f"(ID: {channel_id})",
            flush=True,
        )
        return None
    except discord.HTTPException as e:
        print(
            f"[WebhookSender] Lỗi khi lấy danh sách webhook: kênh #{getattr(channel, 'name', channel_id)} - {e}",
            flush=True,
        )
        return None

    # Tìm webhook đã tồn tại thuộc bot
    bot_user_id = channel.guild.me.id if (channel.guild and channel.guild.me) else None
    for wh in webhooks:
        if wh.name == WEBHOOK_NAME and wh.user and wh.user.id == bot_user_id:
            _webhook_cache[channel_id] = wh
            return wh

    # Tạo webhook mới
    try:
        new_wh = await channel.create_webhook(name=WEBHOOK_NAME)
        _webhook_cache[channel_id] = new_wh
        print(
            f"[WebhookSender] Đã tạo webhook mới trong kênh #{getattr(channel, 'name', channel_id)} "
            f"(ID: {channel_id})",
            flush=True,
        )
        return new_wh
    except discord.Forbidden:
        print(
            f"[WebhookSender] Không có quyền tạo webhook trong kênh #{getattr(channel, 'name', channel_id)}",
            flush=True,
        )
        return None
    except discord.HTTPException as e:
        print(
            f"[WebhookSender] Lỗi khi tạo webhook: kênh #{getattr(channel, 'name', channel_id)} - {e}",
            flush=True,
        )
        return None


async def send_via_webhook(
    channel: discord.TextChannel,
    user: discord.Member | discord.User,
    content: str | None = None,
    embeds: list[discord.Embed] | None = None,
    file: discord.File | None = None,
    view: discord.ui.View | None = None,
    original_message: discord.Message | None = None,
) -> bool:
    """Gửi tin nhắn qua webhook, giả lập người dùng gốc.

    Sử dụng sanitize_username() để xử lý tên hiển thị.
    Nếu content vượt quá 2000 ký tự, tự động cắt ngắn.
    Nếu webhook không khả dụng, fallback sang message.reply() (nếu có)
    hoặc channel.send().
    Trả về True nếu gửi thành công, False nếu thất bại.
    """
    safe_name = sanitize_username(user.display_name)
    avatar_url = user.display_avatar.url if user.display_avatar else None

    # Cắt ngắn content nếu cần
    if content:
        content = _truncate_content(content)

    webhook = await get_or_create_webhook(channel)

    if webhook is not None:
        try:
            kwargs = {
                "username": safe_name,
                "avatar_url": avatar_url,
                "wait": True,
            }
            if content:
                kwargs["content"] = content
            if embeds:
                kwargs["embeds"] = embeds
            if file:
                kwargs["file"] = file
            if view:
                kwargs["view"] = view

            try:
                await webhook.send(**kwargs)
                return True
            except discord.HTTPException as e:
                if view is not None and ("components" in str(e).lower() or e.code == 50035):
                    kwargs.pop("view", None)
                    await webhook.send(**kwargs)
                    return True
                raise e

        except discord.NotFound:
            # Webhook đã bị xoá, xoá cache và thử tạo lại
            _webhook_cache.pop(channel.id, None)
            print(
                f"[WebhookSender] Webhook đã bị xoá, đang thử tạo lại cho kênh #{getattr(channel, 'name', channel.id)}",
                flush=True,
            )

        except discord.HTTPException as e:
            print(
                f"[WebhookSender] Lỗi khi gửi qua webhook: {e}",
                flush=True,
            )
            # Xoá cache nếu webhook bị lỗi
            _webhook_cache.pop(channel.id, None)

    # Fallback: ưu tiên reply() vào tin nhắn gốc nếu có
    if original_message is not None:
        print(
            f"[WebhookSender] Fallback sang message.reply() cho kênh #{getattr(channel, 'name', channel.id)}",
            flush=True,
        )
        try:
            kwargs = {}
            if content:
                kwargs["content"] = content
            if embeds:
                kwargs["embeds"] = embeds
            if file:
                kwargs["file"] = file
            if view:
                kwargs["view"] = view

            try:
                await original_message.reply(**kwargs, mention_author=False)
                return True
            except discord.HTTPException as e:
                if view is not None and ("components" in str(e).lower() or e.code == 50035):
                    kwargs.pop("view", None)
                    await original_message.reply(**kwargs, mention_author=False)
                    return True
                raise e

        except discord.HTTPException as e:
            print(
                f"[WebhookSender] Lỗi khi fallback message.reply(): {e}",
                flush=True,
            )

    # Fallback cuối cùng: gửi trực tiếp qua kênh
    print(
        f"[WebhookSender] Fallback sang channel.send() cho kênh #{getattr(channel, 'name', channel.id)}",
        flush=True,
    )
    try:
        kwargs = {}
        if content:
            kwargs["content"] = content
        if embeds:
            kwargs["embeds"] = embeds
        if file:
            kwargs["file"] = file
        if view:
            kwargs["view"] = view

        if kwargs:
            try:
                await channel.send(**kwargs)
                return True
            except discord.HTTPException as e:
                if view is not None and ("components" in str(e).lower() or e.code == 50035):
                    kwargs.pop("view", None)
                    await channel.send(**kwargs)
                    return True
                raise e
        return False

    except discord.HTTPException as e:
        print(
            f"[WebhookSender] Lỗi khi fallback channel.send(): {e}",
            flush=True,
        )
        return False


def invalidate_webhook_cache(channel_id: int) -> None:
    """Xoá webhook khỏi cache (sử dụng khi kênh bị xoá hoặc cấu hình thay đổi)."""
    _webhook_cache.pop(channel_id, None)
