"""Stable Tarot snapshot reuse without duplicate Gemini calls or private cross-channel leaks."""
from __future__ import annotations

from typing import Callable, Awaitable

from features.tarot.reading.schema import TarotReadingResult


def history_question(question: str | None, context: str | None) -> str | None:
    """Keep the same persisted key used by TarotFlipView history."""
    if question and context:
        return f"{question} (Bối cảnh: {context})"
    if question:
        return question
    if context:
        return f"Bối cảnh: {context}"
    return None


async def reuse_or_generate(
    manager,
    *,
    user_id: int,
    guild_id: int | None,
    channel_id: int | None,
    spread_key: str,
    question: str | None,
    context: str | None,
    drawn_cards,
    reader_style: str,
    fresh: bool,
    generate: Callable[[], Awaitable[TarotReadingResult]],
) -> TarotReadingResult:
    """Same actor + question + spread + context + cards in one channel/day reuses AI.

    A manually fresh shuffle and non-auto personas always generate a new
    interpretation. Failure responses are never cached.
    """
    lookup = getattr(manager, "find_same_day_reading", None)
    if not fresh and reader_style == "auto" and callable(lookup):
        saved = await lookup(
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            spread_type=spread_key,
            question=history_question(question, context),
            drawn_cards=drawn_cards,
        )
        if saved:
            return TarotReadingResult(
                full_reading=saved["ai_reading"],
                topic_tag=saved["topic_tag"],
                mood_tag=saved["mood_tag"],
                ai_model="cached_history",
            )
    return await generate()
