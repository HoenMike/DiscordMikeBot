"""T23.1: strict, explicit feedback intent and versioned design guidance.

This registry is maintained alongside feature changes. Guidance is evidence for
clarification, never a reason to block or auto-reject a user's bug report.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class FeedbackIntent:
    category: str
    text: str


@dataclass(frozen=True)
class BehaviorRule:
    key: str
    version: str
    description: str
    question: str


def normalize(value: str) -> str:
    data = unicodedata.normalize("NFD", (value or "").casefold())
    return "".join(c for c in data if unicodedata.category(c) != "Mn").replace("đ", "d")


def detect_feedback(content: str, *, replying_to_bot: bool = False) -> FeedbackIntent | None:
    """Only explicit reporting, not speculative sentiment or group banter."""
    folded = normalize(content).strip()
    match = re.search(r"\b(bao loi|report bug|bug report|gop y|feedback|de xuat tinh nang|loi bot)\b", folded)
    if match:
        category = "feature" if any(x in folded for x in ("gop y", "de xuat tinh nang")) else "bug"
        return FeedbackIntent(category, content.strip()[:3000])
    if replying_to_bot and re.search(r"\b(tra loi sai|ket qua sai|bot bi loi|cai nay sai|sai roi)\b", folded):
        return FeedbackIntent("bug", content.strip()[:3000])
    return None


RULES: tuple[BehaviorRule, ...] = (
    BehaviorRule(
        key="summary-channel-default",
        version="3.7.8+",
        description="Lệnh /tomtat không chọn tác giả được thiết kế để tóm tắt cả channel hiện tại.",
        question="Bạn dùng /tomtat thông thường hay đã tag một người nhưng bot vẫn lấy cả nhóm?",
    ),
    BehaviorRule(
        key="summary-author-scoped",
        version="3.7.8+",
        description="Câu yêu cầu tóm tắt tin nhắn của một người đã tag phải lọc đúng tác giả; một số cách diễn đạt có thể còn lỗi.",
        question="Bạn có thể cho biết câu lệnh nguyên văn và kết quả mong muốn không?",
    ),
)


def verified_design_hint(description: str, bot_version: str) -> BehaviorRule | None:
    text = normalize(description)
    if not any(x in text for x in ("tom tat", "tomtat", "/tomtat")):
        return None
    if re.search(r"<@!?\d{5,20}>", description) or any(x in text for x in ("cua @", "tag nguoi", "mot nguoi", "theo nguoi")):
        return RULES[1]
    # Only assert the first rule for an explicitly named command; an arbitrary
    # natural-language request may have different behavior.
    if "/tomtat" in text or ".m tomtat" in text:
        return RULES[0]
    return None


def clarification_text(description: str, bot_version: str) -> tuple[str, str]:
    rule = verified_design_hint(description, bot_version)
    if rule:
        return f"Theo thiết kế được ghi nhận của Asumi {rule.version}: {rule.description}\n{rule.question}", rule.key
    return (
        "Mình chưa đủ thông tin để kết luận đây là lỗi hay cách dùng chưa phù hợp. "
        "Bạn có thể bổ sung kết quả mong muốn hoặc câu lệnh đã dùng. "
        "Dù vậy bạn vẫn có thể gửi ticket để admin review.",
        "unknown",
    )
