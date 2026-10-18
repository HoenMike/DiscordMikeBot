# Asumi T31 — AI Usage & Cost Dashboard Roadmap

**Status:** Design + implementation in Draft PR #82. Not deployed or live accepted.

**Owner decision (2026-10-18):** Track models, tokens, estimated AI costs and long-term running expenses in the **historical, classic /admin dashboard**. No new sidebar, separate dashboard shell or replacement of Feedback/Tarot/admin tabs.

## User-facing outcomes

A dashboard owner should see (a) today / 7 / 30 days AI usage, (b) model and feature spending, (c) daily cost trend, (d) requests/errors and input/output/thinking/cache tokens, (e) 30-day projected spending and prepay/verified-credit runway, and (f) missing provider prices/usage.

The dashboard is *read only* and never invokes Gemini to make a report. Only billable token usage returned by provider can be priced; missing usage is **UNKNOWN**, not free. Count Cloudflare Clef requests but do not invent Neurons costs. Source Gemini Standard text prices are snapshotted at invocation.

## Technical integration

- Persist per-attempt metadata via core/ai_usage.py (no prompts, replies, members, channel IDs or secrets).
- Add read-only GET /api/admin/ai-usage?days=7|30 guarded by @login_required. Return bounded, aggregated totals, daily trend and per model/feature breakdown (not individual chat data). Empty results, Turso unavailable and unknown prices must be separate states.
- Add a new **AI Usage** tab in web/templates/dashboard.html, preserving all existing classic tabs, URL navigation and the integrated Feedback iframe.
- Load data **on demand when the tab opens** or user clicks refresh, never within the global 10-second dashboard poll. Render Chart.js trend and model/feature table using safe DOM/textContent.
- Add input fields for **manual remaining** Prepay VND, optional **verified eligible** GCP credits VND, and estimated VND/USD. Values are calculator-only in the browser, not claims of live account balances. No automatic charges/top-up or Google Billing scopes.
- 30-day forecast: observed USD cost divided by actual coverage days (minimum 1, maximum chosen 7/30 window), times 30; low-confidence if less than 3 observed days. Unknown priced requests make forecast a **partial estimate**, never an authoritative bill.
- Actual GCP credits eligibility and debit-card deductions may only be confirmed in Cloud Billing, not inferred from a Google AI Studio rate-limit chart.
- No role ping, unsolicited message, proactive report or notifications in chat channels.

## Delivery stages

| Goal | Work | Status |
| --- | --- | --- |
| T31.0 | Gemini usage metadata ledger, pricing snapshots and owner Discord /ai_cost | CODE_READY, live pending |
| T31.1 | Cloudflare Clef unpriced request counters | CODE_READY, live pending |
| T31.2 | **Historical dashboard AI Usage tab, read-only API, chart, breakdown, runway and tests** | IN PROGRESS |
| T31.3 | Cloud Billing reconciliation for real charges/credit eligibility; explicit authorized read-only access if desired | PLANNED |
| T31.4 | Optional private owner alerts, retention and spend ceilings, never auto top-up | PLANNED |
| T31.5 | Cost/quality-aware model router after 1–2 weeks of evidence | PLANNED |
| T31.6 | Dungeon Misfits DM/intent costs per run, using the central ledger | PLANNED |

## Acceptance tests

- Unauthenticated API 401, no leaking globally aggregated spend or raw user input.
- Only days 7/30 supported, invalid inputs 400; Turso errors show an error state instead of a fake 0 bill.
- No history backfill; zero-data screen is honest.
- Missing prices, Cloudflare Clef, failed or timed-out calls remain visible and marked unknown.
- Existing Feedback/tab URL navigation/other controls unchanged; dashboard lazy-load tested.
- Chart.js mobile layout, 7/30 selector, no HTML injection, JS syntax and relevant CI regressions.
- PR/code/CI/deploy/live-accepted statuses tracked independently.

## Next-session handoff

Read AGENTS.md and docs/ASUMI_HISTORICAL_DASHBOARD_DECISION.md. Implement changes within existing historic dashboard only. Validate production Turso writes are durable, owner/admin auth is preserved, and use code-owned limits in core/constants.py. No automatic merge, deployment or credit-eligibility claims without evidence.
