"""Always acknowledge failed Discord slash commands with a private explanation.

Known access errors are user-actionable, not unhandled server exceptions.
Unknown errors must be logged by the caller before returning a generic reply.
"""
from __future__ import annotations

import discord
from discord import app_commands


def app_error_message(error: app_commands.AppCommandError) -> str:
    if isinstance(error, app_commands.CommandOnCooldown):
        return (
            "⏳ Bạn đang thao tác quá nhanh. "
            f"Thử lại sau {int(error.retry_after) + 1} giây."
        )
    if isinstance(error, app_commands.MissingPermissions):
        missing = ", ".join(error.missing_permissions)
        return (
            "⛔ Bạn không có quyền thực hiện lệnh này "
            f"({missing}). Hãy nhờ quản trị viên server hỗ trợ."
        )
    if isinstance(error, app_commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions)
        return f"⛔ Asumi chưa được cấp quyền cần thiết ({missing})."
    if isinstance(error, app_commands.CheckFailure):
        # Custom Codex owner-auth raises a concise, actionable message.
        return str(error) if error.args else "⛔ Bạn không có quyền dùng lệnh này."
    return "❌ Asumi gặp lỗi khi xử lý lệnh. Vui lòng thử lại hoặc báo cho quản trị viên."


async def reply_app_error(interaction: discord.Interaction,
                          error: app_commands.AppCommandError) -> None:
    message = app_error_message(error)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.response.send_message(
                message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
    except discord.HTTPException as exc:
        print(f"[Slash Command] Could not reply with error: {type(exc).__name__}", flush=True)
