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



class FacebookFallbackView(discord.ui.View):
    """Nút phụ để người gửi link tự chuyển sang proxy Facebook kế tiếp."""

    def __init__(self, cog, payload: dict, timeout: float = 900):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.payload = dict(payload)
        self.button = discord.ui.Button(
            label="Proxy khác",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id=f"asumi:fb-proxy-roll:{self.payload.get('origin_id', 0)}",
        )
        self.button.callback = self._roll_proxy
        self.add_item(self.button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        author_id = int(self.payload.get("author_id", 0) or 0)
        if interaction.user.id == author_id:
            return True
        await interaction.response.send_message(
            "Chỉ người gửi link gốc mới có thể đổi proxy.",
            ephemeral=True,
        )
        return False

    async def _roll_proxy(self, interaction: discord.Interaction):
        self.button.disabled = True
        await interaction.response.edit_message(view=self)

        try:
            result = await self.cog.roll_facebook_proxy(
                self.payload,
                current_preview=interaction.message,
            )
        except Exception as exc:
            result = None
            print(f"[EmbedCog] Facebook proxy roll lỗi: {exc}", flush=True)

        if result is not None and result.success:
            self.stop()
            await interaction.followup.send(
                f"Đã chuyển sang proxy khác: `{result.proxy_domain or 'proxy mới'}`.",
                ephemeral=True,
            )
            return

        reason = getattr(result, "reason", "proxy_roll_failed")
        if reason == "no_more_proxy":
            self.button.label = "Hết proxy"
            self.button.disabled = True
        else:
            self.button.disabled = False

        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        message = (
            "Đã thử hết proxy Facebook khả dụng."
            if reason == "no_more_proxy"
            else f"Chưa đổi được proxy (`{reason}`). Preview hiện tại vẫn được giữ."
        )
        await interaction.followup.send(message, ephemeral=True)


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
