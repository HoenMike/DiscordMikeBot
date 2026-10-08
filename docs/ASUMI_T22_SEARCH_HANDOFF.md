# T22 — Intelligent Search Handoff

**Status:** T22.1 + T22.2 IMPLEMENTED (BOTH DISABLED BY DEFAULT / LIVE VERIFY PENDING); T22.3 IMPLEMENTED / T22.4 NEXT
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
3. T22.2 implemented: official bot-token Discord History Search with author/time/topic, requester ACL and Jump links. Await live bot-authorization/permissions test.
4. T22.3 implemented: gated Clef web/history/archive selection, one-tool bounded retrieval and optional public Brave evidence synthesis. Full chained multi-source reasoning is deferred to T22.4.
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

## T22.2 implementation handoff — 2026-10-08

- Release target: Asumi 3.6.0.
- Added `features/assistant/providers/discord_history.py`, history intent/router bridge, permission-safe Discord Jump links, env flag, Help, tests and CI.
- Examples: `@Asumi tìm xem đầu năm @Theo có nhắn gì về mua xe không?`, `@Asumi tìm tin nhắn về laptop`.
- Bot searches only current guild; uses bot token only; **no new API token required**.
- Env `ASUMI_DISCORD_HISTORY_ENABLED=false` by default. Set true on Render for smoke test, then check Message Content intent, member channel access, 202 indexing/429 rate-limit, matching original message and Jump link.
- Bot caches no historical message bodies and never sends them to Brave. Unknown/uncached channels, private threads and inaccessible channels are excluded.
- Regression: `tests/test_assistant_history.py` under `.github/workflows/asumi-search.yml`; verify workflow actually completes.
- **Next:** T22.3 Clef choice between Web / Discord History / Archive, limited evidence planning and natural Q&A; no automatic source selection shipped in T22.1/2.

## T22.2 CI acceptance (2026-10-08)

- PR: **#35** — `feat: Asumi 3.6.0 T22.2 Discord History Search`.
- GitHub Actions `Asumi Search Regression` completed successfully; 102 tests passed across Brave (12), History (16), Conversational Core (50), Archive (12), Semantic (12).
- Historical search uses a max 12-second overall deadline including live verification. No long passive crawling.
- Added regression for ambiguous `tìm xem` phrasing and fixed existing Vietnamese `ghi chú:` Archive note parsing found in full-suite CI.
- **Live Discord API acceptance remains pending**: needs explicit enable `ASUMI_DISCORD_HISTORY_ENABLED=true` and same-server smoke test, including a private-channel user ACL check.
- Brave live activation also awaits `BRAVE_SEARCH_API_KEY` and `ASUMI_WEB_SEARCH_ENABLED=true`.
- Next technical goal is **T22.3** (Clef chooses Web / History / Archive and synthesizes evidence with citations); T22.4 covers follow-up/ranking/cache/dashboard polish.

## T22.3 implementation handoff — 2026-10-08

- Release target: Asumi 3.7.0, feature default OFF (`ASUMI_AUTO_SEARCH_ENABLED=false`).
- Typed choice criteria added to Cloudflare Clef for Web / Discord History / Archive; Python requires matching provider enabled + source safety + confidence before tool execution.
- Brave public synthesis uses only fresh Brave snippets/URLs, no private server context. When Gemini fails, return raw source links without fabricated answer.
- Same conversation follow-up does not re-run search automatically; explicit web/history/Archive requests still override session routing. No multi-tool recursive agent; T22.4 remains.
- Enabling live requires Brave token/flag for Web and explicit Discord History flag after ACL/bot-token API smoke test; then turn on auto flag.
- New tests `tests/test_assistant_source_routing.py` under CI; verify CI green and real-provider behavior before production acceptance.
- **Next T22.4:** richer follow-up/retrieval context, source ranking, Dashboard search-specific observability and cache improvements.

## T22.3 CI verification — 2026-10-08

- PR **#36** — `feat: Asumi 3.7 T22.3 gated Clef source routing`.
- GitHub Actions `Asumi Search Regression` run 37716844816 passed **117 tests**: Brave (12), History (16), new T22.3 source routing (15), conversational core (50), Archive (12), semantic adapter (12).
- Automatic search is default OFF; Brave and Discord History are separately default OFF. Live source selection and source-derived Gemini explanation still require provider keys, flags and real Discord smoke testing.
- T22.4 remains planned: improved multi-source evidence follow-up and ranking/cache/observability; do not treat T22.3 as an unrestricted autonomous agent.
