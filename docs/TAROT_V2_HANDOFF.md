# Tarot 2.0 — Session Handoff / Resume Guide

> **Purpose:** This file is the short operational handoff for future ChatGPT/Codex/agent sessions.  
> **Status:** T20.1–T20.9 remain complete; current bot release is **Asumi 3.0.0** with a post-roadmap Tarot launcher UX refresh.  
> **Last updated:** 2026-10-05.

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
- Repository-preparation work is complete.
- The user explicitly approved starting Tarot 2.0 implementation.
- **T20.1 — Prompt & Reading Engine 2.0 has been implemented.**
- **T20.2 — Question-first Launcher has been implemented.**
- **T20.3 — Reading Session UX has been implemented.**
- **T20.4 — Renderer 2.0 has been implemented.**
- **T20.5 — Clarifier has been implemented.**
- **Tarot 2.0 release boundary (T20.1–T20.5) is complete in Asumi 2.9.0.**
- **T20.6 — Multi-turn Reading Session has been implemented.**
- **T20.7 — Smart Custom Spread has been implemented.**
- **T20.8 — Tarot Journey has been implemented.**
- **T20.9 — Recap & Polish has been implemented.**
- **T20.1–T20.9 are complete. No next numbered Tarot milestone is defined until a new roadmap is requested.**
- **Asumi 3.0 UX refresh:** launcher now prioritizes question + Daily quick start; recommendation starts in one click; manual spread/style are secondary.

---

## 3. Baseline at handoff creation

Repository:

`HoenMike/DiscordMikeBot`

Baseline at planning time:

- bot version: `2.8.4`
- planning baseline main commit: `560637145b8a96980bcca66b051491e34eb7bc8d`
- T20.1 merged main commit: `c755fa89e194fa15d92fd64d5212ae2f6e29883b`
- T20.2 merged main commit: `46857dbdcaff502579e504a3de09ae34b6e6eb8b`
- T20.3 merged main commit: `8b150ac6823d956445c55d3b2fc5cd311b5b9586`
- T20.6 merged main commit: `7f7f5c26a6741449b04b650bf514fbba4114fa92`
- T20.7 merged main commit: `7aedf5edd8888cb5aaf7a2b60d6be8a9212cd695`
- T20.8 merged main commit: `b4a36c581aa34fd91e825e76d77a146d48440037`
- T20.9 completion release: `2.10.0 / Asumi - Tarot 2.1`
- current bot release: `3.0.0 / Asumi 3.0 - Tarot-first UX`

Always re-check current main before work starts.

### Current Asumi 3.0 launcher contract

- `/tarot` and `.m tarot` open the same launcher.
- No question: primary controls are **✏️ Nhập câu hỏi** and **☀️ Daily hôm nay**; Daily starts immediately after cooldown checks.
- With a question: recommendation is shown in the embed and **✨ Trải theo đề xuất** both accepts it and starts the reading.
- **🧩 Tạo spread riêng** remains available for a generated 3–7 position schema.
- Manual fixed-spread selection and Reader Style are lower **Tuỳ chọn nâng cao** controls.
- Direct syntax remains supported: slash `spread:` choice, `.m tarot daily`, `.m tarot <spread> <question>`, and `.m tarot <free-form question>`.
- One-click Daily/recommendation rolls back temporary selection state when cooldown/validation blocks the start.

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
- spread recommendation + Smart Custom Spread;
- up to three contextual follow-ups;
- owner-only Why / Clarifier / Recap actions;
- Tarot Journey 30-day analytics;
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
| T20.1 | COMPLETE | V2 system prompt, structured schema/parser, adaptive auto tone, natural follow-up and evidence-based Why support |
| T20.2 | COMPLETE | Question-first launcher, deterministic smart recommendation, manual override, repeated-question awareness |
| T20.3 | COMPLETE | Shuffling/face-down/revealing/finalizing lifecycle, compact controls, progress, micro reveal, AI-ready indicator |
| T20.4 | COMPLETE | Reading Board state contract, responsive layouts, position/progress labels, REV/Major/key/new/target states, dynamic 4/6/7 layouts, final board and fallback |
| T20.5 | COMPLETE | Owner-only target picker, deterministic non-reroll one-card draw, Clarifier Board, bounded interpretation, delivery-safe 1/1 limit and separate persistence |
| T20.6 | COMPLETE | Up to 3 contextual follow-ups, shared session state, owner-only Why?, 10-minute inactivity expiry and delivery-safe consumption |
| T20.7 | COMPLETE | Schema-only AI design, validated 3–7 positions, deck-owned draw, fixed-spread fallback |
| T20.8 | COMPLETE | 30-day stored-history analytics + Journey Card + slash/prefix access |
| T20.9 | COMPLETE | Owner-only Recap Card, help/docs polish and Asumi 2.10.0 / Tarot 2.1 release |

### T20.5 implementation contract

- Result action exposes **🃏 Làm rõ** only to the reading owner.
- Picker prioritizes up to two AI-suggested existing positions, while still allowing any real position in the spread.
- `draw_clarifier(...)` excludes every original card and binds retries to the original spread + target so a failed delivery does not silently reroll.
- Clarifier Board preserves the complete original spread, marks the selected TARGET and adds one separate CLARIFIER relation panel.
- AI receives the original question/context/reading, selected target evidence and the one engine-drawn clarifier; it must not regenerate the full reading.
- Default limit is **1 clarifier per reading**. The count is consumed only after a public Discord delivery succeeds; attachment failure may fall back to text-only.
- Successfully delivered clarifiers persist in `tarot_clarifiers`; `tarot_history` remains unchanged.
- T20.6 must build on this state rather than turning Clarifier into an unlimited reroll flow.

### T20.6 implementation contract

- Final result actions now share an in-memory `TarotSessionState` instead of treating each follow-up as an isolated one-shot.
- Each reading supports up to **3** follow-up questions. Previous follow-up Q/A, real-world context and a successfully delivered clarifier are passed forward as bounded session context.
- A follow-up slot is consumed only after its public Discord response is delivered; generation/send failure leaves the slot available.
- **🔍 Vì sao?** is owner-only, one-use, ephemeral, and calls the existing evidence-oriented `generate_why_explanation(...)`; it explains visible card/position evidence rather than hidden reasoning.
- Clarifier remains **1/1** and becomes context for later follow-ups; it is not converted into reroll behavior.
- The result session inherits the Discord View timeout (10 minutes by default). Timeout closes the session actions and disables follow-up / clarifier / Why controls.
- Activity details now track follow-up count and Why usage.

### T20.7 implementation contract

- Launcher exposes **🧩 Trải bài riêng** only after a question exists; fixed recommendation/manual spread remain available.
- AI returns only `title`, `intent`, `reason` and 3–7 positions. Validator rejects duplicate IDs/titles, invalid counts, card/orientation fields and private third-party position framing.
- `draw_custom_spread(...)` remains the sole card-draw authority for custom schemas and keeps no-repeat/fatigue behavior.
- Existing dynamic Reading Board layouts are reused and custom titles flow through live/final/Clarifier boards.
- Invalid or unavailable custom schema generation falls back to the known-spread recommendation instead of failing.

### T20.8 implementation contract

- `/tarot_journey` and `.m tarot journey` summarize only readings actually stored in the last 30 days; no extra divination call is made.
- Metrics include reading/card counts, Minor Arcana suit mix, Major Arcana ratio, repeated cards, repeated reversed cards, topic progression and most-used spread.
- Suit percentages use deterministic apportionment so displayed shares sum to 100% when Minor Arcana data exists.
- `render_journey_card_to_bytes(...)` produces a compact visual summary; both card and embed explicitly frame patterns as reflection statistics, not fate or diagnosis.
- Journey disappears naturally when the user clears Tarot history because it has no parallel hidden profile store.

### T20.9 implementation contract

- Final result view exposes owner-only **📌 Recap** on the secondary component row; follow-up / Why / Clarifier stay on the primary row while Recap + ratings stay compact on row 2.
- Recap does **not** draw cards or call AI again. It reuses the completed structured reading, preferring the actual key card as hero and falling back deterministically to the first drawn card.
- The Recap Card contains only hero card/orientation, short headline, one practical takeaway, spread title, date and lightweight Asumi branding; it does not embed the full reading or Journey analytics.
- Recap is generated ephemerally, includes a text equivalent of hero/headline/takeaway for accessibility, becomes one-use only after successful delivery, and every visible result button is disabled when the View times out.
- T20.1–T20.9 are the maintenance baseline. Asumi 3.0.0 adds a post-roadmap launcher UX refresh without changing those milestone contracts.
- Current launcher contract: **question → one-click recommendation**, **Daily → one-tap start**, advanced manual spread/style below; slash and `.m` share the same launcher.
- Future feature work should start a new roadmap/milestone series unless the user explicitly reopens one of these milestones.

When a milestone starts or completes, update this table in the same PR.

---

## 10.1 T20.1 implementation notes

Implemented in the T20.1 branch:

- introduced `features/tarot/reading/` with reusable V2 Pydantic contracts;
- added rich `TarotReadingResult` while keeping the existing tuple API through an adapter;
- rewrote the main Tarot system instruction around natural Asumi voice and the `OBSERVE → CONNECT → INTERPRET → GROUND → UNCERTAINTY` contract;
- added deterministic auto-tone hints for decision/emotional/playful/high-stakes questions;
- changed model output from legacy `conclusion/cards_analysis/advice/full_reading` toward structured fields such as `core_message`, `connections`, `key_card`, `practical_takeaway`, `uncertainty`, Journey tags and clarifier targets;
- kept a legacy parser path so weaker/fallback models and old-format responses still work;
- added a rich-result generator for future UI milestones while preserving `generate_tarot_reading(...)` compatibility;
- updated existing follow-up prompting to stay in the same reading and avoid re-explaining the whole spread;
- added `generate_why_explanation(...)` for a later Discord **Why?** control;
- corrected the stale recommendation key `celtic_cross` → `celtic`;
- added dedicated regression coverage in `tests/test_tarot_v2_reading.py`.

No renderer/session/clarifier UI work is part of T20.1.

---

## 10.2 T20.2 implementation notes

Implemented:

- launcher now opens **question-first** instead of presenting Daily as if it were the default recommendation;
- user enters/edits question and optional real-world context first;
- deterministic zero-latency recommendation lives in `features/tarot/reading/recommendation.py`;
- recommendation can choose among existing spread keys, including `two_paths` for deeper A/B trade-offs;
- user must explicitly **use Asumi's recommendation** or manually select another spread before Start enables;
- Daily remains available manually with no question;
- reader style remains a secondary option;
- direct slash/prefix spread syntax still bypasses the launcher for backward compatibility;
- launcher detects sufficiently similar recent Tarot questions using local token-overlap logic, without an extra AI call; this awareness is disabled when the user has Tarot memory turned off;
- when a similar question is found, the user can choose:
  - **Xem tình hình hiện tại** — prior Tarot context may be used lightly;
  - **Xem như câu hỏi mới** — prior Tarot context is not injected into this reading;
- card-fatigue behavior remains independent from the context-memory choice;
- standalone `/tarot_recommend` and prefix recommendation commands remain available and now use the same V2 recommender;
- tests added in `tests/test_tarot_v2_launcher.py`.

T20.2 does **not** yet implement one-message reveal lifecycle, micro-reveal, renderer redesign, clarifier or multi-turn continuation. Those belong to later milestones.

---

## 10.3 T20.3 implementation notes

Implemented:

- launcher transitions through a visible **Đang xáo bài** state before the reading board appears;
- `TarotFlipView` now owns a reusable live session embed for FACE-DOWN / REVEALING states;
- progress is always visible as both dots and numeric count (for example `● ○ ○   1 / 3 lá đã lật`);
- card buttons are compact numeric controls (`1`, `2`, …, `✓ 2`) so 10-card spreads remain manageable on mobile;
- each single-card reveal gets deterministic **micro reveal** feedback using the actual card, orientation and top keywords; this does not spend another AI call;
- AI generation continues in parallel with card reveal;
- when AI finishes before the user finishes flipping, the **same Discord message** updates to `Luận giải đã sẵn sàng` without creating another message or rerendering the image;
- when the user finishes flipping before AI finishes, the same message enters a clear **ĐANG LUẬN GIẢI** finalizing state and then becomes the final reading;
- launcher flow, direct slash flow and prefix flow now initialize from the same session-embed builder;
- session presentation helpers live in `features/tarot/reading/session.py`;
- dedicated regression coverage added in `tests/test_tarot_v2_session.py`.

Scope intentionally left for T20.4+: Reading Board visual redesign, responsive canvas overhaul, key-card/just-revealed visual states inside the image, clarifier, multi-turn continuation and Journey.

---

## 10.4 T20.4 implementation notes

Implemented:

- replaced the legacy card-collage renderer with a **Reading Board 2.0** renderer while keeping `render_spread_to_bytes(...)` backward-compatible;
- introduced `features/tarot/rendering/state.py` with the UI-independent `ReadingBoardState` contract;
- visual direction now follows dark celestial / muted violet / warm gold / blue-grey with restrained framing instead of heavy ornament;
- responsive fixed layouts:
  - 1 card — portrait `1080×1350`;
  - 3 cards — `1400×900`;
  - 5-card Two Paths — dedicated `1400×1100`;
  - 5-card Horseshoe — dedicated `1500×1100`;
  - Celtic — `1600×1350`;
- generic layouts are ready for later Smart Custom Spread:
  - 4 cards — diamond;
  - 5 cards — generic cross;
  - 6 cards — 2×3;
  - 7 cards — arc/horseshoe;
  - other counts fall back to a bounded grid;
- board position labels are always visible for face-up and face-down cards;
- progress appears on the board during reveal and is removed/replaced by **FINAL SPREAD** in final state;
- reversed cards keep their 180° rotation **and** receive explicit `REV`/orientation text;
- Major Arcana receive a subtle `MAJOR` marker;
- `NEW`, `KEY` and `TARGET` emphasis states exist in the renderer contract; T20.3 live reveal now passes the just-revealed state;
- interactive Tarot now uses the rich T20.1 `TarotReadingResult`, allowing the final board to highlight the AI-selected key card without an extra AI request;
- final board is rerendered after the AI result is available; card draw/order is never changed by rendering;
- renderer failures fall back to a text-first board image so the reading outcome is preserved instead of failing the session;
- procedural card fallback and resized card/back caches remain available;
- renderer regression coverage added in `tests/test_tarot_v2_renderer.py`, plus rich key-card handoff coverage in `tests/test_tarot_v2_session.py`.

Scope intentionally left for T20.5+: Clarifier target UX/draw/interpretation. The renderer already exposes `target_position_index` so Clarifier can build on the same visual state contract without another renderer rewrite.

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
