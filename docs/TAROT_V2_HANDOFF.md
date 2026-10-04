# Tarot 2.0 — Session Handoff / Resume Guide

> **Purpose:** This file is the short operational handoff for future ChatGPT/Codex/agent sessions.  
> **Status:** planning documented; **implementation has not started yet**.  
> **Last updated:** 2026-10-04.

The user explicitly requested that a future session should be able to point at the repository and continue without needing the original planning conversation.

---

## 1. Read these files first

In a fresh session, read in this order:

1. `AGENTS.md`
2. `docs/TAROT_V2_MASTER_PLAN.md`
3. `docs/TAROT_V2_PROMPT_SPEC.md`
4. `docs/TAROT_V2_RENDERER_SPEC.md`
5. `docs/TAROT_SYSTEM.md`
6. current `features/tarot/` code
7. `core/version.py`
8. latest Git history / open PRs

Do not rely only on this handoff because runtime code may have changed after it was written.

---

## 2. Current planning state

### Requested by user

The user wants a **Tarot 2.0** upgrade focused on:

- more features;
- smarter interpretation;
- more interesting interaction;
- better UX/presentation;
- new renderer/reading-board experience;
- less robotic Asumi system prompt.

### Important status

- Master plan is documented.
- Repository-preparation work is approved.
- **Feature implementation is NOT yet approved/started.**
- Do not begin T20.1+ until the user explicitly says to start or approves a milestone.

---

## 3. Baseline at handoff creation

Repository:

`HoenMike/DiscordMikeBot`

Baseline at planning time:

- bot version: `2.8.4`
- main commit: `560637145b8a96980bcca66b051491e34eb7bc8d`
- codename: `Asumi - Compact Facebook Proxy Link`

Always re-check current main before work starts.

---

## 4. Current Tarot capabilities that already exist

Do not accidentally re-build these as if they were new:

- 78-card Rider-Waite based deck;
- upright/reversed cards;
- 9 spread types;
- interactive card flipping;
- flip-all;
- renderer;
- AI interpretation;
- AI model fallback;
- four Asumi style IDs:
  - `auto`
  - `neutral`
  - `healer`
  - `chaos`
- Daily Card;
- Daily cooldown;
- Tarot history;
- user memory toggle;
- forget/history deletion;
- card fatigue / recent-card avoidance;
- spread recommendation helper;
- one follow-up interaction;
- rating buttons;
- rare-combo / flavor text;
- weekly guild card;
- slash + prefix command compatibility.

---

## 5. Current spread keys

Keep these stable unless there is an explicit migration:

```text
daily
yes_no
single
ppf
choices
mbs
horseshoe
two_paths
celtic
```

---

## 6. Locked V2 direction

Unless the user changes the plan, the main V2 decisions are:

### UX

- question-first launcher;
- smart spread recommendation inside the normal launcher;
- one main session message where practical;
- visible progress states;
- micro reveal for each flipped card;
- structured final reading;
- clarifier;
- contextual follow-ups;
- "Why?" explanation.

### Renderer

- Reading Board, not just card collage;
- responsive layouts;
- mobile readability first;
- position labels on image;
- clear reversed state;
- key-card / clarifier emphasis;
- Final Spread Board;
- later Journey and Recap renderers.

### AI / prompt

- Asumi should sound natural, not like a template;
- avoid repetitive "Lá bài này cho thấy..." writing;
- connect cards instead of interpreting each independently;
- prompt reasoning shape:
  `OBSERVE → CONNECT → INTERPRET → GROUND → UNCERTAINTY`;
- styles change delivery, not core reasoning;
- no forced optimism / generic healing language;
- no deterministic prophecy.

### Product

- do not add many fixed spreads just to make V2 feel bigger;
- Smart Custom Spread comes later;
- Journey is journal-like, not streak/XP gamification;
- no unlimited rerolls or clarifiers.

---

## 7. Release boundary

Planned milestones:

- `T20.0` — docs / baseline / contract lock
- `T20.1` — Prompt & Reading Engine 2.0
- `T20.2` — Question-first Launcher
- `T20.3` — Reading Session UX
- `T20.4` — Renderer 2.0
- `T20.5` — Clarifier
- `T20.6` — Multi-turn session
- `T20.7` — Smart Custom Spread
- `T20.8` — Tarot Journey
- `T20.9` — Recap & polish

**Tarot 2.0 release target:** T20.1 through T20.5.

Later milestones may become Tarot 2.1 / 2.2.

---

## 8. What to do when implementation is approved

Before coding:

1. sync/read current main;
2. compare current code against `docs/TAROT_SYSTEM.md`;
3. update this handoff's baseline if main has moved materially;
4. create a milestone-specific branch;
5. implement only one coherent milestone or sub-goal per PR;
6. add/update regression tests;
7. update:
   - this handoff;
   - master plan status;
   - `docs/TAROT_SYSTEM.md` if runtime architecture changes;
   - CHANGELOG/version only when appropriate for a release.

---

## 9. Suggested branch naming

Examples:

```text
feat/tarot-v2-t20-1-reading-engine
feat/tarot-v2-t20-2-launcher
feat/tarot-v2-t20-3-session-ux
feat/tarot-v2-t20-4-renderer
feat/tarot-v2-t20-5-clarifier
```

Avoid implementing all V2 milestones in one giant branch.

---

## 10. Milestone status table

| Milestone | Status | Notes |
|---|---|---|
| T20.0 | COMPLETE | Master plan, handoff, prompt spec, renderer spec and agent entry-point added |
| T20.1 | NOT STARTED | Wait for explicit approval |
| T20.2 | NOT STARTED | Wait for explicit approval |
| T20.3 | NOT STARTED | Wait for explicit approval |
| T20.4 | NOT STARTED | Wait for explicit approval |
| T20.5 | NOT STARTED | Wait for explicit approval |
| T20.6 | NOT STARTED | Later |
| T20.7 | NOT STARTED | Later |
| T20.8 | NOT STARTED | Later |
| T20.9 | NOT STARTED | Later |

When a milestone starts or completes, update this table in the same PR.

---

## 11. Current source map

Start investigation here:

```text
features/tarot/cog.py
  Discord commands, orchestration, weekly behavior

features/tarot/tarot_view.py
  launcher, flip UI, follow-up/rating interaction

features/tarot/ai.py
  prompt, AI reading, follow-up, recommendation

features/tarot/deck.py
  deck data, spread definitions, draw logic, styles

features/tarot/renderer.py
  current card/spread rendering

features/tarot/manager.py
  persistence, cooldowns, history, memory, rating, weekly config

features/tarot/flavor.py
  deterministic rare-combo/easter-egg text

docs/TAROT_SYSTEM.md
  current architecture reference
```

---

## 12. Things future agents must not assume

Do not assume:

- Tarot 2.0 means repository version 3.0 or similar;
- Smart Custom Spread should ship in first V2 release;
- Journey should ship before renderer/session foundation;
- more spread types automatically improve Tarot;
- all follow-ups should be unlimited;
- AI should choose cards;
- AI should generate runtime card artwork;
- user memory should always be injected;
- "mystical" means verbose or theatrical;
- every difficult reading needs a positive ending.

---

## 13. UX target in one example

A successful V2 flow should roughly feel like:

```text
/tarot
→ user enters concern
→ Asumi recommends Two Paths
→ user accepts
→ one session message begins
→ cards are face-down on a clear board
→ user flips cards
→ each flip gives a short micro insight
→ final reading appears in structured sections
→ user can click Clarify / Ask More / Why
→ session stays coherent
```

If implementation deviates from this significantly, revisit the master plan before continuing.

---

## 14. Prompt target in one paragraph

Asumi should sound like an observant, intelligent Tarot reader who connects the cards to the user's actual question. She should not sound like a form-filling AI, a generic therapy bot, or an omniscient fortune teller. She should explain strong patterns clearly, acknowledge ambiguity, vary phrasing naturally, and avoid repetitive mystical filler.

---

## 15. Documentation rule

When implementation changes a locked decision or milestone scope:

- do not leave docs stale;
- update `TAROT_V2_MASTER_PLAN.md` if the product decision changed;
- update this handoff if current work/status changed;
- update `TAROT_SYSTEM.md` if runtime behavior/architecture changed.

The repo is intended to be sufficient context for a future session.
