from __future__ import annotations

import copy
from dataclasses import dataclass

from features.assistant.router import RouteDecision


@dataclass(frozen=True)
class ToolExecutionResult:
    handled: bool
    command_text: str | None = None
    response_message_ids: tuple[int, ...] = ()
    response_context: str = ""


def _render_bot_message(message, max_chars: int = 2200) -> str:
    parts: list[str] = []
    content = (getattr(message, "content", "") or "").strip()
    if content:
        parts.append(content)

    for embed in list(getattr(message, "embeds", None) or [])[:3]:
        title = (getattr(embed, "title", None) or "").strip()
        description = (getattr(embed, "description", None) or "").strip()
        if title:
            parts.append(title)
        if description:
            parts.append(description[:1200])
        for field in list(getattr(embed, "fields", None) or [])[:8]:
            name = (getattr(field, "name", None) or "").strip()
            value = (getattr(field, "value", None) or "").strip()
            if name or value:
                parts.append(f"{name}: {value}"[:700])

    for attachment in list(getattr(message, "attachments", None) or [])[:4]:
        filename = getattr(attachment, "filename", None)
        if filename:
            parts.append(f"[Attachment] {filename}")

    return "\n".join(parts)[:max_chars]


class CommandToolRegistry:
    """Closed bridge from typed assistant tools to existing prefix commands.

    A shallow copy of the Discord message is used so existing command parsing,
    checks and cooldowns run normally without mutating the live gateway event.
    """

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _command_for(decision: RouteDecision) -> str | None:
        if decision.tool == "help.show":
            return ".m help"
        if decision.tool == "tarot.daily":
            return ".m tarot daily"
        if decision.tool == "tarot.launch":
            return ".m tarot"
        if decision.tool == "summary.catchup":
            hours = decision.arguments.get("hours")
            if hours is None:
                return ".m tomtat"
            safe_hours = max(0.1, min(float(hours), 168.0))
            return f".m tomtat {safe_hours:g}h"
        return None

    async def _capture_bot_outputs(self, message) -> tuple[tuple[int, ...], str]:
        channel = getattr(message, "channel", None)
        history = getattr(channel, "history", None)
        bot_user_id = getattr(getattr(self.bot, "user", None), "id", None)
        if history is None or bot_user_id is None:
            return (), ""

        captured = []
        try:
            async for item in history(
                limit=12,
                after=message,
                oldest_first=True,
            ):
                author_id = getattr(getattr(item, "author", None), "id", None)
                if author_id == bot_user_id:
                    captured.append(item)
        except Exception as exc:
            print(
                f"⚠️ [Asumi Tool] Không capture được output refs: "
                f"{type(exc).__name__}: {str(exc)[:120]}",
                flush=True,
            )
            return (), ""

        message_ids = tuple(
            int(item.id)
            for item in captured
            if getattr(item, "id", None) is not None
        )
        rendered = []
        remaining = 6000
        for item in captured:
            text = _render_bot_message(item)
            if not text:
                continue
            if len(text) > remaining:
                text = text[:remaining]
            rendered.append(text)
            remaining -= len(text)
            if remaining <= 0:
                break

        return message_ids[-8:], "\n\n".join(rendered)[:6000]

    async def execute(self, decision: RouteDecision, message) -> ToolExecutionResult:
        command_text = self._command_for(decision)
        if not command_text:
            return ToolExecutionResult(handled=False)

        synthetic = copy.copy(message)
        synthetic.content = command_text
        await self.bot.process_commands(synthetic)

        response_ids, response_context = await self._capture_bot_outputs(message)
        return ToolExecutionResult(
            handled=True,
            command_text=command_text,
            response_message_ids=response_ids,
            response_context=response_context,
        )
