"""Deterministic, fail-closed interpretation of public Codex reset signals.

Tracker labels/probabilities are NOT official confirmations. Only Tibo's
quoted text is classified into actionable events.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
import re
from urllib.parse import urlparse

LA = ZoneInfo("America/Los_Angeles")
VN = ZoneInfo("Asia/Ho_Chi_Minh")
X_POST = re.compile(r"^https://(?:x\.com|twitter\.com)/thsottiaux/status/(\d{15,22})/?$")
MAX_SOURCE_AGE = timedelta(hours=12)
MAX_POST_AGE = timedelta(days=3)


@dataclass(frozen=True)
class ResetSignal:
    key: str
    stage: str
    post_id: str
    posted_at: datetime
    url: str
    detail: str
    window_vn: str = ""


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone missing")
    return dt.astimezone(timezone.utc)


def fresh_feed(feed: dict, now: datetime) -> bool:
    try:
        age = now.astimezone(timezone.utc) - parse_time(feed["fetched_at"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    return timedelta(0) <= age <= MAX_SOURCE_AGE and feed.get("stale") is not True


def classify_post(post: dict, now: datetime) -> ResetSignal | None:
    """Never promote a tracker category (e.g. type=reset) into a fact."""
    post_id = str(post.get("id", ""))
    url = post.get("url", "")
    match = X_POST.fullmatch(url) if isinstance(url, str) else None
    if match is None or match.group(1) != post_id:
        return None
    try:
        published = parse_time(post["at"])
        age = now.astimezone(timezone.utc) - published
        if not timedelta(0) <= age <= MAX_POST_AGE:
            return None
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    raw = post.get("text", "")
    if not isinstance(raw, str) or len(raw) > 5000:
        return None
    normalized = re.sub(r"\s+", " ", raw.casefold()).strip()
    # Banked resets are distinct: a banked credit is NOT an automatic global
    # usage limit refresh. Only unequivocal statements are announced.
    if "banked reset" in normalized or "reset in everyone's paid accounts" in normalized:
        if re.search(r"\b(loading|loaded|landed|available|announc|grant|giving|giv[ei]n)\w*\b", normalized):
            stage = "banked"
            detail = "Tibo thông báo reset dự trữ (kích hoạt thủ công)."
        else:
            return None
    elif (
        re.search(r"\b(reset(?:s)?\s+(?:all\s+)?propagated|all\s+propagated)\b", normalized)
        and "reset" in normalized
    ) or re.search(r"\b(?:the\s+)?reset\s+has\s+been\s+processed\b", normalized):
        # Avoid the ambiguous one-liner "confirmed landed across all accounts"
        # (previously used for a BANKED credit).
        stage = "completed"
        detail = "Tibo xác nhận global reset đã triển khai xong."
    elif (
        re.search(r"\bglobal\s+reset\b", normalized)
        and re.search(r"\b(?:delayed|postponed|cancelled|canceled)\b", normalized)
    ):
        stage = "changed"
        detail = "Tibo thông báo thay đổi kế hoạch global reset."
    elif (re.search(r"\bglobal\s+reset\b", normalized)
          and not re.search(r"\b(?:no|not|won't|never)\s+(?:a\s+)?global\s+reset\b", normalized)
          and re.search(
              r"\b(by\s+eod|landing|incoming|will\s+(?:happen|land|reset)|tomorrow|scheduled|planned)\b",
              normalized,
          )):
        stage = "announced"
        detail = "Tibo công bố global reset sắp diễn ra."
    else:
        # Excludes 'Day 8 / Reset', jokes, polls, vote % and tracker speculation.
        return None

    window = estimate_window(raw, published) if stage == "announced" else ""
    return ResetSignal(
        key=f"x:{post_id}:{stage}",
        stage=stage,
        post_id=post_id,
        posted_at=published,
        url=url,
        detail=detail,
        window_vn=window,
    )


def estimate_window(text: str, posted: datetime) -> str:
    """EOD refers to the author's LOCAL day, not the UTC calendar date.

    Do not pretend EOD is an official 09:00-12:00 reset window.
    """
    lower = text.casefold()
    if "eod" not in lower:
        return "Chưa rõ giờ (VN)"
    local_posted = posted.astimezone(LA)
    target_day = local_posted.date()
    if "tomorrow" in lower:
        target_day += timedelta(days=1)
    end = datetime.combine(target_day, time(23, 59), tzinfo=LA).astimezone(VN)
    # PDT in October; explicit PST wording is sometimes used colloquially.
    local_label = end.strftime("%H:%M %d/%m")
    if "pst" in lower and local_posted.utcoffset() == timedelta(hours=-7):
        return f"trước khoảng {local_label} (VN; PST viết mơ hồ, có thể trễ 1 giờ)"
    return f"trước khoảng {local_label} (VN, ước tính theo EOD)"


def extract_signals(feed: dict, now: datetime) -> list[ResetSignal]:
    if not isinstance(feed, dict) or not fresh_feed(feed, now):
        return []
    signals: list[ResetSignal] = []
    for post in feed.get("tweets", [])[:80]:
        if not isinstance(post, dict):
            continue
        found = classify_post(post, now)
        if found:
            signals.append(found)
    return sorted(signals, key=lambda x: x.posted_at)


def forecast_warning(primary: dict, independent_percent: tuple[int, int] | None) -> bool:
    """Require TWO differing forecast models, never a poll/commitment score."""
    if independent_percent is None or not isinstance(primary, dict):
        return False
    p = primary.get("probabilities", {})
    if not isinstance(p, dict):
        return False
    try:
        one = [float(p["model_24h"]), float(p["model_48h"])]
        two = [int(independent_percent[0]), int(independent_percent[1])]
    except (KeyError, ValueError, TypeError):
        return False
    return any(a > 75 for a in one) and any(b > 75 for b in two)


def format_alert(signal: ResetSignal, role_mention: str = "") -> str:
    heads = {
        "announced": "🟠 **CODEX GLOBAL RESET — ĐÃ CÔNG BỐ**",
        "completed": "🟢 **CODEX GLOBAL RESET — ĐÃ HOÀN TẤT**",
        "changed": "🔴 **CODEX GLOBAL RESET — THAY ĐỔI LỊCH**",
        "banked": "🟣 **CODEX BANKED RESET — KHÔNG TỰ ĐỘNG**",
    }
    if signal.stage not in heads:
        raise ValueError("Unsupported alert type")
    time_line = f"⏰ {signal.window_vn}" if signal.window_vn else (
        "⏰ Kiểm tra hạn mức trong Codex (giờ VN)"
        if signal.stage == "completed" else
        "⏰ Chưa có mốc cụ thể"
    )
    action = {
        "announced": "⚠️ Chưa hoàn tất; nên sử dụng quota còn lại.",
        "completed": "✅ Hãy kiểm tra Usage của tài khoản; phạm vi có thể khác nhau.",
        "changed": "⚠️ Mốc dự kiến có thể thay đổi, đừng mặc định đã reset.",
        "banked": "ℹ️ Banked reset cần kích hoạt riêng; không phải global reset.",
    }[signal.stage]
    # Wrap the URL to prevent onebox. Caller also MUST set suppress_embeds=True.
    message = "\n".join(x for x in (
        role_mention, heads[signal.stage], signal.detail, time_line, action, f"<{signal.url}>"
    ) if x)
    return message


def format_forecast_alert(url: str, p24: int, p48: int, extra24: int, extra48: int,
                          role_mention: str = "") -> str:
    if url != "https://codex-reset.com/":
        raise ValueError("Unrecognized forecast URL")
    return "\n".join(x for x in (
        role_mention,
        "🟡 **CODEX RESET — DỰ BÁO CAO, CHƯA XÁC NHẬN**",
        f"2 mô hình: {p24}%/{p48}% và {extra24}%/{extra48}% (24h/48h).",
        "⚠️ Chưa có cam kết chính thức; đừng coi là đã reset.",
        "<https://codex-reset.com/>",
    ) if x)
