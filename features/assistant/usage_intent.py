"""Deterministic private AI-usage intent, before Clef/Gemini.

No inferred account identity, no public conversation is sent to a search API.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageIntent:
    period: str = "7d"
    metric: str = "tokens_and_cost"


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFD", (value or "").casefold())
    return "".join(c for c in value if unicodedata.category(c) != "Mn").replace("đ", "d")


def parse_usage_intent(query: str) -> UsageIntent | None:
    """Classify explicit requests for Asumi's API usage, not arbitrary 'tokens'."""
    text = _fold(query).strip()
    if not text or len(text) > 230:
        return None
    # Literal key/token questions are different from *usage* questions.
    if re.search(r"\b(jwt|oauth|api key|access token|refresh token|token dang nhap|token xac thuc|web3|nft)\b", text):
        return None
    token = re.search(r"\b(tokens?|token|usage)\b", text)
    finance = re.search(r"\b(chi phi|tien|cost|billing|spend)\b", text)
    ai = re.search(r"\b(asumi|bot|gemini|ai|api|model)\b", text)
    usage_verb = re.search(
        r"\b(da|het|con|ton|xai|su dung|tieu|mat|thong ke|bao cao|report)\b", text
    )
    spending = re.search(r"\b(het|ton|xai|dung|su dung|tieu|mat|bao nhieu|thong ke|bao cao|report)\b", text)

    # A question about token length/context/authentication is not bot usage.
    if re.search(r"\b(context window|context length|context size|context limit|token limit)\b", text):
        return None
    # Short 'token' is a command; longer questions must target usage/accounting.
    token_query = bool(token and (
        usage_verb or len(text.split()) <= 3
        or (ai and spending)
    ))
    finance_query = bool(finance and ai and (spending or "chi phi" in text or "billing" in text))
    if not (token_query or finance_query):
        return None

    if any(x in text for x in ("hom nay", "today", "trong ngay")):
        period = "today"
    elif any(x in text for x in ("thang nay", "this month", "dau thang")):
        period = "month"
    elif any(x in text for x in ("30 ngay", "30d", "30 days")):
        period = "30d"
    else:
        period = "7d"
    if any(x in text for x in ("7 ngay", "tuan nay", "7d", "7 days")):
        period = "7d"
    metric = "cost" if finance and not token else "tokens_and_cost"
    return UsageIntent(period=period, metric=metric)
