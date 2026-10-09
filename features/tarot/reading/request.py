"""Parse explicit conversational Tarot requests without losing the user's question.

Routing stays deterministic and never makes a model call or draws cards here.
Only a clearly requested draw with a non-empty question should auto-start.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class TarotRequest:
    question: str = ""
    daily: bool = False
    draw_now: bool = False


def _word(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.replace("đ", "d").strip(".,!?;:()[]{}\"'“”‘’")


_PREFIX_FILLERS = {
    "cho", "toi", "tui", "minh", "em", "anh", "giup", "xem", "ve",
    "mot", "1", "que", "la", "bai", "thu", "thu", "voi", "nha", "nhe",
    "daily",
}
_TRAILING_FILLERS = {"nha", "nhe", "voi", "nheee", "thoi"}
_EMPTY_REQUESTS = {
    "di", "nha", "nhe", "hom nay", "ngay hom nay", "cho toi",
    "cho minh", "giup toi", "giup minh", "thu di", "di nha",
}


def parse_tarot_request(text: str) -> TarotRequest:
    """Extract a question after 'tarot' or 'bói/bốc/rút bài'.

    Handles e.g. 'bốc cho quẻ tarot xem mai nên mặc áo màu gì đi nhậu'
    without passing the leading instruction into the reading prompt.
    Empty/ambiguous requests still use the existing launcher.
    """
    raw = " ".join((text or "").split()).strip()
    if not raw:
        return TarotRequest()

    words = list(re.finditer(r"\S+", raw))
    normalized = [_word(m.group()) for m in words]
    anchor = next((i for i, token in enumerate(normalized) if token == "tarot"), None)
    after = anchor + 1 if anchor is not None else None
    if after is None:
        after = next((
            i + 2 for i in range(len(normalized) - 1)
            if normalized[i] in {"boc", "boi", "rut"}
            and normalized[i + 1] == "bai"
        ), None)
    if after is None:
        return TarotRequest()

    tail_start = after
    while tail_start < len(words) and normalized[tail_start] in _PREFIX_FILLERS:
        tail_start += 1
    tail_end = len(words)
    while tail_end > tail_start and normalized[tail_end - 1] in _TRAILING_FILLERS:
        tail_end -= 1

    question = (
        raw[words[tail_start].start():words[tail_end - 1].end()].strip(" \t.,:;!?")
        if tail_start < tail_end else ""
    )
    if _word(question) in _EMPTY_REQUESTS or (
        len(normalized[tail_start:tail_end]) == 1
        and normalized[tail_start] in {"di", "thoi", "help", "menu", "ui"}
    ):
        question = ""
    question = question[:500].strip()
    daily = (
        "daily" in normalized
        or (not question and "hom nay" in " ".join(normalized))
        or (
            not question
            and any(token in normalized for token in ("nang", "luong"))
            and "hom nay" in " ".join(normalized)
        )
    )
    draw_now = bool(question) and any(token in {"boc", "boi", "rut"} for token in normalized)
    return TarotRequest(question=question, daily=daily, draw_now=draw_now)
