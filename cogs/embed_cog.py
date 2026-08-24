import discord
from discord.ext import commands
import aiohttp
import io

from utils.constants import PLATFORMS
from services.platform_fetchers import FETCHER_MAP
from services.embed_builder import NSFWFilter, build_embed, build_gallery_embeds

EMBED_COOLDOWN = commands.CooldownMapping.from_cooldown(5, 30.0, commands.BucketType.channel)
MAX_LINKS_PER_MESSAGE = 3


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

        should_suppress = False
        platforms_enabled = config.get("platforms_enabled", {})

        for platform_key, url, match in detected[:MAX_LINKS_PER_MESSAGE]:
            if not platforms_enabled.get(platform_key, True):
                continue

            fetcher = FETCHER_MAP.get(platform_key)
            if not fetcher:
                continue

            try:
                post_data = await fetcher(self.session, url, match)
                if post_data is None:
                    continue

                filter_result = self.nsfw_filter.process(post_data, message.channel, config)
                if filter_result.is_blocked:
                    continue

                if post_data.media_type == "gallery" and len(post_data.media_urls) > 1:
                    embeds = build_gallery_embeds(post_data, filter_result)
                else:
                    single_embed = build_embed(post_data, filter_result)
                    embeds = [single_embed] if single_embed else []

                if not embeds:
                    continue

                if filter_result.should_spoiler_media and post_data.media_urls:
                    await self._send_with_spoiler_media(message, embeds, post_data.media_urls[0])
                else:
                    await message.reply(embeds=embeds, mention_author=False)

                should_suppress = True

            except Exception as e:
                print(f"[EmbedCog] Lỗi khi xử lý {platform_key} ({url}): {e}", flush=True)
                continue

        if should_suppress and config.get("suppress_original_embed", True):
            try:
                await message.edit(suppress=True)
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _send_with_spoiler_media(
        self,
        message: discord.Message,
        embeds: list[discord.Embed],
        image_url: str,
    ):
        try:
            async with self.session.get(image_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    await message.reply(embeds=embeds, mention_author=False)
                    return

                image_data = await resp.read()
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                ext_map = {
                    "image/jpeg": "jpg",
                    "image/png": "png",
                    "image/gif": "gif",
                    "image/webp": "webp",
                }
                ext = ext_map.get(content_type.split(";")[0].strip(), "jpg")

                file = discord.File(
                    fp=io.BytesIO(image_data),
                    filename=f"SPOILER_nsfw_media.{ext}",
                    spoiler=True,
                )

                await message.reply(embeds=embeds, file=file, mention_author=False)

        except Exception:
            await message.reply(embeds=embeds, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCog(bot))
