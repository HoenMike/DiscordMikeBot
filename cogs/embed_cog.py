import asyncio
import time

import discord
from discord.ext import commands
import aiohttp
import io

from utils.constants import PLATFORMS
from services.platform_fetchers import FETCHER_MAP
from services.nsfw_filter import NSFWFilter
from services.embed_builder import build_embed, build_gallery_embeds
from services.proxy_validator import find_valid_proxy
from services.ytdlp_fallback import extract_media_ytdlp
from services.webhook_sender import send_via_webhook

EMBED_COOLDOWN = commands.CooldownMapping.from_cooldown(5, 30.0, commands.BucketType.channel)
MAX_LINKS_PER_MESSAGE = 3

# Thời gian chờ tối đa cho toàn bộ pipeline xử lý một URL (giây)
_PIPELINE_TIMEOUT = 45


class EmbedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = bot.config_manager
        self.nsfw_filter = NSFWFilter()
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "MikeDaBot/1.0"}
        )

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _detect_urls(self, content: str) -> list[tuple[str, str, object]]:
        """Phát hiện URL của các nền tảng được hỗ trợ trong nội dung tin nhắn."""
        detected = []
        for platform_key, platform_info in PLATFORMS.items():
            for pattern in platform_info["patterns"]:
                for match in pattern.finditer(content):
                    detected.append((platform_key, match.group(0), match))
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

        for platform_key, url, match in detected[:MAX_LINKS_PER_MESSAGE]:
            if not platforms_enabled.get(platform_key, True):
                continue

            success = await self._process_url_with_fallback(
                message, platform_key, url, match, config
            )
            if success:
                any_success = True

        # Xóa tin nhắn gốc nếu ít nhất một URL được xử lý thành công
        if any_success:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                print(
                    f"[EmbedCog] Không thể xóa tin nhắn gốc: {e}",
                    flush=True,
                )
                # Fallback: ẩn embed gốc nếu không xóa được
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
                self._run_fallback_chain(message, platform_key, url, match, config),
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
    ) -> bool:
        """Thực thi chuỗi fallback 3 tầng tuần tự."""

        # === TIER 0: API Fetcher ===
        result = await self._try_api_fetcher(message, platform_key, url, match, config)
        if result:
            return True

        # === TIER 1: Proxy URL Chain ===
        result = await self._try_proxy_chain(message, platform_key, url)
        if result:
            return True

        # === TIER 2: yt-dlp Fallback ===
        result = await self._try_ytdlp_fallback(message, platform_key, url, config)
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
    ) -> bool:
        """Tier 0: Sử dụng API fetcher để lấy dữ liệu có cấu trúc và tạo embed."""
        fetcher = FETCHER_MAP.get(platform_key)
        if not fetcher:
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

            success = await send_via_webhook(
                channel=message.channel,
                user=message.author,
                embeds=embeds,
                file=file,
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

    async def _try_proxy_chain(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
    ) -> bool:
        """Tier 1: Tìm proxy hợp lệ và gửi URL đã viết lại qua webhook."""
        try:
            proxy_url = await find_valid_proxy(self.session, url, platform_key)
            if not proxy_url:
                return False

            success = await send_via_webhook(
                channel=message.channel,
                user=message.author,
                content=proxy_url,
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
    ) -> bool:
        """Tier 2: Sử dụng yt-dlp để trích xuất media và tạo embed."""
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

            # Thêm ghi chú nguồn fallback
            if single_embed.footer and single_embed.footer.text:
                single_embed.set_footer(
                    text=f"{single_embed.footer.text} (yt-dlp fallback)",
                    icon_url=single_embed.footer.icon_url,
                )

            file = None
            if filter_result.should_spoiler_media and post_data.media_urls:
                file = await self._create_spoiler_file(post_data.media_urls[0])

            success = await send_via_webhook(
                channel=message.channel,
                user=message.author,
                embeds=[single_embed],
                file=file,
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
