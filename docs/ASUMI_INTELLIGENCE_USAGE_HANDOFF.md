# Asumi Intelligence + Zero-LLM AI Usage — test handoff (2026-10-21)

Status: **Draft implementation / not merged / not deployed / no version bump**.
Branch: `feat/asumi-intelligence-usage-fastpath`. Based on current main, not on the outdated T31 branch.
T31 telemetry/dashboard comes from open draft PR #82 and is applied to current main without overwriting the recent Gemini 429 circuit.

## User contract

- `@Asumi token`, `hết bao nhiêu token rồi?`, `token hôm nay`, `token tháng này`, `token 30 ngày`, and explicit bot cost questions are local deterministic intents.
- Fast path is before Discord 15-minute history collection, Clef and Gemini. No inference request to obtain token usage.
- Only the Discord application owner may read global usage. In a guild, the report is sent by DM, while the channel sees a short acknowledgement. If DM is closed, show a generic instruction to use private slash `/ai_cost`. Unauthorized users cannot query the ledger.
- Gemini metadata records input/output/thinking/cache tokens. Clef records request counts as unpriced; no invented Cloudflare token counts. Estimates are not quota remaining, AI Studio account balance, invoices, or free-tier allocation.
- Errors, unknown prices, provider timeouts and unavailable Turso must not appear as free use. History cannot be reconstructed before telemetry starts.
- The original classic admin Dashboard gains a **read-only AI Usage** tab. No new admin shell, no change to Feedback/Tarot tabs.

## Conversational changes (no emoji learning)

- Continue to use up to 15 minutes of live channel context only when Asumi is explicitly invoked. No passive harvesting, emoji database, persistent emote definitions or image-learning jobs.
- Mimic the live room's tone selectively instead of applying a stereotyped persona. When a custom Discord emoji appears, its name is not evidence of visual meaning. The model may reuse **only exact custom emoji tags actually observed in the current request/reply/recent messages**.
- Treat earlier Asumi text as fallible conversation, not as verified citations. When a user asks about numeric claims, distinguish samples, denominator, time period, observed data and assumptions. Stay answer-first in normal Discord chat.
- On a live followup, reconsider tools for explicitly self-contained public factual questions (with source/date cues), while avoiding derived search queries from private Discord history.
- Date/time grounding is now generic for any Vietnamese dd/mm, based on backend-provided Asia/Ho_Chi_Minh clock; removed the 20/10-only special case.
- Existing Tarot, Feedback, moderation, historical search/privacy boundaries, model tiers and deploy recovery should stay unchanged.

## Root cause and invariant

The old routing shortcut assumed all live replies were chat without independently checking if the new message contained a public fact request. The chat prompt was also free to compound its own unsupported facts, infer emoji semantics from an opaque name and apply a fixed-day workaround. Separately, T31 instrumentation existed on a divergent draft branch, not production main. Changes address routing, evidence contract, request boundaries, data capture and output validation rather than hardcoding the startup screenshot or emoji name.

## QA

Automated regression: tests/test_ai_usage_cost.py, test_ai_usage_dashboard.py, test_assistant_usage_intelligence.py, test_assistant_time_flash_search.py, test_assistant_mentions_and_quota.py, test_assistant_search_followup.py, plus dashboard JS syntax. The GitHub Actions workflow includes these tests.

**Live acceptance still required:** new Gemini calls with actual usage_metadata; compare AI Studio/Billing totals (which can lag), 429 fallback behavior, owner/non-owner Discord asks, disabled DMs, mobile UI, Turso outage/restore, emoji use within and outside recent context, reply routing and no surprise external searches. This Draft PR does not perform deployment. The bot version, changelog and patch notes remain untouched.

## Remaining gaps

- T31.3 reconciliation with actual Google Cloud Billing, and a first-party quota-remaining endpoint, are separate authorization/integration tasks. Asumi must not claim these values are known.
- Long-horizon empirical quality/cost measurements should precede any model routing change.
