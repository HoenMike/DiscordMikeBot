"""Tarot 2.0 reading-session presentation helpers.

This module intentionally contains no Discord API calls so reveal-state behavior can be
unit tested without a live bot connection.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from features.tarot.deck import DrawnCard


def build_reveal_progress(revealed_indices: Iterable[int], total: int) -> str:
    """Return a compact visual + numeric reveal progress string."""
    total = max(0, int(total))
    revealed = {idx for idx in revealed_indices if 0 <= idx < total}
    if total == 0:
        return "0 / 0"

    dots = " ".join("●" if idx in revealed else "○" for idx in range(total))
    return f"{dots}   **{len(revealed)} / {total} lá đã lật**"


def build_ai_ready_status(done: bool) -> str:
    """User-facing AI readiness copy used while cards are still being revealed."""
    if done:
        return "✓ **Luận giải đã sẵn sàng** — lật nốt các lá để xem toàn bộ câu chuyện."
    return "✨ *Asumi đang đọc mối liên hệ giữa các lá trong lúc bạn lật bài...*"


def build_micro_reveal(drawn: DrawnCard, display_index: int) -> str:
    """Deterministic one-card reveal payoff; never calls AI and never invents meaning."""
    orient = "Ngược" if drawn.is_reversed else "Xuôi"
    keywords: Sequence[str] = (
        drawn.card.keywords_reversed if drawn.is_reversed else drawn.card.keywords_upright
    )
    keyword_text = " · ".join(str(item).strip() for item in keywords[:3] if str(item).strip())

    position = drawn.position_title
    prefix = f"**{display_index} · {position} — {drawn.card.name_vi} · {orient}**"
    if keyword_text:
        return f"{prefix}\n\`{keyword_text}\`"
    return prefix


def compact_flip_label(index: int, opened: bool) -> str:
    """Compact button labels keep 10-card spreads usable on mobile."""
    return f"✓ {index + 1}" if opened else f"{index + 1}"
