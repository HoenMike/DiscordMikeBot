"""T23.2: private Discord notifications from durable Turso outbox."""
import discord
from discord.ext import tasks
from features.feedback.store import feedback_store, FeedbackStorageError


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
            safe_reason = discord.utils.escape_mentions(str(reason or "Chưa có chi tiết."))[:1200]
            text = (
                f"📩 Ticket #{number}: {status}\n"
                f"Lý do / cập nhật: {safe_reason}\n"
                f"Dùng /feedback status với mã #{number} để xem chi tiết riêng tư."
            )
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
