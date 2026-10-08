import asyncio
import io
import re
import time
import secrets
from dataclasses import replace
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from features.embed.constants import PLATFORMS, PROXY_DOMAINS, extract_urls
from features.embed.ui import PlatformToggleView, EmbedActionView
from features.embed.builder import NSFWFilter, build_embed, build_gallery_embeds
from features.embed.fetchers import FETCHER_MAP
from features.embed.validator import find_valid_proxy
from features.embed.validator import is_generic_or_login_preview
from features.embed.result import PreviewResult, PreviewSafety
from features.embed.fallback import extract_media_ytdlp
from core.webhook_sender import BoundedDict

EMBED_COOLDOWN = commands.CooldownMapping.from_cooldown(5, 30.0, commands.BucketType.channel)
MAX_LINKS_PER_MESSAGE = 3
_PIPELINE_TIMEOUT = 70
_UNFURL_DELAYS = (1.0, 1.5, 1.5, 2.0)
_SEND_TIMEOUT = 15


class PreviewSendUncertain(Exception):
    """Discord may have accepted a send; another tier must not duplicate it."""

# Regex kiểm tra domain hợp lệ
_DOMAIN_PATTERN = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)+$"
)

_PLATFORM_CHOICES = [
    app_commands.Choice(name=info["name"], value=key)
    for key, info in PLATFORMS.items()
]


def _validate_domain(domain: str) -> bool:
    domain = domain.strip().lower()
    if not domain or domain.startswith(("http://", "https://")):
        return False
    return _DOMAIN_PATTERN.match(domain) is not None


def _parse_domain_list(raw: str) -> list[str]:
    parts = re.split(r"[,\s]+", raw.strip())
    return [p.strip().lower() for p in parts if p.strip()]


def _clean_markdown_label(text: str) -> str:
    """Làm sạch tên người dùng và escape markdown để hiển thị an toàn trên Discord."""
    cleaned = re.sub(r"[\u200b-\u200f\ufeff\u2060\u180e\n\r\t]+", " ", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "Người dùng"
    return discord.utils.escape_markdown(cleaned)


def _is_matching_emoji(reaction_emoji, target_emoji: discord.PartialEmoji) -> bool:
    """So sánh 2 emoji xem có cùng loại hay không (hỗ trợ cả Unicode Emoji và Custom Emoji)."""
    if target_emoji.is_custom_emoji():
        target_id = target_emoji.id
        r_id = getattr(reaction_emoji, "id", None)
        if r_id is not None and target_id is not None:
            return r_id == target_id
        return str(reaction_emoji) == str(target_emoji)
    return str(reaction_emoji) == str(target_emoji) or getattr(reaction_emoji, "name", None) == target_emoji.name


class EmbedCog(commands.Cog):
    """Cog xử lý tự động phát hiện, sửa lỗi và nhúng link mạng xã hội."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = getattr(bot, "config_manager", None)
        self.nsfw_filter = NSFWFilter()
        self.session: aiohttp.ClientSession | None = None
        # Cache liên kết 2 chiều giữa tin nhắn gốc của user và bản xem trước của bot
        self._origin_to_preview_map = BoundedDict(max_size=3000)
        self._preview_to_origin_map = BoundedDict(max_size=3000)
        # Bounded cache lưu danh sách ID các tin nhắn gốc đã bị người dùng xóa
        self._deleted_message_ids = BoundedDict(max_size=5000)
        # Quản lý các task đang xử lý dở dang cho từng tin nhắn gốc
        self._in_flight_tasks: dict[int, asyncio.Task] = {}
        self._scan_task: asyncio.Task | None = None
        # Lock quản lý đồng bộ reaction theo từng tin nhắn để tránh race condition khi nhiều người tương tác cùng lúc
        self._reaction_locks = BoundedDict(max_size=1000)
        self._pending_sends = BoundedDict(max_size=3000)
        self._manual_fallback_previews = BoundedDict(max_size=3000)
        self._facebook_proxy_roll_state = BoundedDict(max_size=3000)
        self._facebook_retry_at = BoundedDict(max_size=3000)

    def _get_reaction_lock(self, msg_id: int) -> asyncio.Lock:
        lock = self._reaction_locks.get(msg_id)
        if lock is None:
            lock = asyncio.Lock()
            self._reaction_locks[msg_id] = lock
        return lock

    def _manual_fallback_payload(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        *,
        is_spoiler: bool = False,
        tried_domains: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> dict | None:
        if platform_key not in PLATFORMS or not url:
            return None
        return {
            "origin_id": message.id,
            "channel_id": message.channel.id,
            "author_id": message.author.id,
            "platform": platform_key,
            "url": url,
            "is_spoiler": is_spoiler,
            "tried_domains": sorted(set(tried_domains or [])),
        }

    def _manual_fallback_view(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        *,
        is_spoiler: bool = False,
        tried_domains: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> EmbedActionView | None:
        payload = self._manual_fallback_payload(
            message,
            platform_key,
            url,
            is_spoiler=is_spoiler,
            tried_domains=tried_domains,
        )
        return EmbedActionView(self, payload) if payload else None

    def _register_manual_fallback_preview(
        self,
        origin_id: int,
        url: str,
        channel_id: int,
        preview_id: int,
    ) -> None:
        key = (origin_id, url)
        targets = self._manual_fallback_previews.get(key)
        if targets is None:
            targets = []
            self._manual_fallback_previews[key] = targets
        target = (channel_id, preview_id)
        if target not in targets:
            targets.append(target)

    def _set_facebook_proxy_state(
        self,
        origin_id: int,
        url: str,
        tried_domains: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        self._facebook_proxy_roll_state[(origin_id, url)] = set(tried_domains)

    async def _offer_manual_fallback(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        *,
        reason: str,
        is_spoiler: bool = False,
    ) -> PreviewResult:
        view = self._manual_fallback_view(
            message, platform_key, url, is_spoiler=is_spoiler
        )
        if not view:
            return PreviewResult(
                reason=reason,
                platform=platform_key,
                origin_message_id=message.id,
            )

        # Do not show an empty "Preview lỗi?" ghost as if a video was
        # generated. Link buttons don't trigger another unfurl/login card.
        if platform_key == "facebook":
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower()
            if (
                parsed.scheme == "https"
                and (hostname == "facebook.com" or hostname.endswith(".facebook.com")
                     or hostname == "fb.watch")
                and len(url) <= 512
            ):
                view.add_item(discord.ui.Button(
                    label="Mở Facebook",
                    style=discord.ButtonStyle.link,
                    url=url,
                ))
            hint = (
                "Không lấy được preview video công khai qua các proxy. "
                "Link có thể yêu cầu đăng nhập, bị giới hạn chia sẻ "
                "hoặc proxy đang lỗi. 🔄 để thử lại sau."
            )
        else:
            hint = "Không tạo được preview; nhấn 🔄 để thử lại."
        author_name = _clean_markdown_label(message.author.display_name)
        sent_msg = await self._send_embed_preview(
            message=message,
            content=f"-# [Trả lời]({message.jump_url}) **{author_name}** • {hint}",
            view=view,
        )
        if not sent_msg:
            return PreviewResult(
                reason="manual_fallback_offer_send_failed",
                platform=platform_key,
                origin_message_id=message.id,
            )
        self._register_manual_fallback_preview(
            message.id, url, message.channel.id, sent_msg.id
        )
        return PreviewResult(
            status="action_required",
            tier="manual",
            reason="manual_fallback_offered",
            platform=platform_key,
            origin_message_id=message.id,
            preview_message_id=sent_msg.id,
            fallback_reason=reason,
        )

    async def cog_load(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discord.app)"}
        )
        # Khởi động tác vụ quét ngầm các embed trước đó để phát hiện embed mồ côi
        self._scan_task = asyncio.create_task(self._initial_orphan_scan())

    async def cog_unload(self):
        tasks = set(self._in_flight_tasks.values())
        if self._scan_task:
            tasks.add(self._scan_task)
        tasks.discard(asyncio.current_task())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._in_flight_tasks.clear()
        if self.session and not self.session.closed:
            await self.session.close()

    def _register_preview(self, origin_id: int, channel_id: int, preview_id: int):
        previews = self._origin_to_preview_map.get(origin_id)
        if previews is None:
            previews = []
            self._origin_to_preview_map[origin_id] = previews
        target = (channel_id, preview_id)
        if target not in previews:
            previews.append(target)
        self._preview_to_origin_map[preview_id] = (channel_id, origin_id)

    def _unregister_preview(self, origin_id: int, preview_id: int) -> None:
        self._preview_to_origin_map.pop(preview_id, None)
        previews = self._origin_to_preview_map.get(origin_id, [])
        previews[:] = [target for target in previews if target[1] != preview_id]
        if not previews:
            self._origin_to_preview_map.pop(origin_id, None)

    async def _settle_io(self, task: asyncio.Task):
        """Giữ ownership đến khi I/O có timeout kết thúc, kể cả khi caller bị hủy."""
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:
                break
        return cancelled

    async def _discard_preview(self, origin_id: int, preview: discord.Message) -> bool:
        task = asyncio.create_task(asyncio.wait_for(preview.delete(), timeout=5))
        cancelled = await self._settle_io(task)
        removed = False
        try:
            task.result()
            removed = True
        except discord.NotFound:
            removed = True
        except (discord.HTTPException, asyncio.TimeoutError) as exc:
            print(f"[Embed][{origin_id}] Không xóa được preview {preview.id}: {type(exc).__name__}; giữ mapping.", flush=True)
        if removed:
            self._unregister_preview(origin_id, preview.id)
        if cancelled:
            raise asyncio.CancelledError
        return removed

    async def _verify_proxy_unfurl(self, origin_id: int, preview: discord.Message, platform_key: str) -> tuple[bool, str]:
        """Fetch the rendered message over a bounded grace window; send acceptance is not preview acceptance."""
        saw_generic_or_login = False
        for delay in _UNFURL_DELAYS:
            await asyncio.sleep(delay)
            if origin_id in self._deleted_message_ids:
                return False, "origin_deleted"
            try:
                current = await preview.channel.fetch_message(preview.id)
            except discord.NotFound:
                return False, "preview_deleted"
            except (discord.Forbidden, discord.HTTPException):
                continue
            for embed in current.embeds:
                if is_generic_or_login_preview(
                    title=embed.title or "", description=embed.description or "",
                    final_url=embed.url or "", platform_key=platform_key,
                    meta_tags={"og:image": getattr(embed.image, "url", "") or getattr(embed.thumbnail, "url", "") or "",
                               "og:video": getattr(embed.video, "url", "") or ""},
                ):
                    # Discord có thể dựng generic card trước rồi mới thay bằng video/card thật.
                    # Không fail-fast ở poll đầu tiên; tiếp tục hết grace window để tránh fallback giả.
                    saw_generic_or_login = True
                    continue
                if embed.video or embed.image or embed.thumbnail or (
                    embed.title and embed.title.casefold() not in {"facebook", "instagram", "tiktok", "twitter", "x"}
                ) or (embed.description and len(embed.description.strip()) > 20):
                    return True, "usable_embed"
        return False, "generic_or_login_card" if saw_generic_or_login else "unfurl_timeout"


    def _detect_urls(self, content: str) -> list[tuple[str, str, object, bool]]:
        raw_urls = extract_urls(content)
        detected = []
        for url, is_spoiler in raw_urls:
            for platform_key, platform_info in PLATFORMS.items():
                matched = False
                for pattern in platform_info["patterns"]:
                    m = pattern.search(url)
                    if m:
                        detected.append((platform_key, url, m, is_spoiler))
                        matched = True
                        break
                if matched:
                    break
        return detected

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        nonce = str(getattr(message, "nonce", ""))
        pending = self._pending_sends.get(nonce)
        if pending and message.author.bot and message.channel.id == pending["channel_id"]:
            if self.bot.user and message.author.id == self.bot.user.id:
                pending["preview"] = message
                self._register_preview(pending["origin_id"], message.channel.id, message.id)
                if pending["discard"] or pending["origin_id"] in self._deleted_message_ids:
                    await self._discard_preview(pending["origin_id"], message)
                    self._pending_sends.pop(nonce, None)
                return
        if message.author.bot or not message.guild or not message.content:
            return

        detected = self._detect_urls(message.content)
        if not detected:
            return

        bucket = EMBED_COOLDOWN.get_bucket(message)
        if bucket.update_rate_limit():
            return

        try:
            if self.config_manager:
                config = await self.config_manager.get_effective_config(
                    message.guild.id, message.channel.id
                )
            else:
                config = {"auto_embed_enabled": True}
        except Exception:
            return

        if not config.get("auto_embed_enabled", True):
            return

        any_success = False
        any_blocked = False
        any_action_required = False
        platforms_enabled = config.get("platforms_enabled", {})

        curr_task = asyncio.current_task()
        if curr_task:
            self._in_flight_tasks[message.id] = curr_task

        try:
            for platform_key, url, match, is_spoiler in detected[:MAX_LINKS_PER_MESSAGE]:
                # Nếu tin nhắn gốc đã bị xóa trong lúc đang duyệt hàng đợi URL, dừng ngay lập tức
                if message.id in self._deleted_message_ids:
                    print(f"[EmbedCog] Hủy xử lý URL vì tin nhắn gốc (ID: {message.id}) đã bị xóa.", flush=True)
                    break

                if not platforms_enabled.get(platform_key, True):
                    continue

                t_embed_start = time.monotonic()
                result = await self._process_url_with_fallback(
                    message, platform_key, url, match, config,
                    is_spoiler=is_spoiler
                )
                elapsed_ms = round((time.monotonic() - t_embed_start) * 1000, 1)

                # Ghi nhận hoạt động vào Live Activity Logger
                try:
                    from core.activity_logger import activity_logger
                    platform_name = PLATFORMS.get(platform_key, {}).get("name", platform_key.capitalize())
                    user_avatar = message.author.display_avatar.url if message.author.display_avatar else None
                    activity_logger.log(
                        action_type="embed",
                        action_name=f"Embed: {platform_name}",
                        user_id=message.author.id,
                        user_name=message.author.display_name,
                        user_avatar=user_avatar,
                        guild_name=message.guild.name if message.guild else "Direct Message",
                        guild_id=message.guild.id if message.guild else None,
                        channel_name=getattr(message.channel, 'name', 'Unknown'),
                        channel_id=message.channel.id,
                        prompt=url,
                        response=(
                            f"Tạo bản xem trước {platform_name} thành công"
                            if result.success else
                            f"Đã giữ bản xem trước và chờ đổi proxy thủ công: {result.reason}"
                            if result.status == "action_required" else
                            f"Không thể tạo bản xem trước {platform_name}: {result.reason}"
                        ),
                        status="success" if result.success else ("warning" if result.status in ("blocked", "action_required") else "error"),
                        duration_ms=elapsed_ms,
                        details={
                            "platform": platform_key,
                            "source_url": url,
                            "is_spoiler": is_spoiler,
                            "tier": result.tier,
                            "reason": result.reason,
                            "proxy_domain": result.proxy_domain,
                            "unfurl_verified": result.unfurl_verified,
                            "used_fallback": result.used_fallback,
                            "fallback_reason": result.fallback_reason,
                            "origin_message_id": result.origin_message_id,
                            "preview_message_id": result.preview_message_id,
                            "result_status": result.status,
                        }
                    )
                except Exception as act_err:
                    print(f"⚠️ [ActivityLogger] Lỗi ghi nhận Embed: {act_err}", flush=True)

                if result.success:
                    any_success = True
                elif result.status == "blocked":
                    any_blocked = True
                elif result.status == "action_required":
                    any_action_required = True
                elif result.status not in ("blocked", "cancelled", "action_required") and message.id not in self._deleted_message_ids:
                    platform_name = PLATFORMS.get(platform_key, {}).get("name", platform_key.capitalize())
                    try:
                        reason = ("🔒 Bài viết có thể không công khai hoặc yêu cầu đăng nhập."
                                  if result.reason == "generic_or_login_card" else
                                  "⚠️ Không thể tạo preview cho liên kết này.")
                        await message.reply(
                            f"{reason}",
                            mention_author=False,
                            delete_after=15,
                        )
                    except Exception:
                        pass
        except asyncio.CancelledError:
            print(f"[EmbedCog] Task xử lý embed cho tin nhắn {message.id} đã bị hủy do tin nhắn gốc bị xóa.", flush=True)
            raise
        finally:
            self._in_flight_tasks.pop(message.id, None)

        # Only hide native previews when Asumi actually produced media or
        # moderation blocked it. An action-required warning is NOT a preview.
        # For mixed-success multi-link messages, keep the original native card
        # when any platform failed, rather than silently hiding useful media.
        if (any_success or any_blocked) and not any_action_required and config.get("suppress_original_embed", True):
            if message.id not in self._deleted_message_ids:
                try:
                    await message.edit(suppress=True)
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"[EmbedCog] Không thể suppress embed tin nhắn gốc: {e}", flush=True)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """Tự động xóa Embed Preview nếu người dùng xóa tin nhắn gốc chứa link."""
        self._deleted_message_ids[payload.message_id] = True

        # 1. Hủy ngay lập tức Task đang xử lý (nếu bot còn đang crawl/download video chưa kịp gửi)
        task = self._in_flight_tasks.get(payload.message_id)
        if task and not task.done():
            task.cancel()
            print(f"[EmbedCog] 🛑 Đã hủy xử lý embed cho tin nhắn gốc (ID: {payload.message_id}) vì vừa bị xóa.", flush=True)
            try:
                from core.activity_logger import activity_logger
                channel = self.bot.get_channel(payload.channel_id)
                guild = channel.guild if channel and hasattr(channel, "guild") else None
                activity_logger.log(
                    action_type="embed",
                    action_name="Embed: Hủy tạo bản xem trước (Tin nhắn gốc bị xóa)",
                    user_id=self.bot.user.id if self.bot.user else 0,
                    user_name="System",
                    guild_name=guild.name if guild else "Unknown Guild",
                    guild_id=guild.id if guild else payload.guild_id,
                    channel_name=getattr(channel, "name", "Unknown Channel"),
                    channel_id=payload.channel_id,
                    prompt=f"Original Message ID: {payload.message_id}",
                    response="Đã hủy tiến trình tải/xử lý embed vì người dùng đã xóa tin nhắn gốc trước khi bot kịp phản hồi.",
                    status="warning",
                    details={"origin_message_id": payload.message_id}
                )
            except Exception as log_err:
                print(f"[EmbedCog] Lỗi ghi activity logger khi hủy task: {log_err}", flush=True)

        # 2. Xóa bản xem trước nếu đã được gửi ra kênh chat
        targets = list(self._origin_to_preview_map.get(payload.message_id, []))
        for channel_id, preview_msg_id in targets:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception:
                        channel = None

                if channel:
                    partial_msg = channel.get_partial_message(preview_msg_id)
                    if not await self._discard_preview(payload.message_id, partial_msg):
                        continue
                    print(f"[EmbedCog] 🗑️ Đã tự động xóa Embed Preview (ID: {preview_msg_id}) do tin nhắn gốc (ID: {payload.message_id}) bị xóa.", flush=True)
                    try:
                        from core.activity_logger import activity_logger
                        guild = channel.guild if hasattr(channel, "guild") else None
                        activity_logger.log(
                            action_type="embed",
                            action_name="Embed: Đã xóa bản xem trước",
                            user_id=self.bot.user.id if self.bot.user else 0,
                            user_name="System",
                            guild_name=guild.name if guild else "Unknown Guild",
                            guild_id=guild.id if guild else payload.guild_id,
                            channel_name=getattr(channel, "name", "Unknown Channel"),
                            channel_id=channel_id,
                            prompt=f"Preview ID: {preview_msg_id}",
                            response=f"Đã tự động xóa embed preview do người dùng xóa tin nhắn gốc (ID: {payload.message_id}).",
                            status="info",
                            details={"origin_message_id": payload.message_id, "preview_message_id": preview_msg_id}
                        )
                    except Exception as log_err:
                        print(f"[EmbedCog] Lỗi ghi activity logger khi xóa embed: {log_err}", flush=True)
            except (discord.NotFound, discord.Forbidden):
                pass
            except Exception as e:
                print(f"[EmbedCog] Lỗi khi tự động xóa Embed Preview: {e}", flush=True)
        # Dọn state proxy-roll theo origin để không giữ state/button mapping mồ côi.
        for state_key in list(self._facebook_proxy_roll_state.keys()):
            if state_key[0] == payload.message_id:
                self._facebook_proxy_roll_state.pop(state_key, None)
        for state_key in list(self._facebook_retry_at.keys()):
            if state_key[0] == payload.message_id:
                self._facebook_retry_at.pop(state_key, None)
        for state_key in list(self._manual_fallback_previews.keys()):
            if state_key[0] == payload.message_id:
                self._manual_fallback_previews.pop(state_key, None)

        origin = self._preview_to_origin_map.pop(payload.message_id, None)
        if origin:
            channel_id, origin_id = origin
            previews = self._origin_to_preview_map.get(origin_id, [])
            previews[:] = [target for target in previews if target[1] != payload.message_id]
            if not previews:
                self._origin_to_preview_map.pop(origin_id, None)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        """Xóa hàng loạt Embed Preview khi các tin nhắn gốc bị xóa hàng loạt (purge)."""
        for msg_id in payload.message_ids:
            fake_payload = discord.RawMessageDeleteEvent({
                "id": msg_id,
                "channel_id": payload.channel_id,
                "guild_id": payload.guild_id,
            })
            await self.on_raw_message_delete(fake_payload)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Khi có người thả tương tác vào Embed Preview của bot:
        - Nếu bot chưa thả emote này vào tin nhắn gốc: bot thả mới.
        - Nếu bot đã thả emote này rồi (có người thứ 2+ cùng thả emote đó trên embed):
          bot gỡ ra rồi thả lại ngay để Discord kích hoạt lại thông báo/hiệu ứng tương tác cho chủ tin nhắn gốc.
        """
        if not self.bot.user or payload.user_id == self.bot.user.id:
            return

        target = self._preview_to_origin_map.get(payload.message_id)
        if not target:
            return

        channel_id, orig_msg_id = target
        lock = self._get_reaction_lock(orig_msg_id)
        async with lock:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception:
                        channel = None

                if not channel:
                    return

                # Tìm tin nhắn gốc từ cache hoặc fetch để kiểm tra trạng thái reaction hiện tại của bot
                orig_msg = discord.utils.find(lambda m: m.id == orig_msg_id, self.bot.cached_messages)
                if orig_msg is None:
                    try:
                        orig_msg = await channel.fetch_message(orig_msg_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        orig_msg = None

                if orig_msg is None:
                    # Fallback nếu không fetch được toàn bộ tin nhắn gốc (dùng partial message)
                    partial_msg = channel.get_partial_message(orig_msg_id)
                    await partial_msg.add_reaction(payload.emoji)
                    return

                # Kiểm tra bot đã thả emote này trên tin nhắn gốc chưa
                bot_already_reacted = False
                for r in orig_msg.reactions:
                    if _is_matching_emoji(r.emoji, payload.emoji) and r.me:
                        bot_already_reacted = True
                        break

                if bot_already_reacted:
                    # Gỡ ra rồi thả lại ngay để Discord nổ lại thông báo/hiệu ứng cho chủ tin nhắn gốc
                    try:
                        await orig_msg.remove_reaction(payload.emoji, self.bot.user)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                    await asyncio.sleep(0.3)
                    await orig_msg.add_reaction(payload.emoji)
                else:
                    await orig_msg.add_reaction(payload.emoji)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            except Exception as e:
                print(f"[EmbedCog] Lỗi khi đồng bộ reaction sang tin nhắn gốc: {e}", flush=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Khi người dùng gỡ tương tác khỏi Embed Preview:
        - Kiểm tra xem trên Embed Preview còn ai khác đang thả emote này không.
        - Nếu VẪN CÒN người thả trên Embed Preview: giữ nguyên reaction của bot trên tin nhắn gốc (chống desync).
        - Nếu KHÔNG CÒN AI thả emote này trên Embed Preview: gỡ reaction của bot khỏi tin nhắn gốc.
        """
        if not self.bot.user or payload.user_id == self.bot.user.id:
            return

        target = self._preview_to_origin_map.get(payload.message_id)
        if not target:
            return

        channel_id, orig_msg_id = target
        lock = self._get_reaction_lock(orig_msg_id)
        async with lock:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception:
                        channel = None

                if not channel:
                    return

                # Lấy tin nhắn Embed Preview để kiểm tra xem còn ai khác thả emote này không
                # Fetch trực tiếp từ API để đảm bảo số đếm (count) chính xác nhất từ server Discord
                preview_msg = None
                try:
                    preview_msg = await channel.fetch_message(payload.message_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    preview_msg = discord.utils.find(lambda m: m.id == payload.message_id, self.bot.cached_messages)

                if preview_msg is not None:
                    # Kiểm tra xem còn reaction nào của emote này với count > 0 không
                    still_has_reaction = False
                    for r in preview_msg.reactions:
                        if _is_matching_emoji(r.emoji, payload.emoji):
                            if r.count > 0:
                                still_has_reaction = True
                                break

                    # Nếu trên Embed Preview vẫn còn ít nhất 1 người thả emote này, không gỡ reaction trên tin nhắn gốc!
                    if still_has_reaction:
                        return

                # Nếu không còn ai thả emote này trên Embed Preview, gỡ trên tin nhắn gốc
                partial_msg = channel.get_partial_message(orig_msg_id)
                await partial_msg.remove_reaction(payload.emoji, self.bot.user)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            except Exception as e:
                print(f"[EmbedCog] Lỗi khi gỡ reaction đồng bộ trên tin nhắn gốc: {e}", flush=True)

    async def _send_embed_preview(
        self,
        message: discord.Message,
        content: str | None = None,
        embeds: list[discord.Embed] | None = None,
        file: discord.File | None = None,
        view: discord.ui.View | None = None,
    ) -> discord.Message | None:
        """Gửi bản xem trước trực tiếp vào kênh chat (không dùng native reply để tránh thanh quote lặp text)."""
        # Nếu tin nhắn gốc đã bị xóa trong lúc bot đang tải video hoặc gọi proxy, không gửi nữa!
        if message.id in self._deleted_message_ids:
            print(f"[EmbedCog] Hủy gửi bản xem trước vì tin nhắn gốc (ID: {message.id}) đã bị xóa.", flush=True)
            if file:
                file.close()
            return None

        if content and len(content) > 2000:
            if file:
                file.close()
            return None
        kwargs = {"allowed_mentions": discord.AllowedMentions.none()}
        if content:
            kwargs["content"] = content
        if embeds:
            kwargs["embeds"] = embeds
        if file:
            kwargs["file"] = file
        if view:
            kwargs["view"] = view

        cancelled = False
        nonce = secrets.token_hex(12)
        pending = {"origin_id": message.id, "channel_id": message.channel.id,
                   "preview": None, "discard": False}
        self._pending_sends[nonce] = pending
        kwargs["nonce"] = nonce
        try:
            # Shield chỉ bảo vệ I/O có giới hạn; caller luôn chờ task kết thúc.
            task = asyncio.create_task(asyncio.wait_for(message.channel.send(**kwargs), timeout=_SEND_TIMEOUT))
            cancelled = await self._settle_io(task)
            sent_msg = task.result()
            self._register_preview(message.id, message.channel.id, sent_msg.id)
            self._pending_sends.pop(nonce, None)
            if cancelled or message.id in self._deleted_message_ids:
                await self._discard_preview(message.id, sent_msg)
                return None
            return sent_msg
        except (discord.HTTPException, asyncio.TimeoutError) as e:
            pending["discard"] = True
            # A gateway MESSAGE_CREATE can resolve a send even if its HTTP response
            # was lost. Keep the nonce owned for a late event; never send a duplicate.
            accepted = pending["preview"]
            if accepted is not None:
                await self._discard_preview(message.id, accepted)
                self._pending_sends.pop(nonce, None)
            elif isinstance(e, discord.HTTPException) and 400 <= e.status < 500:
                self._pending_sends.pop(nonce, None)
                return None
            print(f"[Embed][{message.id}] Kết quả gửi chưa xác định ({type(e).__name__}); dừng fallback, giữ nonce để đối soát gateway.", flush=True)
            raise PreviewSendUncertain from e
        finally:
            if file:
                file.close()
            if cancelled:
                raise asyncio.CancelledError

    async def _read_media(self, response, max_bytes: int) -> bytes | None:
        content_len = response.headers.get("Content-Length")
        if content_len and int(content_len) > max_bytes:
            return None
        data = bytearray()
        async for chunk in response.content.iter_chunked(65536):
            if len(data) + len(chunk) > max_bytes:
                return None
            data.extend(chunk)
        return bytes(data) if data else None

    async def _download_video_file(self, video_urls: list[str] | str, platform_key: str, max_bytes: int = 10 * 1024 * 1024) -> discord.File | None:
        """Tải file video nếu kích thước <= 25MB để Discord phát native trực tiếp.
        Nếu video có nhiều định dạng ứng viên (HD, SD), tự động thử lần lượt cho đến khi tìm được định dạng <= 25MB."""
        if isinstance(video_urls, str):
            video_urls = [video_urls]
        if not video_urls or not self.session:
            return None

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        for v_url in video_urls:
            try:
                async with self.session.get(v_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        video_data = await self._read_media(resp, max_bytes)
                        if video_data:
                            print(f"[EmbedCog] Đã tải thành công video {platform_key} ({len(video_data)/1024/1024:.2f}MB) để đính kèm trực tiếp.", flush=True)
                            return discord.File(
                                fp=io.BytesIO(video_data),
                                filename=f"{platform_key}_video.mp4",
                            )
            except Exception as dl_err:
                print(f"[EmbedCog] Không thể tải ứng viên video {platform_key}: {dl_err}", flush=True)
        return None
    async def _process_url_with_fallback(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        is_spoiler: bool = False,
    ) -> PreviewResult:
        t_start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._run_fallback_chain(
                    message, platform_key, url, match, config,
                    is_spoiler=is_spoiler
                ),
                timeout=_PIPELINE_TIMEOUT,
            )
            elapsed = time.monotonic() - t_start
            if result:
                print(f"[EmbedCog] Xử lý hoàn tất cho {platform_key} trong {elapsed:.2f}s: {url}", flush=True)
            return result
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t_start
            print(f"[EmbedCog] Hết thời gian chờ ({_PIPELINE_TIMEOUT}s) cho {platform_key}: {url}", flush=True)
            return PreviewResult(reason="pipeline_timeout", platform=platform_key, origin_message_id=message.id)

    async def _run_fallback_chain(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        is_spoiler: bool = False,
    ) -> PreviewResult:
        if message.id in self._deleted_message_ids:
            return PreviewResult(status="cancelled", reason="origin_deleted", platform=platform_key, origin_message_id=message.id)

        safety = PreviewSafety()
        # Trạng thái nhạy cảm chỉ tăng trong cùng một URL.
        api_result = await self._try_api_fetcher(message, platform_key, url, match, config, is_spoiler=is_spoiler, safety=safety)
        if isinstance(api_result, PreviewResult):
            return api_result
        if api_result:
            return PreviewResult("success", "api", "api_preview_sent", platform_key, origin_message_id=message.id)

        if message.id in self._deleted_message_ids:
            return PreviewResult(status="cancelled", reason="origin_deleted", platform=platform_key, origin_message_id=message.id)

        # Tier 1: Proxy URL Chain
        proxy_result = await self._try_proxy_chain(message, platform_key, url, config, is_spoiler=is_spoiler, safety=safety)
        if proxy_result.success or proxy_result.status in ("blocked", "cancelled", "degraded", "action_required"):
            return proxy_result

        if message.id in self._deleted_message_ids:
            return PreviewResult(status="cancelled", reason="origin_deleted", platform=platform_key, origin_message_id=message.id)

        # Tier 2: bounded yt-dlp fallback for Facebook *video* URLs only.
        # Never synthesize a playable result from a generic login thumbnail.
        # Successful native proxy previews above NEVER invoke yt-dlp.
        if platform_key == "facebook":
            facebook_path = urlparse(url).path.lower()
            facebook_video = bool(
                re.search(r"/(?:share/[vr]/|reels?/|videos/)", facebook_path)
                or facebook_path.startswith("/watch")
            )
            if facebook_video:
                fallback_result = await self._try_ytdlp_fallback(
                    message, platform_key, url, config,
                    is_spoiler=is_spoiler, safety=safety,
                )
                if isinstance(fallback_result, PreviewResult) and (
                    fallback_result.success or fallback_result.status in
                    ("blocked", "cancelled", "degraded")
                ):
                    return replace(fallback_result, fallback_reason=proxy_result.reason)
            return await self._offer_manual_fallback(
                message,
                platform_key,
                url,
                reason=proxy_result.reason,
                is_spoiler=is_spoiler,
            )

        # Tier 2: yt-dlp Fallback
        ytdlp_result = await self._try_ytdlp_fallback(message, platform_key, url, config, is_spoiler=is_spoiler, safety=safety)
        if isinstance(ytdlp_result, PreviewResult):
            return replace(ytdlp_result, fallback_reason=proxy_result.reason)
        if ytdlp_result:
            return PreviewResult("success", "ytdlp", "fallback_sent", platform_key, origin_message_id=message.id, used_fallback=True, fallback_reason=proxy_result.reason)

        print(f"[EmbedCog] Tất cả các tier đã thất bại cho {platform_key}: {url}", flush=True)
        return PreviewResult(reason=proxy_result.reason, platform=platform_key, origin_message_id=message.id)

    async def _try_api_fetcher(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        is_spoiler: bool = False,
        safety: PreviewSafety | None = None,
    ) -> PreviewResult | bool:
        fetcher = FETCHER_MAP.get(platform_key)
        if not fetcher or self.session is None:
            return False

        try:
            post_data = await fetcher(self.session, url, match)
            if post_data is None:
                return False
            if safety is not None:
                safety.is_nsfw |= post_data.is_nsfw
                post_data.is_nsfw = safety.is_nsfw

            if is_spoiler:
                post_data.is_spoiler = True

            filter_result = self.nsfw_filter.process(post_data, message.channel, config)
            if filter_result.is_blocked:
                return PreviewResult("blocked", "api", "nsfw_blocked", platform_key, origin_message_id=message.id)

            if post_data.media_type == "gallery" and len(post_data.media_urls) > 1:
                embeds = build_gallery_embeds(post_data, filter_result)
            else:
                single_embed = build_embed(post_data, filter_result)
                embeds = [single_embed] if single_embed else []

            if not embeds:
                return False

            file = None
            if filter_result.should_spoiler_media and post_data.media_urls:
                file = await self._create_spoiler_file(post_data.media_urls[0], max_bytes=message.guild.filesize_limit)
            elif post_data.media_type == "video" and post_data.media_urls:
                file = await self._download_video_file(post_data.media_urls, platform_key, max_bytes=message.guild.filesize_limit)

            author_name = _clean_markdown_label(message.author.display_name)
            fallback_view = self._manual_fallback_view(
                message, platform_key, url, is_spoiler=is_spoiler
            )
            header_text = f"-# [Trả lời]({message.jump_url}) **{author_name}**"

            sent_msg = await self._send_embed_preview(
                message=message,
                content=header_text,
                embeds=embeds,
                file=file,
                view=fallback_view,
            )
            if sent_msg and fallback_view:
                self._register_manual_fallback_preview(
                    message.id, url, message.channel.id, sent_msg.id
                )
            return (PreviewResult("success", "api", "api_preview_sent", platform_key,
                                  origin_message_id=message.id, preview_message_id=sent_msg.id)
                    if sent_msg else False)
        except PreviewSendUncertain:
            return PreviewResult("degraded", "api", "send_outcome_unknown", platform_key, origin_message_id=message.id)
        except Exception as e:
            print(f"[EmbedCog] Tier 0 (API) lỗi cho {platform_key} ({url}): {e}", flush=True)
            return False

    async def _try_proxy_chain(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        config: dict,
        is_spoiler: bool = False,
        safety: PreviewSafety | None = None,
    ) -> PreviewResult:
        safety = safety if safety is not None else PreviewSafety()
        if self.session is None:
            return PreviewResult(reason="session_unavailable", platform=platform_key, origin_message_id=message.id)

        try:
            guild_proxy_domains = None
            if self.config_manager:
                guild_proxy_domains = await self.config_manager.get_guild_proxy_domains(
                    message.guild.id, platform_key
                )

            domains = guild_proxy_domains if guild_proxy_domains is not None else PROXY_DOMAINS.get(platform_key, [])
            tried: set[str] = set()
            last_reason = "no_valid_proxy"
            for _ in range(len(domains)):
                if message.id in self._deleted_message_ids:
                    return PreviewResult("cancelled", "proxy", "origin_deleted", platform_key, origin_message_id=message.id)
                proxy_url, is_proxy_nsfw = await find_valid_proxy(
                    self.session, url, platform_key,
                    guild_proxy_domains=guild_proxy_domains, excluded_domains=tried,
                    attempted_domains=tried,
                )
                if not proxy_url:
                    break
                domain = urlparse(proxy_url).hostname or ""
                tried.add(domain)

                is_nsfw_channel = getattr(message.channel, "is_nsfw", False)
                if callable(is_nsfw_channel):
                    is_nsfw_channel = is_nsfw_channel()
                safety.is_nsfw |= is_proxy_nsfw
                is_effective_nsfw = safety.is_nsfw and not is_nsfw_channel
                if is_effective_nsfw and config.get("nsfw_mode", "spoiler") == "block":
                    try:
                        await message.reply("⚠️ Nội dung NSFW đã bị chặn theo cài đặt của máy chủ.", mention_author=False, delete_after=10)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    return PreviewResult("blocked", "proxy", "nsfw_blocked", platform_key, domain, message.id)

                author_name = _clean_markdown_label(message.author.display_name)
                author_jump = f"[Trả lời]({message.jump_url}) **{author_name}**"

                # Facebook giữ URL proxy trong masked markdown link để dòng chat gọn hơn.
                # Không bọc URL đích bằng <...>, vì dạng đó sẽ suppress Discord unfurl.
                # Button chỉ là điều khiển phụ để người gửi chủ động chuyển sang proxy kế tiếp.
                if platform_key == "facebook":
                    proxy_link = f"[{domain}]({proxy_url})"
                    if is_spoiler or (is_effective_nsfw and config.get("nsfw_mode", "spoiler") == "spoiler"):
                        proxy_link = f"||{proxy_link}||"
                    fallback_view = self._manual_fallback_view(
                        message,
                        platform_key,
                        url,
                        is_spoiler=is_spoiler,
                        tried_domains=tried,
                    )
                    sent_msg = await self._send_embed_preview(
                        message=message,
                        content=f"-# {author_jump} • {proxy_link}",
                        view=fallback_view,
                    )
                    if not sent_msg:
                        last_reason = "proxy_send_failed"
                        continue

                    self._register_manual_fallback_preview(
                        message.id, url, message.channel.id, sent_msg.id
                    )
                    self._set_facebook_proxy_state(message.id, url, tried)
                    return PreviewResult(
                        "success",
                        "proxy",
                        "proxy_link_sent",
                        platform_key,
                        domain,
                        message.id,
                        sent_msg.id,
                        False,
                    )

                link = f"[Xem bài viết gốc]({proxy_url})"
                if is_spoiler or (is_effective_nsfw and config.get("nsfw_mode", "spoiler") == "spoiler"):
                    link = f"||{link}||"
                action_view = self._manual_fallback_view(
                    message,
                    platform_key,
                    url,
                    is_spoiler=is_spoiler,
                    tried_domains=tried,
                )
                sent_msg = await self._send_embed_preview(
                    message=message,
                    content=f"-# {author_jump} • {link}",
                    view=action_view,
                )
                if not sent_msg:
                    last_reason = "proxy_send_failed"
                    continue
                if action_view:
                    self._register_manual_fallback_preview(
                        message.id, url, message.channel.id, sent_msg.id
                    )
                verified = False
                removed = True
                try:
                    verified, last_reason = await self._verify_proxy_unfurl(message.id, sent_msg, platform_key)
                    if verified and message.id not in self._deleted_message_ids:
                        return PreviewResult("success", "proxy", "usable_embed", platform_key, domain, message.id, sent_msg.id, True)
                    if message.id in self._deleted_message_ids:
                        verified = False
                        last_reason = "origin_deleted"
                finally:
                    if not verified:
                        removed = await self._discard_preview(message.id, sent_msg)

                if not removed:
                    return PreviewResult("degraded", "proxy", "cleanup_failed", platform_key, domain, message.id, sent_msg.id)
            return PreviewResult(reason=last_reason, platform=platform_key, origin_message_id=message.id)
        except asyncio.CancelledError:
            raise
        except PreviewSendUncertain:
            return PreviewResult("degraded", "proxy", "send_outcome_unknown", platform_key, origin_message_id=message.id)
        except Exception as e:
            print(f"[EmbedCog] Tier 1 (Proxy) lỗi cho {platform_key} ({url}): {e}", flush=True)
            return PreviewResult(reason="proxy_error", platform=platform_key, origin_message_id=message.id)

    async def _try_ytdlp_fallback(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        config: dict,
        is_spoiler: bool = False,
        safety: PreviewSafety | None = None,
        manual: bool = False,
    ) -> PreviewResult | bool:
        # Facebook is allowed only for actual video routes; ordinary posts
        # must not be mistaken for playable video based on generic thumbnails.
        supported = ("twitter", "tiktok", "instagram", "reddit", "twitch", "facebook")
        if platform_key not in supported:
            return False
        if platform_key == "facebook" and not (
            re.search(r"/(?:share/[vr]/|reels?/|videos/)", urlparse(url).path,
                      flags=re.IGNORECASE)
            or urlparse(url).path.startswith("/watch")
        ):
            return False

        try:
            post_data = await extract_media_ytdlp(url, platform_key)
            if post_data is None:
                return False

            # A generic Facebook login page or a static preview poster
            # is not a playable fallback.
            if platform_key == "facebook" and (
                post_data.media_type != "video" or not post_data.media_urls
                or is_generic_or_login_preview(
                    title=post_data.text or "", platform_key="facebook"
                )
            ):
                return False

            if safety is not None:
                safety.is_nsfw |= post_data.is_nsfw
                post_data.is_nsfw = safety.is_nsfw

            if is_spoiler:
                post_data.is_spoiler = True

            filter_result = self.nsfw_filter.process(post_data, message.channel, config)
            if filter_result.is_blocked:
                return PreviewResult("blocked", "ytdlp", "nsfw_blocked", platform_key, origin_message_id=message.id, used_fallback=True)

            single_embed = build_embed(post_data, filter_result)
            if not single_embed:
                return False

            proxy_name = "Facebed" if platform_key == "facebook" else "Proxy"
            if single_embed.footer and single_embed.footer.text:
                single_embed.set_footer(
                    text=f"{single_embed.footer.text} • Fallback từ {proxy_name.lower()}",
                    icon_url=single_embed.footer.icon_url,
                )

            file = None
            if filter_result.should_spoiler_media and post_data.media_urls:
                file = await self._create_spoiler_file(post_data.media_urls[0], max_bytes=message.guild.filesize_limit)
            elif post_data.media_type == "video" and post_data.media_urls:
                file = await self._download_video_file(post_data.media_urls, platform_key, max_bytes=message.guild.filesize_limit)

            # Facebook video fallback must genuinely attach playable media.
            # If Facebook blocks the CDN or the file exceeds guild limits,
            # do not advertise a static thumbnail as a successful video.
            if platform_key == "facebook" and file is None:
                return False

            # Nếu đã đính kèm file video MP4 (Discord tự hiển thị video player native),
            # xóa ảnh thumbnail tĩnh khỏi embed để tránh bị lặp 2 lần hình ảnh trong giao diện chat
            if file is not None:
                single_embed.set_image(url=None)

            author_name = _clean_markdown_label(message.author.display_name)
            fallback_hint = (
                " • ↪ *fallback thủ công*"
                if manual else
                f" • ⚠️ *{proxy_name} lỗi, đã tự động fallback*"
            )
            header_text = f"-# [Trả lời]({message.jump_url}) **{author_name}**{fallback_hint}"

            action_view = self._manual_fallback_view(
                message,
                platform_key,
                url,
                is_spoiler=is_spoiler,
            )
            sent_msg = await self._send_embed_preview(
                message=message,
                content=header_text,
                embeds=[single_embed],
                file=file,
                view=action_view,
            )
            if sent_msg and action_view:
                self._register_manual_fallback_preview(
                    message.id, url, message.channel.id, sent_msg.id
                )
            result_reason = "manual_fallback_sent" if manual else "fallback_sent"
            return (PreviewResult("success", "ytdlp", result_reason, platform_key,
                                  origin_message_id=message.id, preview_message_id=sent_msg.id, used_fallback=True)
                    if sent_msg else False)
        except PreviewSendUncertain:
            return PreviewResult("degraded", "ytdlp", "send_outcome_unknown", platform_key, origin_message_id=message.id)
        except Exception as e:
            print(f"[EmbedCog] Tier 2 (yt-dlp) lỗi cho {platform_key} ({url}): {e}", flush=True)
            return False

    async def reload_embed(
        self,
        payload: dict,
        *,
        current_preview: discord.Message | None = None,
    ) -> PreviewResult:
        """Reload one social preview while keeping the current preview on failure."""
        origin_id = int(payload.get("origin_id", 0) or 0)
        channel_id = int(payload.get("channel_id", 0) or 0)
        author_id = int(payload.get("author_id", 0) or 0)
        platform_key = str(payload.get("platform", ""))
        url = str(payload.get("url", ""))
        is_spoiler = bool(payload.get("is_spoiler", False))

        if platform_key not in PLATFORMS or not origin_id or not channel_id or not author_id or not url:
            return PreviewResult(
                reason="reload_invalid_payload",
                platform=platform_key,
                origin_message_id=origin_id or None,
            )

        # Facebook reload checks remaining proxies, then a bounded video-only
        # yt-dlp fallback if no validated proxy is available.
        if platform_key == "facebook":
            return await self.roll_facebook_proxy(
                payload,
                current_preview=current_preview,
            )

        if origin_id in self._deleted_message_ids:
            return PreviewResult(
                status="cancelled",
                reason="origin_deleted",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        if channel is None:
            return PreviewResult(
                reason="reload_channel_missing",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        try:
            origin_message = await channel.fetch_message(origin_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return PreviewResult(
                reason="reload_origin_missing",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        if origin_message.author.id != author_id:
            return PreviewResult(
                reason="reload_author_mismatch",
                platform=platform_key,
                origin_message_id=origin_id,
            )
        if url not in origin_message.content:
            return PreviewResult(
                reason="reload_url_mismatch",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        try:
            if self.config_manager:
                config = await self.config_manager.get_effective_config(
                    origin_message.guild.id,
                    origin_message.channel.id,
                )
            else:
                config = {
                    "auto_embed_enabled": True,
                    "nsfw_mode": "spoiler",
                    "suppress_original_embed": True,
                }
        except Exception:
            config = {
                "auto_embed_enabled": True,
                "nsfw_mode": "spoiler",
                "suppress_original_embed": True,
            }

        match = None
        for pattern in PLATFORMS.get(platform_key, {}).get("patterns", []):
            match = pattern.search(url)
            if match:
                break

        result = await self._run_fallback_chain(
            origin_message,
            platform_key,
            url,
            match,
            config,
            is_spoiler=is_spoiler,
        )

        has_replacement = result.success or (
            result.status == "action_required" and result.preview_message_id is not None
        )
        if has_replacement and current_preview is not None:
            current_id = getattr(current_preview, "id", None)
            if current_id and current_id != result.preview_message_id:
                try:
                    await self._discard_preview(origin_id, current_preview)
                except Exception as exc:
                    print(
                        f"[EmbedCog] Reload đã tạo preview mới nhưng không dọn được preview {current_id}: {exc}",
                        flush=True,
                    )

        return result

    async def revert_embed(self, payload: dict) -> PreviewResult:
        """Restore Discord's native embed and remove all Asumi previews for the origin message."""
        origin_id = int(payload.get("origin_id", 0) or 0)
        channel_id = int(payload.get("channel_id", 0) or 0)
        author_id = int(payload.get("author_id", 0) or 0)
        platform_key = str(payload.get("platform", ""))
        url = str(payload.get("url", ""))

        if platform_key not in PLATFORMS or not origin_id or not channel_id or not author_id or not url:
            return PreviewResult(
                reason="revert_invalid_payload",
                platform=platform_key,
                origin_message_id=origin_id or None,
            )

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        if channel is None:
            return PreviewResult(
                reason="revert_channel_missing",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        try:
            origin_message = await channel.fetch_message(origin_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return PreviewResult(
                reason="revert_origin_missing",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        if origin_message.author.id != author_id:
            return PreviewResult(
                reason="revert_author_mismatch",
                platform=platform_key,
                origin_message_id=origin_id,
            )
        if url not in origin_message.content:
            return PreviewResult(
                reason="revert_url_mismatch",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        try:
            await origin_message.edit(suppress=False)
        except (discord.Forbidden, discord.HTTPException):
            return PreviewResult(
                reason="native_unsuppress_failed",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        cleanup_ok = True
        targets = list(self._origin_to_preview_map.get(origin_id, []))
        for preview_channel_id, preview_id in targets:
            target_channel = (
                channel
                if preview_channel_id == channel_id
                else self.bot.get_channel(preview_channel_id)
            )
            if target_channel is None:
                try:
                    target_channel = await self.bot.fetch_channel(preview_channel_id)
                except Exception:
                    target_channel = None
            if target_channel is None:
                cleanup_ok = False
                continue

            try:
                preview = target_channel.get_partial_message(preview_id)
                if not await self._discard_preview(origin_id, preview):
                    cleanup_ok = False
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                cleanup_ok = False
            except Exception:
                cleanup_ok = False

        for state_key in list(self._facebook_proxy_roll_state.keys()):
            if state_key[0] == origin_id:
                self._facebook_proxy_roll_state.pop(state_key, None)
        for state_key in list(self._facebook_retry_at.keys()):
            if state_key[0] == origin_id:
                self._facebook_retry_at.pop(state_key, None)
        for state_key in list(self._manual_fallback_previews.keys()):
            if state_key[0] == origin_id:
                self._manual_fallback_previews.pop(state_key, None)

        try:
            from core.activity_logger import activity_logger
            activity_logger.log(
                action_type="embed",
                action_name="Embed: Revert to native",
                user_id=author_id,
                user_name=origin_message.author.display_name,
                user_avatar=origin_message.author.display_avatar.url if origin_message.author.display_avatar else None,
                guild_name=origin_message.guild.name if origin_message.guild else "Unknown Guild",
                guild_id=origin_message.guild.id if origin_message.guild else None,
                channel_name=getattr(origin_message.channel, "name", "Unknown"),
                channel_id=channel_id,
                prompt=url,
                response="Người gửi link đã bỏ preview Asumi và khôi phục embed gốc của Discord.",
                status="success" if cleanup_ok else "warning",
                details={
                    "platform": platform_key,
                    "origin_message_id": origin_id,
                    "native_embed_restored": True,
                    "cleanup_complete": cleanup_ok,
                },
            )
        except Exception:
            pass

        return PreviewResult(
            "success",
            "native",
            "native_embed_restored" if cleanup_ok else "native_embed_restored_cleanup_partial",
            platform_key,
            origin_message_id=origin_id,
        )

    async def roll_facebook_proxy(
        self,
        payload: dict,
        *,
        current_preview: discord.Message | None = None,
    ) -> PreviewResult:
        """Roll a Facebook preview to the next configured proxy; never jump to yt-dlp."""
        origin_id = int(payload.get("origin_id", 0) or 0)
        channel_id = int(payload.get("channel_id", 0) or 0)
        author_id = int(payload.get("author_id", 0) or 0)
        platform_key = str(payload.get("platform", ""))
        url = str(payload.get("url", ""))
        is_spoiler = bool(payload.get("is_spoiler", False))
        payload_tried = {
            str(domain).strip().lower()
            for domain in payload.get("tried_domains", [])
            if str(domain).strip()
        }

        if platform_key != "facebook" or not origin_id or not channel_id or not author_id or not url:
            return PreviewResult(
                reason="proxy_roll_invalid_payload",
                platform=platform_key,
                origin_message_id=origin_id or None,
            )
        if origin_id in self._deleted_message_ids:
            return PreviewResult(
                status="cancelled",
                reason="origin_deleted",
                platform=platform_key,
                origin_message_id=origin_id,
            )
        if self.session is None:
            return PreviewResult(
                reason="session_unavailable",
                platform=platform_key,
                origin_message_id=origin_id,
            )

        lock = self._get_reaction_lock(origin_id)
        async with lock:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    channel = None
            if channel is None:
                return PreviewResult(
                    reason="proxy_roll_channel_missing",
                    platform=platform_key,
                    origin_message_id=origin_id,
                )

            try:
                origin_message = await channel.fetch_message(origin_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return PreviewResult(
                    reason="proxy_roll_origin_missing",
                    platform=platform_key,
                    origin_message_id=origin_id,
                )

            if origin_message.author.id != author_id:
                return PreviewResult(
                    reason="proxy_roll_author_mismatch",
                    platform=platform_key,
                    origin_message_id=origin_id,
                )
            if url not in origin_message.content:
                return PreviewResult(
                    reason="proxy_roll_url_mismatch",
                    platform=platform_key,
                    origin_message_id=origin_id,
                )

            try:
                if self.config_manager:
                    config = await self.config_manager.get_effective_config(
                        origin_message.guild.id, origin_message.channel.id
                    )
                    guild_proxy_domains = await self.config_manager.get_guild_proxy_domains(
                        origin_message.guild.id, platform_key
                    )
                else:
                    config = {"nsfw_mode": "spoiler"}
                    guild_proxy_domains = None
            except Exception:
                config = {"nsfw_mode": "spoiler"}
                guild_proxy_domains = None

            state_key = (origin_id, url)
            remembered = set(self._facebook_proxy_roll_state.get(state_key, set()))
            tried = remembered | payload_tried
            if time.monotonic() < self._facebook_retry_at.get(state_key, 0):
                return PreviewResult(
                    status="action_required",
                    tier="proxy",
                    reason="proxy_retry_cooldown",
                    platform=platform_key,
                    origin_message_id=origin_id,
                )
            attempted = set(tried)

            proxy_url, is_proxy_nsfw = await find_valid_proxy(
                self.session,
                url,
                platform_key,
                guild_proxy_domains=guild_proxy_domains,
                excluded_domains=tried,
                attempted_domains=attempted,
            )
            tried = attempted

            if not proxy_url:
                # Explicit Reload authorizes trying the last fallback; only
                # attach an actually downloaded playable video. Preserve the
                # current preview if yt-dlp is blocked/unavailable/oversized.
                fallback = await self._try_ytdlp_fallback(
                    origin_message, "facebook", url, config,
                    is_spoiler=is_spoiler, manual=True,
                )
                if isinstance(fallback, PreviewResult) and fallback.success:
                    if current_preview is not None and (
                        getattr(current_preview, "id", None) != fallback.preview_message_id
                    ):
                        try:
                            await self._discard_preview(origin_id, current_preview)
                        except Exception:
                            pass
                    return fallback
                if isinstance(fallback, PreviewResult) and fallback.status == "degraded":
                    return fallback
                # A failed validation/HTTP timeout does NOT mean that proxy
                # was permanently consumed. Keep previously successful proxy
                # rotations excluded, but allow bounded retries of failures.
                domains = guild_proxy_domains if guild_proxy_domains is not None else PROXY_DOMAINS.get(platform_key, [])
                exhausted = bool(domains) and all(d in tried for d in domains)
                if not exhausted:
                    self._facebook_retry_at[state_key] = time.monotonic() + 30.0
                return PreviewResult(
                    status="action_required",
                    tier="proxy",
                    reason="no_more_proxy" if exhausted else "proxy_temporarily_unavailable",
                    platform=platform_key,
                    origin_message_id=origin_id,
                )

            self._facebook_retry_at.pop(state_key, None)
            domain = (urlparse(proxy_url).hostname or "").lower()
            if domain:
                tried.add(domain)

            is_nsfw_channel = getattr(origin_message.channel, "is_nsfw", False)
            if callable(is_nsfw_channel):
                is_nsfw_channel = is_nsfw_channel()
            is_effective_nsfw = is_proxy_nsfw and not is_nsfw_channel
            if is_effective_nsfw and config.get("nsfw_mode", "spoiler") == "block":
                return PreviewResult(
                    "blocked",
                    "proxy",
                    "nsfw_blocked",
                    platform_key,
                    domain,
                    origin_id,
                )

            proxy_link = f"[{domain}]({proxy_url})"
            if is_spoiler or (
                is_effective_nsfw
                and config.get("nsfw_mode", "spoiler") == "spoiler"
            ):
                proxy_link = f"||{proxy_link}||"

            author_name = _clean_markdown_label(origin_message.author.display_name)
            author_jump = f"[Trả lời]({origin_message.jump_url}) **{author_name}**"
            next_view = self._manual_fallback_view(
                origin_message,
                platform_key,
                url,
                is_spoiler=is_spoiler,
                tried_domains=tried,
            )
            sent_msg = await self._send_embed_preview(
                message=origin_message,
                content=f"-# {author_jump} • {proxy_link}",
                view=next_view,
            )
            if not sent_msg:
                return PreviewResult(
                    reason="proxy_roll_send_failed",
                    platform=platform_key,
                    proxy_domain=domain,
                    origin_message_id=origin_id,
                )

            self._set_facebook_proxy_state(origin_id, url, tried)

            old_removed = True
            if current_preview is not None and getattr(current_preview, "id", None) != sent_msg.id:
                try:
                    old_removed = await self._discard_preview(origin_id, current_preview)
                except Exception:
                    old_removed = False

            preview_targets = [(channel_id, sent_msg.id)]
            if (
                not old_removed
                and current_preview is not None
                and getattr(current_preview, "id", None)
            ):
                old_channel_id = getattr(getattr(current_preview, "channel", None), "id", channel_id)
                preview_targets.append((old_channel_id, current_preview.id))
            self._manual_fallback_previews[state_key] = preview_targets

            print(
                f"[EmbedCog] Facebook proxy roll: origin={origin_id} -> {domain}; tried={sorted(tried)}",
                flush=True,
            )
            try:
                from core.activity_logger import activity_logger
                activity_logger.log(
                    action_type="embed",
                    action_name="Embed: Facebook proxy roll",
                    user_id=author_id,
                    user_name=origin_message.author.display_name,
                    user_avatar=origin_message.author.display_avatar.url if origin_message.author.display_avatar else None,
                    guild_name=origin_message.guild.name if origin_message.guild else "Unknown Guild",
                    guild_id=origin_message.guild.id if origin_message.guild else None,
                    channel_name=getattr(origin_message.channel, "name", "Unknown"),
                    channel_id=channel_id,
                    prompt=url,
                    response=f"Người dùng chuyển preview sang proxy {domain}.",
                    status="success",
                    details={
                        "platform": platform_key,
                        "origin_message_id": origin_id,
                        "preview_message_id": sent_msg.id,
                        "proxy_domain": domain,
                        "tried_domains": sorted(tried),
                        "manual_proxy_roll": True,
                    },
                )
            except Exception:
                pass

            return PreviewResult(
                "success",
                "proxy",
                "proxy_rolled",
                platform_key,
                domain,
                origin_id,
                sent_msg.id,
                False,
                True,
                "manual_proxy_roll",
            )

    async def _create_spoiler_file(self, image_url: str, max_bytes: int = 10 * 1024 * 1024) -> discord.File | None:
        if self.session is None:
            return None
        try:
            async with self.session.get(image_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                image_data = await self._read_media(resp, max_bytes)
                if not image_data:
                    return None
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp", "video/mp4": "mp4", "video/webm": "webm"}
                ext = ext_map.get(content_type.split(";")[0].strip().lower())
                if not ext:
                    return None
                return discord.File(fp=io.BytesIO(image_data), filename=f"SPOILER_nsfw_media.{ext}", spoiler=True)
        except Exception:
            return None

    async def _initial_orphan_scan(self):
        """Quét các tin nhắn embed gần đây của bot trên các kênh text sau khi khởi động.
        1. Xóa các embed mồ côi nếu tin nhắn gốc đã bị xóa trong lúc bot offline/redeploy.
        2. Nạp lại ánh xạ _origin_to_preview_map để tiếp tục lắng nghe sự kiện xóa cho các embed trước đó."""
        try:
            await self.bot.wait_until_ready()
            # Đợi một chút để Gateway và các Cog khác ổn định
            await asyncio.sleep(4.0)
            print("[EmbedCog] 🔍 Bắt đầu quét các bản xem trước embed trước đó để phát hiện embed mồ côi...", flush=True)

            scanned_channels = 0
            cleaned_count = 0
            restored_count = 0

            for guild in self.bot.guilds:
                for channel in guild.text_channels:
                    perms = channel.permissions_for(guild.me)
                    if not (perms.read_messages and perms.read_message_history):
                        continue

                    scanned_channels += 1
                    try:
                        async for msg in channel.history(limit=50):
                            if not self.bot.user or msg.author.id != self.bot.user.id:
                                continue

                            # Nhận diện embed do bot tạo ra thông qua header jump_url
                            if not msg.content or "-# [Trả lời]" not in msg.content:
                                continue

                            match = re.search(r"discord\.com/channels/\d+/\d+/(\d+)", msg.content)
                            if not match:
                                continue

                            orig_id = int(match.group(1))

                            # Kiểm tra xem tin nhắn gốc còn tồn tại trên Discord không
                            try:
                                await channel.fetch_message(orig_id)
                                # Tin nhắn gốc vẫn còn -> Khôi phục vào bộ nhớ cache để tiếp tục đồng bộ
                                self._register_preview(orig_id, channel.id, msg.id)
                                restored_count += 1
                            except discord.NotFound:
                                # Tin nhắn gốc đã bị xóa mất trước đó -> Dọn dẹp ngay embed mồ côi
                                try:
                                    await msg.delete()
                                    cleaned_count += 1
                                    print(
                                        f"[EmbedCog] 🧹 Đã dọn dẹp Embed mồ côi (ID: {msg.id}) trong #{channel.name} "
                                        f"do tin nhắn gốc ({orig_id}) không còn tồn tại.",
                                        flush=True,
                                    )
                                    try:
                                        from core.activity_logger import activity_logger
                                        activity_logger.log(
                                            action_type="embed",
                                            action_name="Embed: Dọn dẹp embed mồ côi (Startup Scan)",
                                            user_id=self.bot.user.id,
                                            user_name=self.bot.user.name,
                                            guild_name=guild.name,
                                            guild_id=guild.id,
                                            channel_name=channel.name,
                                            channel_id=channel.id,
                                            prompt=f"Preview ID: {msg.id}",
                                            response=f"Đã tự động xóa embed mồ côi vì tin nhắn gốc ({orig_id}) đã bị xóa trước đó.",
                                            status="info",
                                            details={"origin_message_id": orig_id, "preview_message_id": msg.id},
                                        )
                                    except Exception as log_err:
                                        print(f"[EmbedCog] Lỗi ghi activity logger: {log_err}", flush=True)
                                except Exception as del_err:
                                    print(f"[EmbedCog] Lỗi xóa embed mồ côi {msg.id}: {del_err}", flush=True)
                            except Exception:
                                pass

                    except Exception:
                        pass
                    # Nghỉ nhỏ giữa các kênh để không làm nghẽn Discord API
                    await asyncio.sleep(0.15)

            print(
                f"[EmbedCog] ✅ Hoàn tất quét embed: Đã kiểm tra {scanned_channels} kênh, "
                f"dọn dẹp {cleaned_count} embed mồ côi, khôi phục theo dõi {restored_count} embed.",
                flush=True,
            )
        except Exception as e:
            print(f"[EmbedCog] Lỗi trong quá trình quét embed ban đầu: {e}", flush=True)


class EmbedConfigCog(commands.Cog):
    """Cog cấu hình Embed cho Server / Channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = getattr(bot, "config_manager", None)

    @app_commands.command(name="autoembed", description="Bật/tắt tính năng tự động tạo embed")
    @app_commands.describe(
        enabled="Bật (True) hoặc tắt (False) tính năng auto-embed",
        channel="Kênh cần áp dụng (để trống nếu áp dụng cho toàn máy chủ)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autoembed(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | None = None,
    ):
        if not self.config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

        if channel:
            await self.config_manager.set_channel_config(channel.id, interaction.guild.id, "auto_embed_enabled", enabled)
            target = f"kênh {channel.mention}"
        else:
            await self.config_manager.set_guild_config(interaction.guild.id, "auto_embed_enabled", enabled)
            target = "toàn máy chủ"

        state = "BẬT" if enabled else "TẮT"
        await interaction.response.send_message(
            f"Đã **{state}** tính năng tự động tạo embed cho **{target}**.",
            ephemeral=True,
        )

    @app_commands.command(name="nsfwmode", description="Cấu hình cách xử lý nội dung NSFW")
    @app_commands.describe(
        mode="Chế độ xử lý: block (chặn), spoiler (thêm spoiler), allow (cho phép)",
        channel="Kênh cần áp dụng (để trống nếu áp dụng cho toàn máy chủ)",
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Chặn nội dung NSFW (block)", value="block"),
        app_commands.Choice(name="Thêm cảnh báo và che spoiler (spoiler)", value="spoiler"),
        app_commands.Choice(name="Cho phép hiển thị bình thường (allow)", value="allow"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nsfwmode(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        channel: discord.TextChannel | None = None,
    ):
        if not self.config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

        if channel:
            await self.config_manager.set_channel_config(channel.id, interaction.guild.id, "nsfw_mode", mode.value)
            target = f"kênh {channel.mention}"
        else:
            await self.config_manager.set_guild_config(interaction.guild.id, "nsfw_mode", mode.value)
            target = "toàn máy chủ"

        mode_descriptions = {
            "block": "Chặn hiển thị",
            "spoiler": "Che bằng spoiler kèm cảnh báo",
            "allow": "Hiển thị bình thường",
        }
        await interaction.response.send_message(
            f"Đã đặt chế độ NSFW cho **{target}**: **{mode_descriptions[mode.value]}** (`{mode.value}`).",
            ephemeral=True,
        )

    @app_commands.command(name="embedplatform", description="Bật/tắt hỗ trợ embed cho từng nền tảng")
    @app_commands.describe(channel="Kênh cần áp dụng (để trống nếu áp dụng cho toàn máy chủ)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def embedplatform(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        if not self.config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

        if channel:
            effective = await self.config_manager.get_effective_config(interaction.guild.id, channel.id)
            scope = "channel"
            channel_id = channel.id
            title = f"Cài đặt nền tảng -- Kênh #{channel.name}"
        else:
            effective = await self.config_manager.get_guild_config(interaction.guild.id)
            scope = "guild"
            channel_id = None
            title = "Cài đặt nền tảng -- Toàn máy chủ"

        view = PlatformToggleView(effective, scope, channel_id)
        platforms_enabled = effective.get("platforms_enabled", {})
        status_lines = [
            f"[{'BẬT' if platforms_enabled.get(key, True) else 'TẮT'}] {info['name']}"
            for key, info in PLATFORMS.items()
        ]

        embed = discord.Embed(
            title=title,
            description="Sử dụng menu bên dưới để chọn các nền tảng muốn bật/tắt:\n\n" + "\n".join(status_lines),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="embedconfig", description="Xem cấu hình embed hiện tại của máy chủ hoặc kênh")
    @app_commands.describe(channel="Kênh cần xem cấu hình cụ thể (để trống để xem cấu hình máy chủ)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def embedconfig(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        if not self.config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

        channel_id = channel.id if channel else None
        effective = await self.config_manager.get_effective_config(interaction.guild.id, channel_id)
        guild_raw = await self.config_manager.get_guild_config(interaction.guild.id)
        channel_raw = await self.config_manager.get_channel_config(channel_id) if channel_id else {}

        auto_embed = "BẬT" if effective.get("auto_embed_enabled", True) else "TẮT"
        nsfw_mode = effective.get("nsfw_mode", "spoiler")
        suppress = "BẬT" if effective.get("suppress_original_embed", True) else "TẮT"

        platforms = effective.get("platforms_enabled", {})
        platform_lines = [
            f"  • {info['name']}: {'BẬT' if platforms.get(k, True) else 'TẮT'}"
            for k, info in PLATFORMS.items()
        ]

        embed = discord.Embed(
            title=f"Cấu hình Embed -- {channel.name if channel else interaction.guild.name}",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Cài đặt chung",
            value=f"• Tự động tạo embed: **{auto_embed}**\n• Chế độ NSFW: **{nsfw_mode}**\n• Ẩn embed gốc: **{suppress}**",
            inline=False,
        )
        embed.add_field(name="Nền tảng được hỗ trợ", value="\n".join(platform_lines), inline=False)

        if channel_id and channel_raw:
            embed.set_footer(text="Kênh này có cấu hình ghi đè riêng.")
        elif not guild_raw:
            embed.set_footer(text="Đang sử dụng cấu hình mặc định của hệ thống.")

        await interaction.response.send_message(embed=embed, ephemeral=True)


class ProxyCog(commands.Cog):
    """Cog quản lý proxy domains tùy chỉnh cho máy chủ."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = getattr(bot, "config_manager", None)

    proxy_group = app_commands.Group(
        name="proxy",
        description="Quản lý danh sách proxy domain theo nền tảng",
    )

    @proxy_group.command(name="view", description="Xem danh sách proxy hiện tại cho nền tảng")
    @app_commands.describe(platform="Nền tảng cần xem danh sách proxy")
    @app_commands.choices(platform=_PLATFORM_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def proxy_view(self, interaction: discord.Interaction, platform: str):
        if not self.config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

        if platform not in PLATFORMS:
            await interaction.response.send_message(f"Nền tảng '{platform}' không được hỗ trợ.", ephemeral=True)
            return

        platform_info = PLATFORMS[platform]
        guild_domains = await self.config_manager.get_guild_proxy_domains(interaction.guild.id, platform)
        default_domains = PROXY_DOMAINS.get(platform, [])
        is_custom = guild_domains is not None
        active_domains = guild_domains if is_custom else default_domains

        embed = discord.Embed(title=f"Danh sách Proxy - {platform_info['name']}", color=platform_info["color"])
        if active_domains:
            domain_lines = [f"`{i}.` {domain}" for i, domain in enumerate(active_domains, start=1)]
            embed.add_field(name="Danh sách hiện tại" + (" (tuỳ chỉnh)" if is_custom else " (mặc định)"), value="\n".join(domain_lines), inline=False)
        else:
            embed.add_field(name="Danh sách hiện tại", value="Không có proxy nào được cấu hình cho nền tảng này.", inline=False)

        if is_custom and default_domains:
            default_lines = [f"`{i}.` {d}" for i, d in enumerate(default_domains, start=1)]
            embed.add_field(name="Danh sách mặc định toàn cục", value="\n".join(default_lines), inline=False)

        embed.set_footer(text="Proxy được thử theo thứ tự từ trên xuống cho đến khi Discord hiển thị bản xem trước dùng được.", icon_url=platform_info.get("icon_url"))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @proxy_group.command(name="set", description="Ghi đè danh sách proxy cho nền tảng (phân cách bằng dấu phẩy)")
    @app_commands.describe(platform="Nền tảng cần thay đổi proxy", domains="Danh sách domain proxy, phân cách bằng dấu phẩy (VD: fxtwitter.com,vxtwitter.com)")
    @app_commands.choices(platform=_PLATFORM_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def proxy_set(self, interaction: discord.Interaction, platform: str, domains: str):
        if not self.config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

        if platform not in PLATFORMS:
            await interaction.response.send_message(f"Nền tảng '{platform}' không được hỗ trợ.", ephemeral=True)
            return

        parsed = _parse_domain_list(domains)
        if not parsed:
            await interaction.response.send_message("Danh sách domain trống. Vui lòng nhập ít nhất một domain hợp lệ.", ephemeral=True)
            return

        invalid_domains = [d for d in parsed if not _validate_domain(d)]
        if invalid_domains:
            invalid_str = ", ".join(f"`{d}`" for d in invalid_domains)
            await interaction.response.send_message(f"Các domain không hợp lệ: {invalid_str}\nChỉ nhập tên domain (VD: `fxtwitter.com`), không nhập URL đầy đủ.", ephemeral=True)
            return

        if len(parsed) > 10:
            await interaction.response.send_message("Số lượng domain tối đa cho mỗi nền tảng là 10.", ephemeral=True)
            return

        platform_info = PLATFORMS[platform]
        await self.config_manager.set_guild_proxy_domains(interaction.guild.id, platform, parsed)

        domain_lines = [f"`{i}.` {d}" for i, d in enumerate(parsed, start=1)]
        embed = discord.Embed(
            title=f"Đã cập nhật Proxy - {platform_info['name']}",
            description=f"Danh sách proxy mới cho **{interaction.guild.name}**:",
            color=discord.Color.green(),
        )
        embed.add_field(name="Thứ tự ưu tiên", value="\n".join(domain_lines), inline=False)
        embed.set_footer(text="Dùng /proxy reset để khôi phục về mặc định.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @proxy_group.command(name="reset", description="Khôi phục danh sách proxy về mặc định toàn cục")
    @app_commands.describe(platform="Nền tảng cần khôi phục proxy mặc định")
    @app_commands.choices(platform=_PLATFORM_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def proxy_reset(self, interaction: discord.Interaction, platform: str):
        if not self.config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

        if platform not in PLATFORMS:
            await interaction.response.send_message(f"Nền tảng '{platform}' không được hỗ trợ.", ephemeral=True)
            return

        platform_info = PLATFORMS[platform]
        await self.config_manager.reset_guild_proxy_domains(interaction.guild.id, platform)

        default_domains = PROXY_DOMAINS.get(platform, [])
        domains_text = "\n".join(f"`{i}.` {d}" for i, d in enumerate(default_domains, start=1)) if default_domains else "Không có proxy mặc định cho nền tảng này."

        embed = discord.Embed(
            title=f"Đã khôi phục Proxy - {platform_info['name']}",
            description=f"Proxy cho **{platform_info['name']}** đã được đưa về mặc định toàn cục.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Danh sách mặc định", value=domains_text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCog(bot))
    await bot.add_cog(EmbedConfigCog(bot))
    await bot.add_cog(ProxyCog(bot))
