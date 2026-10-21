"""Private, zero-LLM Asumi AI usage snapshot backed by the T31 ledger."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from core.ai_usage import store

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
LABELS = {"today": "hôm nay", "month": "tháng này", "7d": "7 ngày", "30d": "30 ngày"}


def usage_window(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or period not in LABELS:
        raise ValueError("Invalid usage window")
    vn = now.astimezone(VIETNAM)
    if period == "today":
        start = vn.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = vn.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=7 if period == "7d" else 30)
    return start.astimezone(timezone.utc), now.astimezone(timezone.utc)


def format_quick_usage(rows, period: str, *, tracked_since: str | None = None) -> str:
    """Display observed Gemini metadata only; unknown != zero-cost/free quota."""
    if not rows:
        return (
            "**Asumi AI Usage — " + LABELS[period] + "**\n"
            "Chưa có dữ liệu ghi nhận trong khoảng này. Bộ đếm chỉ bắt đầu "
            "từ khi tính năng được chạy; không tự lấy lại token lịch sử."
        )
    total_calls = sum(int(r[2] or 0) for r in rows)
    failed = sum(int(r[4] or 0) for r in rows)
    unknown = sum(int(r[5] or 0) for r in rows)
    gemini = [r for r in rows if str(r[1]).startswith("gemini-")]
    inp = sum(int(r[6] or 0) for r in gemini)
    output = sum(int(r[7] or 0) for r in gemini)
    thinking = sum(int(r[8] or 0) for r in gemini)
    cached = sum(int(r[9] or 0) for r in gemini)
    usd = sum(int(r[10] or 0) for r in rows) / 1_000_000
    model = max(gemini, key=lambda r: int(r[2] or 0))[1] if gemini else "chưa có"
    lines = [
        "**Asumi AI Usage — " + LABELS[period] + "**",
        f"Gemini input: **{inp:,} token** (cached {cached:,})",
        f"Output: **{output:,}** · thinking: **{thinking:,}**",
        f"API calls ghi nhận: **{total_calls:,}** (lỗi {failed:,})",
        f"Model gọi nhiều nhất: **{model}**",
        f"Chi phí Gemini đã định giá: **~${usd:,.4f}**",
    ]
    if unknown or failed:
        lines.append(f"**Chưa đầy đủ:** {unknown} lượt thiếu giá/metadata, {failed} lượt lỗi không rõ billing.")
    lines.append(
        "_Ước tính từ metadata Gemini, không phải hóa đơn/số dư/quota còn lại; "
        "Clef và các dịch vụ khác có thể chưa được định giá._"
    )
    return "\n".join(lines)


async def quick_usage_report(period: str) -> str:
    start, end = usage_window(period)
    rows = await store.aggregate_between(start, end)
    return format_quick_usage(rows, period)
