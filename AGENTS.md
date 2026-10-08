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

**Status: T22.1 BRAVE + T22.2 HISTORY + T22.3 CLEF IMPLEMENTED; T22.4a CHRONOLOGICAL HISTORY IMPLEMENTED (LIVE VERIFY PENDING); T22.4b IMPLEMENTED (LIVE VERIFY PENDING); T22.5 PLANNED. All search providers opt-in.** Before any T22 work read:

1. `docs/ASUMI_T22_INTELLIGENT_SEARCH_PLAN.md`
2. `docs/ASUMI_T22_SEARCH_HANDOFF.md`
3. `docs/ASUMI_INTELLIGENCE_HANDOFF.md` for unfinished T21 live tests.

Owner selected Brave Search API for external web retrieval. **Separate goal:** native on-demand Discord guild history search to find actual old messages by author/time/topic, even if they were never explicitly saved in Archive. Return original Discord Jump to Message URLs.

Non-negotiable: no passive entire-guild indexing/backfill, no personal user tokens, no leaks from channels the requester cannot read, no private Discord text sent to Brave, and no unbounded provider usage. Start with official bot-token guild search endpoint and permission validation; use optional index only if justified by real need and explicit admin consent.

T22.4a supports oldest/latest messages by one @mentioned author (no topic required) with chronological search and conservative partial-result wording. T22.4b adds safe explicit web follow-up, source-grounded chat, channel metadata and privacy-safe Dashboard search tracing; T22.5 multi-source automatic chaining remains gated pending live validation. Brave adapter is implemented but requires external API key, explicit enable and live acceptance. Discord History Search and Clef auto-routing implemented but await bot-token/ACL and Brave key live validation; feature flags default OFF; code does not equal live-verified capability. Every T22 PR updates its plan/handoff, tests, and README/help only when behavior ships.

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
