"""Persistent Gemini text-API usage metrics; not Google Cloud billing."""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import re
import uuid

from core import constants as policy
from core.db import db_client

PRICE_URL = "https://ai.google.dev/gemini-api/docs/pricing"
# (USD per million input, output [includes thinking], cached input).
# Only Gemini Standard text; unknown models/tiers must remain UNPRICED.
PRICES = {
    "gemini-3.8-flash": ("0.75", "3.75", "0.075"),
    "gemini-3.7-flash": ("0.75", "3.75", "0.075"),
    "gemini-3.6-flash": ("0.75", "3.75", "0.075"),
    "gemini-3.5-flash": ("1.50", "9.00", "0.15"),
    "gemini-3.5-flash-lite": ("0.30", "2.50", "0.03"),
    "gemini-3.1-flash-lite": ("0.25", "1.50", "0.025"),
}
DOUBLE_IN_2027 = {"gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"}
CHANGE_DATE = datetime(2027, 1, 1, tzinfo=timezone.utc)
DDL = """CREATE TABLE IF NOT EXISTS asumi_ai_usage (
 request_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, provider TEXT NOT NULL,
 task TEXT NOT NULL, requested_model TEXT NOT NULL, actual_model TEXT NOT NULL,
 outcome TEXT NOT NULL, prompt_tokens INTEGER, output_tokens INTEGER,
 thinking_tokens INTEGER, cached_tokens INTEGER, estimated_usd_micros INTEGER,
 pricing_status TEXT NOT NULL, latency_ms INTEGER NOT NULL, error_type TEXT
)"""
INDEX = "CREATE INDEX IF NOT EXISTS ix_ai_usage_date ON asumi_ai_usage(occurred_at)"


def normalize_model(model: str) -> str:
    name = (model or "").strip().lower()
    return (name.removeprefix("models/"))[:96]


def task_family(label: str) -> str:
    name = (label or "").lower()
    if "clef" in name or "router" in name: return "routing"
    if "conversation" in name or "chat" in name: return "chat"
    if "tarot" in name: return "tarot"
    if "cabin" in name: return "cabin"
    if any(x in name for x in ("summary", "mapreduce", "single-pass", "qa evaluator")): return "summary"
    if any(x in name for x in ("dnd", "dungeon", "misfits")): return "dnd"
    return "other"


def extract_usage(response):
    """prompt includes cached; thinking is separate from candidates."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None: return None
    def token(key):
        n = getattr(meta, key, 0) or 0
        return n if type(n) is int and n >= 0 else None
    p, o, t, c = (token(k) for k in (
        "prompt_token_count", "candidates_token_count",
        "thoughts_token_count", "cached_content_token_count",
    ))
    if None in (p, o, t, c) or c > p or not (p or o or t): return None
    return {"prompt": p, "output": o, "thinking": t, "cached": c}


def estimate_micros(model: str, usage: dict | None, at: datetime):
    """USD micro-units, None for missing/inapplicable metadata."""
    model = normalize_model(model)
    if not usage or model not in PRICES: return None
    inp, out, cached = map(Decimal, PRICES[model])
    if model in DOUBLE_IN_2027 and at >= CHANGE_DATE:
        inp *= 2; out *= 2; cached *= 2
    value = ((usage["prompt"] - usage["cached"]) * inp
             + usage["cached"] * cached
             + (usage["output"] + usage["thinking"]) * out)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def usage_event(*, model: str, response=None, label="AI", outcome="ok",
                latency_ms=0, error_type=None, at=None,
                provider="google-gemini") -> tuple:
    at = at or datetime.now(timezone.utc)
    usage = extract_usage(response) if response is not None else None
    actual = normalize_model(getattr(response, "model_version", None) or model)
    value = (estimate_micros(actual, usage, at)
             if outcome == "ok" and provider == "google-gemini" else None)
    status = ("ESTIMATED" if value is not None else
              "FAILED_UNKNOWN_BILLING" if outcome != "ok" else
              "PROVIDER_UNPRICED" if provider != "google-gemini" else "UNPRICED")
    return (uuid.uuid4().hex, at.astimezone(timezone.utc).isoformat(),
            provider[:32], task_family(label), normalize_model(model), actual,
            outcome, usage["prompt"] if usage else None,
            usage["output"] if usage else None,
            usage["thinking"] if usage else None,
            usage["cached"] if usage else None, value,
            status, max(0, int(latency_ms)),
            re.sub("[^A-Za-z0-9_]", "", error_type or "")[:64] or None)


class UsageStore:
    def __init__(self):
        self._ready_loops = set()

    async def _init(self):
        await db_client.connect()
        import config
        # Prevent split-brain billing ledger if Render loses Turso.
        if (config.TURSO_AUTH_TOKEN or os.getenv("RENDER")) and not db_client.is_cloud:
            raise RuntimeError("AI usage store requires Turso in production")
        loop = asyncio.get_running_loop()
        if loop not in self._ready_loops:
            await db_client.execute(DDL)
            await db_client.execute(INDEX)
            await db_client.commit()
            self._ready_loops.add(loop)

    async def add(self, event: tuple):
        await self._init()
        await db_client.execute(
            """INSERT OR IGNORE INTO asumi_ai_usage (
            request_id,occurred_at,provider,task,requested_model,actual_model,
            outcome,prompt_tokens,output_tokens,thinking_tokens,cached_tokens,
            estimated_usd_micros,pricing_status,latency_ms,error_type
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", event)
        await db_client.commit()

    async def aggregate(self, days=30, at=None):
        if days not in (7, 30): raise ValueError("Invalid days")
        await self._init()
        at = at or datetime.now(timezone.utc)
        since = (at - timedelta(days=days)).isoformat()
        async with db_client.execute(
            """SELECT task, actual_model, COUNT(*),
             SUM(CASE WHEN outcome='ok' THEN 1 ELSE 0 END),
             SUM(CASE WHEN outcome!='ok' THEN 1 ELSE 0 END),
             SUM(CASE WHEN outcome='ok' AND pricing_status!='ESTIMATED' THEN 1 ELSE 0 END),
             SUM(COALESCE(prompt_tokens,0)), SUM(COALESCE(output_tokens,0)),
             SUM(COALESCE(thinking_tokens,0)), SUM(COALESCE(cached_tokens,0)),
             SUM(COALESCE(estimated_usd_micros,0))
             FROM asumi_ai_usage WHERE occurred_at>=? AND occurred_at<=?
             GROUP BY task,actual_model
             ORDER BY SUM(COALESCE(estimated_usd_micros,0)) DESC LIMIT 100""",
            (since, at.isoformat())) as cursor:
            return await cursor.fetchall()


    async def dashboard(self, days=7, at=None):
        """Bounded aggregate for the classic admin dashboard, no raw prompts."""
        if days not in (7, 30):
            raise ValueError("days must be 7 or 30")
        await self._init()
        at = at or datetime.now(timezone.utc)
        since = (at - timedelta(days=days)).isoformat()
        async with db_client.execute(
            """SELECT SUBSTR(occurred_at,1,10), provider, task, actual_model,
              COUNT(*),
              SUM(CASE WHEN outcome='ok' THEN 1 ELSE 0 END),
              SUM(CASE WHEN outcome!='ok' THEN 1 ELSE 0 END),
              SUM(CASE WHEN outcome='ok' AND pricing_status!='ESTIMATED' THEN 1 ELSE 0 END),
              SUM(COALESCE(prompt_tokens,0)),
              SUM(COALESCE(output_tokens,0)),
              SUM(COALESCE(thinking_tokens,0)),
              SUM(COALESCE(cached_tokens,0)),
              SUM(COALESCE(estimated_usd_micros,0))
              FROM asumi_ai_usage
              WHERE occurred_at>=? AND occurred_at<=?
              GROUP BY SUBSTR(occurred_at,1,10),provider,task,actual_model
              ORDER BY SUBSTR(occurred_at,1,10) ASC
              LIMIT 2001""",
            (since, at.isoformat()),
        ) as cursor:
            rows = await cursor.fetchall()
        async with db_client.execute(
            "SELECT MIN(occurred_at) FROM asumi_ai_usage"
        ) as cursor:
            first = await cursor.fetchone()
        return build_dashboard_payload(
            rows[:2000], days=days, at=at,
            first_recorded_at=(first[0] if first else None),
            truncated=len(rows) > 2000,
        )


def build_dashboard_payload(rows, *, days, at, first_recorded_at=None, truncated=False):
    """Presentation-ready numeric aggregates; rate estimates are conditional."""
    if days not in (7, 30):
        raise ValueError("invalid days")
    sums = ["calls", "success", "failed", "unpriced", "input_tokens",
            "output_tokens", "thinking_tokens", "cached_tokens", "usd_micros"]
    def zero():
        return {name: 0 for name in sums}
    def combine(dst, nums):
        for name, val in zip(sums, nums):
            dst[name] += int(val or 0)
    total = zero()
    daily = {}
    models = {}
    features = {}
    for day, provider, task, model, *nums in rows:
        day = str(day)[:10]
        provider = str(provider)[:32]
        task = str(task)[:32]
        model = str(model)[:96]
        combine(total, nums)
        combine(daily.setdefault(day, zero()), nums)
        model_key = (provider, model)
        combine(models.setdefault(model_key, zero()), nums)
        combine(features.setdefault(task, zero()), nums)

    initial = None
    if first_recorded_at:
        try:
            initial = datetime.fromisoformat(str(first_recorded_at))
            if initial.tzinfo is None:
                initial = initial.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            initial = None
    elapsed_days = max(1.0, (at - initial).total_seconds() / 86400) if initial else 1.0
    sample_days = min(float(days), elapsed_days)
    priced_success = total["success"] - total["unpriced"]
    has_unknown = total["failed"] > 0 or total["unpriced"] > 0 or truncated
    forecast = (
        round(total["usd_micros"] * 30 / sample_days)
        if priced_success > 0 and not truncated else None
    )
    today_key = at.astimezone(timezone.utc).date().isoformat()
    return {
        "window_days": days, "as_of": at.astimezone(timezone.utc).isoformat(),
        "first_recorded_at": first_recorded_at,
        "observed_days": round(sample_days, 2),
        "early_sample": elapsed_days < 3,
        "incomplete": has_unknown,
        "truncated": bool(truncated),
        "totals": total,
        "today_utc": daily.get(today_key, zero()),
        "forecast_30d_usd_micros": forecast,
        "daily": [{"date": day, **metrics} for day, metrics in sorted(daily.items())],
        "by_model": [{"provider": provider, "model": model, **metrics}
                     for (provider, model), metrics in sorted(
                         models.items(), key=lambda item: item[1]["usd_micros"], reverse=True)],
        "by_feature": [{"feature": task, **metrics}
                       for task, metrics in sorted(
                           features.items(), key=lambda item: item[1]["usd_micros"], reverse=True)],
        "disclaimer": (
            "Ước tính từ Gemini Standard text, không phải hóa đơn Google. "
            "Clef/provider khác có thể chưa định giá. "
            "Không bao gồm grounding, phí lưu cache, hosting hoặc các request bị mất metadata. "
            "GCP Credits và Prepay chỉ là giả định nhập tay; xác minh ở Google Billing."
        ),
    }


def render_report(rows, *, days, vnd_per_usd=26000, prepay_vnd=None,
                  eligible_credits_vnd=None):
    """Transparent 30-day straight-line projection. Credits are manual only."""
    if days not in (7, 30) or not 1000 <= vnd_per_usd <= 100000:
        raise ValueError("Invalid report settings")
    if prepay_vnd is not None and not 0 <= prepay_vnd <= 1_000_000_000:
        raise ValueError("Invalid prepay")
    if eligible_credits_vnd is not None and not 0 <= eligible_credits_vnd <= 1_000_000_000:
        raise ValueError("Invalid credits")
    if not rows:
        return ("**AI Cost Monitor — " + str(days) + " ngày**\n"
                "Chưa có dữ liệu kể từ khi deploy; không truy xuất lịch sử token cũ. "
                "Dùng /ai_cost lại sau khi Asumi nhận request Gemini.")
    count = sum(int(r[2]) for r in rows)
    succeeded = sum(int(r[3]) for r in rows)
    failed = sum(int(r[4]) for r in rows)
    unpriced = sum(int(r[5]) for r in rows)
    micros = sum(int(r[10] or 0) for r in rows)
    priced_count = succeeded - unpriced
    month_micros = micros * 30 / days if priced_count > 0 else None
    fmt = lambda n: format(round(n / 1_000_000 * vnd_per_usd), ",")
    models = {}
    tasks = {}
    for task, model, calls, ok, err, unknown, pin, pout, thought, cache, value in rows:
        stats = models.setdefault(model, [0, 0, 0, 0, 0, 0])
        for i, v in enumerate((calls,pin,pout,thought,cache,value)):
            stats[i] += int(v or 0)
        tasks[task] = tasks.get(task, 0) + int(value or 0)
    lines = [
        "**AI Cost Monitor — " + str(days) + " ngày gần nhất**",
        f"Requests: **{count:,}** (thành công {succeeded:,}, lỗi {failed:,}, chưa định giá {unpriced:,})",
        (f"Ước tính Gemini có giá: **USD {micros/1_000_000:,.4f}** (~**{fmt(micros)}đ**)"
         if priced_count > 0 else "Chi phí: **CHƯA XÁC ĐỊNH** (không có request nào đủ dữ liệu định giá)."),
        (f"Nếu giữ nhịp gọi: **~{fmt(month_micros)}đ / 30 ngày**."
         if priced_count > 0 else "Chưa đủ dữ liệu định giá để dự phóng chi phí hàng tháng."),
        "**Theo model:**",
    ]
    for model, (calls, inp, out, thought, cache, val) in sorted(
            models.items(), key=lambda row: row[1][-1], reverse=True)[:6]:
        model_unknown = sum(int(row[5] or 0) for row in rows if row[1] == model)
        model_success = sum(int(row[3] or 0) for row in rows if row[1] == model)
        price = f"~{fmt(val)}đ" if model_success > model_unknown else "chưa định giá"
        lines.append(f"• {model}: {calls} calls · in {inp:,}, out {out:,}, think {thought:,}, cached {cache:,} · {price}")
    lines.append("**Theo tính năng:**")
    for task, val in sorted(tasks.items(), key=lambda row: row[1], reverse=True)[:6]:
        lines.append(f"• {task}: ~{fmt(val)}đ")
    month_vnd = (month_micros / 1_000_000 * vnd_per_usd
                 if month_micros is not None else 0)
    if prepay_vnd is not None:
        lines.append(f"Prepay do admin nhập: {prepay_vnd:,}đ")
        if month_vnd > 0:
            lines.append(f"Đủ khoảng **{prepay_vnd/month_vnd:.1f} tháng** (chưa tính credit).")
        if eligible_credits_vnd is not None:
            lines.append(f"Credit GIẢ ĐỊNH hợp lệ: {eligible_credits_vnd:,}đ")
            if month_vnd > 0:
                lines.append(f"Nếu hợp lệ, tổng đủ khoảng **{(prepay_vnd+eligible_credits_vnd)/month_vnd:.1f} tháng**.")
    lines += [
        "_Chỉ ước tính Standard text Paid Tier; không phải hóa đơn hoặc số dư thực.",
        "Chưa tính phí grounding, cache storage, đa phương thức, Cloudflare Clef, Brave, "
        "request thiếu metadata và các khoản ngoài Gemini. Thinking tính vào output. "
        f"Tỷ giá giả định {vnd_per_usd:,}đ/USD; 7/30 ngày là cửa sổ trượt, "
        "dự báo có thể lệch nếu lưu lượng thay đổi._",
    ]
    return "\n".join(lines)


store = UsageStore()
_pending = set()


def queue(event):
    if not getattr(policy, "ASUMI_AI_USAGE_ENABLED", True): return
    task = asyncio.create_task(store.add(event))
    _pending.add(task)
    def complete(fut):
        _pending.discard(fut)
        try: fut.result()
        except Exception as exc:
            print("[AI Cost] ledger unavailable: " + type(exc).__name__, flush=True)
    task.add_done_callback(complete)
