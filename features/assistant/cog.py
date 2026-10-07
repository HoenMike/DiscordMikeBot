from __future__ import annotations

import os

from discord.ext import commands

from features.assistant.ai import generate_chat_reply
from features.assistant.response import send_conversation_reply
from features.assistant.router import route_locally
from features.assistant.session import SessionStore
from features.assistant.tools import CommandToolRegistry
from features.assistant.trigger import has_explicit_mention, strip_bot_mention


class AssistantCog(commands.Cog):
    """Asumi 3.1 conversational entrypoint.

    This cog deliberately has no on_message listener. bot_instance owns message
    dispatch so command precedence stays deterministic.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        ttl = float(os.getenv("ASUMI_SESSION_TTL_SECONDS", "1200"))
        turns = int(os.getenv("ASUMI_SESSION_MAX_TURNS", "4"))
        self.sessions = SessionStore(ttl_seconds=ttl, max_turns=turns)
        self.tools = CommandToolRegistry(bot)

    def should_handle(self, message) -> bool:
        bot_user_id = getattr(getattr(self.bot, "user", None), "id", None)
        if has_explicit_mention(message, bot_user_id):
            return True
        return self.sessions.is_live_reply(message)

    def _query_from_message(self, message) -> str:
        content = getattr(message, "content", "") or ""
        bot_user_id = getattr(getattr(self.bot, "user", None), "id", None)
        if has_explicit_mention(message, bot_user_id):
            return strip_bot_mention(content, bot_user_id)
        return content.strip()

    async def handle_conversation_message(self, message) -> bool:
        if not self.should_handle(message):
            return False

        query = self._query_from_message(message)
        decision = route_locally(query)

        if decision.tool:
            result = await self.tools.execute(decision, message)
            if result.handled:
                return True

        previous_session = self.sessions.get(message)
        try:
            async with message.channel.typing():
                reply_text = await generate_chat_reply(
                    query or "Bạn có thể làm gì?",
                    previous_session,
                )
        except Exception as exc:
            print(
                f"❌ [Asumi Conversation] Không tạo được phản hồi: "
                f"{type(exc).__name__}: {str(exc)[:180]}",
                flush=True,
            )
            sent = await message.reply(
                "Mình chưa gọi được AI lúc này. Các lệnh .m và / vẫn hoạt động bình thường.",
                mention_author=False,
            )
            self.sessions.record_exchange(
                message,
                sent.id,
                query,
                "AI unavailable; deterministic commands remain available.",
                intent="chat_error",
            )
            return True

        sent = await send_conversation_reply(message, reply_text)
        self.sessions.record_exchange(
            message,
            sent.id,
            query,
            reply_text,
            intent=decision.intent,
        )
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(AssistantCog(bot))
