# T30 — Dungeon Misfits: Engine, Data Schema & Balance Contract

> Status: **PROPOSED, NOT IMPLEMENTED**. Initial coefficients to test, not empirically balanced.
> Companion: ASUMI_T30_DUNGEON_MISFITS_GDD.md; ASUMI_T30_BACKLOG.md.
> Version 0.1 schema. Design assumes SQLite-compatible Turso/libSQL, UTC ISO timestamps and Discord snowflake IDs stored as TEXT.

## 1. Authority boundaries

| Component | Can decide | Must not decide |
| --- | --- | --- |
| Discord adapter / Cog | Authenticate interaction, ACK, render allowlisted UI | Damage, rolls, loot |
| Intent interpreter (AI + validator) | Classify bounded text into approved ActionSpec; choose suggested allowed target | Commit state, create arbitrary mechanic IDs |
| Rules engine (pure Python) | Validation, turn order, checks, HP/Focus/status updates, rewards according to rules | Arbitrary natural-language prose |
| DM narrator (AI) | Concise story around immutable ResolutionReport | Change rules, invent damage, loot, buffs or dice |
| Transactional store | CAS/lease ownership, atomic commits, immutable event history, grant dedupe | Generate unlogged random outcome |
| Renderer/outbox | Publish compact board and narration in configured channel | Mutate combat state after successful send |

Domain logic should be pure and independently testable, separated from Discord and AI implementations. A source prompt is **data**, never an instruction to access the environment. No Discord history, Clef public search or Brave is required to resolve a run.

## 2. Canonical state machines

### Session state

~~~mermaid
stateDiagram-v2
  [*] --> LOBBY: create (configured channel)
  LOBBY --> RUNNING: 2-5 ready, start
  LOBBY --> CANCELLED: leader/admin cancel
  RUNNING --> PAUSED: leader/admin or recoverable outage
  PAUSED --> RUNNING: resume after valid recovery
  RUNNING --> COMPLETED: boss/alternative victory
  RUNNING --> FAILED: party wipe/retreat/round cap
  RUNNING --> CANCELLED: authorized confirmed cancel
  PAUSED --> CANCELLED: authorized confirmed cancel
  COMPLETED --> [*]
  FAILED --> [*]
  CANCELLED --> [*]
~~~

State enum: LOBBY, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED. The latter three are terminal and immutable except for idempotent publication/retention status. PAUSED preserves room, deadline remaining, members, dice/events. On resume, compute new deadline based on frozen remaining seconds, never count server downtime against players by accident.

Session stage within RUNNING:
ROOM_INTRO -> COLLECTING -> RESOLVING -> ROOM_COMPLETE -> (ROOM_INTRO next room | COMPLETED/FAILED).
ROOM_INTRO must commit scene content/telegraph first; COLLECTING accepts intents, RESOLVING is a leased worker operation; ROOM_COMPLETE applies prevalidated scene outcome and advances only once. Exploration, social choices and combat all share this stage/round machinery, with scene_type = EXPLORE|SOCIAL|TRAP|COMBAT|BOSS.

### Round state

~~~mermaid
stateDiagram-v2
  [*] --> COLLECTING
  COLLECTING --> LOCKED: deadline or all actors ready
  LOCKED --> RESOLVING: atomic worker lease
  RESOLVING --> COMMITTED: resolution + events + snapshot persisted atomically
  RESOLVING --> LOCKED: expired lease with no commit
  COMMITTED --> [*]
~~~

Invariants:
- Exactly **one** round may be COLLECTING/LOCKED/RESOLVING per active session; COMMITTED is immutable.
- User may replace own intent only in COLLECTING. Every accepted submission increments revision. Lock snapshots exactly one intent revision per member. Stale interaction revision returns informative ephemeral response.
- AI parse after locking is tied to frozen raw text hash/revision. On timeout invalid intent becomes Guard, preserving order and log; no invented abilities.
- Before rolling, atomically claim a lease keyed by session/round/current state_version. Only the winner may publish a committed ResolutionReport. On restart, recover expired lease; if COMMITTED exists, load it, NEVER recompute.
- Round advancement and event seq increments are optimistic CAS; scene terminal outcome may commit only once. Concurrent calls return current state, not an error that rolls again.
- The current core/db.py adapter **does not implement a unified multi-statement transaction**; T30.0 must provide a provider-verified atomic transaction/batch abstraction on Turso and SQLite with integration tests. No multi-step commit on existing independent db_client.execute calls.
- Production must fail closed on Turso unavailability. Core local SQLite fallback is not durable on the current Render deployment and could fork the game state; do not start/live-resume runs against that fallback.

## 3. Data storage model (SQL proposal; migration-reviewed before execution)

**Tables and cardinality:** one guild configuration -> many historical sessions; one user/guild -> one active character (MVP); one session -> 2–5 members, many rounds and append-only events; one user/round -> at most one active intent; one session/user -> at most one reward grant. All writes must be authorized server-side.

~~~sql
CREATE TABLE dnd_guild_config (
  guild_id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
  allow_threads INTEGER NOT NULL DEFAULT 0 CHECK(allow_threads IN (0,1)),
  updated_by TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE dnd_characters (
  character_id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  archetype TEXT NOT NULL,
  stats_json TEXT NOT NULL,
  skills_json TEXT NOT NULL,
  quirk_json TEXT NOT NULL,
  bio_json TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX uq_dnd_active_character
 ON dnd_characters(guild_id,user_id) WHERE active=1;

CREATE TABLE dnd_sessions (
  session_id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  leader_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN
    ('LOBBY','RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED')),
  stage TEXT NOT NULL,
  scene_type TEXT,
  scene_no INTEGER NOT NULL DEFAULT 0,
  round_no INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  content_version TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  state_json TEXT NOT NULL,
  rng_seed_id TEXT NOT NULL,
  board_message_id TEXT,
  deadline_at TEXT,
  paused_remaining_seconds INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  ended_at TEXT
);
CREATE UNIQUE INDEX uq_dnd_one_live_session
 ON dnd_sessions(guild_id)
 WHERE state IN ('LOBBY','RUNNING','PAUSED');
CREATE INDEX ix_dnd_sessions_channel ON dnd_sessions(guild_id,channel_id);

CREATE TABLE dnd_members (
  session_id TEXT NOT NULL REFERENCES dnd_sessions(session_id),
  user_id TEXT NOT NULL,
  character_id TEXT NOT NULL REFERENCES dnd_characters(character_id),
  character_snapshot_json TEXT NOT NULL,
  battle_state_json TEXT NOT NULL,
  ready INTEGER NOT NULL DEFAULT 0,
  joined_at TEXT NOT NULL,
  PRIMARY KEY(session_id,user_id)
);

CREATE TABLE dnd_rounds (
  session_id TEXT NOT NULL REFERENCES dnd_sessions(session_id),
  round_no INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('COLLECTING','LOCKED','RESOLVING','COMMITTED')),
  deadline_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  lock_snapshot_json TEXT,
  lease_owner TEXT,
  lease_until TEXT,
  resolution_event_seq INTEGER,
  created_at TEXT NOT NULL,
  committed_at TEXT,
  PRIMARY KEY(session_id,round_no)
);
CREATE UNIQUE INDEX uq_dnd_one_open_round
 ON dnd_rounds(session_id) WHERE state IN ('COLLECTING','LOCKED','RESOLVING');

CREATE TABLE dnd_intents (
  session_id TEXT NOT NULL,
  round_no INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  raw_intent TEXT NOT NULL,
  action_json TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  ready INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(session_id,round_no,user_id),
  FOREIGN KEY(session_id,round_no) REFERENCES dnd_rounds(session_id,round_no)
);

CREATE TABLE dnd_interaction_receipts (
  interaction_id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  session_id TEXT,
  actor_id TEXT NOT NULL,
  action_kind TEXT NOT NULL,
  result_code TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE dnd_events (
  session_id TEXT NOT NULL REFERENCES dnd_sessions(session_id),
  seq INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  actor_id TEXT,
  payload_json TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(session_id,seq),
  UNIQUE(session_id,idempotency_key)
);
CREATE INDEX ix_dnd_events_kind ON dnd_events(session_id,event_type);

CREATE TABLE dnd_reward_grants (
  grant_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES dnd_sessions(session_id),
  user_id TEXT NOT NULL,
  reward_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(session_id,user_id)
);

CREATE TABLE dnd_outbox (
  outbox_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES dnd_sessions(session_id),
  event_seq INTEGER NOT NULL,
  destination_channel_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PENDING','SENDING','SENT','RETRY','ABANDONED')),
  lease_until TEXT,
  message_id TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  UNIQUE(session_id,event_seq,kind)
);
CREATE INDEX ix_dnd_outbox_due ON dnd_outbox(status,lease_until);

-- T30.5 only: item instances rather than a scalar inventory count.
CREATE TABLE dnd_inventory_items (
  item_instance_id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  item_def_id TEXT NOT NULL,
  source_grant_id TEXT NOT NULL REFERENCES dnd_reward_grants(grant_id),
  bound INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(source_grant_id,item_def_id,item_instance_id)
);
~~~

Production migrations must be additive, versioned, reviewed and transactional. Index and foreign-key behavior must be tested against both SQLite and Turso, with foreign keys explicitly enabled where required. Store compact snapshots in state_json (authoritative latest materialized state) and append-only event payload_json (source for audits/replay); update both atomically, assert parity with replay tests. Historical story text can have retention limits while mechanical events remain sufficient to reconstruct resolved effects.

**Identifiers:** UUID/ULID for game entities, Discord snowflakes as TEXT, UTC timestamps, integer game stats. Never store Discord interaction tokens as durable credentials. Session-scoped inventory and rewards cannot cross guilds. User-owned character/intent read endpoints always verify guild and channel visibility.

## 4. Snapshot and event contracts

Example minimal snapshot (all fields validate against a strict schema):

~~~json
{
  "schema_version": 1,
  "rules_version": "misfits-rules-0.1",
  "content_version": "mushroom-dungeon-0.1",
  "scene": {"id": "mushroom_boss", "type": "BOSS", "no": 4},
  "round": 3,
  "members": {
    "discord-user-id": {"hp": 14, "hp_max": 16, "focus": 1, "zone": "COVER", "statuses": []}
  },
  "enemies": [{"id": "slime_king_1", "hp": 24, "armor": 1, "defense": 12, "zone": "FRONT", "telegraph": "AOE_SPIT"}],
  "flags": {"telegraph_locked": true, "room_reward_claimed": false}
}
~~~

Example immutable resolved event:

~~~json
{
  "event_type": "ROUND_RESOLVED",
  "idempotency_key": "round:3:commit",
  "round_no": 3,
  "action_revisions": {"discord-user-id": 2},
  "rolls": [{"actor_id": "discord-user-id", "raw_d20": 14, "modifier": 3, "dc": 12, "success": true}],
  "effects": [{"source": "discord-user-id", "target": "slime_king_1", "type": "DAMAGE", "value": 4}],
  "next_snapshot_hash": "sha256:...",
  "narration_status": "PENDING"
}
~~~

The dice values and applied effects are committed as part of the event; a new narrator call never changes them. For low-complexity first release, random rolls use a server-side RNG and **record outcomes**, not just a seed. The seed/content version are also persisted for reproducibility. Later deterministic PRNG implementation must record algorithm version and identical inputs.

## 5. AI action interpreter schema and validator

Input contains bounded session snapshot, actor summary, current telegraph, target IDs and the actor's <=140-character submitted text. Use explicit-mention mapping when coordinating: Discord user ID, never free-text display-name guessing.

AI returns an untrusted typed proposal:

~~~json
{
  "kind": "ATTACK",
  "ability_id": null,
  "target_id": "slime_king_1",
  "ally_user_id": null,
  "zone": "FRONT",
  "tactic_tag": "DISTRACT",
  "confidence": 0.86
}
~~~

Allowed kinds: ATTACK, DEFEND, ASSIST, ABILITY, ITEM (T30.5), INTERACT, REPOSITION, RETREAT. Ability IDs, targets, tactic tags and zone IDs must exist in the content/character allowlist. Engine rejects unauthorized targets, 2 actions in one sentence, impossible effects, nonconsensual control over ally, unfunded skill or illegal state. If ambiguous while collecting, return a short private suggestion. After lock, fallback to DEFEND/Guard and label it as a fallback. No model-generated arbitrary Python, SQL, JSON patches, numbers, extra turns or currency changes.

**Pipeline:** Discord submit -> auth/ACK -> input bound and persist -> round lock/CAS -> interpret frozen intents (allowlist validation) -> deterministic resolve -> atomically commit rolls/effects/snapshot/reward candidates/outbox -> separate DM narrative -> edit board and post compact explanation. Validate JSON both syntactically and semantically. Two independent users can submit at the same time without making two round resolutions.

## 6. Core mechanics — initial playtest values

### Stats and derived values

- Four stats Might/Finesse/Wits/Spirit, total allocated = 8, each 0–4.
- HP max = 12 + 2×Might (range 12–20). Focus max = 3; first room starts full; room completion restores +1 up to 3; not from repeated waiting or combat stalling.
- Defense = 10 + floor(Finesse/2) + Guard/cover bonuses; overall defense cap 16 for MVP.
- One main action per character/round. Basic actions no Focus cost; two special skills cost 1 and 2 Focus respectively.
- A single character cannot simultaneously ATTACK and ASSIST. This tradeoff is intentional.

### Dice and skill checks

Default: raw d20 in [1..20]. For an attack/skill check, total = d20 + relevant attribute + proficiency (0–2, default 1 for specialty) + situational bonus (−2..+2). Success if total >= target DC/Defense. Natural 1 always misses on attacks; natural 20 always hits on feasible attacks and adds +2 damage (not an extra turn). For narrative skill challenges, impossible actions are ruled invalid before rolling, not automatically successful on 20.

DC guide: Easy 9, Standard 12, Hard 15, Heroic 18. With attribute 2 and proficiency 1 vs DC 12, a player succeeds on 9–20 = 12/20 = **60%**; a specialized attribute 4/proficiency 1 succeeds on 7–20 = **70%**. These are mathematical baselines, not current playtest win-rate data.

### Combat effects

Basic successful hit damage = max(1, 3 + floor(attack_stat/2) + gear_bonus [0..1] − armor [0..2]). Example Might=2, no gear, target armor=1 => 3 damage. Basic attacks have no friendly fire. A Focus=1 damage skill may add up to 2 direct damage OR one modest status, not both at full strength; Focus=2 gives up to 3 extra damage OR a stronger bounded utility package. Balance ability effect points, not natural-language intensity.

MVP statuses and strict ceilings:
- GUARD: +2 defense until actor's next activation, nonstacking.
- EXPOSED: next hostile hit within 2 rounds gains +2 damage; then removed.
- WEAKENED: −2 next qualifying action check, removed after one use or 2 rounds.
- STAGGER: disrupts one telegraphed charged action if a validated prerequisite is met; boss immunity window prevents perma-lock, substitute reduced damage if immune.
- SHIELDED: absorb 2 damage from next eligible hit before expiry.
- DISPLACED: a validated zone movement with range limitations, not an infinite stun.

Effects from creative tactical play map to the above. Favor choices with tradeoffs, not free narrative buffs. Natural language cannot create arbitrary kill, double reward or permanent boss stun.

### Synergy rule

A synergy bonus is earned only if two distinct party members spend their actions on compatible and feasible **mechanical** actions (for example ASSIST/DISTRACT + ally ATTACK, or REPOSITION + CONTROL) with valid targets, same round and matching prerequisites. Apply at most +2 to **one** check or one damage effect per receiver per round, nonstacking and logged with linked actor IDs. An explicit @mention alone is not a bonus. No ally sabotage: harmful transformations or statuses require an opt-in character quirk with bounded harmless non-HP effects and a party-level disable option.

### Initiative and simultaneous intents

Each collecting round takes intentions in parallel. At lock, freeze all declared actions. Deterministic initiative ordering uses character Finesse plus one recorded d20 tie-break/initiative roll where applicable; enemy initiative is a rules-defined value. Protect legal targets with clear fallback if a previous action kills or moves them; retarget only among explicit legal alternatives, otherwise Guard. Once effects are committed, the narrator cannot change sequence.

Enemies have a planned telegraphed attack before player lock. Boss telegraph may be partially interrupted; avoid unavoidable zero-warning high-damage attacks. AI can decide the next tell from a curated tactics list only after the previous round is committed.

### Initial encounter targets (scale with party size n)

- Skirmish enemy total HP budget = 8 + 4×(n−2): n=2 -> 8 HP, n=3 -> 12, n=5 -> 20.
- Boss combined HP budget = 18 + 6×(n−2): n=2 ->18, n=3 ->24, n=5 ->36.
- Enemies use defense 11–13, armor 0–1 and damage 2–4 per hit or clearly telegraphed weak AoE. At standard difficulty, tune after simulating party compositions and multiple rounds, not solely enemy HP.
- Boss target ~3–5 effective combat rounds for an average three-player party; run target ~10–20 minutes; standard clear-rate playtest target ~65–80% (not a guarantee). Defeat should feel explainable and lead to a new run, not erase the character.

### Fairness and anti-meta guardrails

Same total stat budget and skill effect budget for any prompt. Quirks may have small positive/negative expected value but never compulsory griefing. No permanent upgrades that raise all four attributes endlessly. Re-running a short dungeon cannot infinitely farm reward grants; a session/user grant is unique; future content reward ceilings/cooldowns are explicit and server-verified. No loot before a committed terminal event.

## 7. Worked 3-player example

Characters: Vanguard Might=3, Finesse=1; Mage Spirit=4, Finesse=1; Trickster Finesse=3, Wits=3. Boss HP=24, defense=12, armor=1.

- Trickster ASSIST distracts boss and passes a feasibility check; attaches one +2 synergy bonus to Mage's next attack.
- Mage casts Focus=1 offensive ability, d20=9, Spirit=4, proficiency=1, synergy=2 => total 16 vs DC 12, success. Basic 3+floor(4/2)−armor1=4 plus Focus skill bonus 2 => **6 boss HP lost**, Focus decreases by 1.
- Vanguard attacks with d20=8, Might=3, proficiency=1 => 12 vs DC12, hit. Damage 3+floor(3/2)−armor1 = **3 boss HP lost**.
- Total boss HP 24 ->15; boss executes previously telegraphed limited attack, Guard and Shield mitigation apply according to committed order. Narrator explains only the recorded events and can add harmless character-flavor humor.

If Trickster had simply written "I help" but used an incompatible action or failed its check, do not award synergy. If Mage tries "I annihilate the dungeon and all bosses", reject the unbounded effect and suggest the existing cast/attack actions.

## 8. Atomicity, leases and outbox sequence

At T30.0 implement and test a true provider-specific transaction capability. Expected atomic commit set for a round:
1. assert session state RUNNING, round state RESOLVING, matching lease and versions;
2. write one unique ROUND_RESOLVED event containing roll/effect report;
3. update state snapshot and member current states;
4. advance round/session stage and version;
5. enqueue board/narration outbox intents using unique (session,event_seq,kind);
6. commit transaction.

An expired lease lets another worker **resume** a not-yet-committed round; it must first query by idempotency_key and never reapply committed events. Rewards commit transactionally with the terminal event, with UNIQUE(session_id,user_id) and a grant ID; inventory insertion is keyed to the unique grant. If commit fails, DO NOT narrate fictional success.

Outbox and Discord side effects are at-least-once attempts and may ambiguously deliver. Prefer editing one persisted board ID; send a new message only under a guarded reconciliation policy. On timeout/unknown status, query/inspect known target message when possible; do not blindly send twice. Treat the message text as a projection of authoritative DB state. A best-effort recovery queue for generic mention messages does not replace this D&D-specific outbox.

## 9. Test and observability matrix

Unit/property tests:
- stat-point/skill-cost invariants across thousands of random prompts;
- d20 probability thresholds, attack nat1/nat20, damage range, no negative HP/focus;
- all transitions accept legal states, reject stale/terminal transitions;
- multi-submission revision replacement only before LOCKED;
- 2 concurrent workers race to lock/resolve same round: exactly one event commit;
- 2 concurrent reward deliveries: exactly one logical DB grant;
- pause/resume preserves exact state and unspent deadline, recovery after crash at each boundary;
- malformed/hostile AI JSON cannot write mechanics or commands;
- wrong guild/channel/owner/role gets zero mutation and zero game posts;
- session max one active per guild enforced by partial unique index;
- seed/replay from committed event log matches snapshot; rule version frozen per session;
- release regression suite for Tarot, Feedback, Search, Embed, dashboard and core help/sync.

Integration gates:
- both SQLite and Turso transaction implementations tested; **no successful production game write on Turso outage with local fallback**;
- Discord 3-second interaction acknowledgment, modal vs defer paths, button custom_id scope/version and persistent view restart;
- real mobile board readability, API error fallback, deleted board/permissions handling;
- burst concurrent join/Ready/submit, redeploy while a round is locked, no duplicate message/reward;
- LLM budget and latency instrumentation by parser/narrator, model failure recovery.

Suggested logs/metrics: guild/session hash, rules_version, scene/round, transition, action kind, outcome, rng record ID, token count, AI time/cost estimate, DB commit time, outbox state, sanitized error class. Never log full free-text prompts or Discord tokens by default.

## 10. Freeze decisions before implementing T30.1

1. One dedicated channel / one live session / guild for MVP; opt-in threads post-MVP.
2. Basic stat bounds, 140-char action, 90s round timer, 2–5 players, 3–4 rooms.
3. Prompt generates flavor plus balanced mechanical IDs, no arbitrary user-defined abilities.
4. Pure rules engine is the only mechanical authority; narrator is post-commit.
5. Turso-backed transactional state must be durable before gameplay is released.
6. UI and game actions in configured channel only, independent of conversational 15-minute context.
7. Every release goal includes deterministic simulations, regression and live Discord smoke.

Balance coefficients are **design defaults**, adjustable through versioned code/content after controlled playtests, never silent mid-run changes.
