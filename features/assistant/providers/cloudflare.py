from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True)
class ClefDecision:
    intent: str
    confidence: float = 0.0


class CloudflareDecisionRouter:
    """Optional Clef-flash router using the Workers AI REST API.

    Missing credentials or a disabled flag means the router is simply skipped.
    """

    def __init__(
        self,
        account_id: str = "",
        api_token: str = "",
        enabled: bool = False,
        model: str = "@cf/cloudflare/clef-flash",
        timeout_seconds: float = 4.0,
    ):
        self.account_id = account_id.strip()
        self.api_token = api_token.strip()
        self.enabled = bool(enabled and self.account_id and self.api_token)
        raw_model = model.strip() or "@cf/cloudflare/clef-flash"
        if raw_model in {"clef", "clef-flash"}:
            raw_model = f"@cf/cloudflare/{raw_model}"
        self.model = raw_model
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    @classmethod
    def from_env(cls) -> "CloudflareDecisionRouter":
        from core import constants as policy
        token = (
            os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
            or os.getenv("CLOUDFLARE_AUTH_TOKEN", "").strip()
        )
        return cls(
            account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            api_token=token,
            enabled=policy.ASUMI_CLEF_ENABLED,
            model=policy.ASUMI_CLEF_MODEL,
            timeout_seconds=policy.ASUMI_CLEF_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _parse_choice(answer: Any) -> ClefDecision | None:
        """Only calibrated, schema-valid Clef choices may drive tool routing.

        Cloudflare returns a choice object with confidence/probabilities.
        A bare string carries no confidence: never treat it as certainty 1.0.
        """
        if not isinstance(answer, dict):
            return None

        choice = answer.get("choice") or answer.get("value") or answer.get("label")
        supported = {
            "chat", "tarot", "summarize", "help",
            "web_search", "discord_history", "archive_search",
        }
        if not isinstance(choice, str) or choice not in supported:
            return None

        confidence = answer.get("confidence")
        if confidence is None:
            probabilities = answer.get("probabilities")
            if isinstance(probabilities, dict):
                confidence = probabilities.get(choice)
        try:
            score = float(confidence) if confidence is not None else 0.0
        except (TypeError, ValueError, OverflowError):
            score = 0.0
        if not math.isfinite(score):
            score = 0.0
        return ClefDecision(choice, max(0.0, min(score, 1.0)))

    async def classify(self, state: str) -> ClefDecision | None:
        if not self.enabled:
            return None

        model_path = self.model
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{model_path}"
        )
        payload = {
            "model": "clef-flash" if model_path.endswith("clef-flash") else "clef",
            "state": state[:12000],
            "questions": {
                "intent": {
                    "type": "choice",
                    "instructions": (
                        "Classify what the Discord user wants Asumi to do. "
                        "Choose the closest supported intent. "
                        "Use chat for vague follow-ups/replies, not external search. "
                        "Do not select web_search for private Discord text."
                    ),
                    "criteria": {
                        "chat": "General conversation or a question that does not map to another tool.",
                        "tarot": "Start or discuss a Tarot reading.",
                        "summarize": "Summarize or catch up on recent Discord conversation.",
                        "help": "Explain Asumi capabilities or how to use the bot.",
                        "web_search": (
                            "Requires fresh PUBLIC information from the open Internet: "
                            "current prices, announcements, news, updates or external verification. "
                            "NOT for messages in this Discord server, Archive, screenshots or replies."
                        ),
                        "discord_history": (
                            "Find a message someone previously wrote in this Discord server, "
                            "often with author, dates or old conversations. "
                            "NOT a public web search."
                        ),
                        "archive_search": (
                            "Find a user-owned item that someone explicitly SAVED to "
                            "Asumi Archive / saved memory. NOT all Discord message history."
                        ),
                    },
                }
            },
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                body = await response.json()

        result = body.get("result", body) if isinstance(body, dict) else {}
        answers = result.get("answers", {}) if isinstance(result, dict) else {}
        return self._parse_choice(answers.get("intent"))
