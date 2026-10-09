# AGENTS.md — DiscordMikeBot Working Context

This repository is expected to be used across multiple AI/agent sessions. Read this file before making non-trivial changes.

## General workflow

1. Inspect current `main`, `core/version.py`, open PRs and recent commits before assuming repository state.
2. Read the relevant feature documentation before changing a subsystem.
3. Treat runtime code as the current truth when docs are stale, then update the docs in the same change.
4. Prefer focused branches/PRs over large mixed changes.
5. Preserve existing user-facing behavior unless the active task intentionally changes it.
6. Add or update regression tests for bug fixes and behavior changes.
7. Do not bump the repository version for planning/docs-only changes. Bump version/changelog when a release behavior change warrants it.
8. Avoid silently deleting compatibility aliases, stored data, commands or configuration.

## Asumi 3.13.2 — Tarot mention question preservation (2026-10-09)

- A mention such as @Asumi bốc cho quẻ tarot xem mai nên mặc áo màu gì đi nhậu must preserve the actual question through router → tool bridge → TarotCog.
- Explicit bốc/rút/bói + meaningful question runs the existing Tarot draw command with a recommended spread; a bare Tarot mention never auto-draws. General Tarot questions launch the prefilled question-first view.
- Do not use "hôm nay" anywhere in a sentence as a Daily classifier: "tarot hôm nay nên mặc gì" is a specific question.
- Retain Tarot cooldowns, ownership, session persistence and reading safeguards; add router, command bridge and recommendation regressions.

## T25.1b — Tarot read-only Components V2 (2026-10-09)

- Scoped to the one-card `📖 Đọc đầy đủ` callback; only its *ephemeral reply* uses LayoutView, never mutate the original Tarot V1 reveal/edit message into V2.
- For text longer than 3900 characters, send the complete `tarot_reading.txt` plus a native File component; ensure source reading is not redrawn or regenerated.
- Only retry with a legacy embed on an explicit Discord HTTP 400 rejection; never duplicate an uncertain 5xx or timeout.
- Source toggle: `ASUMI_TAROT_READING_NATIVE_V2_ENABLED` in core/constants.py. Owner permission policy remains the same: full reading readable by channel viewers, followup/why/clarifier author-only.
- T25.1c interactive pagination and live mobile/desktop screenshots are still outstanding.

## T25.1a — Native Components V2 Pilot (2026-10-09)

- Discord library upgraded to discord.py 2.7.1. Native V2 messages use `discord.ui.LayoutView` and **cannot include content or embed fields alongside the view**.
- The only production V2 entry point so far is non-fuel public Search replies, using code-owned `build_search_layout`. Preserve bold answer / [1] [2] compact citations, privacy, quota, no raw result dump. HTTP 400 can fall back to legacy; never retry uncertain timeouts or 5xx.
- Tarot/Feedback/Weather/Fuel/social previews remain on legacy views/embeds until separately compatibility-tested. Do not treat T25.1 as fully finished; see docs/ASUMI_T25_GENERATIVE_UI_ADOPTION.md.
- Roll back UI pilot by editing `ASUMI_SEARCH_NATIVE_V2_ENABLED` in core/constants.py and redeploy. Do not move non-secret flags to Render env.

## T26 Deploy Recovery Queue (2026-10-09)

- Asumi Discord Gateway and Flask share the same Render process; Gateway events can be lost during deploy. Do not claim Discord buffers them.
- Asumi 3.12.0 adds Turso-backed ID-only queue for incoming conversation mentions and bounded history catch-up when READY; read docs/ASUMI_DEPLOY_RECOVERY.md first.
- Critical safety: do not auto-replay mutating tools, Tarot draws, slash/prefix commands or Feedback; check permissions, old bot replies, atomic claims and expiring leases.
- Do not promise a truly zero-downtime bot. Without Turso or if a mention is older than the short scan window, recovery is unavailable.
- Keep existing historical Admin Dashboard and Tarot/Search/Feedback behavior. Live Render verification remains mandatory.

## T25 Search/Feedback follow-up and OpenUI direction (2026-10-09)

- Owner feedback from live Discord: self-chronological History Search (`của t`) previously required a user mention; public CKTG schedule questions fell through to chat; multiple feedback reports were blocked by a pending draft.
- Patch branch `fix/asumi-20261009-search-feedback-ux` implements self-target History, named tournament schedule Brave routing and replace/keep/cancel draft UX. Regression tests and live provider acceptance remain essential.
- Read `docs/ASUMI_T25_GENERATIVE_UI_ADOPTION.md`. **Do not treat OpenUI or Components V2 as deployed.** The repo pins `discord.py==2.4.0`; the V2 upgrade must be a separate compatibility-tested goal.
- Preserve the original historical tabbed Admin Dashboard and its embedded Feedback tab. Do not create another sidebar/dashboard shell.

## T25 Asumi 3.11.0 rich chat UI + answer-first Search

- Owner specifically wants rich generated messages **inside Discord chat**, not a new Admin Dashboard. The practical Tarot single-card pilot uses Pillow-rendered images + existing Discord buttons; do not claim actual OpenUI/React runs in messages.
- In `feat/asumi-t25-tarot-rich-search-answers`, Tarot Daily/Single/Yes-No have a compact inline Insight card and **Đọc đầy đủ** button for message viewers, plus a durable text attachment; Followup, Why and Clarifier remain author-only. Preserve legacy multi-card flip flows, Tarot V2 result schemas, draw semantics and secure interactions.
- Brave is a background retrieval component. Every non-fuel public search route must attempt answer-first synthesis with short citations, never raw snippets as default UX; lack of evidence should be admitted, not filled in.
- Read `docs/ASUMI_T25_GENERATIVE_UI_ADOPTION.md` and validate Search + Tarot regressions before merge. Keep old dashboard, report/ticket, R2/Turso and embed proxy fallbacks unchanged.
- Post-deploy smoke is still required before calling the design live-accepted.

## Search response style acceptance (Asumi 3.11.1)

- User-approved answer-first Search layout: bold the short direct takeaway, leave supporting detail readable, keep references at the bottom as clickable **[1] · [2]** only.
- Do not show a source-title list, domain badges, `Kiểm chứng thông tin` heading or provider snippets in ordinary Search embeds. The existing underlying sources must remain accessible from the numeric links.
- Search routing, privacy, quotas, evidence verification and specific factual provider views remain unchanged. Add regression coverage for the display schema.

## Active Tarot initiative

There is an active planned **Asumi Tarot 2.0** initiative.

Before any Tarot 2.0 work, read:

1. `docs/TAROT_V2_MASTER_PLAN.md`
2. `docs/TAROT_V2_HANDOFF.md`
3. `docs/TAROT_V2_PROMPT_SPEC.md` when touching AI/prompt/reading schema
4. `docs/TAROT_V2_RENDERER_SPEC.md` when touching renderer/presentation
5. `docs/TAROT_SYSTEM.md`
6. current `features/tarot/` code

### Important Tarot status

Tarot 2.0 / 2.1 roadmap T20.1–T20.9 is implemented and now in maintenance mode.

- T20.0 — baseline/docs: complete.
- T20.1 — Prompt & Reading Engine 2.0: complete.
- T20.2 — Question-first Launcher: complete.
- T20.3 — Reading Session UX: complete.
- T20.4 — Renderer 2.0: complete.
- T20.5 — Clarifier: complete.
- **Tarot 2.0 release boundary is complete in Asumi 2.9.0.**
- **T20.6 — Multi-turn Reading Session: complete.**
- **T20.7 — Smart Custom Spread: complete.**
- **T20.8 — Tarot Journey: complete.**
- **T20.9 — Recap & Polish: complete.**
- **Asumi 3.0.0 is the current bot release.** It keeps the completed Tarot 2.1 runtime and adds question-first / one-tap Daily / one-click recommendation launcher UX. No next Tarot milestone is defined until the user requests a new roadmap.

### Tarot milestone IDs

```text
T20.0  Baseline / docs / contract lock
T20.1  Prompt & Reading Engine 2.0
T20.2  Question-first Launcher
T20.3  Reading Session UX
T20.4  Renderer 2.0
T20.5  Clarifier — COMPLETE
T20.6  Multi-turn Reading Session — COMPLETE
T20.7  Smart Custom Spread — COMPLETE
T20.8  Tarot Journey — COMPLETE
T20.9  Recap & Polish — COMPLETE
```

Tarot 2.0 release target T20.1–T20.5 is complete in v2.9.0; T20.6–T20.9 completed in v2.10.0 / Tarot 2.1. Asumi 3.0.0 is a repository-wide major release layered on that shipped behavior; treat all milestone contracts as stable unless the user explicitly asks to change them.

### Tarot continuity rule

If you start, complete, reject or materially change a Tarot milestone, update `docs/TAROT_V2_HANDOFF.md` in the same PR so a future session can resume without the original conversation.


## Active T21 — Asumi Intelligence / Conversational Core

T21 is the planned natural-language assistant layer for Asumi. The primary UX is explicit `@Asumi ...` conversation plus reply continuation; existing slash/prefix/mention commands remain deterministic and take precedence.

Before any T21 work, read:

1. `docs/ASUMI_INTELLIGENCE_MASTER_PLAN.md`
2. `docs/ASUMI_INTELLIGENCE_HANDOFF.md`
3. current `bot_instance.py`, `core/ai.py`, and the affected `features/` modules

### T21 status

- **T21.0 — Baseline + contracts: complete (docs).**
- **Asumi 3.1 Conversational Core: implemented/released in 3.1.0.**
- T21.1, T21.2 and T21.4 are complete; T21.3 Clef adapter is implemented but requires Cloudflare credentials for live verification.
- **Asumi 3.2 Context + Lens is implemented; remaining reply/link/image edge-case checks roll into the final regression matrix.** Image input is required and audio/voice transcription remains out of scope.
- **Asumi 3.3 Archive Core is shipped; 3.3.1 optional semantic retrieval is implemented behind `CF_ARCHIVE_SEMANTIC_ENABLED` and requires Vectorize credential/live validation.** Canonical Archive records use the existing core.db Turso/SQLite adapter; Vectorize is derived state only and R2 remains optional.
- **Asumi 3.4 Intelligence Polish is implemented; final production regression/live semantic validation remains.** Dashboard telemetry exposes Clef/Archive/Vectorize fallback state without storing assistant prompt/response bodies.
- Cloudflare/AI work is **free-only** and must fail closed rather than silently create paid usage.
- Do not make Asumi respond to ordinary unmentioned server chat.
- Clef-flash is a decision/router layer, not the primary prose model.
- Persistent Archive/memory is explicit opt-in only. Never add passive full-server logging. Search/delete must remain owner-scoped.

### T21 continuity rule

If you start, complete, reject or materially change a T21 milestone, update `docs/ASUMI_INTELLIGENCE_HANDOFF.md` in the same PR. Update the master plan when the product/architecture contract changes.


## Planned next initiative — T22 Intelligent Search

**Status: T22.1 BRAVE + T22.2 HISTORY + T22.3 CLEF IMPLEMENTED; T22.4a CHRONOLOGICAL HISTORY IMPLEMENTED (LIVE VERIFY PENDING); T22.4b IMPLEMENTED (LIVE VERIFY PENDING); T22.5 SUPERVISED MULTI-SOURCE IMPLEMENTED (LIVE VERIFY PENDING). All search providers require their existing credentials and gates.** Before any T22 work read:

1. `docs/ASUMI_T22_INTELLIGENT_SEARCH_PLAN.md`
2. `docs/ASUMI_T22_SEARCH_HANDOFF.md`
3. `docs/ASUMI_INTELLIGENCE_HANDOFF.md` for unfinished T21 live tests.

Owner selected Brave Search API for external web retrieval. **Separate goal:** native on-demand Discord guild history search to find actual old messages by author/time/topic, even if they were never explicitly saved in Archive. Return original Discord Jump to Message URLs.

Non-negotiable: no passive entire-guild indexing/backfill, no personal user tokens, no leaks from channels the requester cannot read, no private Discord text sent to Brave, and no unbounded provider usage. Start with official bot-token guild search endpoint and permission validation; use optional index only if justified by real need and explicit admin consent.

T22.4a supports oldest/latest messages by one @mentioned author (no topic required) with chronological search and conservative partial-result wording. T22.4b adds safe explicit web follow-up, source-grounded chat, channel metadata and privacy-safe Dashboard search tracing; T22.5 now implements **at most one History search then one public lookup only if the user literally provides a standalone public web query**. Inferred/private-history-to-public-search transitions remain gated; never auto-export Discord text, and never assume matched history and public web refer to the same entity. Brave adapter is implemented but requires external API key, explicit enable and live acceptance. Discord History Search and Clef auto-routing implemented but await bot-token/ACL and Brave key live validation; feature flags default OFF; code does not equal live-verified capability. Every T22 PR updates its plan/handoff, tests, and README/help only when behavior ships.

## Feature documentation

- Asumi Intelligence master plan: `docs/ASUMI_INTELLIGENCE_MASTER_PLAN.md`
- Asumi Intelligence handoff: `docs/ASUMI_INTELLIGENCE_HANDOFF.md`
- T22 Intelligent Search plan (Brave + Discord history): `docs/ASUMI_T22_INTELLIGENT_SEARCH_PLAN.md`
- T22 Search handoff: `docs/ASUMI_T22_SEARCH_HANDOFF.md`
- Social embed pipeline: `docs/EMBED_PIPELINE.md`
- Current Tarot system: `docs/TAROT_SYSTEM.md`
- Tarot 2.0 master plan: `docs/TAROT_V2_MASTER_PLAN.md`
- Tarot 2.0 handoff: `docs/TAROT_V2_HANDOFF.md`
- Tarot 2.0 prompt spec: `docs/TAROT_V2_PROMPT_SPEC.md`
- Tarot 2.0 renderer spec: `docs/TAROT_V2_RENDERER_SPEC.md`


## Asumi configuration authority — 3.7.3

**Never add non-secret Asumi feature flags or quota/model/timing settings to Render env.** The source of truth is `core/constants.py`. Environment is for external API keys/tokens and deployment-specific service/account IDs. Brave is credential-gated with conservative durable cloud quota (500/month); deterministic clearly-public gasoline/current-price questions may use it even if Clef is unavailable. Discord History remains user-requested, channel-ACL-safe; do not claim live success before Discord bot-token tests. Vectorize semantic remains code-OFF until accepted. Whenever policy changes, update tests and handoff.

## Asumi Brave Search UX — 3.7.4

A user-facing Brave result must be an **answer-first, bounded Discord embed**, not a raw wall of links/snippets. Use `features/assistant/search_presenter.py` to show at most three original clickable sources; sanitize HTML and mentions and omit unresolved numeric citation markers. For volatile prices, avoid unsupported exact values; dates/snippets are not ground truth. Cost remains one bounded Brave request per lookup, with durable quota enforcement. Preferred source domains are relevance hints, not freshness guarantees. Read `docs/ASUMI_T22_SEARCH_HANDOFF.md` before touching Search.


## Source verification rule — Asumi 3.7.5

A Brave result is only an excerpt and URL; never treat it as a verified full price table. For Vietnam public fuel prices, `features/assistant/providers/pvoil_prices.py` reads two fixed official PVOIL HTTPS pages, checks dated product-price pairs, and emits figures only when source extraction succeeds. This pilot does **not** authorize arbitrary URL fetching. Failure must preserve honest Brave fallback, no guessed prices. No extra chargeable Brave requests, no private Discord history in public searches. Test page accessibility on Render; CI fixtures alone do not establish live acceptance.


## Fact-first retrieval policy — Asumi 3.7.6

When the user asks for a value (price, weather, date, count), prioritize **structured factual retrieval** over web snippets and answer with value/unit/time first. Weather uses Open-Meteo (separate from AQI). Fuel calls PVOIL prior to Brave; do not spend Brave quota on a valid first-party answer. General public snippets can be enriched from two bounded, HTTPS allowlisted pages; NEVER turn this into an arbitrary private Discord URL fetch, allow redirects, or scrape privileged chat. Keep runtime toggles/limits in `core/constants.py`. Every fact retrieval change needs regression tests and live acceptance in Discord; passing mocks alone is insufficient.


## Fuel source fallback — Asumi 3.7.7

If direct PVOIL HTML is inaccessible (e.g. HTTP 403), try strictly validated dated WebGia.TV *non-official HTML* price table, then Brave. Never present community prices as first-party official PVOIL data or hardcode a pump price. Preserve true dates and Vùng 1 pricing; reject stale, missing or implausible data. Keep diagnostics of HTTP/parse failures in Dashboard, not raw payloads, and do not equate CI mocks with Render network access.


## Historical context — T24 Admin Console 2.0 (no longer UI baseline)

**Status: T24 3.9.0 backend/features retained, but its sidebar UI superseded by the owner's original historical eight-tab dashboard preference in Asumi 3.9.1.**
Read `docs/ASUMI_T24_ADMIN_CONSOLE_REDESIGN_PLAN.md` before any Admin Dashboard UI/route restructuring. T24 redesign keeps the existing Flask application, consolidates Feedback + AI proposals into the same ticket-detail workflow, and introduces five grouped navigation sections through focused goals T24.0–T24.7. Keep old /admin and /admin/feedback URLs operational; do not create a separate Request Review approval screen. Respect T23 terminal-only reporter notifications, including independent pending PR #51, before changing feedback UI. Record each goal's status/test/live-verification in repository docs so new sessions can resume.

### Historical Dashboard baseline (owner correction — 2026-10-08)

**The OWNER explicitly wants the pre-T24 eight-tab admin Dashboard that has been used historically, not Asumi 3.9.0's new sidebar nor the separate prototype.** The authoritative source is `web/templates/dashboard.html`, now served at `/admin`. Preserve current backend/features and improve that original template incrementally. Old T24 sidebar information architecture and PR #55 proposal are superseded for UI direction. Read `docs/ASUMI_HISTORICAL_DASHBOARD_DECISION.md` before touching Admin UI. Keep T23 Feedback and final-only reporter DMs.


### T24.9 Feedback in the classic Admin tab bar

**Owner explicitly requires Feedback to live inside the historical Dashboard**, not open a separate admin page. The classic `web/templates/dashboard.html` has a ninth Feedback tab, with a chrome-free authenticated same-origin view of the existing T23 Feedback Center. Old `/admin/feedback[/ticket]` links redirect to `/admin?tab=feedback[&ticket=...]`; only the classic topbar/tab strip is visible. Preserve the existing CSRF, ticket data, AI proposals, private R2 access, and terminal-only notifications. See `docs/ASUMI_HISTORICAL_DASHBOARD_DECISION.md`.


## Social Embed reliability checkpoint — Asumi 3.10.1 (2026-10-09)

**Authoritative details:** `docs/EMBED_PIPELINE.md`. User reported recurring Facebook `/share/v/` login/no-preview cards in Discord mobile. Correct behavior:
- Preserve Facebook `/share/v/{token}` verbatim; never rewrite it to `/share/r/`. Numeric reel/watch conversion remains distinct.
- Try existing multiple proxy candidates, with Facebook four-provider order in `core/constants.py`; validators must reject thumbnail-only/log-in cards for video routes.
- Only after no usable candidate can Facebook VIDEO links attempt yt-dlp. Require a successfully downloaded, guild-size-bounded playable video; never fabricate an embed from generic thumbnails or ask for private Facebook cookies.
- If no media is available, retain original Discord message/native preview and present a clear, user-owned manual Reload/Remove/open-original action. Do not suppress originals for action-required warnings; failed replacement never deletes working preview.
- All other platforms preserve existing API → proxy → yt-dlp behavior and cleanup. CI: `.github/workflows/asumi-embed.yml`, `tests/test_embed_resilience.py`, historical `test_release28.py` and `test_embed_audit.py`.
- Production Discord/Render testing of the reported Facebook permalink is still an independent gate; don't assert guaranteed Facebook private-content retrieval from CI fixtures.

