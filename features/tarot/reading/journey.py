"""Tarot Journey analytics derived only from stored reading history."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable


SUITS = ("cups", "swords", "wands", "pentacles")


@dataclass(frozen=True)
class JourneyRepeat:
    name: str
    count: int


@dataclass(frozen=True)
class TarotJourneySummary:
    days: int
    reading_count: int
    total_cards: int
    suit_counts: dict[str, int] = field(default_factory=dict)
    suit_percentages: dict[str, int] = field(default_factory=dict)
    major_count: int = 0
    major_ratio: int = 0
    repeated_cards: tuple[JourneyRepeat, ...] = ()
    repeated_reversed_cards: tuple[JourneyRepeat, ...] = ()
    topic_counts: dict[str, int] = field(default_factory=dict)
    mood_counts: dict[str, int] = field(default_factory=dict)
    spread_counts: dict[str, int] = field(default_factory=dict)
    most_used_spread: str = ""
    theme_progression: tuple[str, ...] = ()

    @property
    def has_data(self) -> bool:
        return self.reading_count > 0


def _clean_tag(value: Any, fallback: str = "general") -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:48] or fallback


def _compress_progression(values: Iterable[str], limit: int = 4) -> tuple[str, ...]:
    compressed: list[str] = []
    for value in values:
        clean = _clean_tag(value)
        if not compressed or compressed[-1].casefold() != clean.casefold():
            compressed.append(clean)
    return tuple(compressed[-limit:])


def _percentages_that_sum_to_100(counter: Counter[str], keys: tuple[str, ...]) -> dict[str, int]:
    total = sum(counter.get(key, 0) for key in keys)
    if not total:
        return {key: 0 for key in keys}

    raw = {key: counter.get(key, 0) * 100 / total for key in keys}
    result = {key: int(value) for key, value in raw.items()}
    remaining = 100 - sum(result.values())
    order = sorted(
        keys,
        key=lambda key: raw[key] - result[key],
        reverse=True,
    )
    for key in order[:remaining]:
        result[key] += 1
    return result


def summarize_journey(history: list[dict], days: int = 30) -> TarotJourneySummary:
    """Aggregate stored history without inferring fate, diagnosis or hidden traits."""
    reading_count = len(history)
    suit_counter: Counter[str] = Counter()
    card_counter: Counter[str] = Counter()
    reversed_counter: Counter[str] = Counter()
    topic_counter: Counter[str] = Counter()
    mood_counter: Counter[str] = Counter()
    spread_counter: Counter[str] = Counter()
    major_count = 0
    total_cards = 0

    for item in history:
        topic_counter[_clean_tag(item.get("topic_tag"))] += 1
        mood = _clean_tag(item.get("mood_tag"), fallback="")
        if mood:
            mood_counter[mood] += 1
        spread_counter[_clean_tag(item.get("spread_type"), fallback="unknown")] += 1

        cards = item.get("cards") or []
        for card in cards:
            card_id = str(card.get("id") or "").casefold()
            card_name = _clean_tag(card.get("name_vi") or card.get("name_en"), fallback=card_id or "Lá bài")
            total_cards += 1
            card_counter[card_name] += 1
            if card.get("is_reversed"):
                reversed_counter[card_name] += 1

            if card_id.startswith("major_"):
                major_count += 1
            else:
                for suit in SUITS:
                    if card_id.startswith(f"{suit}_"):
                        suit_counter[suit] += 1
                        break

    suit_percentages = _percentages_that_sum_to_100(suit_counter, SUITS)
    major_ratio = round(major_count * 100 / total_cards) if total_cards else 0

    repeated_cards = tuple(
        JourneyRepeat(name=name, count=count)
        for name, count in card_counter.most_common(5)
        if count >= 2
    )
    repeated_reversed = tuple(
        JourneyRepeat(name=name, count=count)
        for name, count in reversed_counter.most_common(5)
        if count >= 2
    )

    chronological = sorted(
        history,
        key=lambda item: str(item.get("created_at") or ""),
    )
    progression = _compress_progression(item.get("topic_tag") for item in chronological)
    most_used = spread_counter.most_common(1)[0][0] if spread_counter else ""

    return TarotJourneySummary(
        days=max(1, int(days)),
        reading_count=reading_count,
        total_cards=total_cards,
        suit_counts={suit: suit_counter.get(suit, 0) for suit in SUITS},
        suit_percentages=suit_percentages,
        major_count=major_count,
        major_ratio=major_ratio,
        repeated_cards=repeated_cards,
        repeated_reversed_cards=repeated_reversed,
        topic_counts=dict(topic_counter.most_common()),
        mood_counts=dict(mood_counter.most_common()),
        spread_counts=dict(spread_counter.most_common()),
        most_used_spread=most_used,
        theme_progression=progression,
    )
