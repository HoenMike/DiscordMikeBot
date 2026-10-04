"""Validated schema-only Smart Custom Spread contracts for T20.7."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


MIN_CUSTOM_POSITIONS = 3
MAX_CUSTOM_POSITIONS = 7
PROHIBITED_MODEL_FIELDS = {
    "card", "card_id", "card_name", "cards", "drawn_card", "tarot_card",
    "orientation", "is_reversed", "upright", "reversed",
}

# Generated positions must stay on the user's observable choices/context rather than
# claiming privileged access to another person's inner state.
UNSAFE_POSITION_FRAGMENTS = (
    "bí mật của",
    "đang nghĩ gì",
    "thực sự nghĩ gì",
    "che giấu điều gì",
    "secret of",
    "what they think",
    "what he thinks",
    "what she thinks",
)


@dataclass(frozen=True)
class CustomSpreadPosition:
    id: str
    title: str
    description: str


@dataclass(frozen=True)
class CustomSpreadSchema:
    title: str
    intent: str
    reason: str
    positions: tuple[CustomSpreadPosition, ...]

    @property
    def card_count(self) -> int:
        return len(self.positions)

    def as_spread_info(self) -> dict:
        return {
            "key": "custom",
            "name": self.title,
            "card_count": self.card_count,
            "is_daily": False,
            "requires_question": True,
            "positions": [
                (f"LÁ {idx}: {position.title.upper()}", position.description)
                for idx, position in enumerate(self.positions, start=1)
            ],
        }


def _compact(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def _position_id(value: Any) -> str:
    raw = _compact(value, 48).casefold()
    raw = re.sub(r"[^a-z0-9_\-]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_-")
    return raw[:32]


def _has_unsafe_private_framing(*parts: str) -> bool:
    text = " ".join(parts).casefold()
    return any(fragment in text for fragment in UNSAFE_POSITION_FRAGMENTS)


def validate_custom_spread_payload(payload: Any) -> Optional[CustomSpreadSchema]:
    """Accept only a bounded position schema; reject any model-supplied card data."""
    if not isinstance(payload, Mapping):
        return None

    if {str(key).casefold() for key in payload.keys()} & PROHIBITED_MODEL_FIELDS:
        return None

    title = _compact(payload.get("title"), 72)
    intent = _compact(payload.get("intent"), 220)
    reason = _compact(payload.get("reason"), 260)
    raw_positions = payload.get("positions")

    if not title or not intent or not reason:
        return None
    if not isinstance(raw_positions, Sequence) or isinstance(raw_positions, (str, bytes)):
        return None
    if not MIN_CUSTOM_POSITIONS <= len(raw_positions) <= MAX_CUSTOM_POSITIONS:
        return None

    positions = []
    seen_ids = set()
    seen_titles = set()

    for raw in raw_positions:
        if not isinstance(raw, Mapping):
            return None
        if {str(key).casefold() for key in raw.keys()} & PROHIBITED_MODEL_FIELDS:
            return None

        position_id = _position_id(raw.get("id"))
        position_title = _compact(raw.get("title"), 64)
        description = _compact(raw.get("description"), 180)
        normalized_title = position_title.casefold()

        if not position_id or not position_title or not description:
            return None
        if position_id in seen_ids or normalized_title in seen_titles:
            return None
        if _has_unsafe_private_framing(position_title, description):
            return None

        seen_ids.add(position_id)
        seen_titles.add(normalized_title)
        positions.append(CustomSpreadPosition(position_id, position_title, description))

    return CustomSpreadSchema(
        title=title,
        intent=intent,
        reason=reason,
        positions=tuple(positions),
    )
