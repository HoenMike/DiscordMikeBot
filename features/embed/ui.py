import discord
from features.embed.constants import PLATFORMS, remove_query_params


def create_platform_view(platform_key: str, original_url: str) -> discord.ui.View | None:
    """Tạo discord.ui.View chứa button link tới bài viết gốc."""
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



class EmbedControlView(discord.ui.View):
    """Owner-only controls shared by every Asumi social preview."""

    def __init__(self, cog, payload: dict, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.payload = dict(payload)
        origin_id = self.payload.get("origin_id", 0)
        platform = self.payload.get("platform", "social")

        self.reload_button = discord.ui.Button(
            label="Tải lại",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id=f"asumi:embed-reload:{origin_id}:{platform}",
        )
        self.reload_button.callback = self._reload_embed
        self.add_item(self.reload_button)

        self.remove_button = discord.ui.Button(
            label="Bỏ embed",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id=f"asumi:embed-remove:{origin_id}:{platform}",
        )
        self.remove_button.callback = self._remove_embed
        self.add_item(self.remove_button)

        # Compatibility for older tests/code that referenced the single Facebook button.
        self.button = self.reload_button

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        author_id = int(self.payload.get("author_id", 0) or 0)
        if interaction.user.id == author_id:
            return True
        await interaction.response.send_message(
            "Chỉ người gửi link gốc mới có thể điều khiển preview này.",
            ephemeral=True,
        )
        return False

    async def _reload_embed(self, interaction: discord.Interaction):
        self.reload_button.disabled = True
        self.remove_button.disabled = True
        await interaction.response.edit_message(view=self)

        try:
            result = await self.cog.reload_embed(
                self.payload,
                current_preview=interaction.message,
            )
        except Exception as exc:
            result = None
            print(f"[EmbedCog] Reload preview lỗi: {exc}", flush=True)

        if result is not None and result.success:
            self.stop()
            await interaction.followup.send(
                "Đã tải lại preview.",
                ephemeral=True,
            )
            return

        reason = getattr(result, "reason", "reload_failed")
        if reason == "no_more_proxy":
            self.reload_button.label = "Hết proxy"
            self.reload_button.disabled = True
        else:
            self.reload_button.disabled = False
        self.remove_button.disabled = False

        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        message = (
            "Đã thử hết proxy khả dụng. Preview hiện tại vẫn được giữ."
            if reason == "no_more_proxy"
            else f"Chưa tải lại được preview (`{reason}`). Preview hiện tại vẫn được giữ."
        )
        await interaction.followup.send(message, ephemeral=True)

    async def _remove_embed(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.cog.restore_original_embed(
                self.payload,
                current_preview=interaction.message,
            )
        except Exception as exc:
            result = None
            print(f"[EmbedCog] Restore original embed lỗi: {exc}", flush=True)

        if result is not None and result.success:
            self.stop()
            await interaction.followup.send(
                "Đã bỏ preview của Asumi và khôi phục embed gốc của Discord.",
                ephemeral=True,
            )
            return

        reason = getattr(result, "reason", "restore_failed")
        await interaction.followup.send(
            f"Chưa thể khôi phục embed gốc (`{reason}`).",
            ephemeral=True,
        )


# Compatibility alias for code/tests from v2.8.2-v2.8.4.
FacebookFallbackView = EmbedControlView


class PlatformToggleSelect(discord.ui.Select):
    """Dropdown multi-select để bật/tắt các nền tảng mạng xã hội."""
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
        config_manager = getattr(interaction.client, "config_manager", None)
        if not config_manager:
            await interaction.response.send_message("Config manager không khả dụng.", ephemeral=True)
            return

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
    """View bọc PlatformToggleSelect với timeout 60 giây."""
    def __init__(self, current_config: dict, scope: str, channel_id: int | None = None):
        super().__init__(timeout=60)
        self.add_item(PlatformToggleSelect(current_config, scope, channel_id))
