from __future__ import annotations

import os
import time

from discord.ext import commands, tasks

from core.activity_logger import activity_logger
from features.assistant.ai import ChatTimeoutBudgetError, generate_chat_reply
from features.assistant.context import ContextBuilder
from features.assistant.response import send_conversation_reply
from features.assistant.router import RouteDecision, route_locally, route_message
from features.assistant.session import SessionStore
from features.assistant.tools import CommandToolRegistry
from features.assistant.trigger import has_explicit_mention, strip_bot_mention
from features.assistant.providers.cloudflare import CloudflareDecisionRouter


async def choose_conversation_route(
    query: str,
    *,
    previous_session,
    is_live_continuation: bool,
    has_images: bool,
    cloudflare_router,
    min_confidence: float,
) -> RouteDecision:
    """Choose routing without allowing a live reply to reopen tools."""

    # Explicit Archive actions are user-requested persistence mutations and
    # must beat continuation routing, including when the user replies directly
    # to Asumi's latest response with "nhớ cái này" or "quên #12".
    local = route_locally(query)
    if local.tool and local.tool.startswith("archive."):
        return local

    if is_live_continuation:
        return RouteDecision(
            intent=getattr(previous_session, "intent", None) or "chat",
            source="session_followup",
        )
    if not query and has_images:
        return RouteDecision(intent="vision", source="image_only")
    return await route_message(
        query,
        cloudflare_router=cloudflare_router,
        min_confidence=min_confidence,
    )


class AssistantCog(commands.Cog):
    """Asumi conversational entrypoint.

    This cog deliberately has no on_message listener. bot_instance owns message
    dispatch so command precedence stays deterministic.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        ttl = float(os.getenv("ASUMI_SESSION_TTL_SECONDS", "1200"))
        turns = int(os.getenv("ASUMI_SESSION_MAX_TURNS", "4"))
        self.sessions = SessionStore(ttl_seconds=ttl, max_turns=turns)
        self.tools = CommandToolRegistry(bot)
        self.context_builder = ContextBuilder.from_env()
        self.cloudflare_router = CloudflareDecisionRouter.from_env()
        self.router_min_confidence = float(os.getenv("CF_ROUTER_MIN_CONFIDENCE", "0.55"))

    async def cog_load(self):
        if not self.session_cleanup_loop.is_running():
            self.session_cleanup_loop.start()

    async def cog_unload(self):
        if self.session_cleanup_loop.is_running():
            self.session_cleanup_loop.cancel()

    @tasks.loop(minutes=5)
    async def session_cleanup_loop(self):
        removed = self.sessions.prune_expired()
        if removed:
            print(
                f"🧹 [Asumi Session] Đã giải phóng {removed} session hết hạn.",
                flush=True,
            )

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

    def _log_dashboard_activity(
        self,
        message,
        *,
        action_name: str,
        status: str,
        duration_ms: float,
        details: dict,
    ) -> None:
        """Persist assistant performance metadata without archiving message bodies."""

        try:
            author = message.author
            guild = getattr(message, "guild", None)
            channel = getattr(message, "channel", None)
            avatar = (
                author.display_avatar.url
                if getattr(author, "display_avatar", None)
                else None
            )
            activity_logger.log(
                action_type="assistant",
                action_name=action_name,
                user_id=author.id,
                user_name=(
                    getattr(author, "display_name", None)
                    or getattr(author, "name", str(author))
                ),
                user_avatar=avatar,
                guild_name=getattr(guild, "name", None),
                guild_id=getattr(guild, "id", None),
                channel_name=getattr(channel, "name", None),
                channel_id=getattr(channel, "id", None),
                prompt="",
                response="",
                status=status,
                duration_ms=duration_ms,
                details=details,
            )
        except Exception as exc:
            print(
                f"⚠️ [ActivityLogger] Lỗi ghi nhận Asumi Assistant: "
                f"{type(exc).__name__}: {str(exc)[:160]}",
                flush=True,
            )

    async def handle_conversation_message(self, message) -> bool:
        if not self.should_handle(message):
            return False

        request_started = time.perf_counter()
        request_id = getattr(message, "id", "unknown")
        query = self._query_from_message(message)
        previous_session = self.sessions.get(message)
        is_live_continuation = self.sessions.is_live_reply(message)

        context_started = time.perf_counter()
        context = await self.context_builder.build(
            message,
            query,
            session=previous_session,
            is_live_continuation=is_live_continuation,
        )
        context_ms = (time.perf_counter() - context_started) * 1000

        route_started = time.perf_counter()
        decision = await choose_conversation_route(
            query,
            previous_session=previous_session,
            is_live_continuation=is_live_continuation,
            has_images=bool(context.images),
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
                    f"context_ms={context_ms:.0f} route_ms={route_ms:.0f} "
                    f"clef_ms={decision.clef_ms:.0f} tool_ms={tool_ms:.0f} "
                    f"total_ms={total_ms:.0f}",
                    flush=True,
                )
                self._log_dashboard_activity(
                    message,
                    action_name=f"Asumi → {decision.tool}",
                    status="success",
                    duration_ms=total_ms,
                    details={
                        "request_id": str(request_id),
                        "path": "tool",
                        "intent": decision.intent,
                        "source": decision.source,
                        "tool": decision.tool,
                        "context_ms": round(context_ms, 1),
                        "route_ms": round(route_ms, 1),
                        "clef_ms": round(decision.clef_ms, 1),
                        "tool_ms": round(tool_ms, 1),
                        "total_ms": round(total_ms, 1),
                        "query_chars": len(query),
                        "reply_context": context.reply is not None,
                        "recent_messages": len(context.recent),
                        "images": len(context.images),
                        "tool_output_messages": len(result.response_message_ids),
                        **result.details,
                    },
                )
                if result.response_message_ids:
                    self.sessions.record_exchange(
                        message,
                        result.response_message_ids[-1],
                        query,
                        result.response_context or f"[Tool {decision.tool} completed]",
                        intent=decision.intent,
                        response_message_ids=list(result.response_message_ids),
                        tool=decision.tool,
                    )
                return True

        try:
            ai_started = time.perf_counter()
            async with message.channel.typing():
                default_query = (
                    "Hãy xem ảnh này và mô tả hoặc giải thích nội dung chính."
                    if context.images
                    else "Bạn có thể làm gì?"
                )
                reply = await generate_chat_reply(
                    query or default_query,
                    previous_session,
                    context=context,
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
                f"source={decision.source} context_ms={context_ms:.0f} "
                f"route_ms={route_ms:.0f} clef_ms={decision.clef_ms:.0f} "
                f"total_ms={total_ms:.0f}",
                flush=True,
            )
            is_timeout = isinstance(exc, ChatTimeoutBudgetError)
            sent = await message.reply(
                (
                    "AI chat đang phản hồi quá chậm nên mình đã dừng sớm. "
                    "Bạn thử lại sau một chút; các lệnh .m và / vẫn hoạt động bình thường."
                    if is_timeout
                    else
                    "Mình chưa gọi được AI lúc này. "
                    "Các lệnh .m và / vẫn hoạt động bình thường."
                ),
                mention_author=False,
            )
            self._log_dashboard_activity(
                message,
                action_name="Asumi Chat",
                status="error",
                duration_ms=total_ms,
                details={
                    "request_id": str(request_id),
                    "path": "chat",
                    "intent": decision.intent,
                    "source": decision.source,
                    "context_ms": round(context_ms, 1),
                    "route_ms": round(route_ms, 1),
                    "clef_ms": round(decision.clef_ms, 1),
                    "total_ms": round(total_ms, 1),
                    "error_type": type(exc).__name__,
                    "chat_models_tried": list(
                        getattr(exc, "models_tried", ()) or ()
                    ),
                    "chat_attempts": int(
                        getattr(exc, "attempts", 0) or 0
                    ),
                    "chat_budget_seconds": float(
                        getattr(exc, "budget_seconds", 0.0) or 0.0
                    ),
                    "chat_last_error_type": getattr(
                        exc,
                        "last_error_type",
                        type(exc).__name__,
                    ),
                    "query_chars": len(query),
                    "reply_context": context.reply is not None,
                    "recent_messages": len(context.recent),
                    "images": len(context.images),
                    "session_images": context.used_session_images,
                },
            )
            self.sessions.record_exchange(
                message,
                sent.id,
                query,
                "AI unavailable; deterministic commands remain available.",
                intent="chat_error",
                images=context.images,
            )
            return True

        send_started = time.perf_counter()
        delivery = await send_conversation_reply(message, reply.text)
        sent = delivery.last_message
        send_ms = (time.perf_counter() - send_started) * 1000
        total_ms = (time.perf_counter() - request_started) * 1000

        print(
            f"⏱️ [Asumi Timing] id={request_id} path=chat status=ok "
            f"intent={decision.intent} source={decision.source} "
            f"context_ms={context_ms:.0f} route_ms={route_ms:.0f} "
            f"clef_ms={decision.clef_ms:.0f} ai_ms={ai_ms:.0f} "
            f"model={reply.model} attempts={reply.attempts} "
            f"send_ms={send_ms:.0f} total_ms={total_ms:.0f}",
            flush=True,
        )

        self._log_dashboard_activity(
            message,
            action_name="Asumi Chat",
            status="success",
            duration_ms=total_ms,
            details={
                "request_id": str(request_id),
                "path": "chat",
                "intent": decision.intent,
                "source": decision.source,
                "context_ms": round(context_ms, 1),
                "route_ms": round(route_ms, 1),
                "clef_ms": round(decision.clef_ms, 1),
                "ai_ms": round(ai_ms, 1),
                "send_ms": round(send_ms, 1),
                "total_ms": round(total_ms, 1),
                "model": reply.model,
                "attempts": reply.attempts,
                "query_chars": len(query),
                "response_chars": len(reply.text),
                "reply_context": context.reply is not None,
                "recent_messages": len(context.recent),
                "images": len(context.images),
                "session_images": context.used_session_images,
            },
        )
        self.sessions.record_exchange(
            message,
            sent.id,
            query,
            reply.text,
            intent=decision.intent,
            images=context.images,
            response_message_ids=list(delivery.message_ids),
        )
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(AssistantCog(bot))
