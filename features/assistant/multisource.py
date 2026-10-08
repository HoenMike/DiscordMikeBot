"""T22.5 supervised Discord History -> explicit public Web source planning.

No model or history excerpt is allowed to synthesize a Brave query. The user
must provide the standalone public query literally in the same message.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence, TypeVar


@dataclass(frozen=True)
class CrossSourceRequest:
    history_query: str
    public_query: str
    explicit_web: bool


# A two-step request is possible only with an explicit connector and a
# recognizable public action. The first part is checked by route_locally.
_STEP = re.compile(
    r"\s+(?:rồi|roi|sau\s+(?:đó|do)|và|va)\s+"
    r"(?P<action>"
    r"(?:tìm|tim|tra\s+cứu|tra\s+cuu|search)\s+"
    r"(?:(?:trên|tren)\s+)?(?:web|mạng|mang|internet|online)"
    r"|(?:kiểm\s+tra|kiem\s+tra|check|xem)\s+(?:giá|gia|thông\s+tin|thong\s+tin)"
    r")\b\s*[:,-]?\s*",
    flags=re.IGNORECASE,
)
_WEB_ACTION = re.compile(
    r"^(?:tìm|tim|tra\s+cứu|tra\s+cuu|search)\s+"
    r"(?:(?:trên|tren)\s+)?(?:web|mạng|mang|internet|online)\b",
    flags=re.IGNORECASE,
)


def split_cross_source_request(query: str) -> CrossSourceRequest | None:
    """Return literal user-authored segments, without inferring an entity."""
    text = unicodedata.normalize("NFC", (query or "").strip())
    if not text or len(text) > 1200:
        return None
    match = _STEP.search(text)
    if not match:
        return None
    history = text[: match.start()].strip()
    public = text[match.end():].strip()
    if not history:
        return None
    explicit_web = bool(_WEB_ACTION.match(match.group("action")))
    # "check price of that one" is not permission to export context.
    return CrossSourceRequest(history, public if explicit_web else "", explicit_web)


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFD", value.casefold())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").replace("đ", "d")


def safe_literal_public_query(query: str) -> bool:
    """Second-stage query must be an independent public question.

    A user saying "mẫu đó" is NOT an independently specified public subject.
    Reject message links/mentions, Discord references, and vague deixis even
    when a public cue such as "giá hôm nay" is present.
    """
    from features.assistant.router import _safe_public_web_query

    if not isinstance(query, str) or not 12 <= len(query.strip()) <= 250:
        return False
    folded = _fold(query)
    if not _safe_public_web_query(query):
        return False
    if re.search(
        r"\b(?:cai|mau|xe|hang|nguoi|san pham|mon|con|loai)\s+"
        r"(?:do|nay|kia|vua nhac|vua noi)\b",
        folded,
    ):
        return False
    if any(t in folded for t in (
        "tin nhan", "doan chat", "discord", "trong server",
        "phia tren", "do hoi nay", "ban vua", "theo vua",
        "noi o tren", "nguoi do", "cai truoc", "trich dan",
    )):
        return False
    return True


T = TypeVar("T")
_STOP = frozenset({
    "gia", "ban", "hom", "nay", "hien", "tai", "moi", "nhat",
    "thong", "tin", "tim", "tren", "web", "xe", "mua", "bao", "nhieu",
    "cua", "cho", "cap", "nhat", "gio", "ve", "the", "nao",
})


def rank_verified_history_hits(hits: Sequence[T], public_query: str) -> tuple[T, ...]:
    """Stable local reranking of ACL-verified hits using *user-written* terms.

    Ranking doesn't infer product identity or expand the web query. The
    Discord Search provider must verify channel permissions before this step.
    """
    tokens = {
        token for token in re.findall(r"[a-z0-9]{3,}", _fold(public_query))
        if token not in _STOP
    }
    if not tokens or not hits:
        return tuple(hits)

    def score(hit: T) -> int:
        content = _fold(str(getattr(hit, "content", "")))
        # Whole-token matching avoids treating "sh" as a model identifier.
        words = set(re.findall(r"[a-z0-9]{3,}", content))
        return len(tokens & words)

    return tuple(sorted(hits, key=lambda hit: -score(hit)))
