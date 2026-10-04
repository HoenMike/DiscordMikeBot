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

Tarot 2.0 implementation is active and user-approved.

- T20.0 — baseline/docs: complete.
- T20.1 — Prompt & Reading Engine 2.0: complete.
- T20.2 — Question-first Launcher: complete.
- T20.3 — Reading Session UX: complete.
- T20.4 — Renderer 2.0: complete.
- T20.5 — Clarifier: complete.
- **Tarot 2.0 release boundary is complete in Asumi 2.9.0.**
- **Next milestone: T20.6 — Multi-turn Reading Session.**
- Continue milestone-by-milestone; do not skip ahead or bundle unrelated later milestones into one PR.

### Tarot milestone IDs

```text
T20.0  Baseline / docs / contract lock
T20.1  Prompt & Reading Engine 2.0
T20.2  Question-first Launcher
T20.3  Reading Session UX
T20.4  Renderer 2.0
T20.5  Clarifier — COMPLETE
T20.6  Multi-turn Reading Session — COMPLETE
T20.7  Smart Custom Spread — NEXT
T20.8  Tarot Journey
T20.9  Recap & Polish
```

Tarot 2.0 release target T20.1–T20.5 is complete in v2.9.0. T20.6 is also complete; continue with T20.7, then T20.8 and T20.9 without waiting for per-milestone approval unless a real blocker appears.

### Tarot continuity rule

If you start, complete, reject or materially change a Tarot milestone, update `docs/TAROT_V2_HANDOFF.md` in the same PR so a future session can resume without the original conversation.

## Feature documentation

- Social embed pipeline: `docs/EMBED_PIPELINE.md`
- Current Tarot system: `docs/TAROT_SYSTEM.md`
- Tarot 2.0 master plan: `docs/TAROT_V2_MASTER_PLAN.md`
- Tarot 2.0 handoff: `docs/TAROT_V2_HANDOFF.md`
- Tarot 2.0 prompt spec: `docs/TAROT_V2_PROMPT_SPEC.md`
- Tarot 2.0 renderer spec: `docs/TAROT_V2_RENDERER_SPEC.md`
