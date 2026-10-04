from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class TarotFollowupTurn:
    question: str
    answer: str


@dataclass
class TarotSessionState:
    """In-memory lifecycle state for post-reading Tarot interactions."""

    max_followups: int = 3
    timeout_seconds: float = 900.0
    followups: List[TarotFollowupTurn] = field(default_factory=list)
    clarifier_summary: Optional[str] = None
    why_used: bool = False
    closed: bool = False
    last_activity_at: float = field(default_factory=time.monotonic)

    @property
    def remaining_followups(self) -> int:
        return max(0, self.max_followups - len(self.followups))

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else now
        return self.closed or (current - self.last_activity_at) >= self.timeout_seconds

    def touch(self, now: Optional[float] = None) -> None:
        if not self.closed:
            self.last_activity_at = time.monotonic() if now is None else now

    def can_followup(self, now: Optional[float] = None) -> bool:
        return not self.is_expired(now) and self.remaining_followups > 0

    def record_followup(self, question: str, answer: str, now: Optional[float] = None) -> bool:
        if not question.strip() or not answer.strip() or not self.can_followup(now):
            return False
        self.followups.append(TarotFollowupTurn(question=question.strip(), answer=answer.strip()))
        self.touch(now)
        return True

    def set_clarifier(self, summary: str, now: Optional[float] = None) -> None:
        self.clarifier_summary = summary.strip()[:2200] if summary else None
        self.touch(now)

    def mark_why_used(self, now: Optional[float] = None) -> bool:
        if self.why_used or self.is_expired(now):
            return False
        self.why_used = True
        self.touch(now)
        return True

    def prompt_history(self, max_turns: int = 3) -> list[tuple[str, str]]:
        return [(turn.question, turn.answer) for turn in self.followups[-max_turns:]]

    def close(self) -> None:
        self.closed = True
