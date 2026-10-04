# Asumi Tarot 2.0 — Master Plan

> **Status:** ACTIVE implementation plan.  
> **Implementation status:** **T20.1–T20.8 COMPLETE — Tarot 2.0 released; post-release expansion continues. T20.9 NEXT.** The user approved continuing through T20.9 without per-milestone approval.  
> **Last planning update:** 2026-10-05  
> **Repository baseline at planning time:** DiscordMikeBot `v2.8.4`, main commit `560637145b8a96980bcca66b051491e34eb7bc8d`.  
> **Primary runtime code:** `features/tarot/`  
> **Current-system reference:** `docs/TAROT_SYSTEM.md`  
> **Session handoff / resume checklist:** `docs/TAROT_V2_HANDOFF.md`  
> **Prompt/reading intelligence spec:** `docs/TAROT_V2_PROMPT_SPEC.md`  
> **Renderer/presentation spec:** `docs/TAROT_V2_RENDERER_SPEC.md`

---

## 0. Why this document exists

This is the source of truth for the planned **Asumi Tarot 2.0** upgrade.

The user explicitly wants the repository to contain enough context that a future ChatGPT/Codex/agent session can be pointed at the repo and continue correctly without needing the original conversation.

Therefore this document records:

- current Tarot behavior that must be preserved;
- product intent and design principles;
- UX and visual direction;
- AI/system-prompt direction;
- architecture and data-model direction;
- milestone ordering;
- acceptance criteria;
- non-goals;
- compatibility requirements;
- decisions that should not be casually re-opened.

This is a **product + engineering plan**, not an instruction to ship all items in one pull request.

---

# 1. Product Vision

## Tarot 1.x mental model

Current Tarot is already feature-rich, but the dominant interaction still feels like:

```text
choose spread
→ enter question
→ draw cards
→ flip cards
→ AI interpretation
→ optional follow-up
→ end
```

## Tarot 2.0 mental model

Tarot 2.0 should feel like a **guided reading session with Asumi**:

```text
tell Asumi what is bothering you
→ Asumi understands the intent
→ Asumi recommends or creates an appropriate spread
→ cards are presented as a coherent visual board
→ each reveal has a small payoff
→ Asumi connects the cards into one story
→ user can ask why / ask follow-up / draw a clarifier
→ session remains coherent
→ reading can later contribute to a personal Tarot Journey
```

### Core product statement

> **Tarot 1.x:** AI reads the cards you drew.  
> **Tarot 2.0:** Asumi explores a problem with you through the cards.

---

# 2. Three Pillars

Tarot 2.0 is organized around three pillars.

## 2.1 Intelligence

Asumi should:

- understand the user's question before forcing a spread choice;
- recommend an appropriate spread;
- connect cards to each other instead of reading them independently;
- distinguish observation, interpretation, advice and uncertainty;
- remember relevant prior Tarot context without letting memory dominate a new reading;
- support contextual follow-ups and clarifier cards;
- create a validated custom spread when a fixed spread is not ideal.

## 2.2 Interaction

A reading should behave like a session:

- one main Discord message where possible;
- clear lifecycle / progress state;
- interactive card reveal;
- clarifier flow;
- follow-up flow;
- evidence-oriented "Why?" explanation;
- clean owner-only controls;
- bounded interaction counts to prevent endless rerolling.

## 2.3 Presentation

Tarot 2.0 should visibly feel like a new generation:

- new Reading Board renderer;
- responsive layouts by spread size;
- position labels on the board;
- visual hierarchy for key / outcome / reversed / clarifier cards;
- improved final reading layout;
- Journey summary renderer;
- optional recap/share card.

---

# 3. Current Tarot Baseline — Preserve Before Refactor

At the time of this plan, the existing system already includes substantial functionality.

## 3.1 Existing spreads

The active UI supports **9 spread types**:

1. `daily` — Daily Card, 1 card
2. `yes_no` — Yes / No, 1 card
3. `single` — Single Card, 1 card
4. `ppf` — Past / Present / Future, 3 cards
5. `choices` — Two Choices, 3 cards
6. `mbs` — Mind / Body / Spirit, 3 cards
7. `horseshoe` — Horseshoe, 5 cards
8. `two_paths` — Two Paths, 5 cards
9. `celtic` — Celtic Cross, 10 cards

Do not remove or rename existing spread keys without an explicit migration plan.

## 3.2 Existing interaction behavior

Current system includes:

- slash and prefix Tarot commands;
- launcher with spread/style selection;
- question + optional real-world context;
- interactive card flipping;
- "flip all";
- background AI generation while cards are being revealed;
- rating buttons;
- one follow-up flow;
- history;
- daily cooldown;
- anti-spam cooldown;
- weekly guild card;
- user memory toggle;
- forget/history deletion flow.

## 3.3 Existing intelligence features

Current system already has:

- `auto`, `neutral`, `healer`, `chaos` style IDs;
- recent-context memory;
- card fatigue / recent-card avoidance;
- spread recommendation helper;
- structured AI output handling;
- model fallback cascade;
- topic/mood context support;
- flavor/easter-egg detection for rare card combinations;
- previous-reading context support.

## 3.4 Existing important modules

Primary files:

```text
features/tarot/
├── ai.py
├── cog.py
├── deck.py
├── flavor.py
├── manager.py
├── renderer.py
├── tarot_view.py
└── assets/
```

Supporting documentation:

```text
docs/TAROT_SYSTEM.md
```

Tests relevant to Tarot are currently mixed into the repository's existing test suite. Any V2 implementation must add focused regression tests rather than relying only on manual Discord testing.

---

# 4. Locked Product Principles

These decisions are considered the intended direction unless the user explicitly changes them.

## P1 — Do not solve Tarot 2.0 by adding many more fixed spreads

Nine existing spreads are already enough for the base product.

New value should come primarily from:

- better recommendation;
- better interpretation;
- dynamic/custom spread support;
- interaction;
- visual presentation;
- Journey / continuity.

## P2 — Question-first UX

Users should not need Tarot vocabulary before they can use Tarot.

The default V2 path should start from:

> "What do you want to ask / explore?"

Spread selection becomes a recommendation or secondary choice.

## P3 — One reading should feel like one session

Prefer one main Discord session message that changes state over time rather than producing many unrelated messages.

Exceptions are allowed for:

- ephemeral controls;
- long content attachments;
- follow-up answers where Discord component limits require a separate response;
- technical fallback/error messages.

## P4 — Clarifier is not reroll

A clarifier:

- adds a new card;
- targets an existing position/question;
- does not replace the original spread;
- does not silently reroll unwanted cards.

Default limit: **1 clarifier per reading**. Deep/custom reading may allow up to 2 if explicitly designed.

## P5 — Tarot is reflective, not deterministic prophecy

The reading should:

- identify patterns;
- connect cards;
- ground them in the user's context;
- distinguish uncertainty;
- avoid presenting outcomes as fixed fate.

## P6 — Do not over-gamify Tarot

Avoid:

- daily streak pressure;
- XP / level system;
- collectible/gacha Tarot;
- engagement farming;
- unlimited rerolls.

Journey should feel like a reflection journal, not a retention mechanic.

## P7 — Mobile readability first

Most renderer decisions should be checked at Discord-mobile scale.

A beautiful desktop board that becomes unreadable on a phone is not acceptable.

---

# 5. UX 2.0

## 5.1 Question-first Launcher

### Current problem

The current launcher exposes Tarot implementation choices early:

- spread;
- reader style;
- question;
- context.

This is useful for experienced users but can feel like configuration rather than conversation.

### V2 target

Primary launcher question:

> **What do you want to look at today?**

Primary CTA:

`✏️ Nhập câu hỏi`

After question input, Asumi analyzes the intent and offers:

> **Asumi đề xuất: Two Paths · 5 lá**  
> Because the question compares two paths and benefits from explicit trade-offs.

Controls:

- `✨ Dùng đề xuất`
- `🃏 Chọn kiểu khác`
- style remains secondary / optional.

### Backward compatibility

Existing slash parameters must continue working:

- explicitly supplied spread should be honored;
- prefix aliases should remain valid;
- existing users should not be forced through the smart launcher.

---

## 5.2 Smart Spread Recommendation

Move spread recommendation into the normal launcher rather than keeping it only as a separate command.

Recommendation should consider:

- comparison / choice question;
- timeline question;
- one clear focused question;
- wellbeing / internal-state question;
- broad complex situation;
- yes/no wording;
- no question / Daily intent.

Recommendation should produce:

```text
spread_key
spread_name
reason
confidence or suitability
```

If confidence is low, prefer a safe fixed spread such as `single`, `ppf`, or `horseshoe` rather than inventing complexity.

---

# 6. Single-Message Session Lifecycle

Target lifecycle:

```text
SETUP
→ SHUFFLING
→ FACE_DOWN
→ REVEALING
→ READING_READY
→ FINAL_READING
→ OPTIONAL_CLARIFIER/FOLLOWUP
→ COMPLETE
```

The same main Discord message should be edited through these states whenever practical.

## Suggested user-visible state

### Shuffling

> Asumi is preparing the spread...

### Revealing

`● ● ○ ○ ○   2/5 revealed`

> Asumi is already reading the relationships between the cards...

### AI ready

> ✓ Reading ready

### Final

Final reading + action buttons.

---

# 7. Micro Reveal

Every card flip should provide a small immediate reward.

Example:

> **II · Hiện tại — The Moon · Reversed**  
> `Mơ hồ · lo âu · trực giác bị nhiễu`

Rules:

- short;
- deterministic or card-data based where possible;
- not a full AI paragraph;
- do not spoil the whole final interpretation;
- keep position + orientation visible.

This reduces the feeling that card-flipping is only cosmetic.

---

# 8. Final Reading Presentation

Do not present the final AI response as one large undifferentiated Markdown block.

Target sections:

## 8.1 Core Message

2–3 concise sentences summarizing the central reading.

## 8.2 The Story Between the Cards

Focus on:

- reinforcement;
- contradiction;
- movement;
- dominant suit;
- Major Arcana concentration;
- important position relationships.

## 8.3 What to Do Now

1–3 practical implications or reflection prompts.

## 8.4 What the Spread Cannot Say for Certain

Explicit uncertainty / unresolved variables.

## 8.5 Key Card

The card carrying the strongest thematic weight and why.

### Final controls

Primary:

- `🃏 Làm rõ`
- `❓ Hỏi thêm`
- `🔍 Vì sao?`

Secondary:

- rating;
- optional recap;
- Journey-related action later.

---

# 9. Clarifier Card

Clarifier is one of the highest-priority V2 features.

## 9.1 Flow

User clicks:

`🃏 Làm rõ`

Show an ephemeral target selector:

> What do you want to clarify?

Possible targets:

- future;
- obstacle;
- advice;
- a specific card / position;
- custom spread position.

Then draw **one new card**.

## 9.2 Interpretation

AI receives:

- original question;
- original spread;
- original reading summary;
- target position;
- target card;
- clarifier card;
- orientation;
- user context.

AI should explain the relationship between the original target and clarifier.

Do not regenerate the whole reading unless explicitly requested.

## 9.3 Limits

Default:

- max 1 clarifier per reading.

Possible exception:

- max 2 for deep/custom reading.

No unlimited reroll.

---

# 10. Reading Session / Multi-turn Follow-up

Current system already has a follow-up concept. V2 should turn it into a coherent reading session.

Session context should include:

- original question;
- real-world context;
- spread schema;
- drawn cards;
- final reading structure;
- clarifier if any;
- prior follow-up questions;
- prior follow-up answers.

Suggested limit:

- 3 follow-ups per reading;
- session expires after approximately 10–15 minutes of inactivity.

The exact expiration policy can be tuned during implementation.

---

# 11. "Why?" Explanation

Button:

`🔍 Vì sao?`

Purpose:

- improve trust;
- explain the reading using visible card evidence.

Example:

> Asumi emphasizes uncertainty because Two of Swords is in the Present position while The Moon appears in the Future position. Both reinforce incomplete information, so the reading is "do not lock the decision yet", not "something bad will happen."

This is **not** a request to expose hidden chain-of-thought.

Implementation should generate a concise user-facing rationale based on:

- cards;
- positions;
- orientation;
- known spread relationships.

---

# 12. Smart Custom Spread

This is the flagship V2 intelligence feature, but it should not be in the first implementation milestone.

## 12.1 Example

User question:

> "Should I keep building this project alone or bring another person in?"

AI may propose:

1. current situation;
2. strength of staying solo;
3. weakness of staying solo;
4. what collaboration could add;
5. best priority now.

## 12.2 Safety / validation contract

AI generates a **spread schema only**.

It must never directly choose the resulting cards.

Suggested schema:

```json
{
  "title": "...",
  "intent": "...",
  "reason": "...",
  "positions": [
    {
      "id": "current_state",
      "title": "...",
      "description": "..."
    }
  ]
}
```

Validation:

- 3–7 cards only;
- unique position IDs;
- bounded title/description length;
- no duplicate positions;
- no unsafe/private third-party framing;
- fallback to known spread on invalid schema.

Normal engine still performs:

`schema → draw → render → interpretation`.

---

## T20.7 implementation status — COMPLETE

Implemented 2026-10-05:

- schema-only AI generation with no card selection;
- validated 3–7 unique positions with bounded text and privacy/card-field guards;
- fixed-spread fallback when schema generation is invalid/unavailable;
- deck-owned custom draw with existing fatigue behavior;
- launcher integration plus existing dynamic Reading Board reuse.

# 13. Tarot Journey

Journey evolves current history into a reflection view.

Possible command:

`/tarot_journey`

## 13.1 30-day summary

Potential metrics:

- number of readings;
- suit distribution;
- Major Arcana ratio;
- repeated cards;
- repeated reversed cards;
- common topic tags;
- theme progression;
- most-used spread.

Example:

```text
14 readings · last 30 days

Cups       31%
Swords     27%
Wands      23%
Pentacles  19%

Repeating card: The Hermit ×3
Major Arcana: 36%

Recent theme:
Decision → Clarity → Action
```

## 13.2 Interpretation limits

Journey analytics should be based on stored reading metadata and card statistics.

Avoid pretending statistical repetition proves fate or psychological diagnosis.

---

## T20.8 implementation status — COMPLETE

Implemented 2026-10-05:

- 30-day query over stored Tarot history only;
- suit distribution with coherent percentages, Major Arcana ratio, repeated/reversed-repeat cards;
- topic progression and most-used spread;
- `/tarot_journey` plus `.m tarot journey`;
- dedicated Journey Card renderer with explicit non-fate/non-diagnostic framing.

# 14. Renderer 2.0

Renderer V2 is a primary release feature, not optional polish.

## 14.1 Reading Board

Current renderer should evolve from "arrange cards on an image" toward a reusable **Reading Board**.

The board should include:

- spread title;
- card positions;
- face-down/face-up state;
- card orientation;
- progress;
- subtle state emphasis.

Do **not** render the full AI reading paragraph into the image.

Discord embed/text remains the content layer.

## 14.2 Visual hierarchy

Potential visual states:

- normal card;
- newly revealed card;
- reversed card;
- Major Arcana;
- Advice position;
- Outcome position;
- Key Card;
- Clarifier target;
- Clarifier card.

Use restrained emphasis:

- border;
- ring;
- small tag;
- subtle glow.

Avoid turning every card into a different UI style.

---

# 15. Visual Direction

Target mood:

> **dark celestial + muted violet + warm gold + blue-grey**

Characteristics:

- modern;
- friendly;
- slightly mystical;
- premium;
- readable;
- not overly gothic;
- not cluttered with moons/stars everywhere.

Asumi's friendly identity should remain visible.

Card art remains the visual focal point.

---

# 16. Responsive Render Layouts

Do not use one canvas ratio for every spread.

Suggested starting targets:

| Spread size | Layout concept | Approx canvas |
|---|---|---|
| 1 | Portrait Hero | 1080×1350 |
| 3 | Horizontal / gentle arc | 1400×900 |
| 4 | Diamond | 1300×1100 |
| 5 | Cross / fan | 1300×1100 |
| 6 | 2×3 | 1500×1150 |
| 7 | Horseshoe | 1500×1150 |
| 10 | Celtic-specific | 1600×1350 |
| Dynamic 3–7 | Template selected by card count | variable |

These are design targets, not immutable constants. Validate actual Discord compression and mobile readability.

---

# 17. Dynamic Layout Contract

Renderer should eventually accept a layout/spread schema instead of knowing only hardcoded spread keys.

Conceptual input:

```text
spread metadata
positions[]
drawn cards[]
revealed position IDs
emphasis state
clarifier relationship
```

Known fixed spreads can still provide custom templates.

Dynamic spread uses general templates by card count.

---

# 18. Additional Render Outputs

## 18.1 Final Spread Board

A cleaner complete version after all cards are revealed.

## 18.2 Clarifier Board

Visually communicates:

```text
TARGET CARD
    ↓
CLARIFIER
```

## 18.3 Reading Recap Card

Optional portrait output suitable for saving/sharing.

Should contain only:

- Asumi Tarot branding;
- hero/key card;
- short headline;
- one takeaway;
- spread name;
- date.

Do not put the entire reading on the recap image.

## 18.4 Journey Card

Visual 30-day summary with:

- reading count;
- suit distribution;
- repeated card;
- Major ratio;
- current theme.

---

# 19. System Prompt 2.0

Prompt quality is a core V2 deliverable.

## 19.1 Persona

Target persona:

> Asumi is an intelligent Tarot reader who observes carefully, speaks naturally, and connects card symbolism to the user's actual situation. She does not perform exaggerated mysticism, does not speak as an all-knowing prophet, and does not turn every difficult card into generic healing language.

`auto` remains the primary personality.

Existing style IDs remain compatible:

- `auto` — adaptive natural Asumi;
- `neutral` — calm, direct, reflective;
- `healer` — softer and supportive;
- `chaos` — playful when appropriate, never unserious about serious topics.

Styles modify delivery, not core reasoning quality.

---

# 20. Prompt Reasoning Contract

Internal prompt structure should encourage:

```text
OBSERVE
→ CONNECT
→ INTERPRET
→ GROUND
→ UNCERTAINTY
```

## Observe

Use:

- card;
- orientation;
- position;
- spread purpose;
- dominant suits;
- Major count;
- repeated cards;
- clarifier;
- contradiction.

## Connect

Look for:

- reinforcement;
- conflict;
- progression;
- transition;
- missing element;
- center of gravity.

## Interpret

Apply the pattern to the user's actual question/context.

Do not simply repeat textbook card meanings.

## Ground

Explain what the pattern could look like in real life.

## Uncertainty

Separate:

- strong signal;
- plausible suggestion;
- unknown / dependent on user choice.

---

# 21. Anti-Robot Prompt Rules

The V2 prompt should explicitly discourage repetitive template language.

Avoid repeatedly using:

- "Lá bài này cho thấy..."
- "Điều này có nghĩa rằng..."
- "Vũ trụ muốn nhắn nhủ..."
- "Hãy tin tưởng vào hành trình của mình..."
- "Năng lượng của lá bài..."

These phrases are not absolutely forbidden, but they should not become structural defaults.

Additional rules:

- no generic greeting at the start of every reading;
- do not thank the user for asking every time;
- do not force an inspirational closing;
- do not force a positive interpretation;
- do not call every difficulty "an opportunity for growth";
- do not produce one mechanically identical paragraph per card;
- do not overuse emojis;
- vary sentence rhythm;
- speak to the user's actual question.

---

# 22. Tone Adaptation

Examples of desired tone.

## Casual

> "Queen of Wands ở đây có hơi hướng 'đủ quan sát rồi, tới lúc tự cầm lái'."

## Serious decision

> "Điểm đáng chú ý không phải hướng nào tốt hơn tuyệt đối, mà là hiện tại bạn chưa có cùng mức thông tin cho cả hai lựa chọn."

## Emotional

> "Three of Swords ở vị trí này không nhất thiết báo một cú sốc mới. Nó giống một vết đau cũ vẫn đang ảnh hưởng cách bạn đọc tình huống hiện tại hơn."

Natural does not mean meme-heavy.

---

# 23. Memory Rules

Existing user Tarot memory is valuable, but V2 should tighten when it is used.

## Memory may be used when:

- prior reading is clearly about the same topic;
- user asks to continue;
- repeated-question detection finds high similarity;
- card repetition is relevant to Journey context.

## Memory should not be injected merely because data exists.

Do not force statements such as:

> "Last time you asked about work..."

when the new question is unrelated.

Memory must remain user-controllable through existing memory preference / forget flows.

---

# 24. Same-question Awareness

If a highly similar question was asked recently, Asumi may offer:

- `↩️ Tiếp tục quẻ cũ`
- `🔮 Xem tình hình hiện tại`
- `🆕 Xem như câu hỏi mới`

This is advisory, not a block.

The user can always start a new reading.

---

# 25. AI Output Schema V2

Prefer structured fields instead of asking the model to return one giant preformatted Markdown block.

Suggested conceptual schema:

```json
{
  "headline": "...",
  "core_message": "...",
  "card_insights": [],
  "connections": [],
  "dominant_theme": "...",
  "key_card": "...",
  "practical_takeaway": [],
  "uncertainty": "...",
  "suggested_clarifier_targets": [],
  "journey_tags": [],
  "mood_tag": "...",
  "topic_tag": "..."
}
```

`full_reading` may remain temporarily for backward compatibility, but UI should increasingly render from structured fields.

---

# 26. Session Data Model Direction

Potential new concepts.

## Reading Session

Fields may include:

```text
session_id
history_id
user_id
guild_id
channel_id
created_at
expires_at
state
followup_count
clarifier_count
```

## Follow-up

```text
session_id
sequence
question
answer
created_at
```

## Clarifier

```text
history_id/session_id
target_position_id
card_id
is_reversed
interpretation
created_at
```

## Journey metadata

```text
topic_tag
mood_tag
dominant_suit
major_ratio
key_card
custom_spread_schema
```

Do not create all tables blindly in one migration. Add only what the implemented milestone needs.

---

# 27. Architecture Direction

Do not perform a large-bang refactor merely to match this tree.

Target direction over time:

```text
features/tarot/
  cog.py
  deck.py
  flavor.py
  manager.py

  reading/
    engine.py
    schema.py
    prompt.py
    session.py

  journey/
    service.py
    analytics.py

  rendering/
    spread_renderer.py
    recap_renderer.py
    journey_renderer.py

  ui/
    launcher.py
    reading_view.py
    clarifier.py
    followup.py

  assets/
```

Migration should be incremental.

The existing modules may remain until a milestone gives a clear reason to split them.

---

# 28. Milestones

## T20.0 — Baseline & Contract Lock

Goal: prepare for safe V2 work without behavior changes.

Tasks:

- document current behavior;
- document V2 master plan;
- document handoff process;
- identify regression tests;
- record current DB schema and public commands;
- fix stale documentation where necessary.

**This repository-preparation work is what the user requested before implementation.**

---

## T20.1 — Prompt & Reading Engine 2.0 — COMPLETE

Implemented:

- new persona prompt;
- Observe → Connect → Interpret → Ground → Uncertainty;
- structured V2 response;
- anti-robot rules;
- improved `auto` tone adaptation;
- improved final-reading schema;
- evidence-based "Why?" generation support.

Acceptance:

- reading does not feel like identical per-card templates;
- direct connection to user question;
- explicit uncertainty;
- existing styles remain compatible.

Implementation notes are recorded in `docs/TAROT_V2_HANDOFF.md` and `docs/TAROT_V2_PROMPT_SPEC.md`. The rich result API is available now, while Discord UI consumption remains backward-compatible until later milestones.

---

## T20.2 — Question-first Launcher — COMPLETE

Implemented:

- primary question entry;
- integrated spread recommendation;
- use-recommendation CTA;
- manual spread override;
- context entry;
- style as secondary choice;
- initial same-question awareness.

Acceptance:

A new user can start a suitable reading without knowing Tarot spread names.

Implementation keeps manual spread selection and direct-command compatibility, while the launcher requires an explicit recommendation acceptance or manual spread selection before starting.

---

## T20.3 — Reading Session UX — COMPLETE

Implemented:

- one-message lifecycle where practical;
- shuffling/revealing/ready state;
- compact card controls;
- progress indicator;
- micro reveal;
- clean completion state.

Acceptance:

Reading flow feels coherent and channel noise is reduced.

---

## T20.4 — Renderer 2.0 — COMPLETE

Implemented:

- Reading Board;
- mobile-friendly responsive layouts;
- position labels;
- reversed indicator;
- key-card emphasis;
- fixed spread templates;
- dynamic layout contract;
- Final Spread Board.

Acceptance:

- all 9 existing spreads render correctly;
- labels are readable on Discord mobile;
- existing card assets remain valid;
- renderer has regression coverage for major layout classes.

---

## T20.5 — Clarifier — COMPLETE

Implemented:

- clarifier target picker;
- one-card draw;
- Clarifier Board;
- contextual clarifier interpretation;
- clarifier limit;
- persistence where needed.

Acceptance:

Clarifier adds context without rerolling original cards.

Implementation notes:
- owner-only ephemeral target picker, with structured-AI suggestions promoted but not forced;
- exactly one clarifier card, excluding every card in the original spread;
- deterministic retry binding to the original spread/target;
- original spread + TARGET → CLARIFIER visual board;
- bounded structured AI interpretation tied only to the selected target and new card;
- 1/1 limit committed only after successful Discord delivery;
- delivered Clarifiers persist separately so the original history record remains immutable.

### Tarot 2.0 release boundary

**T20.1 through T20.5 are complete and form the Tarot 2.0 release in Asumi 2.9.0.**

---

## T20.6 — Multi-turn Reading Session — COMPLETE

Implemented 2026-10-05:

- bounded post-reading session state;
- up to 3 contextual follow-up turns;
- prior Q/A + clarifier context carried forward;
- owner-only evidence-oriented **Why?** control;
- failed generation/delivery does not consume a follow-up slot;
- 10-minute default inactivity expiry and cleanup.

Original scope:

Implement:

- up to ~3 follow-ups;
- session state;
- expiration;
- "Why?";
- cleanup and cancellation.

Target release: Tarot 2.1 candidate.

---

## T20.7 — Smart Custom Spread

Implement:

- AI spread-schema generation;
- validation;
- 3–7 card limit;
- dynamic renderer;
- fallback to known spread.

Target release: Tarot 2.1 candidate.

---

## T20.8 — Tarot Journey

Implement:

- Journey analytics;
- repeating cards;
- suit distribution;
- Major ratio;
- topic progression;
- `/tarot_journey`;
- Journey renderer.

Target release: Tarot 2.2 candidate.

---

## T20.9 — Recap & Polish

Implement:

- Recap Card;
- share/save-friendly render;
- mobile polish;
- accessibility;
- copy cleanup;
- error states;
- performance review.

---

# 29. Versioning Guidance

Important distinction:

- Bot currently uses repository-wide versions such as `2.8.4`.
- "Tarot 2.0" is a **feature/product generation name**, not necessarily the repository's next semantic version.

When implementation begins, choose repository version bumps according to the project's existing semantic version rules.

Do not change repository version simply because planning docs were added.

---

# 30. Backward Compatibility Requirements

During V2 work:

- preserve existing spread keys;
- preserve prefix aliases unless intentionally deprecated;
- preserve slash command behavior;
- preserve memory preference and forget capability;
- preserve Daily cooldown semantics unless a milestone explicitly changes them;
- preserve history records or migrate them safely;
- preserve Reader style IDs;
- preserve current card IDs;
- preserve current Rider-Waite asset references;
- preserve existing DB data.

Any incompatible DB change requires explicit migration logic.

---

# 31. Reliability Requirements

All major V2 interaction flows need failure behavior.

Examples:

## AI failure

- cards remain usable;
- deterministic card details still render;
- user gets a concise fallback explanation;
- session should not deadlock.

## Renderer failure

- fall back to text/embed card list;
- do not lose the reading.

## Clarifier failure

- original reading remains intact;
- clarifier count should not be consumed if no clarifier was successfully delivered.

## Session timeout

- disable controls cleanly;
- retain final reading;
- no orphan background task.

## Discord edit/send failure

- do not create duplicate readings unnecessarily;
- preserve original history consistency.

---

# 32. Testing Strategy

Before shipping V2, add tests around behavior rather than only implementation details.

Minimum categories:

## Prompt / schema

- valid structured output;
- malformed output fallback;
- no required field silently missing;
- style compatibility;
- uncertainty section present.

## Launcher

- recommendation flow;
- explicit spread override;
- question-required spreads;
- Daily behavior.

## Session

- reveal one;
- reveal all;
- AI ready before/after reveal;
- timeout;
- owner-only controls.

## Clarifier

- allowed target;
- limit;
- no original-card mutation;
- failure preserves session.

## Renderer

- 1-card;
- 3-card;
- 5-card;
- Celtic;
- dynamic 3–7;
- reversed card;
- clarifier emphasis.

## Persistence

- history;
- memory preference;
- migration;
- session cleanup;
- Journey metadata.

---

# 33. Non-goals for Tarot 2.0

Do not add by default:

- 20+ extra fixed spreads;
- Tarot XP;
- Tarot levels;
- daily streak pressure;
- gacha;
- collectible cards;
- runtime AI-generated Tarot card art;
- deterministic compatibility percentages;
- horoscope system unrelated to Tarot;
- many new personas;
- unlimited clarifiers;
- unlimited rerolls.

These may only be revisited if the user explicitly asks.

---

# 34. UX Copy Direction

Copy should be:

- natural Vietnamese;
- concise;
- specific;
- not overly ceremonial;
- not packed with mystical filler;
- not excessively cute;
- not robotic.

Avoid a UI where every line contains an emoji.

Use emojis primarily as navigation/state markers.

---

# 35. Accessibility / Mobile Checklist

Before release:

- all important text readable at Discord mobile thumbnail size;
- avoid low-contrast gold-on-purple;
- labels must not depend on color alone;
- reversed state needs text/marker, not only rotation;
- progress must have number text, not only dots;
- button labels must remain understandable without emoji;
- no critical meaning hidden only in the image.

---

# 36. Performance Constraints

Tarot V2 will increase:

- renderer work;
- AI prompt complexity;
- session state;
- DB writes.

Implementation should preserve:

- asynchronous rendering via worker thread where appropriate;
- background AI task behavior;
- bounded caches;
- bounded session lifetime;
- cancellation on abandoned/deleted readings;
- no unbounded in-memory history.

Do not add expensive AI calls for deterministic UI details that can be derived from card metadata.

---

# 37. Recommended Implementation Order

When the user approves implementation, follow this order:

1. T20.1 Prompt/Schema
2. T20.2 Question-first launcher
3. T20.3 Session UX
4. T20.4 Renderer 2.0
5. T20.5 Clarifier
6. release Tarot 2.0
7. T20.6 Follow-up session
8. T20.7 Smart Custom Spread
9. T20.8 Journey
10. T20.9 Recap/polish

Do not start with Journey or Custom Spread before the base session and renderer contracts are stable.

---

# 38. Definition of Done — Tarot 2.0

A new user should be able to:

1. run `/tarot`;
2. describe a concern without knowing spread names;
3. receive a sensible spread recommendation;
4. start a visually clear reading;
5. reveal cards with meaningful micro feedback;
6. read a natural, non-template interpretation;
7. understand which cards support the interpretation;
8. draw a bounded clarifier;
9. keep the reading coherent throughout one session.

If this flow is smooth, the feature has earned the "Tarot 2.0" name.

---

# 39. Future-agent rule

If you are an AI/agent opening this repository in a fresh session:

1. Read `AGENTS.md`.
2. Read this file completely.
3. Read `docs/TAROT_V2_HANDOFF.md`.
4. Read `docs/TAROT_V2_PROMPT_SPEC.md` before T20.1/AI work.
5. Read `docs/TAROT_V2_RENDERER_SPEC.md` before T20.4/presentation work.
6. Read `docs/TAROT_SYSTEM.md`.
7. Inspect current `features/tarot/` code before making assumptions.
8. Check `core/version.py` and latest commits because the code may have advanced beyond this baseline.
9. Do **not** assume every milestone above has been approved or implemented.
10. Update the handoff file whenever a milestone is started, completed, changed or rejected.
11. Preserve current user-facing behavior unless the active milestone intentionally changes it.
12. If implementation and documentation disagree, treat code as the current runtime truth and update the docs as part of the same change.
