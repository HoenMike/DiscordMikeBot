from __future__ import annotations

import re
from typing import Optional


def _mention_pattern(bot_user_id: int) -> re.Pattern[str]:
    return re.compile(rf"<@!?{int(bot_user_id)}>")


def has_explicit_mention(message, bot_user_id: Optional[int]) -> bool:
    if not bot_user_id or getattr(message, "guild", None) is None:
        return False
    content = getattr(message, "content", "") or ""
    return bool(_mention_pattern(bot_user_id).search(content))


def strip_bot_mention(content: str, bot_user_id: Optional[int]) -> str:
    text = (content or "").strip()
    if not bot_user_id:
        return text
    return _mention_pattern(bot_user_id).sub("", text, count=1).strip()
