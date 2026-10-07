from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    tool: str | None = None
    arguments: Dict[str, Any] = field(default_factory=dict)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _extract_hours(text: str) -> float | None:
    folded = _fold(text).replace(",", ".")
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:h|gio|tieng)\b", folded)
    if not match:
        return None
    value = float(match.group(1))
    if value <= 0:
        return None
    return min(value, 168.0)


def route_locally(text: str) -> RouteDecision:
    """Cheap deterministic pass before any model router is considered."""

    folded = _fold(text).strip()
    if not folded:
        return RouteDecision(intent="help", tool="help.show")

    help_signals = (
        "help",
        "huong dan",
        "lam duoc gi",
        "co the lam gi",
        "chuc nang gi",
    )
    if any(signal in folded for signal in help_signals):
        return RouteDecision(intent="help", tool="help.show")

    tarot_signal = any(signal in folded for signal in ("tarot", "boc bai", "boi bai"))
    if tarot_signal:
        if any(signal in folded for signal in ("daily", "hom nay", "ngay hom nay")):
            return RouteDecision(intent="tarot_daily", tool="tarot.daily")
        return RouteDecision(intent="tarot", tool="tarot.launch")

    summary_signals = (
        "tom tat",
        "catchup",
        "catch up",
        "nay gio",
        "tu chieu toi gio",
        "tu sang toi gio",
        "co gi dang chu y",
    )
    if any(signal in folded for signal in summary_signals):
        hours = _extract_hours(text)
        args: Dict[str, Any] = {}
        if hours is not None:
            args["hours"] = hours
        return RouteDecision(intent="summary", tool="summary.catchup", arguments=args)

    return RouteDecision(intent="chat")


async def route_message(text: str, cloudflare_router=None, min_confidence: float = 0.55) -> RouteDecision:
    """Run deterministic routing first, then optional Clef classification."""

    local = route_locally(text)
    if local.tool or not (text or "").strip():
        return local
    if cloudflare_router is None or not getattr(cloudflare_router, "enabled", False):
        return local

    try:
        clef = await cloudflare_router.classify(text)
    except Exception as exc:
        print(
            f"⚠️ [Asumi Router] Clef unavailable: {type(exc).__name__}: {str(exc)[:160]}",
            flush=True,
        )
        return local

    if clef is None or clef.confidence < min_confidence:
        return local

    if clef.intent == "tarot":
        return RouteDecision(intent="tarot", tool="tarot.launch")
    if clef.intent == "summarize":
        args: Dict[str, Any] = {}
        hours = _extract_hours(text)
        if hours is not None:
            args["hours"] = hours
        return RouteDecision(intent="summary", tool="summary.catchup", arguments=args)
    if clef.intent == "help":
        return RouteDecision(intent="help", tool="help.show")
    return local
