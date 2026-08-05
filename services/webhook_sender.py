import discord

from utils.constants import sanitize_username

# Cache webhook theo channel ID de tranh tao lai moi lan
_webhook_cache: dict[int, discord.Webhook] = {}

WEBHOOK_NAME = "MikeDaBot Proxy"


async def get_or_create_webhook(channel: discord.TextChannel) -> discord.Webhook | None:
    """Tim hoac tao webhook thuoc bot trong kenh.

    Uu tien su dung webhook da cache. Neu chua co, tim trong danh sach webhook
    cua kenh. Neu khong tim thay, tao moi.
    Tra ve None neu khong co quyen manage_webhooks.
    """
    channel_id = channel.id

    # Kiem tra cache truoc
    cached = _webhook_cache.get(channel_id)
    if cached is not None:
        try:
            # Xac nhan webhook van con hoat dong
            await cached.fetch()
            return cached
        except (discord.NotFound, discord.HTTPException):
            # Webhook da bi xoa hoac khong truy cap duoc, xoa cache
            _webhook_cache.pop(channel_id, None)

    try:
        webhooks = await channel.webhooks()
    except discord.Forbidden:
        print(
            f"[WebhookSender] Khong co quyen manage_webhooks trong kenh #{channel.name} "
            f"(ID: {channel_id})",
            flush=True,
        )
        return None
    except discord.HTTPException as e:
        print(
            f"[WebhookSender] Loi khi lay danh sach webhook: kenh #{channel.name} - {e}",
            flush=True,
        )
        return None

    # Tim webhook da ton tai thuoc bot
    bot_user_id = channel.guild.me.id if channel.guild.me else None
    for wh in webhooks:
        if wh.name == WEBHOOK_NAME and wh.user and wh.user.id == bot_user_id:
            _webhook_cache[channel_id] = wh
            return wh

    # Tao webhook moi
    try:
        new_wh = await channel.create_webhook(name=WEBHOOK_NAME)
        _webhook_cache[channel_id] = new_wh
        print(
            f"[WebhookSender] Da tao webhook moi trong kenh #{channel.name} "
            f"(ID: {channel_id})",
            flush=True,
        )
        return new_wh
    except discord.Forbidden:
        print(
            f"[WebhookSender] Khong co quyen tao webhook trong kenh #{channel.name}",
            flush=True,
        )
        return None
    except discord.HTTPException as e:
        print(
            f"[WebhookSender] Loi khi tao webhook: kenh #{channel.name} - {e}",
            flush=True,
        )
        return None


async def send_via_webhook(
    channel: discord.TextChannel,
    user: discord.Member | discord.User,
    content: str | None = None,
    embeds: list[discord.Embed] | None = None,
    file: discord.File | None = None,
) -> bool:
    """Gui tin nhan qua webhook, gia lap nguoi dung goc.

    Su dung sanitize_username() de xu ly ten hien thi.
    Tra ve True neu gui thanh cong, False neu that bai.
    Neu webhook khong kha dung, fallback sang channel.send().
    """
    safe_name = sanitize_username(user.display_name)
    avatar_url = user.display_avatar.url if user.display_avatar else None

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

            await webhook.send(**kwargs)
            return True

        except discord.HTTPException as e:
            print(
                f"[WebhookSender] Loi khi gui qua webhook: {e}",
                flush=True,
            )
            # Xoa cache neu webhook bi loi
            _webhook_cache.pop(channel.id, None)

    # Fallback: gui truc tiep qua kenh
    print(
        f"[WebhookSender] Fallback sang channel.send() cho kenh #{channel.name}",
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

        if kwargs:
            await channel.send(**kwargs)
            return True
        return False

    except discord.HTTPException as e:
        print(
            f"[WebhookSender] Loi khi fallback channel.send(): {e}",
            flush=True,
        )
        return False


def invalidate_webhook_cache(channel_id: int) -> None:
    """Xoa webhook khoi cache (su dung khi kenh bi xoa hoac cau hinh thay doi)."""
    _webhook_cache.pop(channel_id, None)
