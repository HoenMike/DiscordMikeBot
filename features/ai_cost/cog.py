"""Private owner-only on-demand estimated Gemini API usage report."""
from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from core.ai_usage import store, render_report, _pending


class AICostCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="ai_cost",
        description="Báo cáo token/model và dự kiến tiền Gemini API (chỉ chủ Asumi)",
    )
    @app_commands.guild_only()
    @app_commands.choices(days=[
        app_commands.Choice(name="7 ngày", value=7),
        app_commands.Choice(name="30 ngày", value=30),
    ])
    @app_commands.describe(
        days="Khoảng thời gian theo dõi (cửa sổ trượt)",
        prepay_vnd="Số dư Prepay nhập thủ công, không tự lấy từ Google",
        credits_vnd="Chỉ nhập credit đã xác nhận dùng được cho Gemini API",
        fx_vnd="Tỷ giá VND/USD dùng để ước lượng (mặc định 26000)",
    )
    async def ai_cost(self, interaction: discord.Interaction, days: int = 7,
                      prepay_vnd: int | None = None, credits_vnd: int | None = None,
                      fx_vnd: int = 26000):
        # Defer *before* owner lookup/remote Turso, respecting Discord ACK limit.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            is_owner = await self.bot.is_owner(interaction.user)
        except (discord.DiscordException, OSError, asyncio.TimeoutError):
            await interaction.followup.send(
                "Không xác minh được chủ bot lúc này, thử lại sau.", ephemeral=True)
            return
        if not is_owner:
            await interaction.followup.send(
                "Báo cáo chi phí toàn bot chỉ dành cho chủ ứng dụng Asumi.",
                ephemeral=True,
            )
            return
        if days not in (7, 30) or not 1000 <= fx_vnd <= 100000:
            await interaction.followup.send("Tham số báo cáo không hợp lệ.", ephemeral=True)
            return
        if (prepay_vnd is not None and not 0 <= prepay_vnd <= 1_000_000_000) or (
            credits_vnd is not None and not 0 <= credits_vnd <= 1_000_000_000
        ):
            await interaction.followup.send(
                "Số dư phải là số dương và nhỏ hơn 1 tỷ đồng.", ephemeral=True)
            return
        if credits_vnd is not None and prepay_vnd is None:
            await interaction.followup.send(
                "Nhập prepay_vnd cùng credits_vnd để dự kiến thời gian duy trì.",
                ephemeral=True)
            return
        # Pending telemetry tasks may have recorded a reply only moments ago.
        # Do not indefinitely wait for an unreachable store.
        try:
            if _pending:
                await asyncio.wait_for(
                    asyncio.gather(*list(_pending), return_exceptions=True), timeout=2
                )
        except asyncio.TimeoutError:
            pass
        try:
            rows = await asyncio.wait_for(store.aggregate(days), timeout=8)
            message = render_report(rows, days=days, prepay_vnd=prepay_vnd,
                                    eligible_credits_vnd=credits_vnd,
                                    vnd_per_usd=fx_vnd)
        except (Exception, asyncio.TimeoutError) as exc:
            print("[AI Cost] report unavailable: " + type(exc).__name__, flush=True)
            await interaction.followup.send(
                "Chưa đọc được số liệu Turso. Không có báo cáo ước tính hợp lệ lúc này.",
                ephemeral=True)
            return
        # Split safely only if model list becomes unusually large.
        for i in range(0, len(message), 1800):
            await interaction.followup.send(
                message[i:i + 1800], ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AICostCog(bot))
