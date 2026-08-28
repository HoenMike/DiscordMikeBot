import io
import re
from collections import OrderedDict
import discord

# Cache webhook theo channel ID để tránh tạo lại mỗi lần gửi.
_webhook_cache: dict[int, discord.Webhook] = {}

WEBHOOK_NAME = "MikeDaBot Proxy"

# Giới hạn ký tự tối đa cho content gửi qua Discord API
_MAX_CONTENT_LENGTH = 2000


class BoundedDict(OrderedDict):
    """Dictionary có giới hạn kích thước tối đa (LRU eviction)."""
    def __init__(self, max_size: int = 10000):
        super().__init__()
        self.max_size = max_size

    def __setitem__(self, key, value):
        if len(self) >= self.max_size:
            self.popitem(last=False)
        super().__setitem__(key, value)


# Cache lưu mapping message_id của Webhook -> (user_id, display_name) của người gửi gốc
_embed_message_authors = BoundedDict(max_size=10000)


def register_embed_message(message_id: int, user_id: int, user_name: str = "") -> None:
    """Ghi nhận message_id do bot/webhook gửi đại diện cho người dùng."""
    _embed_message_authors[message_id] = (user_id, user_name)


def get_embed_message_author(message_id: int) -> tuple[int, str] | None:
    """Lấy thông tin người dùng gốc đã gửi tin nhắn embed này."""
    return _embed_message_authors.get(message_id)


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
    files: list[discord.File] | None = None,
    view: discord.ui.View | None = None,
    original_message: discord.Message | None = None,
) -> bool:
    """Gửi tin nhắn qua webhook, giả lập người dùng gốc.

    - Giữ nguyên toàn bộ ảnh/tệp đính kèm từ original_message.
    - Giữ nguyên ngữ cảnh trả lời (reply) nếu original_message đang reply một tin nhắn khác.
    - Ghi nhận ID tin nhắn đã gửi để phục vụ chuyển tiếp thông báo khi người khác reply.
    - Nếu webhook không khả dụng, fallback sang message.reply() hoặc channel.send().
    """
    safe_name = sanitize_username(user.display_name)
    avatar_url = user.display_avatar.url if user.display_avatar else None

    # 1. Thu thập toàn bộ file cần gửi (bao gồm cả file tạo bởi bot và attachments từ tin nhắn gốc)
    all_files: list[discord.File] = []
    if files:
        all_files.extend(files)
    if file:
        all_files.append(file)

    # Đọc và đính kèm lại toàn bộ ảnh/file từ tin nhắn gốc của người dùng
    if original_message and original_message.attachments:
        for att in original_message.attachments:
            try:
                # Giới hạn file tối đa 25MB để tránh vượt giới hạn upload của Discord
                if att.size is None or att.size <= 25 * 1024 * 1024:
                    att_bytes = await att.read()
                    all_files.append(
                        discord.File(
                            fp=io.BytesIO(att_bytes),
                            filename=att.filename,
                            spoiler=att.is_spoiler(),
                            description=att.description
                        )
                    )
            except Exception as att_err:
                print(f"[WebhookSender] Lỗi khi đọc file đính kèm '{att.filename}': {att_err}", flush=True)

    # 2. Xử lý ngữ cảnh Reply nếu tin nhắn gốc của người dùng là một reply tới người khác
    if original_message and original_message.reference and original_message.reference.message_id:
        try:
            ref_msg = original_message.reference.resolved
            if ref_msg is None and hasattr(original_message.channel, "fetch_message"):
                ref_msg = await original_message.channel.fetch_message(original_message.reference.message_id)
            if ref_msg and isinstance(ref_msg, discord.Message):
                ref_author = ref_msg.author
                guild_id = original_message.guild.id if original_message.guild else "@me"
                ref_jump = f"https://discord.com/channels/{guild_id}/{original_message.channel.id}/{ref_msg.id}"
                reply_prefix = f"*↩️ Trả lời [{sanitize_username(ref_author.display_name)}]({ref_jump}):*\n"
                content = f"{reply_prefix}{content}" if content else reply_prefix.strip()
        except Exception as ref_err:
            print(f"[WebhookSender] Lỗi khi lấy thông tin message reference: {ref_err}", flush=True)

    # 3. Cắt ngắn content nếu cần
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
            if all_files:
                kwargs["files"] = all_files[:10]
            if view:
                kwargs["view"] = view

            try:
                sent_msg = await webhook.send(**kwargs)
                if sent_msg and hasattr(sent_msg, "id"):
                    register_embed_message(sent_msg.id, user.id, user.display_name)
                return True
            except discord.HTTPException as e:
                if view is not None and ("components" in str(e).lower() or e.code == 50035):
                    kwargs.pop("view", None)
                    sent_msg = await webhook.send(**kwargs)
                    if sent_msg and hasattr(sent_msg, "id"):
                        register_embed_message(sent_msg.id, user.id, user.display_name)
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
            if all_files:
                kwargs["files"] = all_files[:10]
            if view:
                kwargs["view"] = view

            try:
                sent_msg = await original_message.reply(**kwargs, mention_author=False)
                if sent_msg and hasattr(sent_msg, "id"):
                    register_embed_message(sent_msg.id, user.id, user.display_name)
                return True
            except discord.HTTPException as e:
                if view is not None and ("components" in str(e).lower() or e.code == 50035):
                    kwargs.pop("view", None)
                    sent_msg = await original_message.reply(**kwargs, mention_author=False)
                    if sent_msg and hasattr(sent_msg, "id"):
                        register_embed_message(sent_msg.id, user.id, user.display_name)
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
        if all_files:
            kwargs["files"] = all_files[:10]
        if view:
            kwargs["view"] = view

        if kwargs:
            try:
                sent_msg = await channel.send(**kwargs)
                if sent_msg and hasattr(sent_msg, "id"):
                    register_embed_message(sent_msg.id, user.id, user.display_name)
                return True
            except discord.HTTPException as e:
                if view is not None and ("components" in str(e).lower() or e.code == 50035):
                    kwargs.pop("view", None)
                    sent_msg = await channel.send(**kwargs)
                    if sent_msg and hasattr(sent_msg, "id"):
                        register_embed_message(sent_msg.id, user.id, user.display_name)
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
