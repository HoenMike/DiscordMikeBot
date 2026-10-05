# Tarot 2.0 — Renderer & Presentation Spec

> **Status:** T20.4 implementation complete; this remains the renderer/presentation behavior contract.  
> **Parent plan:** `docs/TAROT_V2_MASTER_PLAN.md`  
> **Current renderer:** `features/tarot/renderer.py`

This document captures the intended visual/UX direction so a future session can implement T20.4 without reconstructing the design from prior chat.

---

## 1. Goal

Tarot 2.0 should move from "cards arranged on a canvas" toward a reusable **Reading Board** system.

The renderer should communicate:

- what spread is being used;
- what each position means;
- what has been revealed;
- what is reversed;
- which card/position is currently important;
- how a clarifier relates to the original spread.

The image is a **visual state layer**, not the place for the full AI reading.

---

## 2. Visual direction

Target mood:

> **dark celestial + muted violet + warm gold + blue-grey**

Desired feeling:

- modern;
- elegant;
- friendly;
- slightly mystical;
- premium;
- readable on Discord mobile;
- consistent with Asumi rather than generic occult art.

Avoid:

- heavy gothic ornament;
- too many stars/moons;
- extreme glow;
- low-contrast decorative text;
- unnecessary frames around every element;
- tiny labels.

Card art remains the primary focal point.

### Spread title fitting

- Never hard-truncate the spread title with `...`.
- Prefer a modest font-size reduction when a full title almost fits on one line.
- If needed, wrap the complete title to at most two readable lines.
- This applies to fixed bilingual names and Smart Custom Spread titles.

---

## 3. Reading Board anatomy

A normal Reading Board may contain:

1. spread title;
2. optional short subtitle;
3. cards;
4. position label for each card;
5. reversed marker when needed;
6. progress text;
7. optional key-card / active-card emphasis;
8. minimal Asumi/Tarot branding.

Do not render:

- the full AI interpretation;
- long question/context paragraphs;
- large help/instruction blocks;
- rating controls;
- follow-up text.

---

## 4. State model

Each rendered card should support a visual state.

Conceptual states:

```text
FACE_DOWN
REVEALED
JUST_REVEALED
KEY_CARD
TARGET
CLARIFIER
DISABLED/COMPLETE (rarely needed visually)
```

State should be represented with restrained UI:

- border;
- subtle ring;
- tag;
- small marker;
- slight shadow/glow difference.

Do not alter the card art destructively.

---

## 5. Reversed cards

Current rotation behavior should remain understandable.

V2 requirements:

- keep 180° card rotation if that is the current visual convention;
- also include a readable `REV` / `NGƯỢC` marker;
- do not rely on rotation alone;
- marker must remain readable at mobile scale.

---

## 6. Major Arcana

Major Arcana may receive subtle differentiation.

Allowed:

- slightly different frame accent;
- tiny Major marker;
- restrained gold emphasis.

Avoid making all Major cards brighter than the actual key card.

Major ≠ automatically most important.

---

## 7. Position labels

Position labels belong on the board.

Examples:

- Quá khứ
- Hiện tại
- Tương lai
- Trở ngại
- Lời khuyên
- Kết quả
- Hướng A
- Hướng B

Rules:

- short title;
- readable at thumbnail scale;
- no paragraph descriptions on image;
- position description stays in embed/text if needed.

This allows Discord buttons to become compact `1`, `2`, `3` controls.

---

## 8. Progress

Show text progress such as:

`2 / 5 revealed`

Optional dot visualization can accompany it:

`● ● ○ ○ ○`

But dots must never be the only progress indicator.

---

## 9. Responsive layout targets

Starting design targets:

| Card count | Layout | Approx size |
|---:|---|---|
| 1 | Portrait Hero | 1080×1350 |
| 3 | Horizontal / gentle arc | 1400×900 |
| 4 | Diamond | 1300×1100 |
| 5 | Cross / fan / spread-specific | 1300×1100 |
| 6 | 2×3 | 1500×1150 |
| 7 | Horseshoe | 1500×1150 |
| 10 | Celtic-specific | 1600×1350 |

These dimensions are not hard requirements. Validate output after Discord compression.

---

## 10. Existing fixed spreads

V2 must preserve visual support for all existing spread keys:

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

Recommended mapping:

### 1 card

- centered hero card;
- position/title below;
- enough space for card to remain visually strong.

### 3 cards

Used by:

- `ppf`
- `choices`
- `mbs`

Horizontal or shallow arc.

### 5 cards

Used by:

- `horseshoe`
- `two_paths`

Prefer dedicated templates rather than forcing a generic grid.

### 10 cards

`celtic`

Keep a recognizable Celtic Cross composition while improving label readability and spacing.

---

## 11. Dynamic spread layout

Smart Custom Spread later requires a generic renderer.

Dynamic renderer input should be based on:

- spread title;
- ordered position schema;
- drawn cards;
- reveal state;
- emphasis state.

Suggested generic templates:

- 3 → horizontal
- 4 → diamond
- 5 → cross/fan
- 6 → 2×3
- 7 → horseshoe/general arc

Known spreads can override generic templates.

---

## 12. Just-revealed feedback

When a card is newly revealed, renderer may temporarily emphasize it.

Possible treatment:

- brighter outline;
- slightly larger frame;
- small "REVEALED" or position accent.

This visual state should disappear on the next action.

Avoid expensive animation requirements; Discord image edit state change is enough.

---

## 13. Key Card

Final Reading Board may emphasize a Key Card selected by the reading engine.

Possible treatment:

- thin warm-gold ring;
- `KEY` tag;
- slightly elevated shadow.

Do not move the card to a different position and break spread meaning.

---

## 14. Clarifier Board

Clarifier must visually read as an **addition**, not replacement.

Preferred patterns:

### Target relation

```text
[ Original target card ]
          ↓
[ Clarifier card ]
```

or

```text
spread remains visible
target receives highlight
clarifier appears in a dedicated side panel
```

Requirements:

- original spread stays intact;
- target is clearly identifiable;
- clarifier has its own label;
- relationship is readable on mobile.

---

## 15. Final Spread Board

After all cards are revealed, optionally render a cleaner final board.

Differences from reveal-state board:

- remove progress dots;
- all positions visible;
- key-card emphasis;
- clean complete composition;
- optionally include short headline, but no long reading.

This final board may later be used as source material for recap.

---

## 16. Reading Recap Card

**Implemented in T20.9.**

Implemented portrait output:

`1200×1500`

Content:

- Asumi Tarot branding;
- key/hero card;
- reading headline;
- one takeaway sentence;
- spread name;
- date.

Do not include:

- all card meanings;
- long reading;
- analytics;
- huge watermarks.

This is save/share-friendly presentation.

---

## 17. Journey Card

**Implemented in T20.8.**

Potential layout:

```text
YOUR TAROT JOURNEY
LAST 30 DAYS

14 READINGS

Cups       31%
Swords     27%
Wands      23%
Pentacles  19%

REPEATING CARD
THE HERMIT ×3

MAJOR ARCANA
36%

CURRENT THEME
Decision → Clarity → Action
```

Keep analytics readable and restrained.

---

## 18. Typography direction

Use a clear hierarchy:

- serif/display feel for Tarot title if available in the existing approved font stack;
- sans/readable type for labels/metadata;
- position labels large enough for mobile;
- avoid all-caps for long phrases.

Do not introduce font files casually. Reuse existing project-compatible fonts/assets unless a deliberate asset change is approved.

---

## 19. Color/contrast rules

Do not encode important state only by color.

Examples:

- reversed = rotation + REV label;
- target = highlight + TARGET label if needed;
- key card = highlight + KEY marker.

Check contrast against dark backgrounds.

Avoid overly bright saturated violet/gold combinations that reduce readability.

---

## 20. Mobile review checklist

Before T20.4 is complete, inspect generated images at a phone-like preview size.

Questions:

- Can I read all position labels?
- Can I tell which cards are face-down?
- Can I tell which card is reversed?
- Does Celtic still make sense without zooming?
- Is key-card emphasis visible but not distracting?
- Does a 5-card spread still feel balanced?
- Are labels colliding with card art?

---

## 21. Renderer API direction

Do not hardcode V2 UI state directly into Discord view code.

Prefer a renderer request/state object concept.

Example:

```python
ReadingBoardState(
    spread_key=...,
    spread_title=...,
    positions=...,
    cards=...,
    revealed_ids=...,
    just_revealed_id=...,
    key_card_id=...,
    target_position_id=...,
    clarifier=...,
    progress=...
)
```

Exact implementation can differ, but keep rendering concerns separated from Discord interaction concerns.

---

## 22. Caching

Current renderer has image caching.

V2 should preserve or improve caching for:

- resized upright card art;
- reversed card art;
- card backs;
- reusable textures/background components.

Do not cache full boards without a bounded strategy because reveal state combinations can grow.

---

## 23. Performance

Renderer 2.0 should remain compatible with async Discord flow.

Prefer:

- render CPU work in `asyncio.to_thread`;
- reuse cached card bitmaps;
- avoid repeated disk decode for every flip;
- avoid expensive runtime vector effects;
- avoid rendering text at excessive resolution.

Measure:

- initial board render;
- single flip render;
- flip-all render;
- Celtic render;
- clarifier render.

---

## 24. Fallback

If V2 renderer fails:

- keep the reading usable;
- fall back to a simpler card list/embed;
- do not lose already-drawn cards;
- do not redraw a different spread.

Rendering failure must not alter Tarot outcome.

---

## 25. Renderer acceptance tests

At minimum test:

- 1-card upright;
- 1-card reversed;
- 3-card partially revealed;
- 3-card all revealed;
- 5-card spread;
- Celtic 10-card;
- key card emphasis;
- clarifier target;
- dynamic 4/6/7 card layouts;
- missing asset fallback;
- output file is valid and under practical Discord limits.

Image snapshot tests may be brittle; combine structural checks with manual visual review.

---

## 26. Presentation copy

Keep image text short.

Good:

- `HIỆN TẠI`
- `LỜI KHUYÊN`
- `2 / 5 REVEALED`

Bad:

- full paragraph descriptions;
- question repeated on image;
- AI-generated interpretation inside card labels.

---

## 27. Implementation order for T20.4

Suggested order:

1. define board-state contract;
2. create common visual primitives;
3. port 1-card;
4. port 3-card;
5. port 5-card;
6. port Celtic;
7. add progress/position labels;
8. add reversed/key/just-revealed states;
9. add generic dynamic templates;
10. add Final Board;
11. add Clarifier support when T20.5 begins.

Do not start with Recap/Journey renderers before the core Reading Board is stable.

---

## 27.1 Implemented in T20.4

Current runtime implementation now includes:

- `ReadingBoardState` in `features/tarot/rendering/state.py`;
- a new responsive Reading Board renderer in `features/tarot/renderer.py`;
- fixed 1/3/Two Paths/Horseshoe/Celtic layouts;
- generic 4/5/6/7 layouts for future dynamic spreads;
- progress/final board states;
- explicit reversed marker;
- subtle Major marker;
- just-revealed, key-card and target emphasis states;
- rich-reading integration so final boards can use the AI-selected key card;
- text-first renderer fallback that preserves the original cards;
- regression tests in `tests/test_tarot_v2_renderer.py`.

Clarifier rendering itself remains T20.5. The target-state primitive is intentionally present now so T20.5 can add a clarifier card without replacing the board architecture.

---

## 28. Scope boundary

T20.4 renderer work should not automatically include:

- new Tarot card artwork;
- AI image generation;
- animated GIF/video;
- web canvas;
- 3D effects;
- custom user themes;
- recap/journey unless explicitly pulled forward.

The V2 visual upgrade comes from layout, hierarchy, responsiveness and coherence—not from adding expensive effects.
