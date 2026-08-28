import discord
from features.embed.constants import PLATFORMS, remove_query_params


class EmbedPreviewView(discord.ui.View):

    """View cho bản xem trước Embed: Nút link bài viết gốc + Nút 🗑️ xóa preview."""
    def __init__(self, platform_key: str, original_url: str, author_id: int | None = None, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.author_id = author_id

        clean_url = remove_query_params(original_url) if original_url else None
        if clean_url and len(clean_url) > 512:
            clean_url = original_url.split("?")[0]

        if clean_url and len(clean_url) <= 512 and clean_url.startswith(("http://", "https://")):
            platform_info = PLATFORMS.get(platform_key, {})
            label = platform_info.get("button_label", "Xem bài viết gốc")
            self.add_item(discord.ui.Button(label=label, url=clean_url, style=discord.ButtonStyle.link, row=0))

        if author_id is not None:
            del_btn = discord.ui.Button(emoji="🗑️", style=discord.ButtonStyle.secondary, custom_id="delete_embed_preview", row=0)
            del_btn.callback = self._delete_callback
            self.add_item(del_btn)

    async def _delete_callback(self, interaction: discord.Interaction):
        # Cho phép người gửi tin nhắn gốc hoặc Quản trị viên (manage_messages) xóa preview
        is_author = self.author_id is None or interaction.user.id == self.author_id
        is_admin = interaction.user.guild_permissions.manage_messages if interaction.guild else False
        if is_author or is_admin:
            try:
                await interaction.message.delete()
            except Exception:
                pass
        else:
            await interaction.response.send_message("🔒 Chỉ người gửi tin nhắn hoặc Quản trị viên mới có thể xóa bản xem trước này!", ephemeral=True)


def create_platform_view(platform_key: str, original_url: str, author_id: int | None = None) -> discord.ui.View | None:
    """Tạo discord.ui.View chứa button link tới bài viết gốc và nút xóa preview."""
    view = EmbedPreviewView(platform_key, original_url, author_id=author_id)
    return view if view.children else None



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
