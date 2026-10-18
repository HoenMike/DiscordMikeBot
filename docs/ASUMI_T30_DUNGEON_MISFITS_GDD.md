# T30 — Dungeon Misfits: Game Design Document (GDD)

> Status: **PROPOSED / design-only**, 2026-10-18. Baseline: Asumi 3.14.7 at main commit 762a960. Not implemented or deployed.
> This GDD is the product contract. Companion specifications: ASUMI_T30_ENGINE_SCHEMA.md and ASUMI_T30_BACKLOG.md.
> Product: a small-group, original-rule, Discord-native, turn-based fantasy dungeon crawler narrated by Asumi as an AI Dungeon Master (DM). Inspired by tabletop D&D, **not** an implementation of official D&D rules or lore.

## 1. Product hypothesis, pillars, success

**One-line pitch:** 2–5 Discord friends describe ridiculous fantasy characters and submit short natural-language intentions to beat a 10–20-minute dungeon, with real tactics and memorable emergent stories.

Pillars:
1. **Low-friction entry:** a character takes one creative prompt; no character-sheet expertise.
2. **Tactics matter:** deterministic, testable rules assess terrain, timing, resources, synergy and dice; good choices alter actual outcomes.
3. **Absurd but coherent:** character quirks, unexpected consequences and funny DM narration, without humiliating or griefing human players.
4. **Play as a group:** each round gathers intents in parallel; each person gets agency, late/AFK players do not stall the session.
5. **Discord-first, zero main-chat noise:** absolutely no gameplay posts, background triggers, reward pings or adventure activity in the general-chat channel.
6. **Recoverable and auditable:** persistent game state, immutable resolutions, idempotent rewards and no AI authority over HP or loot.

MVP success criteria (targets for pilot, not measured current performance): >=80% of 3-person test runs finish without manual repair; median run <=20 minutes in Quick mode; <=2 public status messages per normal round (prefer 1 edited board and 1 narration); >=95% of accepted actions get a visible outcome or explicit fallback; no double reward; no game posts in unconfigured channels. Pilot at least 10 runs across 2–5 people with observed session-completion and fun/clarity feedback. Later metrics: drop-off by room, prompt-repair frequency, DM fallback ratio, mean/95th round time, TTK, clear rate, run cost.

## 2. Scope and exclusions

MVP (T30.0–T30.4): channel setup and isolation; characters from prompts; lobby/party 2–5; ready/start; one run at a time per guild; 3–4 handcrafted room templates; exploration, trap/social/event, enemy encounter and boss; simultaneous round submissions with initiative resolution; skills, HP, Focus, simple items, telegraphed enemy action, statuses; AI intent parsing and short narration with deterministic fallback; pause/resume/recovery.

Post-MVP (T30.5–T30.7): durable inventory/loot, limited progression, alternate dungeons/bosses, asynchronous sessions, multiple parties using **threads under the configured dungeon channel** if admin opts in, world reputation, optional illustration cards.

Out of scope for T30 MVP: real-time free movement, an open-world MMO, PvP, player trading/economy, Discord-wide ambient AI simulation, voice table, arbitrary code execution, official D&D 5e class/spell replication, permanent death, monetization, standalone React game UI, active-room NPC chats in general channels.

## 3. Strict guild channel policy — owner requirement

**Default game surface:** exactly one admin-selected dedicated text channel per guild (example: #asumi-dungeon). The admin uses /dnd setup channel:<channel>; explicit confirmation and permission check required. No implicit creation, relocation or enabling. Before setup, /dnd help and admin setup can give ephemeral guidance.

- All public game boards, lobby messages, combat narration and rewards are posted **only** to the configured channel (or an opt-in descendant game thread in a later phase). Save the canonical guild_id, channel_id and per-session channel_id.
- All state-mutating commands and component callbacks validate guild, channel, user, session membership, interaction revision and channel ACL on the server. Outside the game channel, do not mutate state; respond ephemerally with a channel mention if accessible.
- Character prompts, secret choices, invalid attempts and individual errors are collected through Discord modals/ephemeral responses initiated in the game channel. No unsolicited DM, role ping, mention spam or public input dumps.
- Ordinary chat messages are **never** interpreted automatically as game actions: explicit /dnd or button/modal only. No passive indexing of general chat. The existing assistant's 15-minute conversation context is not game memory and must not be merged into D&D state.
- Do not create a second dashboard. T30 can appear later as a small read-only tab in the **historical existing** /admin dashboard if needed, only with explicit design approval. All player UX must work inside Discord.
- MVP enforces at most one nonterminal session per guild, in the configured game channel. New-party attempts show the active session/status ephemerally. Future concurrency requires threads plus a migration and permissions plan; no overlapping games in one public transcript.
- If admin changes channel mid-run: refuse by default until the active session is completed/cancelled, or use a dedicated explicit migration operation in a later goal. Never silently move the live run.
- With missing bot permissions or deleted channel: pause/quarantine and show admin diagnostic via a permitted command; **never** spill to #general as a fallback.

## 4. End-to-end player journeys

### A. First entry (target 1–2 minutes)

1. User enters game channel and chooses /dnd character create.
2. Asumi opens a modal: "Mô tả nhân vật của bạn" (<=500 characters) and optional preferred name (<=40).
3. AI transforms flavor into a proposed archetype, stats and two balanced abilities from a **typed allowlisted mechanical palette**, plus one bounded quirk. Invalid/timeout AI => deterministic local draft suggestions, prompt retained.
4. Ephemeral preview includes name, role, four stats, HP, abilities, quirk, resource costs. User may **Confirm**, **Reroll from same prompt** (bounded), or **Edit prompt**. Only Confirm persists a character. Max one active character per user per guild in MVP; replacement requires explicit confirmation and cannot rewrite a character participating in an active run.
5. Successful creation returns a private preview, with optional public join-ready status but not the original prompt.

Example: "Pháp sư tài năng nhưng phép mạnh có thể biến đồng đội thành gà". The resulting specialty may be high burst with a telegraphed self/ally inconvenience. The weakness triggers through known probability and does not remove teammate agency permanently.

### B. Party and run

1. Party leader in game channel clicks **Lập đội** or /dnd start. Bot sends/edits one lobby board with roster 0/5, Ready statuses, mode Quick, dungeon preview, and 2–5 allowed seats.
2. Players join with their confirmed characters; leader starts only when minimum 2 and all members Ready. Owner/leader may disband prior to start. Unauthorized outsiders cannot join by pressing expired controls.
3. Each dungeon has 3–4 rooms: intro/event, skirmish or environmental problem, optional fork/rest, boss. Party decides at bounded branch points via voting; tie resolves with documented fallback or leader choice without secretly giving extra loot.
4. For a room, DM narrates a short scene (<=450 characters), 1–3 visible tactical cues, enemy intent telegraph, and a clear action button. Player taps **Hành động** then modal prompt (<=140 characters) or picks **Tấn công / Phòng thủ / Hỗ trợ / Dùng kỹ năng** preset.
5. Players submit independent intents. They may revise until lock/deadline. One bot round collects them in parallel and resolves in deterministic initiative order; no waiting for each participant to type in strict sequence.
6. Late players use **Guard** autopilot; never consume rare items, Focus or choose irreversible narrative branches. A repeated inactivity threshold changes them to safe autopilot; leader can pause, not kick someone mid-combat by accident.
7. On resolution, board is edited with HP/status/next deadline; one compact narrator summary highlights results, 1–3 rolls and unusual moments. More details behind **Chi tiết lượt**.
8. After boss or terminal outcome, show an end card, contribution highlights and eventually loot (T30.5), including partial rewards on failure if design permits; party can start a fresh run.

### C. Typical session time

Quick mode MVP: 2–5 players; 90-second default submission deadline, explicit **Everyone Ready => resolve early**; 3–4 rooms including 1–2 combat encounters; target 10–20 minutes, but timeout is an estimate not a guarantee. Server deadlines use persisted UTC timestamps, never in-process-only timers. Async mode with 12-hour steps is deferred beyond MVP.

## 5. Character system

**Attributes:** Might (physical force), Finesse (speed/dexterity), Wits (insight/trickery), Spirit (magic/resolve). Allocate 8 points in [0..4] each. Archetype is presentation/ability selection, not a rigid class: Vanguard, Skirmisher, Arcanist, Support, Trickster. NPC and custom character text may be unique, but these numerical bounds are non-negotiable.

At creation: HP = 12 + 2×Might (12–20); Focus maximum 3; defense baseline 10 + floor(Finesse/2) + shield/cover bonuses (capped); one main action per round and one optional conditional response assigned by engine, not free arbitrary multi-actions. Starting equipment budget is equal across roles (attack and defense share a budget). Each character has:
- Basic attack (free).
- Two abilities assembled from **allowed effects** (damage/heal/guard/control/reposition/reveal) and targeting constraints; one can cost 1 Focus, one 2 Focus.
- One quirk offering interesting but bounded upside/downside. No voluntary friendly-fire griefing; potentially harmful ally effects require opt-in/clear telegraph and have strict ceilings.
- Flavor fields, pronouns/name, traits and style; no hateful/sexual-content personalization of other server members.

Character prompt may not specify numeric power, guaranteed criticals, immortality, infinite resources or unbounded control. AI maps fantasy to available effect-budget points. Accepted mechanical schema is generated/validated by code and optionally assisted by AI; never trust direct model-authored arithmetic.

MVP characters reset temporary damage/Focus between runs; no permanent character deletion on a failed expedition. T30.5 introduces modest horizontal variety (gear changes play style, rare quirks, visible achievements) rather than uncapped stat inflation.

## 6. Battles and exploration

**Battle abstraction:** no tile grid in MVP. Enemies/characters occupy one of three abstract positions: Front, Back or Cover. Movement/reposition is a named tactical effect; enemy attack ranges and AoE rules can explicitly target zones. This provides tactical context without maintaining a pixel map.

Enemies have HP, defense, basic intent (damage, guard, charge, summon/control) and a visible telegraph for the upcoming round. AI can vary dialogue and plausible tactics but may not change planned damage mid-round. Human abilities can interrupt a telegraph only through defined rules (Stagger, Shield, Zone Change, etc.).

Room archetypes: (a) simple social choice with tradeoff, (b) trap or environmental puzzle where multiple valid skill approaches exist, (c) standard combat with enemy tell, (d) mini-boss/boss multi-phase encounter. Every obstacle must have a mechanical solution besides witty prose. Creative intentions are mapped to a small ontology and scored for feasibility, cost, risk and synergy.

**Failure should generate a playable consequence**: a failed disarm may apply Exposed rather than instant defeat; a failed persuasion may start a fight; a bad battle roll can result in Guard/Retreat options. Do not silently ignore clever choices, but do not award unlimited buffs just for elaborate text.

**Victory:** boss defeated, or a specifically scripted alternative win condition met. **Defeat:** party wipe or explicit retreat. **Pause:** admin/leader intervention or recoverable infrastructure issue. Endless fights are prevented through an encounter round cap and an escalating danger/routed outcome.

## 7. Tone, DM persona and content rules

Asumi DM is playful, quick and coherent: 2–4 concise paragraphs maximum per resolution, with a short header and clearly separated actual mechanical changes. Respect player-authored personalities. Humor stems from fictional events, not insults directed at real players. Character failure never triggers abusive shaming, private-channel revelations or involuntary out-of-game impersonation. AI cannot create real Discord user pings by generated mention text.

DM receives only the current session's bounded structured state, player submitted intents, party character summaries and most recent game events. It does not ingest the main channel chat history. Player prompt is treated as untrusted game input, never as instructions to run tools, view other channels, change rules or access credentials.

Use a creative contract: separate **narrative_output** (untrusted presentation) from **mechanic_events** (engine-verified). If the narrator times out, publish a short deterministic resolution and continue the game; do not reroll to suit prose.

## 8. Discord command and UI contract (proposed)

- /dnd setup channel:<text channel> — Manage Guild permission; status/enable/disable and audit; no implicit action in main chat.
- /dnd help — short guide and channel locator; outside channel ephemeral only.
- /dnd character create|show|replace — user-owned, channel-scoped, ephemeral/modal.
- /dnd start — lobby only inside the configured game channel.
- /dnd join|ready|leave — bound to guild/session/channel and member.
- /dnd action — opens user-specific prompt modal or preset; submission only during COLLECTING.
- /dnd status|recap — ephemeral full status; public durable board already visible.
- /dnd pause|resume|cancel — leader or admin with explicit confirmation on destructive operations.

Slash groups should be kept under Discord's command-depth limits; the precise command surface is finalized in T30.2 before shipping. Buttons carry compact opaque session/round/revision references (not trusted user IDs), re-authorized on every click. Public board should fit mobile viewport and preserve the main flow without screenshots or an external app. In Components V2 messages, follow Discord's restrictions; do not mix incompatible classic embeds/content in the same V2 message.

**Discord interaction reliability:** acknowledge or open a modal promptly (Discord requires initial response within ~3 seconds). Never block the initial response on DM generation, Turso retry or image rendering. If the engine cannot commit, keep the round pending and report a truthful private recoverable error.

## 9. Content and production strategy

Curated, data-driven MVP pack: "Hầm Nấm Lạc Lối" (title provisional). 4 room templates, 4 enemy archetypes, one boss with 2 phases, 2 puzzle/environment rules, 2 loot tables (loot distribution delayed until T30.5). Fixed numeric stats, status and rewards defined in versioned static YAML/JSON, loaded by validators. AI may compose room introductions or descriptions from template slots, never invent a content ID, resistance or unreviewed reward at runtime.

Seed the sequence once per run. Every generated room is validated against available content and party size; difficulty scales modestly with size and level, never by a secret AI judgement.

## 10. Risk and operational boundaries

- **Deployment/restarts:** no in-memory authoritative game state; resume from Turso. Existing deploy-recovery feature is for non-mutating chat mentions, not D&D command replay.
- **DB fallback:** existing core/db.py can fall back to local SQLite and has no unified multi-statement transaction wrapper. Production game MUST fail closed/pause when Turso unavailable; local SQLite is test/dev only unless explicitly deployed with durable persistence and one writer. Add an atomic transaction-capable D&D store before live matches (T30.0).
- **External Discord sends:** cannot claim exactly-once message delivery from an API with ambiguous timeouts. Use one durable board message ID, transactional outbox, idempotency and reconciliation; mechanical game results and rewards exactly once in DB.
- **Server permissions:** recheck channel ACL on commands, joins and result rendering. Do not rely only on a stored channel ID; server members might lose visibility. Don't leak secret/private player prompts to the party transcript.
- **Privacy:** store only explicit player-entered RPG text and necessary game data with clear retention; admins need export/delete semantics before wide rollout. Limit arbitrary character/action text length; escape mentions.
- **Cost:** set a per-session token ceiling and request count cap, route cheap parsing first, batch narration, cache safe static content; always have deterministic fallback. No Brave web search for game rounds.
- **Rollout:** code-owned flag default OFF, private-guild opt-in, QA with owner, CI + Render deploy check + real Discord mobile and desktop smoke. No version bump in planning-only PR.

## 11. MVP acceptance (product)

1. One dedicated configured channel per guild; automated assertions show zero game posts/DMs in general chat.
2. 2–5 users can create distinct natural-language characters, inspect generated constraints and confirm safely.
3. Two users submit actions simultaneously; double submission or stale button cannot double-apply effects.
4. A clever cooperative tactic yields a bounded real bonus; impossible prompt cannot bypass rules.
5. Offline/deploy restart during room/round can resume without changing the outcome; AI failure produces mechanical summary, not a dead end.
6. Boss can be won or lost; run is bounded; no unwanted permanent death.
7. All commands respect Discord membership, guild ACL, session membership and timeout.
8. Public board concise, mobile-friendly and not spammy; core experiences have no dependency on a new dashboard.

Open design tuning is captured in the engine spec; **numbers there are initial playtest coefficients, not claims of balance validated in production**.
