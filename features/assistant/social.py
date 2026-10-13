"""Bounded, explicitly targeted Discord banter guidance.

Classification is only a *reply-style* hint. It never authorizes any Discord
moderation command, and never fetches or stores additional conversation history.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from features.assistant.context import AssistantContext


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFD", (value or "").lower())
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn").replace("đ", "d")


@dataclass(frozen=True)
class SocialReplyPlan:
    requester: str
    target: str
    mode: str
    target_id: int | None = None
    topic_hint: str = ""


# Only short direct requests with a resolved person. Do not treat every swear,
# mention or question as an invitation to roast someone.
_TEASE = re.compile(r"\b(?:dm|dmm|dit me|say|ca khia|roast|treu|choc|khia|hua theo|troll)\b")
_CHALLENGE = re.compile(r"\bchan\b")
_IMAGINARY_BAN = re.compile(r"\bban\b")
_SERIOUS_MODERATION = re.compile(
    r"\b(?:vi pham|spam|quay roi|lua dao|phat tan|mod|moderator|admin|"
    r"quyen|lenh ban|ban that|ban real|thuc su|report|bao cao)\b"
)


def plan_social_reply(query: str, context: AssistantContext | None) -> SocialReplyPlan | None:
    if context is None or not context.social_referent or not context.requester:
        return None
    if len(context.mentioned_people) > 1 or len(query) > 220:
        return None

    folded = _fold(re.sub(r"<@!?\d{1,20}>", " ", query))
    target_id = (
        context.mentioned_people[0][0]
        if len(context.mentioned_people) == 1
        else None
    )
    # User-authored slang "chan" in casual chat is not the moderation verb "chặn".
    if _CHALLENGE.search(folded):
        mode = "challenge"
    elif _TEASE.search(folded):
        mode = "tease"
    elif _IMAGINARY_BAN.search(folded) and not _SERIOUS_MODERATION.search(folded):
        mode = "pretend_ban"
    else:
        return None

    target = context.social_referent
    hint = ""
    # A message by the target is more relevant than ambient chat by bystanders.
    for line in reversed(context.recent):
        if line.author == target and line.content:
            hint = line.content[:200]
            break
    if not hint and context.reply and context.reply.author == target:
        hint = context.reply.content[:200]
    return SocialReplyPlan(
        requester=context.requester,
        target=target,
        mode=mode,
        target_id=target_id,
        topic_hint=hint,
    )


def social_reply_instruction(plan: SocialReplyPlan) -> str:
    action = {
        "tease": "NGƯỜI GỌI MUỐN ASUMI CÀ KHỊA VUI NGƯỜI ĐƯỢC TAG; 'đm' trong yêu cầu này không phải câu hỏi Mike định làm gì.",
        "challenge": "'chan' LÀ TỪ LÓNG CÓ CHỦ Ý TRONG MẠCH TRÊU NHAU; KHÔNG TỰ SỬA THÀNH 'chặn' HAY THAO TÁC MODERATION.",
        "pretend_ban": "ĐÂY LÀ MẠCH ĐÙA BAN GIẢ TƯỞNG, KHÔNG THỰC HIỆN HOẶC NHẬN ĐÃ BAN.",
    }[plan.mode]
    hint = (
        f"Tin gần đây do đúng mục tiêu gửi: {plan.topic_hint!r}. "
        "Chỉ dùng nó nếu thực sự phù hợp."
        if plan.topic_hint
        else "Không có dữ kiện cụ thể về mục tiêu; đừng sáng tác thành tích hay chuyện cũ."
    )
    return (
        "CHẾ ĐỘ HỘI THOẠI XÃ HỘI (chỉ định phong cách, KHÔNG phải action):\n"
        f"- Người gọi / đồng đội lượt này: {plan.requester}.\n"
        f"- Người cần được đối đáp: {plan.target}.\n"
        f"- {action}\n"
        "- NHIỆM VỤ: Nói một câu cà khịa/đối đáp ngắn, có duyên, "
        f"TRỰC TIẾP VỚI {plan.target}, gọi tên hoặc nickname của người này. "
        "ĐỪNG hỏi ngược người gọi 'định làm gì?', 'muốn gì?', 'lại tính làm gì?' "
        "hay giải thích đang chờ họ ra lệnh. Không đổi target qua người gọi.\n"
        "- Không cần nhắc tới việc Asumi được gọi. Không tự nhận đã ban/kick; "
        "không dùng lời lăng mạ nặng, miệt thị hoặc đe dọa.\n"
        f"- {hint}"
    )


def is_social_reply_on_target(reply: str, plan: SocialReplyPlan) -> bool:
    """Cheap regression guard for obvious role reversal, not a toxicity filter."""
    folded = _fold(reply)
    if not folded.strip():
        return False

    target_alias = _fold(plan.target)
    tokens = target_alias.split()
    short_alias = " ".join(tokens[-2:]) if len(tokens) >= 2 else target_alias
    by_name = target_alias in folded or short_alias in folded
    by_ping = plan.target_id is not None and re.search(
        rf"<@!?{plan.target_id}>", reply
    ) is not None
    if not by_name and not by_ping:
        return False

    caller = _fold(plan.requester)
    # The reported failure addressed Mike instead of delivering the roast.
    # Restrict rejection to clear meta-questions TO the requester.
    if caller and caller in folded and re.search(
        r"\b(?:lai tinh lam gi|dinh goi|dinh ru|dinh pha|"
        r"tinh lam gi|muon lam gi|dinh lam gi)\b",
        folded,
    ):
        return False
    return True


def safe_social_fallback(plan: SocialReplyPlan) -> str:
    """A short, non-deceptive fallback when two prose candidates reverse roles."""
    if plan.mode == "pretend_ban":
        return f"{plan.target} ơi, hội đồng vừa tuyên án: tội quá tự tin, phạt ngồi nghe cà khịa 5 phút =)))"
    if plan.mode == "challenge":
        return f"{plan.target} ơi, nghe có người rủ chan kèo kìa, nhận lời hay né đây =)))"
    return f"{plan.target} ơi, ra đây nhận một câu cà khịa nhẹ coi, đừng núp nữa =)))"
