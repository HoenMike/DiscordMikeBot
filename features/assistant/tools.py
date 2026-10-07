from __future__ import annotations

import copy
from dataclasses import dataclass

from features.assistant.router import RouteDecision


@dataclass(frozen=True)
class ToolExecutionResult:
    handled: bool
    command_text: str | None = None


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

    async def execute(self, decision: RouteDecision, message) -> ToolExecutionResult:
        command_text = self._command_for(decision)
        if not command_text:
            return ToolExecutionResult(handled=False)

        synthetic = copy.copy(message)
        synthetic.content = command_text
        await self.bot.process_commands(synthetic)
        return ToolExecutionResult(handled=True, command_text=command_text)
