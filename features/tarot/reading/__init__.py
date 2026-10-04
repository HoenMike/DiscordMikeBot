"""Tarot 2.0 reading-engine primitives.

This package is introduced incrementally. Discord UI/renderer migrations remain in the
existing modules until their dedicated milestones.
"""

from .clarifier import (
    resolve_clarifier_suggestions,
    target_insight,
)
from .recommendation import (
    SpreadRecommendation,
    find_similar_recent_question,
    question_similarity,
    recommend_spread,
)
from .session import (
    build_ai_ready_status,
    build_micro_reveal,
    build_reveal_progress,
    compact_flip_label,
)
from .schema import (
    TarotAIResponseSchema,
    TarotClarifierAIResponseSchema,
    TarotClarifierResult,
    TarotCardInsight,
    TarotClarifierTarget,
    TarotConnection,
    TarotKeyCard,
    TarotReadingResult,
)

__all__ = [
    "resolve_clarifier_suggestions",
    "target_insight",
    "SpreadRecommendation",
    "find_similar_recent_question",
    "question_similarity",
    "recommend_spread",
    "build_ai_ready_status",
    "build_micro_reveal",
    "build_reveal_progress",
    "compact_flip_label",
    "TarotAIResponseSchema",
    "TarotClarifierAIResponseSchema",
    "TarotClarifierResult",
    "TarotCardInsight",
    "TarotClarifierTarget",
    "TarotConnection",
    "TarotKeyCard",
    "TarotReadingResult",
]
