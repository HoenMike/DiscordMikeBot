import discord
from discord import app_commands
from discord.ext import commands
from utils.constants import CONFIG_KEYS, PLATFORMS


class PlatformToggleSelect(discord.ui.Select):
    def __init__(self, current_config: dict, scope: str, channel_id: int | None = None):
        self.scope = scope
        self.target_channel_id = channel_id

        platforms_enabled = current_config.get("platforms_enabled", {})
        options = []
        for key, info in PLATFORMS.items():
            enabled = platforms_enabled.get(key, True)
            options.append(discord.SelectOption(
                label=info["name"],
                value=key,
                description="Đang bật" if enabled else "Đang tắt",
                default=enabled,
            ))

        super().__init__(
            placeholder="Chọn các nền tảng muốn bật...",
            min_values=0,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = set(self.values)
        config_manager = interaction.client.config_manager

        new_platforms = {key: key in selected for key in PLATFORMS}

        if self.scope == "channel" and self.target_channel_id:
            await config_manager.set_channel_config(
                self.target_channel_id, interaction.guild.id,
                "platforms_enabled", new_platforms
            )
            scope_text = f"kênh <#{self.target_channel_id}>"
        else:
            await config_manager.set_guild_config(
                interaction.guild.id,
                "platforms_enabled", new_platforms
            )
            scope_text = "máy chủ"

        status_lines = [
            f"[{'BẬT' if new_platforms[key] else 'TẮT'}] {info['name']}"
            for key, info in PLATFORMS.items()
        ]

        embed = discord.Embed(
            title="Đã cập nhật cài đặt nền tảng",
            description=f"Phạm vi: **{scope_text}**\n\n" + "\n".join(status_lines),
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class PlatformToggleView(discord.ui.View):
    def __init__(self, current_config: dict, scope: str, channel_id: int | None = None):
        super().__init__(timeout=60)
        self.add_item(PlatformToggleSelect(current_config, scope, channel_id))


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = bot.config_manager

    config_group = app_commands.Group(
        name="config",
        description="Quản lý cấu hình bot cho máy chủ và kênh",
    )

    @config_group.command(name="view", description="Xem cấu hình hiện tại của kênh")
    async def config_view(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        effective = await self.config_manager.get_effective_config(guild_id, channel_id)
        guild_raw = await self.config_manager.get_guild_config_raw(guild_id)
        channel_raw = await self.config_manager.get_channel_config_raw(channel_id)

        embed = discord.Embed(
            title="Cấu hình hiện tại",
            description=f"Kênh: {interaction.channel.mention} | Máy chủ: **{interaction.guild.name}**",
            color=discord.Color.blurple()
        )

        platforms = effective.get("platforms_enabled", {})
        platform_lines = []
        for key, info in PLATFORMS.items():
            enabled = platforms.get(key, True)
            status = "BẬT" if enabled else "TẮT"
            source = ""
            if "platforms_enabled" in channel_raw and key in channel_raw.get("platforms_enabled", {}):
                source = " [Kênh]"
            elif "platforms_enabled" in guild_raw and key in guild_raw.get("platforms_enabled", {}):
                source = " [Máy chủ]"
            platform_lines.append(f"[{status}] {info['name']}{source}")

        embed.add_field(name="Nền tảng", value="\n".join(platform_lines), inline=True)

        nsfw_mode = effective.get("nsfw_mode", "spoiler")
        nsfw_display = {"block": "Chặn", "spoiler": "Che (Spoiler)", "allow": "Cho phép"}.get(nsfw_mode, nsfw_mode)
        auto_embed = "Bật" if effective.get("auto_embed_enabled", True) else "Tắt"
        suppress = "Bật" if effective.get("suppress_original_embed", True) else "Tắt"

        settings_lines = [
            f"**Chế độ NSFW:** {nsfw_display}",
            f"**Tự động Embed:** {auto_embed}",
            f"**Ẩn Embed gốc:** {suppress}",
        ]

        for setting_key in ["nsfw_mode", "auto_embed_enabled", "suppress_original_embed"]:
            if setting_key in channel_raw:
                settings_lines.append(f"`{setting_key}` -> ghi đè bởi Kênh")
            elif setting_key in guild_raw:
                settings_lines.append(f"`{setting_key}` -> ghi đè bởi Máy chủ")

        embed.add_field(name="Cài đặt", value="\n".join(settings_lines), inline=True)

        is_nsfw = getattr(interaction.channel, "is_nsfw", lambda: False)() if callable(getattr(interaction.channel, "is_nsfw", None)) else getattr(interaction.channel, "is_nsfw", False)
        nsfw_status = "Kênh NSFW (Nội dung nhạy cảm hiển thị bình thường)" if is_nsfw else "Kênh thường (Nội dung NSFW xử lý theo cấu hình)"
        embed.add_field(name="Loại kênh", value=nsfw_status, inline=False)

        embed.set_footer(text="Dùng /config set, /config channel_set hoặc /config platforms để thay đổi")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="set", description="Đặt cấu hình mặc định cho toàn máy chủ")
    @app_commands.describe(key="Tên cài đặt", value="Giá trị mới")
    @app_commands.choices(key=[
        app_commands.Choice(name="nsfw_mode (block/spoiler/allow)", value="nsfw_mode"),
        app_commands.Choice(name="auto_embed_enabled (true/false)", value="auto_embed_enabled"),
        app_commands.Choice(name="suppress_original_embed (true/false)", value="suppress_original_embed"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_set(self, interaction: discord.Interaction, key: str, value: str):
        parsed_value, error = self._parse_config_value(key, value)
        if error:
            await interaction.response.send_message(f"Lỗi: {error}", ephemeral=True)
            return

        await self.config_manager.set_guild_config(interaction.guild.id, key, parsed_value)
        embed = discord.Embed(
            title="Đã cập nhật cấu hình máy chủ",
            description=f"**{key}** = `{parsed_value}`\nÁp dụng cho toàn bộ máy chủ **{interaction.guild.name}**.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="channel_set", description="Đặt cấu hình riêng cho kênh hiện tại")
    @app_commands.describe(key="Tên cài đặt", value="Giá trị mới")
    @app_commands.choices(key=[
        app_commands.Choice(name="nsfw_mode (block/spoiler/allow)", value="nsfw_mode"),
        app_commands.Choice(name="auto_embed_enabled (true/false)", value="auto_embed_enabled"),
        app_commands.Choice(name="suppress_original_embed (true/false)", value="suppress_original_embed"),
    ])
    @app_commands.checks.has_permissions(manage_channels=True)
    async def config_channel_set(self, interaction: discord.Interaction, key: str, value: str):
        parsed_value, error = self._parse_config_value(key, value)
        if error:
            await interaction.response.send_message(f"Lỗi: {error}", ephemeral=True)
            return

        await self.config_manager.set_channel_config(interaction.channel.id, interaction.guild.id, key, parsed_value)
        embed = discord.Embed(
            title="Đã cập nhật cấu hình kênh",
            description=f"**{key}** = `{parsed_value}`\nÁp dụng cho kênh {interaction.channel.mention}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="channel_reset", description="Xóa cấu hình riêng của kênh hiện tại")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def config_channel_reset(self, interaction: discord.Interaction):
        await self.config_manager.reset_channel_config(interaction.channel.id, interaction.guild.id)
        embed = discord.Embed(
            title="Đã xóa cài đặt riêng của kênh",
            description=f"{interaction.channel.mention} sẽ áp dụng cấu hình mặc định của máy chủ.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="reset", description="Reset cấu hình máy chủ về mặc định")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_reset(self, interaction: discord.Interaction):
        await self.config_manager.reset_guild_config(interaction.guild.id)
        embed = discord.Embed(
            title="Đã reset cấu hình máy chủ",
            description=f"Toàn bộ cấu hình của **{interaction.guild.name}** đã được đưa về mặc định.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="platforms", description="Bật hoặc tắt các nền tảng mạng xã hội")
    @app_commands.describe(scope="Phạm vi: toàn máy chủ hoặc kênh hiện tại")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Máy chủ", value="guild"),
        app_commands.Choice(name="Kênh hiện tại", value="channel"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_platforms(self, interaction: discord.Interaction, scope: str = "guild"):
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        current_config = await self.config_manager.get_effective_config(guild_id, channel_id)
        scope_text = "máy chủ" if scope == "guild" else f"kênh #{interaction.channel.name}"

        embed = discord.Embed(
            title="Bật/Tắt nền tảng",
            description=f"Chọn các nền tảng muốn bật cho **{scope_text}**.",
            color=discord.Color.blurple()
        )

        view = PlatformToggleView(current_config, scope, channel_id=channel_id if scope == "channel" else None)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @config_set.error
    @config_channel_set.error
    @config_channel_reset.error
    @config_reset.error
    @config_platforms.error
    async def config_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = f"Từ chối truy cập. Cần quyền: {', '.join(error.missing_permissions)}"
        else:
            msg = f"Đã xảy ra lỗi: {error}"

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    @staticmethod
    def _parse_config_value(key: str, raw_value: str) -> tuple:
        meta = CONFIG_KEYS.get(key)
        if not meta:
            return None, f"Cài đặt `{key}` không được hỗ trợ."

        val = raw_value.lower()
        if meta["type"] == "choice":
            if val not in meta["choices"]:
                return None, f"Giá trị `{raw_value}` không hợp lệ cho `{key}`. Cho phép: {', '.join(meta['choices'])}"
            return val, None

        if meta["type"] == "bool":
            if val in ("true", "1", "yes", "on", "bật"):
                return True, None
            elif val in ("false", "0", "no", "off", "tắt"):
                return False, None
            return None, f"Giá trị boolean `{raw_value}` không hợp lệ cho `{key}`."

        return raw_value, None


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
