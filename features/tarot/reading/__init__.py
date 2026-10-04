"""Tarot 2.0 reading-engine primitives.

This package is introduced incrementally. Discord UI/renderer migrations remain in the
existing modules until their dedicated milestones.
"""

from .recommendation import (
    SpreadRecommendation,
    find_similar_recent_question,
    question_similarity,
    recommend_spread,
)
from .schema import (
    TarotAIResponseSchema,
    TarotCardInsight,
    TarotClarifierTarget,
    TarotConnection,
    TarotKeyCard,
    TarotReadingResult,
)

__all__ = [
    "SpreadRecommendation",
    "find_similar_recent_question",
    "question_similarity",
    "recommend_spread",
    "TarotAIResponseSchema",
    "TarotCardInsight",
    "TarotClarifierTarget",
    "TarotConnection",
    "TarotKeyCard",
    "TarotReadingResult",
]
