"""
features/watch/notifier.py - Discord notification formatting, idempotency protection,
and delivery for Watch alerts.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional, Tuple
import discord
from discord.ext import commands

from core.activity_logger import activity_logger
from features.watch.constants import MAX_NOTIFICATION_SOURCES, WATCH_EMBED_COLOR
from features.watch.models import EvaluationResult, SearchResult, WatchDefinition, WatchResult


def _vn_now_str() -> str:
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).strftime("%H:%M")


def build_watch_embed(
    watch: WatchDefinition,
    eval_result: EvaluationResult,
    sources: List[Any],  # List[SearchResult] or List[WatchResult]
    is_terminal: bool = False,
) -> discord.Embed:
    """
    Constructs a concise, beautiful Discord Embed for meaningful Watch updates.
    """
    title_text = f"🔭 WATCH — {watch.title}"
    embed = discord.Embed(
        title=title_text[:256],
        color=WATCH_EMBED_COLOR,
    )

    desc_lines = [
        "**Có diễn biến mới đáng chú ý:**",
        eval_result.summary or "Phát hiện thông tin cập nhật mới liên quan đến chủ đề đang theo dõi.",
    ]

    if is_terminal:
        desc_lines.append("\n✅ **Điều kiện Watch đã được đáp ứng và Watch này đã hoàn tất.**")

    embed.description = "\n".join(desc_lines)

    # Pick 1-3 best sources
    selected_sources = sources[:MAX_NOTIFICATION_SOURCES]
    if selected_sources:
        source_lines = []
        for s in selected_sources:
            s_title = getattr(s, "title", "Tin tức")
            # Truncate title if needed
            s_title_clean = s_title.replace("[", "(").replace("]", ")")[:80]
            s_url = getattr(s, "canonical_url", "") or getattr(s, "url", "")
            s_domain = getattr(s, "source_domain", "")
            domain_label = f" ({s_domain})" if s_domain else ""
            if s_url:
                source_lines.append(f"• [{s_title_clean}]({s_url}){domain_label}")
            else:
                source_lines.append(f"• {s_title_clean}{domain_label}")

        embed.add_field(
            name="**Nguồn**",
            value="\n".join(source_lines),
            inline=False,
        )

    # Footer
    time_str = _vn_now_str()
    status_note = "Watch đã hoàn tất" if is_terminal else "Watch tiếp tục theo dõi"
    embed.set_footer(
        text=f"Asumi kiểm tra lúc {time_str} · {status_note}"
    )

    return embed


async def send_watch_notification(
    bot: commands.Bot,
    watch: WatchDefinition,
    eval_result: EvaluationResult,
    sources: List[Any],
    is_terminal: bool = False,
) -> bool:
    """
    Delivers a notification to the configured channel with strict AllowedMentions protection.
    """
    if not bot.is_ready():
        return False

    channel = bot.get_channel(watch.channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(watch.channel_id)
        except Exception:
            return False

    if not channel or not hasattr(channel, "send"):
        return False

    embed = build_watch_embed(watch, eval_result, sources, is_terminal=is_terminal)

    try:
        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        try:
            activity_logger.log(
                action_type="watch",
                action_name="Gửi thông báo Watch",
                user_id=watch.owner_user_id,
                user_name=f"User {watch.owner_user_id}",
                guild_id=watch.guild_id,
                channel_id=watch.channel_id,
                prompt=f"Watch #{watch.id}: {watch.title}",
                response=f"Đã gửi thông báo: {eval_result.summary[:150]}",
                status="success",
                details={
                    "watch_id": watch.id,
                    "is_terminal": is_terminal,
                    "event_fingerprint": eval_result.event_fingerprint,
                },
            )
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"⚠️ [WatchNotifier] Gửi thông báo thất bại cho channel {watch.channel_id}: {e}", flush=True)
        return False
