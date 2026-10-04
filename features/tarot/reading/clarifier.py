"""Pure helpers for Tarot 2.0 clarifier targeting.

No Discord or AI calls live here so recommendation mapping stays deterministic and
unit-testable.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, Optional

from features.tarot.deck import DrawnCard
from features.tarot.reading.schema import TarotReadingResult


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", (value or "").casefold())
    plain = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    plain = plain.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _position_index_from_id(position_id: str, cards: list[DrawnCard]) -> Optional[int]:
    raw = (position_id or "").strip()
    if not raw:
        return None

    # Prefer the stable 1-based position_index supplied to the AI.
    if raw.isdigit():
        number = int(raw)
        for idx, card in enumerate(cards):
            if card.position_index == number:
                return idx
        # Legacy/tests may have used zero-based ids before real spread drawing.
        if 0 <= number < len(cards):
            return number

    normalized = _normalize(raw)
    if not normalized:
        return None

    for idx, card in enumerate(cards):
        title = _normalize(card.position_title)
        if normalized == title or normalized in title or title in normalized:
            return idx
    return None


def resolve_clarifier_suggestions(
    reading_result: Optional[TarotReadingResult],
    drawn_cards: Iterable[DrawnCard],
) -> Dict[int, str]:
    """Map AI-suggested position ids onto current zero-based card indices."""
    cards = list(drawn_cards)
    if not reading_result:
        return {}

    resolved: Dict[int, str] = {}
    for suggestion in reading_result.suggested_clarifier_targets[:2]:
        idx = _position_index_from_id(suggestion.position_id, cards)
        if idx is None or idx in resolved:
            continue
        resolved[idx] = (suggestion.reason or "").strip()
    return resolved


def target_insight(
    reading_result: Optional[TarotReadingResult],
    target: DrawnCard,
) -> str:
    """Return the existing structured insight for one target card/position."""
    if not reading_result:
        return ""

    for insight in reading_result.card_insights:
        if insight.card_id and insight.card_id == target.card.id:
            return insight.insight.strip()
        idx = _position_index_from_id(insight.position_id, [target])
        if idx == 0:
            return insight.insight.strip()
    return ""
