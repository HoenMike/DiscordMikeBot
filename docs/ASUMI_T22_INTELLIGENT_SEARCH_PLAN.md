# T22 — Asumi Intelligent Search / Brave + Discord History

**Status:** T22.1 BRAVE WEB SEARCH IMPLEMENTED (OFF BY DEFAULT; LIVE KEY PENDING) / T22.2 IMPLEMENTED / T22.3 IMPLEMENTED / T22.4 PLANNED
**Date:** 2026-10-08
**Owner decision:** Use **Brave Search API** for external web search, and add **on-demand Discord History Search** to recover old messages that were never saved into Archive.
**Current baseline:** Asumi 3.4.1 on main; T21 production acceptance remains pending.
**Cost contract:** free-credit / no unexpected charge; no paid fallback, explicit circuit-breaker and request caps.

## 1. Desired user experience

### Historical Discord recall (critical motivating case)

User: @Asumi tìm xem đầu năm @Theo có nhắn gì về chuyện mua xe không?

Expected:
- Asumi extracts author user ID, topic (buying/changing a vehicle), approximate time window (beginning of the year), and current guild scope.
- It searches **real historical messages**, not just recent context and not only explicitly saved Archive items.
- It returns the best **1–5 original Discord messages**, each with a short faithful excerpt, author, date/channel, and a **Jump to Message** deep link for users to scroll to the source.
- If several candidates exist, it can say which one best matches and offer narrower filters/follow-up.
- Never invent quotes or claim a message exists unless the Discord API actually returned it.
- Do not require that the user remember exact keywords or have manually saved the message beforehand.

Other scenarios:
- @Asumi cái tin Khai nói định đổi xe hồi tháng 2 đâu rồi?
- @Asumi tìm đoạn nói về mua xe rồi mở lại giúp tôi.
- @Asumi có thông báo mới nào về vụ này ngoài web không? (Brave search)
- @Asumi tìm đoạn hồi đó Theo nhắc mua xe rồi kiểm tra giá mẫu đó bây giờ. (Discord History + Brave)

## 2. Keep three retrieval sources distinct

| Source | Purpose | Canonical data | Trigger |
| --- | --- | --- | --- |
| Discord History Search | Search past messages (including never-saved messages) | Live Discord API | Explicit user request or narrowly scoped follow-up |
| Archive Search | Retrieve explicitly saved content and personal notes | Existing Turso/SQLite Archive; optional Vectorize derived index | Explicit user-owned Archive search |
| Brave Web Search | Recent/public external information | Brave Search API results with source URLs | Question needs public/current external verification |

Brave must **not** be used to search private Discord messages. Vectorize Archive must **not** be treated as an index of all server chat. Do not silently activate passive archival.

## 3. Key discovery — official Discord native search

Discord API documentation (checked 2026-10-08): GET /guilds/{guild.id}/messages/search supports content, author_id, channel_id, message snowflake min_id/max_id, relevance/timestamp sorting, and returns matching messages. A search query may return HTTP 202 while Discord's historical indexing is not ready.

Official source: https://github.com/discord/discord-api-docs/blob/main/developers/resources/message.mdx#search-guild-messages

**Start with on-demand native guild search; do NOT first backfill/index the entire server.** Verify bot-token compatibility and production permissions on the actual Asumi server before treating this as accepted. discord.py may need a narrowly isolated REST adapter if its public library does not expose the endpoint.

Implementation expectations:
- Resolve @user mention to **Discord author ID**, never search display name as if it were a stable ID.
- Interpret relative time constraints against the current date (e.g. 'đầu năm' could initially scope Jan–Mar of the current year); show the interpreted range and allow narrowing/expanding.
- Search topic with a small bounded set of Vietnamese lexical variants (mua xe, đổi xe, tậu xe, tên xe...), plus author and time scope; dedupe by message ID and rerank results.
- Use Discord snowflake time boundaries for min_id/max_id where appropriate; validate and document inclusive/exclusive behavior in tests.
- Enforce the **intersection** of bot-readable channels and requesting member's channel permissions before exposing any result; never leak bot-visible private channel content to a requester who cannot see it.
- Search stays within the requester's current guild unless an explicit future feature changes the scope with separate access rules.
- Treat deleted/inaccessible messages as unavailable; verify source visibility before returning preview/link as needed.
- Handle 202 not-ready, 429 rate limits, empty/partial results and 403/permission errors without fabricated answers; follow retry_after with a strict retry/time budget.
- Explicitly bound search fan-out, API calls, timeout, results and per-user cooldown. Do not crawl unbounded channel history as fallback.
- Short TTL caching of results/IDs is optional; **no persistent mirroring of chat contents by default**.
- Avoid triggering Discord mentions from quoted messages by suppressing allowed_mentions.

Future enhancement (not part of MVP): opt-in per-guild/channel indexing/backfill only when native search materially underperforms. Requires clear admin consent, exclude-list, retention/deletion/redaction policy, backfill progress and opt-out; keep it distinct from user-owned Archive.

## 4. Brave external search contract

Use Brave **Search** (not Brave Answers) as the external retrieval provider. Official endpoints: https://api.search.brave.com/res/v1/web/search with X-Subscription-Token. Use bounded result counts, source attribution, freshness/date cues and explicit cache TTL; Gemini synthesizes only retrieved evidence for claims about current news.

Official docs: https://api-dashboard.search.brave.com/api-reference/web/search/get
Pricing reference (must recheck when enabling): https://api-dashboard.search.brave.com/documentation/pricing

Config proposed (NOT active yet):

    BRAVE_SEARCH_API_KEY=
    ASUMI_WEB_SEARCH_ENABLED=false
    ASUMI_WEB_SEARCH_MAX_RESULTS=5
    ASUMI_WEB_SEARCH_TIMEOUT_SECONDS=5
    ASUMI_WEB_SEARCH_MONTHLY_REQUEST_CAP=500

Guard policy: hard application-level cap with usage meter in Dashboard; HTTP 429/402/permission failures should fail closed; never auto-switch to paid Brave Answers or another provider. The $5/month Brave promotional free credit is **not** a guarantee that all overages are intrinsically blocked by the provider; enforce a conservative local cap and validate provider billing controls.

## 5. Router / tool execution

User query -> local deterministic command precedence -> Context Builder -> typed decision/planner (Clef only when useful) -> approved tools -> evidence-based response.

Typed tool targets:
- discord_history.search {guild_id, author_id?, channel_ids?, start_time?, end_time?, keywords, max_results}
- archive.search {owner_user_id, query}
- web.search {query, freshness?, max_results}
- chat.generate {context, retrieved_sources}

Clef chooses **which evidence source(s) are needed**, not raw API credentials, unrestricted data access, or the final claim. Tool execution is checked by Python code. Permit a bounded multi-source plan (e.g. history -> web -> synthesis), not an open-ended recursive agent loop.

Do not web-search every chat greeting or use Brave for questions answerable using provided reply/image/context alone. No source found -> say not found and invite user to widen author/date/topic scope. Route decisions, provider success/fallback and latency go into existing Dashboard telemetry, without retaining private query text or message bodies.

## 6. Roadmap / acceptance

| Goal | Deliverable | Status |
| --- | --- | --- |
| T22.0 | Decision, access, privacy and routing contract | DOCUMENTED |
| T22.1 | Brave Web Search adapter, budget/keys, citation UX | IMPLEMENTED; LIVE KEY VERIFY PENDING |
| T22.2 | Discord native History Search + author/date filters + Jump links | IMPLEMENTED; LIVE BOT API VERIFY PENDING |
| T22.3 | Clef source selection / controlled one-tool retrieval | IMPLEMENTED; LIVE VERIFY PENDING |
| T22.4 | Ranking, follow-up, caching, dashboard, edge-case regression | NOT STARTED |

Acceptance — live server:
1. Find an old 'buying a car' message by @author + early-year time hint, even though it was never saved in Archive.
2. Return a working Discord Jump link, correct author/time/channel and faithful snippet; no phantom result.
3. A requester without access to the original private channel receives **no snippet or citation**.
4. Missing author, approximate date, synonyms, edited/deleted messages, 202 indexing, 429, timeout, no matches and cross-guild attempts are covered.
5. A news/current-info question invokes Brave and returns source links; a Discord-history question never sends private Discord text to Brave.
6. No passive full-server archive and no unbounded API crawling; quota/timeout fail safely.
7. Do not mark code done as production accepted without automated tests and real Discord permission checks.

## 7. Handoff / changes rule

Each T22 implementation PR must update this file, docs/ASUMI_T22_SEARCH_HANDOFF.md, regression tests, and release README/help when user-facing behavior ships. Planning-only PR must not bump version or claim live functionality.

### T22.1 implementation note (2026-10-08)

- Endpoint uses Brave Search API GET /res/v1/web/search, **not** Brave Answers.
- Deterministic explicit trigger only (`@Asumi tìm trên web ...`); Clef auto-search remains T22.3.
- Provider key/feature flag off by default. The web query is strictly the user's explicit search phrase; no reply, private Discord channel history, Archive or image context is sent to Brave.
- Reject Discord message URLs, @user/#channel mentions and @everyone/@here in the outbound query.
- Durable UTC calendar-month quota through `asumi_brave_usage` in existing Turso/SQLite adapter; cap default 500, hard maximum 900. Reserve quota before HTTP, including failure. Fail closed when durable Turso is configured but unavailable.
- Cache for 180s in RAM (public search only), 15s per-user cooldown, 5s HTTP timeout, <=5 hits default, no auto retries/paid fallback.
- Discord result includes real Brave source URL and snippets, no AI-generated unsupported assertions; full synthesized cited replies are a future goal.
- Dashboard assistant metadata records web provider/status/latency/cache/remaining count, **not private search terms or result bodies**.
- User must later configure `BRAVE_SEARCH_API_KEY` and `ASUMI_WEB_SEARCH_ENABLED=true`; configure Brave dashboard spend cap/prepay and disable auto reload too.
- Unit tests added in `tests/test_assistant_brave.py`; live acceptance and provider key validation still pending.

### T22.2 implementation note (2026-10-08)

- On-demand `discord_history.search` deterministic route for phrases such as `@Asumi tìm xem đầu năm @Theo có nhắn gì về mua xe không?` or `@Asumi tìm tin nhắn về laptop`.
- Uses official bot-token REST GET /guilds/{id}/messages/search (no user token/self-bot); **disabled by default pending production Discord permission validation**.
- Filters @mentioned author by stable ID (one user at a time), early-year Jan–Mar, specific numeric month/year, plus bounded topic synonyms. Up to three API requests and five results; per-user cooldown 20s.
- Returns verbatim excerpts, original author/date and actual Discord Jump to Message deep links. Never invents hits or archives message content.
- On each candidate, verify requester and bot `VIEW_CHANNEL` + `READ_MESSAGE_HISTORY` and parent visibility. Unknown/uncached channels and private threads fail closed.
- Supports 202 indexing, 429, permission errors, empty results, timeouts and safe non-mention output.
- Logs only status, result/API count, latency, number of permission-filtered hits — no raw message bodies.
- Regression tests and CI were added. Live acceptance is **NOT DONE**; actual guild search/bot token support must be verified after deploy.

### T22.3 implementation note (2026-10-08)

- Clef classifies chat/tarot/summarize/help and typed `web_search`, `discord_history`, `archive_search`. New feature `ASUMI_AUTO_SEARCH_ENABLED=false` by default.
- Python maps tool only when corresponding provider is enabled, source-specific safety checks pass, and Clef confidence is adequate. No open-ended agent loop or automatic multi-tool orchestration yet (reserved for T22.4).
- To avoid private Discord data being sent to Brave, auto web requires a clear external/current-public info cue and rejects Discord mentions, message links, private/replied context referents. Brave adapter separately rejects outbound private references.
- If Clef chooses Brave, a bounded Gemini synthesis step uses **public Brave titles/excerpts and URLs only**, never Discord private context. Sources remain visible; synthesis error -> raw Brave sources.
- Archive source selection remains scoped to requester-owned records; History Search enforces requester and bot effective read permissions.
- Existing live session replies do not automatically open another tool; explicit actions override continuation.
- CI and regression coverage extended with T22.3 safety, provider gating, public synthesis and fallback tests.
