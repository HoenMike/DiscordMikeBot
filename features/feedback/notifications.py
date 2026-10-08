"""T23.2: private Discord notifications from durable Turso outbox."""
import discord
from discord.ext import tasks
from features.feedback.store import feedback_store, FeedbackStorageError


STATUS_LABELS = {
    "needs_info": "Cần bạn bổ sung thông tin",
    "rejected": "Không được duyệt",
    "duplicate": "Đã ghi nhận trùng ticket",
    "deferred": "Tạm hoãn xử lý",
    "approved": "Đã duyệt để triển khai",
    "verified": "Đã sửa và xác minh",
    "closed": "Đã đóng",
    "reopened": "Đã mở lại",
}


def format_feedback_notification(*, number: int, status: str, reason: str) -> str:
    """A human-friendly event-specific DM. No raw Discord mentions/pings."""
    heading = STATUS_LABELS.get(status, status)
    safe_reason = discord.utils.escape_mentions(str(reason or "Chưa có chi tiết."))[:1200]
    return (
        f"📩 **Asumi Feedback #{number} — {heading}**\n"
        f"**Lý do / cập nhật:** {safe_reason}\n"
        f"Dùng `/feedback status` với mã **#{number}** để xem thông tin riêng tư."
    )


class FeedbackNotifier:
    def __init__(self, bot):
        self.bot = bot
        self.delivery.start()

    def stop(self):
        self.delivery.cancel()

    @tasks.loop(minutes=2)
    async def delivery(self):
        try:
            items = await feedback_store.pending_notifications()
        except FeedbackStorageError:
            return
        for notice_id, ticket_id, user_id, action, reason, status, number in items:
            # PR merge / deploy isn't a verified fix; don't promise resolution.
            if action not in ("needs_info", "rejected", "duplicate", "deferred",
                              "approved", "verified", "closed", "reopened"):
                try:
                    await feedback_store.mark_notification(notice_id, delivered=True)
                except FeedbackStorageError:
                    return
                continue
            text = format_feedback_notification(number=number, status=status, reason=reason)
            try:
                user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                await user.send(text, allowed_mentions=discord.AllowedMentions.none())
                await feedback_store.mark_notification(notice_id, delivered=True)
            except (discord.Forbidden, discord.HTTPException) as exc:
                try:
                    await feedback_store.mark_notification(
                        notice_id, delivered=False, error=type(exc).__name__
                    )
                except FeedbackStorageError:
                    return
            except Exception as exc:
                print(f"[Feedback] notification error: {type(exc).__name__}", flush=True)

    @delivery.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()
