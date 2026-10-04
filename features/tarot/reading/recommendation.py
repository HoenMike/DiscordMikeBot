"""Deterministic Tarot launcher recommendation and repeated-question helpers.

These helpers do not draw cards and do not call AI. They keep launcher behavior fast,
predictable, testable, and safe to use before a reading session starts.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class SpreadRecommendation:
    spread_key: str
    spread_name: str
    reason: str


_STOPWORDS = {
    "a", "anh", "ban", "bạn", "bi", "bị", "cai", "cái", "can", "cần", "cho",
    "co", "có", "cua", "của", "dang", "đang", "de", "để", "duoc", "được", "gi",
    "gì", "hay", "hien", "hiện", "khong", "không", "la", "là", "lam", "làm",
    "minh", "mình", "mot", "một", "nao", "nào", "nen", "nên", "nhu", "như",
    "oi", "ra", "sao", "se", "sẽ", "thi", "thì", "toi", "tôi", "trong", "ve",
    "về", "voi", "với",
}


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", (text or "").casefold())
    no_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    no_marks = no_marks.replace("đ", "d")
    return re.sub(r"[^a-z0-9\s]", " ", no_marks)


def question_tokens(text: str) -> set[str]:
    return {
        token
        for token in _normalize_text(text).split()
        if len(token) >= 2 and token not in _STOPWORDS
    }


def question_similarity(a: str, b: str) -> float:
    """Lightweight semantic-ish overlap score for recent-question awareness.

    Uses content-token overlap rather than raw string equality so short paraphrases
    can still be recognized without an AI call.
    """
    left = question_tokens(a)
    right = question_tokens(b)
    if not left or not right:
        return 0.0

    shared = len(left & right)
    if shared == 0:
        return 0.0

    # Exact short questions should still match, while one coincidental shared word
    # in two longer questions should not trigger the "same question" UX.
    if left == right:
        return 1.0
    if shared < 2:
        return 0.0

    overlap = shared / min(len(left), len(right))
    jaccard = shared / len(left | right)
    return (0.7 * overlap) + (0.3 * jaccard)


def find_similar_recent_question(
    history: Iterable[dict[str, Any]],
    question: Optional[str],
    threshold: float = 0.50,
) -> Optional[dict[str, Any]]:
    """Return the best sufficiently-similar prior reading, if any."""
    if not question:
        return None

    best: Optional[dict[str, Any]] = None
    best_score = 0.0
    for item in history:
        old_question = (item or {}).get("question")
        if not old_question:
            continue
        score = question_similarity(question, old_question)
        if score > best_score:
            best_score = score
            best = dict(item)
            best["similarity"] = score

    if best and best_score >= threshold:
        return best
    return None


def recommend_spread(question: str, context: Optional[str] = None) -> SpreadRecommendation:
    """Recommend one existing spread from the user's intent.

    This is intentionally deterministic. T20.7 may later add an AI-generated custom
    spread, but the base launcher must always have a zero-latency fallback.
    """
    q = _normalize_text(f"{question or ''} {context or ''}")

    def has(*terms: str) -> bool:
        return any(_normalize_text(term).strip() in q for term in terms)

    # Deep comparisons first: these benefit from the dedicated 5-card trade-off view.
    if has(
        "doi viec hay o lai", "nghi viec hay o lai", "hai huong", "2 huong",
        "hai con duong", "2 con duong", "so sanh hai", "so sanh 2",
        "tiep tuc hay", "nen o lai hay",
    ):
        return SpreadRecommendation(
            "two_paths",
            "Two Paths (5 lá)",
            "Câu hỏi đang so sánh hai hướng có hệ quả khác nhau. Two Paths cho đủ chỗ để nhìn lợi ích, rủi ro và điều kiện khiến mỗi hướng hợp lý.",
        )

    # Simple A/B decisions can stay compact.
    if has(
        "a hay b", "chon giua", "lua chon", "hai lua chon", "2 lua chon",
        "phuong an a", "phuong an b", "ngả đường", "nga duong",
    ):
        return SpreadRecommendation(
            "choices",
            "Two Choices (3 lá)",
            "Bạn đang cần so sánh nhanh hai lựa chọn. Trải 3 lá giữ câu trả lời gọn: hai hướng và điểm cần ưu tiên.",
        )

    # Broad, multi-factor questions need the full map.
    if has(
        "tong quan", "buc tranh toan canh", "dai han", "ca nam", "nam nay",
        "nhieu khia canh", "phuc tap", "buoc ngoat",
    ):
        return SpreadRecommendation(
            "celtic",
            "Celtic Cross (10 lá)",
            "Câu hỏi khá rộng hoặc có nhiều lớp tác động. Celtic Cross phù hợp khi cần một bức tranh toàn diện thay vì một kết luận nhanh.",
        )

    # Internal balance / wellbeing reflection.
    if has(
        "tam tri", "co the", "tinh than", "can bang", "burnout", "kiet suc",
        "noi tam", "nang luong cua toi",
    ):
        return SpreadRecommendation(
            "mbs",
            "Mind · Body · Spirit (3 lá)",
            "Câu hỏi nghiêng về trạng thái bên trong và sự cân bằng. Mind · Body · Spirit giúp tách ba lớp để thấy chỗ đang đồng thuận hoặc lệch pha.",
        )

    # Relationship/timeline questions often benefit from a progression view.
    if has(
        "tinh cam", "crush", "nguoi yeu", "chia tay", "quay lai", "hon nhan",
        "tinh duyen", "to tinh", "moi quan he", "tien trien", "sap toi",
    ):
        return SpreadRecommendation(
            "ppf",
            "Past · Present · Future (3 lá)",
            "Câu hỏi có dòng diễn biến rõ. Trải Quá khứ · Hiện tại · Tương lai giúp nhìn nguyên nhân, trạng thái hiện tại và xu hướng tiếp theo như một mạch.",
        )

    # Explicit advice/focus questions do better with one deep card.
    if has(
        "loi khuyen", "nen tap trung", "dieu gi quan trong", "toi can biet gi",
        "goc nhin", "mot dieu",
    ):
        return SpreadRecommendation(
            "single",
            "Single Card (1 lá)",
            "Bạn đang cần một trọng tâm hơn là một bản đồ lớn. Một lá cho câu trả lời cô đọng và dễ biến thành hành động.",
        )

    # Closed questions after comparison rules.
    if has(
        "co nen", "duoc khong", "thanh cong khong", "yes no", "co hay khong",
        "lieu co", "co the khong",
    ):
        return SpreadRecommendation(
            "yes_no",
            "Yes / No (1 lá)",
            "Câu hỏi đang ở dạng đóng. Yes / No cho một xu hướng biểu tượng nhanh, kèm điều kiện và phần chưa chắc thay vì một lời bảo đảm.",
        )

    return SpreadRecommendation(
        "ppf",
        "Past · Present · Future (3 lá)",
        "Câu hỏi chưa nghiêng hẳn về một dạng chuyên biệt. Trải 3 lá là lựa chọn cân bằng để nhìn nguồn gốc, hiện trạng và hướng phát triển.",
    )
