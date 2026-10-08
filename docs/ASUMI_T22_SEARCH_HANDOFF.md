# T22 — Intelligent Search Handoff

**Status:** T22.1 IMPLEMENTED / BRAVE KEY & LIVE VERIFY PENDING; T22.2 NEXT
**Recorded:** 2026-10-08
**Primary spec:** docs/ASUMI_T22_INTELLIGENT_SEARCH_PLAN.md
**Baseline:** Asumi 3.4.1 (`main`), T21 final production acceptance remains outstanding.

## User-approved decisions

- **Brave Search API** is selected for public web search (not Brave Answers).
- Add **Discord History Search** that can recover historical messages **without prior Archive Save**.
- Core example: `@Asumi tìm xem đầu năm @Theo có nhắn gì về mua xe vậy?`
- Expected UX: find the actual original message, display original author/date/channel/faithful snippet and a usable **Jump to Message** link so the group can scroll to it.
- Keep existing user-owned Archive separate from guild history search.
- Do not index the entire server passively or store long-term personal chat without explicit product/admin decision.

## Research / implementation caveats

- Current official Discord API documents `GET /guilds/{guild.id}/messages/search` with `author_id`, `content`, `channel_id`, `min_id`/`max_id`, and result sorting. Test bot authorization and permission behavior in production before relying on it as supported by current discord.py.
- Discord may return 202 while historical indexing completes; account for partial results and rate limits.
- Critical permission boundary: filter results by requesting member visibility, not merely the bot's channel permissions.
- A user's name/mention resolves to stable author ID; 'đầu năm' requires explicit interpreted date range (e.g. Jan–Mar current year), widen on request.
- Do not send private Discord text to Brave.
- Source URLs must point at actual messages. No invented quotes, titles, or jump links.

## Plan / next actions

1. Finish T21.9 production regression (including Vectorize enable test) independently; T22 plan need not wait to be documented.
2. T22.1 implemented on a focused PR: explicit Brave Search, durable quota, original result links, cooldown/cache and dashboard tool telemetry. Await manual API key plus live verification. Never paste a key into chat.
3. T22.2 implement on-demand native Discord History Search with author/time/topic filters, permission-safe Jump links, and 'not indexed yet' states.
4. T22.3 add typed Clef web/history/archive source selection and bounded multi-source execution.
5. T22.4 follow-up, ranking, cache/TTL, dashboard telemetry and edge-case regression.

## Agent safety rules

- Never use a personal user token or self-bot for Discord search; bot credential only.
- No blind full-server history crawl. Only bounded, explicit on-demand search initially.
- Any optional future persistent index needs separate admin consent, per-channel scope, retention/delete policy, and data protection plan.
- Do not expose results from channels the *requesting member* cannot view; verify each candidate at result time.
- Keep Brave usage within explicit no-overage budgets, no paid automatic fallback.
- Planning-only state: do not bump version, merge feature flags or claim Brave/history search works today.

## First implementation files to inspect

- features/assistant/router.py, features/assistant/providers/cloudflare.py
- features/assistant/context.py, features/assistant/tools.py, features/assistant/cog.py
- core/db.py, core/activity_logger.py, web/templates/dashboard.html
- docs/ASUMI_INTELLIGENCE_HANDOFF.md for unresolved T21 regressions

## Update protocol

Record each T22 sub-goal as NOT STARTED / IMPLEMENTED / LIVE VERIFIED with PR, tests executed and exact continuation step. Keep this handoff as the resumption point.

## T22.1 implementation handoff — 2026-10-08

- Release target: Asumi 3.5.0 (feature flag OFF by default).
- Files: `features/assistant/providers/brave.py`, `features/assistant/router.py`, `features/assistant/tools.py`, `features/assistant/cog.py`, `.env.example`, `tests/test_assistant_brave.py`.
- Explicit UX: `@Asumi tìm trên web <public query>`; displays real URLs/snippets from Brave. Auto source routing is **not implemented yet**.
- Install env in Render: `BRAVE_SEARCH_API_KEY` (secret), `ASUMI_WEB_SEARCH_ENABLED=true` only after Brave dashboard prepay/usage limits are confirmed. Default monthly cap 500; max hardcoded 900.
- Live tests: no-key disabled, valid key search, 401/429, quota, restart persistence, cache, permission-safe no-private-Discord forwarding, Dashboard metrics.
- Next goal: **T22.2** Discord historical search using native guild Search with requester-side ACL and original Jump links. Do not rely on Brave to search old Discord messages.
