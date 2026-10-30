"""Privacy-bounded public product search from an explicitly replied Discord message.

The bot may read private channel context to understand a request, but it must
never send that context verbatim to Brave. Only a small, unambiguous public
product-pair clause is eligible for extraction, and only when the requester
explicitly asks for a lookup. All other cases stay in local conversation.
"""
from __future__ import annotations

import re
import unicodedata

from features.assistant.context import AssistantContext


_PAIR_SEPARATOR = re.compile(
    r"\s+(?:so\s+với|với|vs\.?|versus|hay|hoặc)\s+",
    flags=re.IGNORECASE,
)
_PUBLIC_PRODUCT_CUES = (
    "wireless", "bluetooth", "gaming", "headset", "headphone",
    "mouse", "chuot", "ban phim", "keyboard", "laptop", "monitor",
    "man hinh", "dien thoai", "smartphone", "iphone", "galaxy",
    "pixel", "xiaomi", "logitech", "razer", "asus", "rog",
    "steelseries", "sony", "samsung", "lenovo", "acer", "msi",
    "intel", "ryzen", "geforce", "radeon", "gpu", "ssd",
)
_PRIVATE_REFERENCES = re.compile(
    r"<[@#][!&]?\d+>|https?://|@|"
    r"\b(?:discord|server|archive|password|mat\s+khau|"
    r"email|dia\s+chi|so\s+dien\s+thoai)\b",
    flags=re.IGNORECASE,
)
_MODEL_ID = re.compile(
    r"\b(?:[a-z]{1,12}[-_]?\d+[a-z0-9-]*|\d+[a-z]{1,8}|ii|iii|iv)\b",
    re.IGNORECASE,
)
_PUBLIC_LABEL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 .+_/-]{2,69}$")


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").replace("đ", "d")


def _explicit_public_lookup_request(query: str) -> bool:
    folded = _fold(query).strip()
    # Finding an old Discord message, or saving/retrieving Archive material, is
    # not consent to send any part of it to a public search provider.
    if any(term in folded for term in (
        "tin nhan", "doan chat", "history", "archive",
        "trong server", "tren discord", "tim lai",
    )):
        return False
    return bool(re.search(
        r"\b(?:tra(?:\s+(?:thu|ho|giup|cuu|cho|thong\s+tin))?|"
        r"tim\s+(?:hieu|thong\s+tin|tren\s+web)|"
        r"search|lookup|check\s+(?:specs?|review|gia))\b",
        folded,
    ))


def _clean_candidate(line: str) -> str:
    # Reply metadata and a leading user ping are not part of the public query.
    # Internal pings, links and identifiers are never stripped and forwarded.
    line = re.sub(r"^\[reply to [^\]\r\n]{1,120}\]\s*", "", line.strip(), flags=re.I)
    line = re.sub(r"^(?:@[\w.\-]{2,50}\s+){1,3}", "", line)
    line = re.sub(r"^\s*(?:con|cai|hai\s+con|giua|mua)\s+", "", line, flags=re.I)
    return " ".join(line.split())


def _credible_public_product_label(label: str) -> bool:
    """Do not mistake one person's short English nickname for a model name."""
    folded = _fold(label)
    for cue in _PUBLIC_PRODUCT_CUES:
        if re.search(r"(?<![a-z])" + re.escape(cue) + r"(?![a-z])", folded):
            return True
    # Unrecognized brands are allowed if their catalog-style model has an
    # alphanumeric SKU *and* a separate suffix (e.g. maker + A7 + Ultra).
    return len(label.split()) >= 3 and bool(re.search(
        r"\b[a-z]{1,12}[-_]?\d+[a-z0-9-]*\b", folded,
    ))


def _public_product_pair(line: str) -> tuple[str, str] | None:
    clause = line.split("?", 1)[0]
    clause = _clean_candidate(clause)
    if _PRIVATE_REFERENCES.search(_fold(clause)):
        return None
    pieces = _PAIR_SEPARATOR.split(clause)
    if len(pieces) != 2:
        return None

    left, right = (_clean_candidate(item) for item in pieces)
    if not all(_PUBLIC_LABEL.fullmatch(item) for item in (left, right)):
        return None
    if not _MODEL_ID.search(left + " " + right):
        return None
    if not all(_credible_public_product_label(item) for item in (left, right)):
        return None
    # Avoid exporting phone numbers or opaque ticket/identifier strings.
    if re.search(r"\b\d{8,}\b", left + " " + right):
        return None
    return left, right


def public_product_search_query(
    query: str,
    context: AssistantContext | None,
) -> str | None:
    """Return names + generic search terms, never an original Discord quote.

    A direct reply is deliberately required: 15-minute ambient channel history
    is not a source of public web queries. This is a narrow positive contract:
    if classification is uncertain, return None rather than leak information.
    """
    if not _explicit_public_lookup_request(query) or context is None or context.reply is None:
        return None
    for line in context.reply.content.splitlines()[:5]:
        pair = _public_product_pair(line)
        if pair:
            left, right = pair
            return f"{left} vs {right} specifications comparison review"
    return None
