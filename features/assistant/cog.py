from __future__ import annotations

import os
import time

from discord.ext import commands

from features.assistant.ai import generate_chat_reply
from features.assistant.response import send_conversation_reply
from features.assistant.router import route_message
from features.assistant.session import SessionStore
from features.assistant.tools import CommandToolRegistry
from features.assistant.trigger import has_explicit_mention, strip_bot_mention
from features.assistant.providers.cloudflare import CloudflareDecisionRouter


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
        self.cloudflare_router = CloudflareDecisionRouter.from_env()
        self.router_min_confidence = float(os.getenv("CF_ROUTER_MIN_CONFIDENCE", "0.55"))

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

        request_started = time.perf_counter()
        request_id = getattr(message, "id", "unknown")
        query = self._query_from_message(message)

        route_started = time.perf_counter()
        decision = await route_message(
            query,
            cloudflare_router=self.cloudflare_router,
            min_confidence=self.router_min_confidence,
        )
        route_ms = (time.perf_counter() - route_started) * 1000

        if decision.tool:
            tool_started = time.perf_counter()
            result = await self.tools.execute(decision, message)
            tool_ms = (time.perf_counter() - tool_started) * 1000
            if result.handled:
                total_ms = (time.perf_counter() - request_started) * 1000
                print(
                    f"⏱️ [Asumi Timing] id={request_id} path=tool "
                    f"intent={decision.intent} source={decision.source} "
                    f"route_ms={route_ms:.0f} clef_ms={decision.clef_ms:.0f} "
                    f"tool_ms={tool_ms:.0f} total_ms={total_ms:.0f}",
                    flush=True,
                )
                return True

        previous_session = self.sessions.get(message)
        try:
            ai_started = time.perf_counter()
            async with message.channel.typing():
                reply = await generate_chat_reply(
                    query or "Bạn có thể làm gì?",
                    previous_session,
                )
            ai_ms = (time.perf_counter() - ai_started) * 1000
        except Exception as exc:
            total_ms = (time.perf_counter() - request_started) * 1000
            print(
                f"❌ [Asumi Conversation] Không tạo được phản hồi: "
                f"{type(exc).__name__}: {str(exc)[:180]}",
                flush=True,
            )
            print(
                f"⏱️ [Asumi Timing] id={request_id} path=chat status=error "
                f"source={decision.source} route_ms={route_ms:.0f} "
                f"clef_ms={decision.clef_ms:.0f} total_ms={total_ms:.0f}",
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

        send_started = time.perf_counter()
        sent = await send_conversation_reply(message, reply.text)
        send_ms = (time.perf_counter() - send_started) * 1000
        total_ms = (time.perf_counter() - request_started) * 1000

        print(
            f"⏱️ [Asumi Timing] id={request_id} path=chat status=ok "
            f"intent={decision.intent} source={decision.source} "
            f"route_ms={route_ms:.0f} clef_ms={decision.clef_ms:.0f} "
            f"ai_ms={ai_ms:.0f} model={reply.model} attempts={reply.attempts} "
            f"send_ms={send_ms:.0f} total_ms={total_ms:.0f}",
            flush=True,
        )

        self.sessions.record_exchange(
            message,
            sent.id,
            query,
            reply.text,
            intent=decision.intent,
        )
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(AssistantCog(bot))
