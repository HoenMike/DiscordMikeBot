import asyncio
import io
import re
import time

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from features.embed.constants import PLATFORMS, PROXY_DOMAINS, extract_urls
from features.embed.ui import create_platform_view, PlatformToggleView
from features.embed.builder import NSFWFilter, build_embed, build_gallery_embeds
from features.embed.fetchers import FETCHER_MAP
from features.embed.validator import find_valid_proxy
from features.embed.fallback import extract_media_ytdlp
from core.webhook_sender import send_via_webhook

EMBED_COOLDOWN = commands.CooldownMapping.from_cooldown(5, 30.0, commands.BucketType.channel)
MAX_LINKS_PER_MESSAGE = 3
_PIPELINE_TIMEOUT = 45

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
    parts = [d.strip().lower() for d in raw.split(",")]
    return [d for d in parts if d]


class EmbedCog(commands.Cog):
    """Cog xử lý tự động phát hiện, sửa lỗi và nhúng link mạng xã hội."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = getattr(bot, "config_manager", None)
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
        if not content:
            return None
        cleaned = content
        for u in urls:
            escaped_u = re.escape(u)
            pattern = re.compile(rf"(\|\|{escaped_u}\|\||<{escaped_u}>|{escaped_u})")
            cleaned = pattern.sub("", cleaned)
        cleaned = cleaned.strip()
        return cleaned if cleaned else None

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
        platforms_enabled = config.get("platforms_enabled", {})
        processed_urls = [u for _, u, _, _ in detected[:MAX_LINKS_PER_MESSAGE]]
        user_comment = self._extract_user_comment(message.content, processed_urls)
        comment_sent = False

        for platform_key, url, match, is_spoiler in detected[:MAX_LINKS_PER_MESSAGE]:
            if not platforms_enabled.get(platform_key, True):
                continue

            current_comment = user_comment if not comment_sent else None

            success = await self._process_url_with_fallback(
                message, platform_key, url, match, config,
                is_spoiler=is_spoiler, user_comment=current_comment
            )
            if success:
                any_success = True
                comment_sent = True
            else:
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

        if any_success:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                print(f"[EmbedCog] Không thể xoá tin nhắn gốc: {e}", flush=True)
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
        is_spoiler: bool = False,
        user_comment: str | None = None,
    ) -> bool:
        t_start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._run_fallback_chain(
                    message, platform_key, url, match, config,
                    is_spoiler=is_spoiler, user_comment=user_comment
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
            return False

    async def _run_fallback_chain(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        is_spoiler: bool = False,
        user_comment: str | None = None,
    ) -> bool:
        # Tier 0: API Fetcher
        if await self._try_api_fetcher(message, platform_key, url, match, config, is_spoiler=is_spoiler, user_comment=user_comment):
            return True
        # Tier 1: Proxy URL Chain
        if await self._try_proxy_chain(message, platform_key, url, config, is_spoiler=is_spoiler, user_comment=user_comment):
            return True
        # Tier 2: yt-dlp Fallback
        if await self._try_ytdlp_fallback(message, platform_key, url, config, is_spoiler=is_spoiler, user_comment=user_comment):
            return True

        print(f"[EmbedCog] Tất cả các tier đã thất bại cho {platform_key}: {url}", flush=True)
        return False

    async def _try_api_fetcher(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        match: object,
        config: dict,
        is_spoiler: bool = False,
        user_comment: str | None = None,
    ) -> bool:
        fetcher = FETCHER_MAP.get(platform_key)
        if not fetcher or self.session is None:
            return False

        try:
            post_data = await fetcher(self.session, url, match)
            if post_data is None:
                return False

            if is_spoiler:
                post_data.is_spoiler = True

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

            file = None
            if filter_result.should_spoiler_media and post_data.media_urls:
                file = await self._create_spoiler_file(post_data.media_urls[0])

            view = create_platform_view(platform_key, post_data.url or url)

            return await send_via_webhook(
                channel=message.channel,
                user=message.author,
                content=user_comment,
                embeds=embeds,
                file=file,
                view=view,
                original_message=message,
            )
        except Exception as e:
            print(f"[EmbedCog] Tier 0 (API) lỗi cho {platform_key} ({url}): {e}", flush=True)
            return False

    def _replace_url_in_content(self, content: str, original_url: str, new_url: str) -> str:
        if not content:
            return new_url
        escaped = re.escape(original_url)
        pattern = re.compile(rf"(\|\|{escaped}\|\||<{escaped}>|{escaped})")
        if pattern.search(content):
            return pattern.sub(new_url, content, count=1)
        return new_url

    async def _try_proxy_chain(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        config: dict,
        is_spoiler: bool = False,
        user_comment: str | None = None,
    ) -> bool:
        if self.session is None:
            return False

        try:
            guild_proxy_domains = None
            if self.config_manager:
                guild_proxy_domains = await self.config_manager.get_guild_proxy_domains(
                    message.guild.id, platform_key
                )

            proxy_url, is_proxy_nsfw = await find_valid_proxy(
                self.session, url, platform_key,
                guild_proxy_domains=guild_proxy_domains,
            )
            if not proxy_url:
                return False

            is_nsfw_channel = getattr(message.channel, "is_nsfw", False)
            if callable(is_nsfw_channel):
                is_nsfw_channel = is_nsfw_channel()

            is_effective_nsfw = is_proxy_nsfw and not is_nsfw_channel
            nsfw_mode = config.get("nsfw_mode", "spoiler")

            if is_effective_nsfw:
                if nsfw_mode == "block":
                    try:
                        await message.reply(
                            "⚠️ Nội dung NSFW đã bị chặn theo cài đặt của máy chủ.",
                            mention_author=False,
                            delete_after=10,
                        )
                    except Exception:
                        pass
                    return True
                elif nsfw_mode == "spoiler":
                    wrapped_proxy_url = f"||{proxy_url}||"
                else:  # allow
                    wrapped_proxy_url = f"||{proxy_url}||" if is_spoiler else proxy_url
            elif is_spoiler:
                wrapped_proxy_url = f"||{proxy_url}||"
            else:
                wrapped_proxy_url = proxy_url

            view = create_platform_view(platform_key, url)
            full_content = self._replace_url_in_content(message.content, url, wrapped_proxy_url)

            return await send_via_webhook(
                channel=message.channel,
                user=message.author,
                content=full_content,
                view=view,
                original_message=message,
            )
        except Exception as e:
            print(f"[EmbedCog] Tier 1 (Proxy) lỗi cho {platform_key} ({url}): {e}", flush=True)
            return False

    async def _try_ytdlp_fallback(
        self,
        message: discord.Message,
        platform_key: str,
        url: str,
        config: dict,
        is_spoiler: bool = False,
        user_comment: str | None = None,
    ) -> bool:
        try:
            post_data = await extract_media_ytdlp(url, platform_key)
            if post_data is None:
                return False

            if is_spoiler:
                post_data.is_spoiler = True

            filter_result = self.nsfw_filter.process(post_data, message.channel, config)
            if filter_result.is_blocked:
                return False

            single_embed = build_embed(post_data, filter_result)
            if not single_embed:
                return False

            if single_embed.footer and single_embed.footer.text:
                single_embed.set_footer(
                    text=f"{single_embed.footer.text} (yt-dlp fallback)",
                    icon_url=single_embed.footer.icon_url,
                )

            file = None
            if filter_result.should_spoiler_media and post_data.media_urls:
                file = await self._create_spoiler_file(post_data.media_urls[0])
            elif post_data.media_type == "video" and post_data.media_urls and self.session:
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

            view = create_platform_view(platform_key, url)

            return await send_via_webhook(
                channel=message.channel,
                user=message.author,
                content=user_comment,
                embeds=[single_embed],
                file=file,
                view=view,
                original_message=message,
            )
        except Exception as e:
            print(f"[EmbedCog] Tier 2 (yt-dlp) lỗi cho {platform_key} ({url}): {e}", flush=True)
            return False

    async def _create_spoiler_file(self, image_url: str) -> discord.File | None:
        if self.session is None:
            return None
        try:
            async with self.session.get(image_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                image_data = await resp.read()
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
                ext = ext_map.get(content_type.split(";")[0].strip(), "jpg")
                return discord.File(fp=io.BytesIO(image_data), filename=f"SPOILER_nsfw_media.{ext}", spoiler=True)
        except Exception:
            return None


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

        embed.set_footer(text="Proxy được thử theo thứ tự từ trên xuống. Proxy hợp lệ đầu tiên sẽ được sử dụng.", icon_url=platform_info.get("icon_url"))
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
