import re
import discord
from discord import app_commands
from discord.ext import commands

from utils.constants import PLATFORMS, PROXY_DOMAINS


# Regex kiểm tra domain hợp lệ (chỉ chấp nhận domain, không chấp nhận URL đầy đủ)
_DOMAIN_PATTERN = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)+$"
)

# Danh sách tên nền tảng hợp lệ cho autocomplete
_PLATFORM_CHOICES = [
    app_commands.Choice(name=info["name"], value=key)
    for key, info in PLATFORMS.items()
]


def _validate_domain(domain: str) -> bool:
    """Kiểm tra xem chuỗi có phải domain hợp lệ không (không phải URL đầy đủ)."""
    domain = domain.strip().lower()
    if not domain:
        return False
    # Loại bỏ trường hợp người dùng nhập URL đầy đủ
    if domain.startswith(("http://", "https://")):
        return False
    return _DOMAIN_PATTERN.match(domain) is not None


def _parse_domain_list(raw: str) -> list[str]:
    """Phân tích chuỗi domain phân cách bởi dấu phẩy thành danh sách đã chuẩn hoá."""
    parts = [d.strip().lower() for d in raw.split(",")]
    return [d for d in parts if d]


class ProxyCog(commands.Cog):
    """Quản lý danh sách proxy domain theo nền tảng cho từng máy chủ."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = bot.config_manager

    proxy_group = app_commands.Group(
        name="proxy",
        description="Quản lý danh sách proxy domain theo nền tảng",
    )

    @proxy_group.command(
        name="view",
        description="Xem danh sách proxy hiện tại cho nền tảng"
    )
    @app_commands.describe(platform="Nền tảng cần xem danh sách proxy")
    @app_commands.choices(platform=_PLATFORM_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def proxy_view(self, interaction: discord.Interaction, platform: str):
        if platform not in PLATFORMS:
            await interaction.response.send_message(
                f"Nền tảng '{platform}' không được hỗ trợ.", ephemeral=True
            )
            return

        platform_info = PLATFORMS[platform]
        guild_domains = await self.config_manager.get_guild_proxy_domains(
            interaction.guild.id, platform
        )

        default_domains = PROXY_DOMAINS.get(platform, [])
        is_custom = guild_domains is not None
        active_domains = guild_domains if is_custom else default_domains

        embed = discord.Embed(
            title=f"Danh sách Proxy - {platform_info['name']}",
            color=platform_info["color"],
        )

        if active_domains:
            domain_lines = []
            for i, domain in enumerate(active_domains, start=1):
                domain_lines.append(f"`{i}.` {domain}")
            embed.add_field(
                name="Danh sách hiện tại" + (" (tuỳ chỉnh)" if is_custom else " (mặc định)"),
                value="\n".join(domain_lines),
                inline=False,
            )
        else:
            embed.add_field(
                name="Danh sách hiện tại",
                value="Không có proxy nào được cấu hình cho nền tảng này.",
                inline=False,
            )

        if is_custom and default_domains:
            default_lines = [f"`{i}.` {d}" for i, d in enumerate(default_domains, start=1)]
            embed.add_field(
                name="Danh sách mặc định toàn cục",
                value="\n".join(default_lines),
                inline=False,
            )

        embed.set_footer(
            text="Proxy được thử theo thứ tự từ trên xuống. Proxy hợp lệ đầu tiên sẽ được sử dụng.",
            icon_url=platform_info.get("icon_url"),
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @proxy_group.command(
        name="set",
        description="Ghi đè danh sách proxy cho nền tảng (phân cách bằng dấu phẩy)"
    )
    @app_commands.describe(
        platform="Nền tảng cần thay đổi proxy",
        domains="Danh sách domain proxy, phân cách bằng dấu phẩy (VD: fxtwitter.com,vxtwitter.com)"
    )
    @app_commands.choices(platform=_PLATFORM_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def proxy_set(self, interaction: discord.Interaction, platform: str, domains: str):
        if platform not in PLATFORMS:
            await interaction.response.send_message(
                f"Nền tảng '{platform}' không được hỗ trợ.", ephemeral=True
            )
            return

        parsed = _parse_domain_list(domains)
        if not parsed:
            await interaction.response.send_message(
                "Danh sách domain trống. Vui lòng nhập ít nhất một domain hợp lệ.",
                ephemeral=True,
            )
            return

        # Kiểm tra từng domain
        invalid_domains = [d for d in parsed if not _validate_domain(d)]
        if invalid_domains:
            invalid_str = ", ".join(f"`{d}`" for d in invalid_domains)
            await interaction.response.send_message(
                f"Các domain không hợp lệ: {invalid_str}\n"
                f"Chỉ nhập tên domain (VD: `fxtwitter.com`), không nhập URL đầy đủ.",
                ephemeral=True,
            )
            return

        # Giới hạn số lượng domain tối đa
        if len(parsed) > 10:
            await interaction.response.send_message(
                "Số lượng domain tối đa cho mỗi nền tảng là 10.",
                ephemeral=True,
            )
            return

        platform_info = PLATFORMS[platform]
        await self.config_manager.set_guild_proxy_domains(
            interaction.guild.id, platform, parsed
        )

        domain_lines = [f"`{i}.` {d}" for i, d in enumerate(parsed, start=1)]
        embed = discord.Embed(
            title=f"Đã cập nhật Proxy - {platform_info['name']}",
            description=f"Danh sách proxy mới cho **{interaction.guild.name}**:",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Thứ tự ưu tiên",
            value="\n".join(domain_lines),
            inline=False,
        )
        embed.set_footer(text="Dùng /proxy reset để khôi phục về mặc định.")

        await interaction.response.send_message(embed=embed, ephemeral=True)
        print(
            f"[ProxyCog] Guild {interaction.guild.id} đã cập nhật proxy cho {platform}: "
            f"{parsed}",
            flush=True,
        )

    @proxy_group.command(
        name="reset",
        description="Khôi phục danh sách proxy về mặc định toàn cục"
    )
    @app_commands.describe(platform="Nền tảng cần khôi phục proxy mặc định")
    @app_commands.choices(platform=_PLATFORM_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def proxy_reset(self, interaction: discord.Interaction, platform: str):
        if platform not in PLATFORMS:
            await interaction.response.send_message(
                f"Nền tảng '{platform}' không được hỗ trợ.", ephemeral=True
            )
            return

        platform_info = PLATFORMS[platform]
        await self.config_manager.reset_guild_proxy_domains(
            interaction.guild.id, platform
        )

        default_domains = PROXY_DOMAINS.get(platform, [])
        if default_domains:
            domain_lines = [f"`{i}.` {d}" for i, d in enumerate(default_domains, start=1)]
            domains_text = "\n".join(domain_lines)
        else:
            domains_text = "Không có proxy mặc định cho nền tảng này."

        embed = discord.Embed(
            title=f"Đã khôi phục Proxy - {platform_info['name']}",
            description=f"Proxy cho **{platform_info['name']}** đã được đưa về mặc định toàn cục.",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Danh sách mặc định",
            value=domains_text,
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        print(
            f"[ProxyCog] Guild {interaction.guild.id} đã khôi phục proxy mặc định cho {platform}",
            flush=True,
        )

    # ---------------------------------------------------------------------------
    # Xử lý lỗi quyền hạn
    # ---------------------------------------------------------------------------

    @proxy_view.error
    @proxy_set.error
    @proxy_reset.error
    async def proxy_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
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


async def setup(bot: commands.Bot):
    await bot.add_cog(ProxyCog(bot))
