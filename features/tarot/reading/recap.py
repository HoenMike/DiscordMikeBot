"""Deterministic Recap Card content selection for T20.9."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence

from features.tarot.deck import DrawnCard
from features.tarot.reading.schema import TarotReadingResult
from features.tarot.rendering.state import RecapCardState


VN_TZ = timezone(timedelta(hours=7))


def _compact(text: Optional[str], limit: int) -> str:
    clean = str(text or "")
    clean = re.sub(r"[`*_>#]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" -•")
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


def _hero_card(
    drawn_cards: Sequence[DrawnCard],
    reading_result: Optional[TarotReadingResult],
) -> DrawnCard:
    if not drawn_cards:
        raise ValueError("Recap requires at least one drawn card")
    key_id = ""
    if reading_result and reading_result.key_card:
        key_id = (reading_result.key_card.card_id or "").strip()
    if key_id:
        for drawn in drawn_cards:
            if drawn.card.id == key_id:
                return drawn
    return drawn_cards[0]


def build_recap_state(
    *,
    spread_title: str,
    user_name: str,
    drawn_cards: Sequence[DrawnCard],
    reading_result: Optional[TarotReadingResult],
    ai_reading: str,
    now: Optional[datetime] = None,
) -> RecapCardState:
    """Build recap content without an extra AI call or hidden interpretation."""
    hero = _hero_card(drawn_cards, reading_result)

    headline = ""
    takeaway = ""
    if reading_result:
        headline = _compact(
            reading_result.headline
            or reading_result.dominant_theme
            or reading_result.core_message,
            110,
        )
        if reading_result.practical_takeaway:
            takeaway = _compact(reading_result.practical_takeaway[0], 190)
        if not takeaway:
            takeaway = _compact(
                reading_result.dominant_theme
                or reading_result.core_message
                or reading_result.uncertainty,
                190,
            )

    if not headline:
        headline = _compact(f"{hero.card.name_vi} là điểm neo của quẻ này.", 110)
    if not takeaway:
        takeaway = _compact(ai_reading, 190) or "Giữ lại điều hữu ích và đối chiếu với dữ kiện thực tế."

    current = now.astimezone(VN_TZ) if now else datetime.now(VN_TZ)
    return RecapCardState(
        spread_title=_compact(spread_title, 64),
        user_name=_compact(user_name, 48) or "Bạn",
        hero_card=hero,
        headline=headline,
        takeaway=takeaway,
        date_label=current.strftime("%d/%m/%Y"),
    )
