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
- **T21.1 — Mention conversational vertical slice: next.**
- T21.2–T21.8: planned; see the master plan.
- Cloudflare/AI work is **free-only** and must fail closed rather than silently create paid usage.
- Do not make Asumi respond to ordinary unmentioned server chat.
- Clef-flash is a decision/router layer, not the primary prose model.
- Persistent Archive/memory is explicit opt-in only and is not part of the first conversational slice.

### T21 continuity rule

If you start, complete, reject or materially change a T21 milestone, update `docs/ASUMI_INTELLIGENCE_HANDOFF.md` in the same PR. Update the master plan when the product/architecture contract changes.


## Feature documentation

- Asumi Intelligence master plan: `docs/ASUMI_INTELLIGENCE_MASTER_PLAN.md`
- Asumi Intelligence handoff: `docs/ASUMI_INTELLIGENCE_HANDOFF.md`
- Social embed pipeline: `docs/EMBED_PIPELINE.md`
- Current Tarot system: `docs/TAROT_SYSTEM.md`
- Tarot 2.0 master plan: `docs/TAROT_V2_MASTER_PLAN.md`
- Tarot 2.0 handoff: `docs/TAROT_V2_HANDOFF.md`
- Tarot 2.0 prompt spec: `docs/TAROT_V2_PROMPT_SPEC.md`
- Tarot 2.0 renderer spec: `docs/TAROT_V2_RENDERER_SPEC.md`
