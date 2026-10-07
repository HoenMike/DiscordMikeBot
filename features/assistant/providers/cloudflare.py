from __future__ import annotations

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
        enabled = os.getenv("CF_ASSISTANT_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        token = (
            os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
            or os.getenv("CLOUDFLARE_AUTH_TOKEN", "").strip()
        )
        return cls(
            account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            api_token=token,
            enabled=enabled,
            model=os.getenv("CF_ROUTER_MODEL", "@cf/cloudflare/clef-flash"),
            timeout_seconds=float(os.getenv("CF_ROUTER_TIMEOUT_SECONDS", "4")),
        )

    @staticmethod
    def _parse_choice(answer: Any) -> ClefDecision | None:
        if isinstance(answer, str):
            return ClefDecision(answer, 1.0)
        if not isinstance(answer, dict):
            return None

        choice = answer.get("choice") or answer.get("value") or answer.get("label")
        if not choice:
            return None

        confidence = answer.get("confidence")
        if confidence is None:
            probabilities = answer.get("probabilities")
            if isinstance(probabilities, dict):
                confidence = probabilities.get(str(choice))
        try:
            score = float(confidence) if confidence is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        return ClefDecision(str(choice), max(0.0, min(score, 1.0)))

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
                        "Choose the closest supported intent."
                    ),
                    "criteria": {
                        "chat": "General conversation or a question that does not map to another tool.",
                        "tarot": "Start or discuss a Tarot reading.",
                        "summarize": "Summarize or catch up on recent Discord conversation.",
                        "help": "Explain Asumi capabilities or how to use the bot.",
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
