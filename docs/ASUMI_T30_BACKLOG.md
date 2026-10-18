# T30 — Dungeon Misfits: Implementation Backlog & Handoff

> **Status as of 2026-10-18: DESIGN ONLY. Nothing in T30.0–T30.7 is implemented or deployed.**
> Baseline: HoenMike/DiscordMikeBot, main 762a960, Asumi 3.14.7.
> Read first: docs/ASUMI_T30_DUNGEON_MISFITS_GDD.md and docs/ASUMI_T30_ENGINE_SCHEMA.md, then AGENTS.md.
> Owner clarification: **the whole D&D feature plays in a dedicated Discord channel, NOT the main chat**.

## 1. Execution principles

- Work in **focused feature branches and one PR per goal**, not one giant RPG rewrite. Each completed goal must update this handoff with actual code paths, tests, deploy status and next steps. Do not ask for repeated approval after the plan is accepted, but preserve code review/CI and production gates.
- Never claim a milestone shipped because docs/PR/tests exist. Status vocabulary: PLANNED -> CODE_READY -> CI_PASSED -> MERGED -> DEPLOYED -> LIVE_ACCEPTED. Record separately for each goal.
- Keep Tarot board/reading, Feedback inside historic dashboard, social embed, assistant chat/search, deployment queue and existing Slash Command sync safety unchanged.
- New feature under features/dnd/, nonsecret flags/limits only under core/constants.py. Secrets only via existing secret management; do not move policy flags into Render env.
- Stage 0 can be testable as a local CLI simulated dungeon; stage 3 is the first **end-to-end Discord-playable run**. Stages 4–7 improve it incrementally.
- Per guild only one configured dedicated channel and one nonterminal run for MVP. Outside this channel, D&D commands return only ephemeral guidance and cannot mutate gameplay; nothing should be sent to #general.
- All models must be replaceable; no provider-dependent game rules. Deterministic local fallback for parser/narration.
- Config flag default OFF until controlled owner opt-in and live permission smoke. Do not globally sync a partially initialized Cog. Add D&D to the extension registry only when guarded startup initialization works, and do not weaken EXPECTED_CORE_SLASH_COMMANDS safety lock.

## 2. Proposed package layout

~~~text
features/dnd/
  __init__.py
  cog.py                   # slash group + interaction authorization
  config.py                # code-owned T30 constants/policies
  models.py                # typed state & ActionSpec
  state_machine.py         # pure transition guards
  rules.py                 # rolls/effects/status/initiative
  balance.py               # unit simulator + thresholds
  characters.py            # prompt-to-balanced-character validator
  content/
    mushroom_dungeon.json  # curated/versioned templates
  content_loader.py
  store.py                 # transactional game repository and migrations
  service.py               # orchestrates DB, engine, AI and output
  intent_parser.py         # approved action mapping + fallback
  narrator.py              # storytelling only, no state changes
  views.py                 # lobby / board / ephemeral user actions
  outbox.py                # recoverable Discord board projection
  privacy.py               # limits, exports and retention
  telemetry.py             # bounded, scrubbed operational events
tests/
  test_dnd_rules.py
  test_dnd_state_machine.py
  test_dnd_store.py
  test_dnd_characters.py
  test_dnd_party.py
  test_dnd_intents.py
  test_dnd_discord_acl.py
  test_dnd_recovery.py
  test_dnd_balance.py
docs/
  ASUMI_T30_DUNGEON_MISFITS_GDD.md
  ASUMI_T30_ENGINE_SCHEMA.md
  ASUMI_T30_BACKLOG.md
~~~

Exact file boundaries may evolve, but **do not** put combat rules inside Cog callbacks or AI response functions.

## 3. Goal-by-goal backlog

### T30.0 — Foundation, migrations and deterministic rules [PLANNED, size L]

Dependencies: none.

Tasks:
- T30.0a: agree on game enums, room/character/action schemas, original-rule scope, stat budget, failure/resume semantics. Write versioned sample character and two golden round fixtures.
- T30.0b: build pure-python state_machine and rules skeleton, validate every legal/illegal transition; seeded/test-fixed d20 rolls, immutable ResolutionReport and snapshot hash.
- T30.0c: design and add game-specific versioned SQL migration, channel config, session/round/member/event tables, partial unique indexes and interaction receipt/outbox tables as specified.
- **T30.0d critical:** add a *verified atomic transactional store API* for Turso and SQLite; integration-test both. Current core/db.py Turso path auto-commits each statement and SQLite requires manual commit. Do not assume several db_client.execute calls form a single transaction. Add CAS, claim/lease, idempotent event append and fail-closed cloud guard.
- T30.0e: implement curated room/content loader and validation, disallow unbounded model-supplied content IDs; a small simulation CLI can resolve a sample encounter without Discord or AI.
- T30.0f: settings source-of-truth / default OFF, error taxonomy, sanitized telemetry, public-game-channel guard layer.

Deliverable: unit-tested library and reproducible CLI encounter; **no live player feature yet**.
Exit: SQLite+Turso transaction tests, no duplicate CAS/event under two-worker race, recovery after every transaction boundary, and no changes to existing game-unrelated commands.

### T30.1 — Prompt-driven character creator [PLANNED, size M]

Dependencies: T30.0 schema/validator and safe Discord entry.

Tasks:
- Admin-only /dnd setup channel selector and permission verification; enable only on explicit confirmation, channel binding saved to Turso.
- /dnd character create opens a modal inside the designated game channel; character prompt <=500 chars, name <=40.
- AI proposes flavor/archetype/skills from predefined effect-budget archetypes; strict output schema and local fallback.
- Ephemeral preview shows 4 attributes (total 8, each <=4), HP, Focus, 2 skills, 1 bounded quirk, plus Confirm/Edit/Reroll. Require explicit Confirm for persistence.
- One active character per user/guild; no changing character while in an active run. Privacy: only store approved character summary, no general-chat history, no public raw prompt.
- Route ordinary general-chat @Asumi messages through existing assistant unchanged, never to the game engine.

Deliverable: a character is safely created, previewed and reused after bot restart, without any public main-chat posting.
Exit: malformed/hostile prompts cannot create overpowered abilities, one-user concurrent confirms create one character, cross-guild/cross-channel cases rejected ephemerally, provider timeout yields usable local draft.

### T30.2 — Party lobby & dedicated-channel UX [PLANNED, size M]

Dependencies: T30.1.

Tasks:
- /dnd start, join, ready, leave, status, cancel; single live session per guild enforced by unique DB index, not in-memory semaphore.
- Dedicated game channel only; one lobby board (Components V2 where validated, classic fallback where needed), roster 2–5, ready status, run settings.
- Per-button revalidation of guild, target channel, member, leader and current session revision; stale buttons fail politely.
- Start only when at least 2 players and everyone Ready; leader and server admin cancellation controls with explicit confirmation.
- Persist board_message_id and build rehydration/recreate UI after restart. Handle removed channel or missing permissions by pausing with safe admin diagnostics.
- Keep commands and Help concise in Vietnamese; optional English copy via structured strings, not hard-coded mixed UI.

Deliverable: multiplayer lobby can form, ready, cancel and survive restart inside #asumi-dungeon.
Exit: 2–5 join; sixth refused; outsider click refused; global command outside channel never changes DB; no accidental auto-pings.

### T30.3 — Deterministic playable dungeon [PLANNED, size XL, **first complete run**]

Dependencies: T30.2 and T30.0 atomic game store.

Tasks:
- Implement a 3–4-room content pack: short intro, trap/social event, skirmish, 2-phase boss; branch variants from curated rules.
- Round/scene state transitions, 90-second default deadline and "all submitted" early lock; persisted UTC deadlines.
- Preset actions ATTACK/DEFEND/ASSIST/ABILITY/INTERACT/REPOSITION/RETREAT and valid target selection.
- Engine: d20/DC, initiative, 4 stats, HP/Focus, zone, statuses, enemy telegraph, synergy, party wipe, win/retreat. Record exact dice and events.
- AI-free template narrator; stable board update and short round output; gameplay proceeds without model access.
- Implement atomic round resolution, event/snapshot parity, outbox recovery and one unique terminal result.
- Simulate combat balance for 2, 3 and 5 players, multiple archetypes and cooperative/no-cooperative strategies; tune only versioned config for **new** sessions.

Deliverable: Discord friends can play one full dungeon and defeat or lose to a boss even with AI disabled.
Exit: race-safe dual submissions; a crashed deploy after a committed result cannot reroll, duplicate events or publish reward twice; 10 pilot runs planned for UX after CI.

### T30.4 — AI DM and free-form action intelligence [PLANNED, size L, **MVP boundary**]

Dependencies: T30.3.

Tasks:
- Action text modal with <=140 chars and optional @player coordination; map explicit Discord mentions to IDs, never infer identity from nicknames.
- Typed structured AI proposal -> validator -> deterministic ActionSpec; reject invented mechanics and handle unknown/ambiguous actions.
- Cooperative tactic mapping with recorded prerequisites and bounded +2 bonus, not a free bonus for simply being verbose.
- Narrator operates **after** game commit from immutable ResolutionReport, cannot write HP/loot or change dice. Local deterministic prose fallback when AI is slow or invalid.
- Batch expensive narrative once per round; bounded provider retries, per-run budget, bounded game-only context. Use neither Brave nor general-chat context.
- AI latency/error instrumentation, style guard, readable narrative and mechanical summary.
- Creator + combat prompt-injection tests; free-text intents cannot access private Discord channels or issue bot admin commands.

Deliverable: players freely describe actions and get genuinely different, rules-grounded, amusing DM narration.
Exit: impossible prompt doesn't cheat; cooperative 2-player tactic has bounded measurable effect; mismatched narrator text rejected/replaced; full run still works with AI down. Feature may be opt-in MVP pilot only after real Discord tests.

### T30.5 — Loot, inventory & horizontal progression [PLANNED, size M]

Dependencies: T30.4 stable core.

Tasks:
- Unique terminal reward grants per session/user, inventory item instances bound to grant; atomic with terminal event, no repeat farming via retries.
- 8–12 original affix/item prototypes, with equal-budget tradeoffs rather than escalating global stat caps.
- Character profile: completed runs, memorable moments, quirk/title unlocks, limited equipment slots and gear presets.
- Reward UI inside game channel, personal inventory ephemeral; no unsolicited general-channel posts or DMs.
- Storage quotas, retention/export/delete semantics and moderated item flavor.

Deliverable: character progression motivates another run without making newcomers irrelevant.
Exit: double-click/restart cannot mint more loot; rerun stats remain bounded; owner can inspect disputes from event/reward IDs.

### T30.6 — Production polish, resilience & rollout [PLANNED, size L]

Dependencies: MVP T30.0–T30.5 or can start reliability tests in parallel.

Tasks:
- Stress tests and migration compatibility on Turso, failure injection at all boundaries, slash-command sync safety, feature flag OFF->opt-in->rollback.
- Discord mobile and desktop acceptance of channel setup, character, lobby, combat and recap; long usernames and bilingual text.
- Persistent views after bot restart, deleted board recreation under documented safety policy; no duplicate noisy messages.
- Quotas, LLM provider cost ceilings and safe fallbacks; no private prompt dump in logs; visibility/permissions and admins.
- Admin monitoring in existing historical dashboard **only if explicitly approved**, otherwise diagnostics via existing logs and /dnd status.
- Session archival policy and player data removal workflow; incident/troubleshooting documentation; incremental versioning based on actual shipped code.

Deliverable: optional stable rollout for the private server.
Exit: regression and controlled real-guild acceptance report, no new critical regressions in existing features and zero main-chat game output.

### T30.7 — Expansion / only after MVP feedback [PLANNED, size variable]

Options, intentionally not blocking MVP:
- More curated dungeon/boss packs and story hooks tied to party achievements.
- Async cadence with stored per-round deadline (e.g. 12 hours), explicit pause/reminder policy, no unsolicited ping.
- Multiple concurrent parties only as **per-run threads under the configured game channel**, opt-in, per-thread ACL and state invariants.
- NPC relationships, environmental item combos, cosmetic character portraits and illustrated end cards; no image dependency for core play.
- Difficulty tiers with published expected clear rates and no paid advantages.
- Optional separate web/Activity viewer when demand proves Discord's layout inadequate; game engine remains portable.

Each expansion needs its own acceptance and cost/performance review.

## 4. Dependency graph

~~~mermaid
flowchart TD
  A[T30.0 Rules, atomic Turso store, schema] --> B[T30.1 Character & channel setup]
  B --> C[T30.2 Lobby/party]
  C --> D[T30.3 Playable deterministic dungeon]
  D --> E[T30.4 Free-form AI DM — MVP]
  E --> F[T30.5 Loot and horizontal progression]
  E --> G[T30.6 Robust rollout]
  F --> G
  G --> H[T30.7 Expansions/threads]
~~~

Do not reverse D and E: build the deterministic core first, then add AI. Character creator can test with a model earlier, but live combat must never rely on AI for lawful results.

## 5. Cross-cutting Definition of Done

For every implemented goal:
1. User workflow and authorization contract updated in docs and in /dnd help when behavior changes.
2. Strict channel isolation and stale-session/server ACL tests.
3. Pure-unit + integration tests and parity of game state/events.
4. Explicit DB migration test and rollback/compatibility notes.
5. Rate/AI budget tests with failed provider and timed-out Discord handling.
6. At least one happy-path and two negative-path Discord interaction QA cases.
7. No changes to historical dashboard shell or Tarot, Feedback, Search, Embed without separate scope approval.
8. PR description with test commands/results, changed paths, status, remaining live-guild acceptance; post-merge version/changelog only for actual behavior releases.
9. No claim of completion based only on code or mock; live deployment and guild smoke are separate gates.

## 6. Initial tracked test cases (must preserve IDs)

| ID | Scenario | Expected |
| --- | --- | --- |
| DND-001 | /dnd start in #general | Ephemeral pointer, no session, no public game message |
| DND-002 | Admin sets private channel lacking bot send/view permissions | Setup rejected, no active config mutation |
| DND-003 | 3 users join & Ready simultaneously | Exactly one lobby/session; correct roster |
| DND-004 | Outsider submits via old button | Rejected without state change |
| DND-005 | User revises 140-char intent twice before round lock | Last accepted revision only |
| DND-006 | Two workers resolve same round concurrently | One ROUND_RESOLVED event/one applied HP update |
| DND-007 | AI generates "damage=999"/unbounded skill | Strictly ignored/rejected by validator |
| DND-008 | Coordinated distract + spell | One bounded synergy if prerequisites pass |
| DND-009 | Participant is AFK | Guard fallback and round continues |
| DND-010 | Bot deploy crashes after commit, before Discord post | No reroll; outbox reconciles/updates board |
| DND-011 | Turso fails; core/db.py tries local fallback | Production refuses writes and pauses |
| DND-012 | Two reward buttons or terminal retries | One durable grant/member |
| DND-013 | Character prompt references other guild/private messages | No retrieval/cross-channel leak |
| DND-014 | Stale session button after cancellation | No mutation; polite private info |
| DND-015 | All characters defeated | FAILED, bounded end, no permanent character loss |
| DND-016 | Existing Tarot / Feedback / Search / embed tests | No behavioral regressions |
| DND-017 | User triggers /dnd while game channel not configured | Admin setup guidance only; no public output |
| DND-018 | User loses View Channel permission mid-run | Game action denied, no private state leak |
| DND-019 | LLM narrator absent/timeout | Exact mechanical report still visible |
| DND-020 | Rules/content update while session active | Session uses frozen rules/content version |

## 7. Suggested owner review gates

- **Gate A:** GDD + rules coefficients and isolated-channel policy accepted (this docs-only PR).
- **Gate B:** T30.0 transactional store/prototype validated before enabling any stateful game in production.
- **Gate C:** T30.3 end-to-end deterministic Discord test demonstrates the loop is fun.
- **Gate D:** T30.4 AI narrative and free-text intents demonstrate quality without compromising mechanics.
- **Gate E:** T30.6 rollout after mobile/readability/cost/reliability verification.

The design authorizes **planning, not automatic production deployment or merging this draft**. Future implementation work can proceed goal by goal in reviewed PRs when the owner explicitly starts execution.

## 8. Handoff prompt for Codex / coding agent

Please implement **only T30.0** of the Dungeon Misfits plan on a fresh branch from latest main. Read AGENTS.md, all three T30 docs and current core/db.py first. Keep all existing Asumi surfaces unchanged. First validate the Turso/SQLite transactional API with integration tests; do not let core/db.py's local fallback accept live production game writes. Implement versioned schemas, pure rules/state machine, CAS/outbox design and a deterministic CLI encounter. Add meaningful race/recovery tests. Commit code, tests and update status to CODE_READY/CI_PASSED only after evidence. Open a PR, do not merge or deploy until the required gates. Never emit gameplay into the general chat; all future interaction routes are scoped to the configured dedicated game channel.
