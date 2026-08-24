import asyncio
import io
import time

import aiohttp
import discord
from discord.ext import commands

from utils.constants import PLATFORMS, extract_urls
from services.platform_fetchers import FETCHER_MAP
from services.embed_builder import NSFWFilter, build_embed, build_gallery_embeds
from services.proxy_validator import find_valid_proxy
from services.ytdlp_fallback import extract_media_ytdlp
from services.webhook_sender import send_via_webhook
from services.platform_ui import create_platform_view

EMBED_COOLDOWN = commands.CooldownMapping.from_cooldown(5, 30.0, commands.BucketType.channel)
MAX_LINKS_PER_MESSAGE = 3

# Thời gian chờ tối đa cho toàn bộ pipeline xử lý một URL (giây)
_PIPELINE_TIMEOUT = 45


import re

class EmbedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = bot.config_manager
        self.nsfw_filter = NSFWFilter()
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discord.app)"}
        )

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _extract_user_comment(self, content: str, urls: list[str]) -> str | None:
        """Trích xuất phần nội dung chữ/lời bình của người dùng, loại bỏ các link đã xử lý."""
        if not content:
            return None
        cleaned = content
        for u in urls:
            escaped_u = re.escape(u)
            pattern = re.compile(rf"(\|\|{escaped_u}\|\||<{escaped_u}>|{escaped_u})")
            cleaned = pattern.sub("", cleaned)
        cleaned = cleaned.strip()
        return cleaned if cleaned else None

    def _detect_urls(self, content: str) -> list[tuple[str, str, object]]:
        """Phát hiện URL của các nền tảng được hỗ trợ trong nội dung tin nhắn.

        Trích xuất danh sách URL duy nhất từ tin nhắn trước, sau đó so khớp
        với từng nền tảng để tuyệt đối tránh tình trạng gửi link 2 lần do trùng lặp pattern.
        """
        raw_urls = extract_urls(content)
        detected = []
        for url, is_spoiler in raw_urls:
            for platform_key, platform_info in PLATFORMS.items():
                matched = False
                for pattern in platform_info["patterns"]:
                    m = pattern.search(url)
                    if m:
                        detected.append((platform_key, url, m))
                        matched = True
                        break
                if matched:
                    break
        return detected

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return

        detected = self._detect_urls(message.content)
        if not detected:
            return

        bucket = EMBED_COOLDOWN.get_bucket(message)
        if bucket.update_rate_limit():
            return

        try:
            config = await self.config_manager.get_effective_config(
                message.guild.id, message.channel.id
            )
        except Exception:
            return

        if not config.get("auto_embed_enabled", True):
            return

        any_success = False
        platforms_enabled = config.get("platforms_enabled", {})
        processed_urls = [u for _, u, _ in detected[:MAX_LINKS_PER_MESSAGE]]
        user_comment = self._extract_user_comment(message.content, processed_urls)

        # Gửi kèm comment của người dùng ở liên kết đầu tiên được xử lý thành công
        comment_sent = False

        for platform_key, url, match in detected[:MAX_LINKS_PER_MESSAGE]:
            if not platforms_enabled.get(platform_key, True):
                continue

            current_comment = user_comment if not comment_sent else None

            success = await self._process_url_with_fallback(
                message, platform_key, url, match, config, user_comment=current_comment
            )
            if success:
                any_success = True
                comment_sent = True
            else:
                # Thông báo cho người dùng khi liên kết bị khoá/riêng tư/lỗi
                platform_name = PLATFORMS.get(platform_key, {}).get("name", platform_key.capitalize())
                try:
                    await message.reply(
                        f"⚠️ Không thể tạo bản xem trước cho liên kết **{platform_name}** này "
                        f"(nội dung có thể ở chế độ riêng tư, nhóm kín hoặc yêu cầu đăng nhập).",
                        mention_author=False,
                        delete_after=15,
                    )
                except Exception:
                    pass

        # Xoá tin nhắn gốc nếu ít nhất một URL được xử lý thành công
        if any_success:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                print(
                    f"[EmbedCog] Không thể xoá tin nhắn gốc: {e}",
                    flush=True,
                )
                # Fallback: ẩn embed gốc nếu không xoá được
                if config.get("suppress_original_embed", True):
                    try:
                        await message.edit(suppress=True)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

    async def _process_url_with_fallback(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        user_comment: str | None = None,
    ) -> bool:
        """Xử lý URL với chuỗi fallback 3 tầng, bọc trong timeout tổng thể.

        Tier 0: API fetcher (dữ liệu có cấu trúc, embed giàu thông tin)
        Tier 1: Proxy URL với xác thực OG metadata
        Tier 2: yt-dlp trích xuất media trực tiếp

        Trả về True nếu gửi thành công qua bất kỳ tier nào.
        """
        t_start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                self._run_fallback_chain(message, platform_key, url, match, config, user_comment=user_comment),
                timeout=_PIPELINE_TIMEOUT,
            )
            elapsed = time.monotonic() - t_start
            if result:
                print(
                    f"[EmbedCog] Xử lý hoàn tất cho {platform_key} trong {elapsed:.2f}s: {url}",
                    flush=True,
                )
            return result

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t_start
            print(
                f"[EmbedCog] Hết thời gian chờ ({_PIPELINE_TIMEOUT}s, "
                f"đã chạy {elapsed:.2f}s) cho {platform_key}: {url}",
                flush=True,
            )
            return False

    async def _run_fallback_chain(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        user_comment: str | None = None,
    ) -> bool:
        """Thực thi chuỗi fallback 3 tầng tuần tự."""

        # === TIER 0: API Fetcher ===
        result = await self._try_api_fetcher(message, platform_key, url, match, config, user_comment=user_comment)
        if result:
            return True

        # === TIER 1: Proxy URL Chain ===
        result = await self._try_proxy_chain(message, platform_key, url, user_comment=user_comment)
        if result:
            return True

        # === TIER 2: yt-dlp Fallback ===
        result = await self._try_ytdlp_fallback(message, platform_key, url, config, user_comment=user_comment)
        if result:
            return True

        print(
            f"[EmbedCog] Tất cả các tier đã thất bại cho {platform_key}: {url}",
            flush=True,
        )
        return False

    async def _try_api_fetcher(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        user_comment: str | None = None,
    ) -> bool:
        """Tier 0: Sử dụng API fetcher để lấy dữ liệu có cấu trúc và tạo embed."""
        fetcher = FETCHER_MAP.get(platform_key)
        if not fetcher or self.session is None:
            return False

        try:
            post_data = await fetcher(self.session, url, match)
            if post_data is None:
                print(
                    f"[EmbedCog] Tier 0 (API) không trả về dữ liệu cho {platform_key}: {url}",
                    flush=True,
                )
                return False

            filter_result = self.nsfw_filter.process(post_data, message.channel, config)
            if filter_result.is_blocked:
                return False

            if post_data.media_type == "gallery" and len(post_data.media_urls) > 1:
                embeds = build_gallery_embeds(post_data, filter_result)
            else:
                single_embed = build_embed(post_data, filter_result)
                embeds = [single_embed] if single_embed else []

            if not embeds:
                return False

            # Xử lý media NSFW với spoiler
            file = None
            if filter_result.should_spoiler_media and post_data.media_urls:
                file = await self._create_spoiler_file(post_data.media_urls[0])

            # Tạo View với nút liên kết tới bài viết gốc
            view = create_platform_view(platform_key, post_data.url or url)

            success = await send_via_webhook(
                channel=message.channel,
                user=message.author,
                content=user_comment,
                embeds=embeds,
                file=file,
                view=view,
                original_message=message,
            )

            if success:
                print(
                    f"[EmbedCog] Tier 0 (API) thành công: {platform_key} - {url}",
                    flush=True,
                )
            return success

        except Exception as e:
            print(
                f"[EmbedCog] Tier 0 (API) lỗi cho {platform_key} ({url}): {e}",
                flush=True,
            )
            return False

    def _replace_url_in_content(self, content: str, original_url: str, new_url: str) -> str:
        """Thay thế chính xác URL gốc bằng proxy_url ngay tại vị trí ban đầu trong tin nhắn."""
        if not content:
            return new_url
        if original_url in content:
            return content.replace(original_url, new_url, 1)
        escaped = re.escape(original_url)
        return re.sub(escaped, new_url, content, count=1)

    async def _try_proxy_chain(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        user_comment: str | None = None,
    ) -> bool:
        """Tier 1: Tìm proxy hợp lệ và gửi URL đã viết lại qua webhook.

        Lấy danh sách proxy tùy chỉnh của guild nếu có, ngược lại dùng mặc định.
        """
        if self.session is None:
            return False

        try:
            # Lấy danh sách proxy tùy chỉnh của guild (nếu đã cấu hình)
            guild_proxy_domains = await self.config_manager.get_guild_proxy_domains(
                message.guild.id, platform_key
            )

            proxy_url = await find_valid_proxy(
                self.session, url, platform_key,
                guild_proxy_domains=guild_proxy_domains,
            )
            if not proxy_url:
                return False

            # Tạo View với nút liên kết tới bài viết gốc
            view = create_platform_view(platform_key, url)

            # Thay thế URL gốc bằng proxy_url ngay tại đúng vị trí xuất hiện trong tin nhắn
            full_content = self._replace_url_in_content(message.content, url, proxy_url)

            success = await send_via_webhook(
                channel=message.channel,
                user=message.author,
                content=full_content,
                view=view,
                original_message=message,
            )

            if success:
                print(
                    f"[EmbedCog] Tier 1 (Proxy) thành công: {platform_key} - {proxy_url}",
                    flush=True,
                )
            return success

        except Exception as e:
            print(
                f"[EmbedCog] Tier 1 (Proxy) lỗi cho {platform_key} ({url}): {e}",
                flush=True,
            )
            return False

    async def _try_ytdlp_fallback(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        config: dict,
        user_comment: str | None = None,
    ) -> bool:
        """Tier 2: Sử dụng yt-dlp để trích xuất media và tạo embed.

        Embed tạo từ yt-dlp tự động áp dụng màu thương hiệu và icon
        của nền tảng tương ứng từ PLATFORMS trong constants.py.
        """
        try:
            post_data = await extract_media_ytdlp(url, platform_key)
            if post_data is None:
                return False

            filter_result = self.nsfw_filter.process(post_data, message.channel, config)
            if filter_result.is_blocked:
                return False

            single_embed = build_embed(post_data, filter_result)
            if not single_embed:
                return False

            # Thêm ghi chú nguồn fallback vào footer
            if single_embed.footer and single_embed.footer.text:
                single_embed.set_footer(
                    text=f"{single_embed.footer.text} (yt-dlp fallback)",
                    icon_url=single_embed.footer.icon_url,
                )

            file = None
            if filter_result.should_spoiler_media and post_data.media_urls:
                file = await self._create_spoiler_file(post_data.media_urls[0])
            elif post_data.media_type == "video" and post_data.media_urls and self.session:
                # Cố gắng tải file video trực tiếp nếu <= 25MB để phát trực tiếp trong Discord
                video_url = post_data.media_urls[0]
                try:
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    async with self.session.get(video_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            content_len = resp.headers.get("Content-Length")
                            if not content_len or int(content_len) <= 25 * 1024 * 1024:
                                video_data = await resp.read()
                                if len(video_data) <= 25 * 1024 * 1024:
                                    file = discord.File(
                                        fp=io.BytesIO(video_data),
                                        filename=f"{platform_key}_video.mp4",
                                    )
                except Exception as dl_err:
                    print(f"[EmbedCog] Không thể tải video fallback {url}: {dl_err}", flush=True)

            # Tạo View với nút liên kết tới bài viết gốc
            view = create_platform_view(platform_key, url)

            success = await send_via_webhook(
                channel=message.channel,
                user=message.author,
                content=user_comment,
                embeds=[single_embed],
                file=file,
                view=view,
                original_message=message,
            )

            if success:
                print(
                    f"[EmbedCog] Tier 2 (yt-dlp) thành công: {platform_key} - {url}",
                    flush=True,
                )
            return success

        except Exception as e:
            print(
                f"[EmbedCog] Tier 2 (yt-dlp) lỗi cho {platform_key} ({url}): {e}",
                flush=True,
            )
            return False

    async def _create_spoiler_file(self, image_url: str) -> discord.File | None:
        """Tải và tạo file spoiler từ URL media."""
        if self.session is None:
            return None

        try:
            async with self.session.get(
                image_url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None

                image_data = await resp.read()
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                ext_map = {
                    "image/jpeg": "jpg",
                    "image/png": "png",
                    "image/gif": "gif",
                    "image/webp": "webp",
                }
                ext = ext_map.get(content_type.split(";")[0].strip(), "jpg")

                return discord.File(
                    fp=io.BytesIO(image_data),
                    filename=f"SPOILER_nsfw_media.{ext}",
                    spoiler=True,
                )
        except Exception:
            return None


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCog(bot))
