"""Tarot 2.0 Reading Board state contract.

Discord views pass state here; Pillow rendering decides how to visualize it. This keeps
interaction concerns out of the renderer and prepares the same renderer for future
clarifier/custom-spread milestones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Sequence

from features.tarot.deck import DrawnCard


@dataclass(frozen=True)
class ReadingBoardState:
    spread_key: str
    drawn_cards: Sequence[DrawnCard]
    revealed_indices: FrozenSet[int] = field(default_factory=frozenset)
    just_revealed_indices: FrozenSet[int] = field(default_factory=frozenset)
    key_card_id: Optional[str] = None
    target_position_index: Optional[int] = None
    final: bool = False
    spread_title: Optional[str] = None

    @property
    def total_cards(self) -> int:
        return len(self.drawn_cards)

    @property
    def revealed_count(self) -> int:
        return len(self.revealed_indices)

    def is_revealed(self, index: int) -> bool:
        return index in self.revealed_indices

    def is_just_revealed(self, index: int) -> bool:
        return index in self.just_revealed_indices

    def is_key_card(self, index: int) -> bool:
        if not self.key_card_id or not 0 <= index < len(self.drawn_cards):
            return False
        return self.drawn_cards[index].card.id == self.key_card_id

    def is_target(self, index: int) -> bool:
        return self.target_position_index == index

    @classmethod
    def from_legacy(
        cls,
        spread_key: str,
        drawn_cards: Sequence[DrawnCard],
        revealed_indices=None,
        *,
        just_revealed_indices=None,
        key_card_id: Optional[str] = None,
        target_position_index: Optional[int] = None,
        final: bool = False,
        spread_title: Optional[str] = None,
    ) -> "ReadingBoardState":
        total = len(drawn_cards)
        revealed = (
            set(range(total))
            if revealed_indices is None
            else {idx for idx in revealed_indices if 0 <= idx < total}
        )
        just_revealed = {
            idx for idx in (just_revealed_indices or set())
            if 0 <= idx < total and idx in revealed
        }
        return cls(
            spread_key=spread_key,
            drawn_cards=tuple(drawn_cards),
            revealed_indices=frozenset(revealed),
            just_revealed_indices=frozenset(just_revealed),
            key_card_id=key_card_id,
            target_position_index=target_position_index,
            final=final,
            spread_title=spread_title,
        )
