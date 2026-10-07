# T21 — Asumi 3.x Intelligence Roadmap

**Status:** LOCKED / APPROVED  
**Owner intent:** Make `@Asumi ...` a natural-language front door for existing and future Asumi capabilities without replacing deterministic commands.  
**Cost constraint:** **Free-only.** No T21 component may silently enable paid usage or automatic paid fallback.  
**Baseline when planned:** `main` at Asumi 3.0.1 (`1df48c4`, 2026-10-05).

---

## Release mapping

```text
Asumi 3.1  Conversational Core
Asumi 3.2  Context + Lens (image input required)
Asumi 3.3  Asumi Archive
Asumi 3.4  Intelligence Polish
```

Audio / voice transcription is explicitly out of scope for Asumi 3.x unless the owner reopens it.

## 1. Goal

A user should be able to mention Asumi and speak naturally:

```text
@Asumi nay có gì vui không
@Asumi tarot daily cho tôi
@Asumi tóm tắt đoạn chat nãy giờ đi
@Asumi cái link Theo gửi hồi chiều là gì ấy
@Asumi ảnh này có gì vậy
```

After Asumi answers, the user can **reply directly to Asumi** without mentioning it again:

```text
Mai: @Asumi tarot daily cho tôi
Asumi: ...
Mai (reply): lá thứ 2 nghĩa sao?
```

The conversational layer is a **natural-language frontend**, not a replacement for feature engines. Tarot, summary, embed/media and future Archive/Lens capabilities remain authoritative tools implemented in code.

---

## 2. Product principles

1. **Mention/reply gated**
   - Asumi does not spontaneously join normal channel conversation.
   - Trigger only on an explicit bot mention, or a reply to an Asumi message that belongs to a live conversation session.
   - DMs are not required for T21 v1.

2. **Commands stay deterministic**
   - Existing slash commands and prefix commands remain supported.
   - If a mention resolves to an existing command such as `@Asumi tarot`, command handling wins before conversational routing.
   - `.m` remains a power-user shortcut. Do not silently reinterpret valid commands through AI.

3. **Tools, not hallucinated actions**
   - AI/router selects a typed tool + validated arguments.
   - Python code performs the actual action.
   - Tarot cards are always drawn by the existing deck engine; AI never chooses or rerolls cards.
   - Summary/media behavior must reuse or wrap existing runtime logic rather than duplicate it.

4. **Bounded context**
   - Never dump an entire channel history into every prompt.
   - Prefer reply target, a small recent-message window, and compact session state.
   - Long-term semantic memory is a later opt-in feature.

5. **Free-only / fail closed**
   - Cloudflare Workers AI, AI Gateway, storage and routing must remain within free allowances.
   - No automatic paid provider upgrade.
   - If a free quota/provider is unavailable, degrade gracefully.
   - Existing Gemini may be used only when explicitly configured under the project's accepted free quota; do not create a paid fallback path.

6. **Privacy by design**
   - Do not archive all Discord conversation by default.
   - Recent context is fetched just-in-time.
   - Persistent memories/media require an explicit later save/archive action.

---

## 3. Verified runtime facts

At planning time:

- `bot_instance.py` already uses `commands.when_mentioned_or(...)`, so a bot mention is already recognized as a prefix.
- `bot_instance.py::on_message` currently handles guild suspension, `.m` help and then calls `process_commands(message)`.
- Unknown prefix commands are silently ignored by the global `CommandNotFound` handler.
- Current feature code lives under `features/` (`embed`, `summary`, `tarot`, `cabin`).
- Shared AI access currently lives in `core/ai.py` and is Google GenAI oriented.
- README still contains some older `cogs/` / `services/` structure references; runtime tree is the source of truth.

Therefore T21 must integrate at the **message dispatch boundary** without breaking mention-as-command behavior.

---

## 4. Target architecture

```text
Discord message
      |
      v
Trigger / command gate
      |
      +---- valid slash/prefix/mention command ----------> existing command
      |
      +---- not mention/reply ----------------------------> ignore
      |
      +---- mention/reply continuation
                  |
                  v
             ContextBuilder
      reply target + recent bounded messages
      attachments/URLs + user/channel metadata
      short session state
                  |
                  v
             DecisionRouter
       deterministic rules first
       Clef-flash decision model second
                  |
        +---------+-----------+
        |         |           |
        v         v           v
      Tool      Simple AI   General chat
        |         |           |
        +---------+-----------+
                  |
                  v
             Response layer
                  |
                  v
                Discord
```

Cloudflare is a supporting edge/AI layer, not the Discord Gateway host.

---

## 5. Proposed module boundaries

Create a dedicated feature package:

```text
features/assistant/
  __init__.py
  cog.py             # Discord integration / conversational entrypoint
  trigger.py         # mention/reply detection + command precedence
  context.py         # bounded Discord context builder
  session.py         # short-term session state
  router.py          # deterministic + Clef decision routing
  tools.py           # typed tool registry / validation
  response.py        # Discord-safe response rendering
  providers/
    cloudflare.py    # Workers AI / Clef / Gateway adapter
    gemini.py        # wrapper around current provider if still needed
```

### Integration contract

Keep `bot_instance.py` thin:

1. Build normal command context.
2. If the message maps to a valid existing command, run normal command processing.
3. Otherwise, if it is an assistant trigger, delegate to `AssistantCog.handle_conversation_message`.
4. Otherwise keep existing behavior.

Do not implement competing `on_message` handlers whose ordering could make command/assistant behavior race.

---

## 6. Context contract

### Immediate context

For a triggered request:

- current user message with bot mention stripped;
- guild/channel/user IDs and display metadata required by tools;
- referenced message when present;
- attachment metadata and URLs;
- a small recent-message window only when useful.

Suggested initial defaults:

```text
recent_messages = 10
max_context_chars = bounded/configurable
include_bot_messages = true
include_system_messages = false
```

### Short session state

```text
session_key = guild_id + channel_id + user_id

last_intent
last_tool
last_entities
last_result_ref
turn_count
updated_at
expires_at
```

Suggested TTL: **20 minutes**, configurable.

The session is not a transcript database. Store compact state/references, not every message.

### Long-term memory

Not part of the first conversational release. Persistent memory is reserved for T21.7 and must be explicit opt-in.

---

## 7. Router contract

### Deterministic first

Do not spend AI quota on data code already knows:

- valid command names/aliases;
- URL/platform detection;
- Discord IDs/mentions;
- reply metadata;
- component actions;
- input/schema validation.

### Clef as decision model

Use Cloudflare Clef-flash as a **router/classifier**, not the primary prose model.

Example typed questions:

```text
intent:
  chat
  tarot
  summarize
  media
  help
  archive
  vision
  unknown

needs_recent_context:
  yes / no

action:
  respond
  call_tool
  ask_for_missing_input
  refuse_or_limit

complexity:
  deterministic
  simple_ai
  complex_ai
```

Convert the result into a local typed `RouteDecision`. Model text never directly executes code.

### Provider order

```text
deterministic
  -> Clef route
      -> local tool when possible
      -> free Workers AI for suitable simple generation
      -> existing Gemini path only when configured/allowed
```

Every provider call needs timeout, bounded retry and a user-visible failure path.

---

## 8. Tool registry

The assistant calls existing features through typed adapters.

Initial registry:

```text
assistant.chat
help.show

tarot.launch
tarot.daily
tarot.ask

summary.catchup
summary.channel

media.inspect_link
media.refresh_embed
media.remove_embed
```

Later:

```text
lens.inspect_image
archive.save
archive.search
```

Each tool defines name, input schema, permission/ownership checks, context allowance, timeout and user-visible fallback.

### Tarot rule

Natural language such as:

```text
@Asumi tarot daily cho tôi
```

must invoke the **existing Tarot runtime**. The conversational model may map intent/arguments, but must not draw cards, invent results or bypass cooldown/persistence.

---

## 9. Cloudflare free-only guardrails

Planned optional components:

- Worker endpoint as thin AI/edge service;
- Workers AI for Clef/router and selected low-cost generation;
- AI Gateway for observability/rate limiting/fallback;
- KV/D1 for lightweight session/routing metadata when useful;
- R2/Vectorize only in later Archive/Lens milestones.

Required config/guards:

```text
CF_ASSISTANT_ENABLED
CF_ROUTER_MODEL
CF_FREE_ONLY=true
CF_DAILY_AI_BUDGET
CF_REQUEST_TIMEOUT
CF_FAIL_OPEN_TO_GEMINI=false
```

Track enough local usage to stop optional AI work after the configured daily budget. Reaching a limit must never break deterministic commands.

Do not require paid Cloudflare Workers or any paid AI provider for Definition of Done.

---

## 10. Milestones

### T21.0 — Baseline + contracts

- Add master plan + handoff.
- Record current dispatch/runtime facts.
- Define conceptual `AssistantTrigger`, `AssistantContext`, `RouteDecision`, `ToolCall`, `ConversationSession`.
- No version bump for docs-only planning.

**Done when:** a new agent can continue without old chat context.

### T21.1 — Mention conversational vertical slice

**Goal:** `@Asumi <natural language>` produces a useful response without breaking commands.

- Create `features/assistant/`.
- Detect explicit mention.
- Preserve valid mention commands before AI routing.
- Strip mention safely.
- Add typing indicator and bounded timeout.
- Minimal `assistant.chat` path.
- Non-mentioned messages stay untouched.

Tests:

- valid mention command still runs;
- unknown mention text reaches assistant;
- normal message does not trigger;
- bot/webhook messages do not recurse;
- suspended guild behavior remains unchanged.

### T21.2 — Reply continuation + short session

**Goal:** reply to an Asumi conversational answer and continue naturally.

- Reply-to-Asumi trigger only.
- Session key: guild + channel + user.
- TTL default 20 minutes.
- Compact intent/tool/entity/result refs.
- No continuation without a live session.
- Bound turns/context.

Examples:

```text
@Asumi tarot daily cho tôi
(reply) giải thích kỹ hơn lá thứ 2
```

```text
@Asumi cái link này nói gì?
(reply) tóm tắt ngắn hơn
```

### T21.3 — Clef decision router

- Deterministic rule pass.
- Cloudflare Clef-flash adapter.
- Typed probability/choice result -> `RouteDecision`.
- Confidence threshold/fallback.
- Daily budget/circuit breaker.
- Observability without logging private message bodies by default.

Acceptance:

- obvious tool requests route correctly;
- low-confidence requests fail/fallback safely;
- Cloudflare outage does not break commands;
- free budget exhaustion degrades gracefully.

### T21.4 — Existing feature tool adapters

Natural language becomes a frontend to real Asumi features.

First tools:

- Tarot launcher / Daily / question-first flow;
- Summary/Catch-up flow;
- Help;
- safe existing embed/media actions.

Examples:

```text
@Asumi tarot daily đi
@Asumi tóm tắt 2 tiếng vừa rồi
@Asumi tôi làm được gì với bot?
```

Do not duplicate Tarot/summary engines.

### T21.5 — Context Builder v2 / Lens text+link

- reply target;
- bounded recent messages;
- URLs/existing embed metadata;
- referent resolution such as "cái này / cái trước / link Theo gửi";
- no persistent archive yet.

Example:

```text
Theo: <game link>
Mai: @Asumi game này có mobile không?
```

### T21.6 — Image Lens

- image understanding from attachments and replied messages;
- screenshot text reading / translation;
- meme/context explanation;
- reuse media pipeline where practical;
- strict file size/time limits;
- **audio/voice transcription is excluded from Asumi 3.x.**

Cloudflare free model availability must be re-checked at implementation time; do not hard-lock the feature contract to a specific generation model.

### T21.7 — Asumi Archive / explicit memory

- explicit `Save / Nhớ` only;
- source metadata for messages/links/media;
- R2 where appropriate;
- Vectorize semantic retrieval;
- D1 canonical records;
- delete/forget path;
- no passive full-server logging.

Examples:

```text
@Asumi nhớ cái này
@Asumi tìm lại cái meme mèo Khai gửi hôm trước
```

### T21.8 — Polish + observability + release

- help/docs updated;
- route/provider/tool failure metrics;
- privacy wording;
- regression tests;
- load/rate-limit smoke tests;
- release version/changelog only when behavior ships.

---

## 11. Delivery order

Do not build all Cloudflare infrastructure first.

```text
T21.0 docs/contracts
  -> T21.1 mention -> chat
  -> T21.2 reply/session
  -> T21.3 Clef router
  -> T21.4 Tarot + Summary tools
  -> T21.5 contextual text/link
  -> T21.6 image lens
  -> T21.7 Archive
  -> T21.8 release polish
```

Each milestone should be independently testable and user-visible.

---

## 12. Definition of Done — conversational core

- `@Asumi <natural language>` works in a normal server channel.
- Replying to Asumi can continue a live session without another mention.
- Normal unmentioned chat never triggers the assistant.
- Existing slash/prefix/mention commands still behave as before.
- Natural-language Tarot calls the existing Tarot engine.
- At least one non-Tarot tool is routed through the same tool registry.
- Context is bounded; no passive full-server archive exists.
- Cloudflare/provider failure has a tested graceful fallback.
- Free-only limits cannot silently become paid usage.
- Regression tests cover command precedence, trigger gating, sessions and tool validation.
- README/help/handoff reflect shipped behavior.

---

## 13. Explicit non-goals for first release

- voice/audio transcription;
- autonomous messages without mention/reply;
- replacing slash/prefix commands;
- moving Discord Gateway to Cloudflare Workers;
- storing every Discord message;
- making Clef the prose/chat model;
- rewriting Tarot or embed systems;
- paid Cloudflare tiers;
- unlimited conversation history.

---

## 14. Main risks

**Command collision:** mentions are already prefixes.  
Mitigation: resolve valid command context before assistant routing.

**AI action hallucination:** router may request nonexistent actions.  
Mitigation: closed tool registry + typed schema + local permission checks.

**Context/token growth:** conversational context can become expensive.  
Mitigation: bounded window/session, deterministic routing first.

**Privacy creep:** memory can become passive logging.  
Mitigation: no long-term memory before T21.7; explicit save only.

**Free quota dependency:** model availability/allowances can change.  
Mitigation: provider abstraction, configurable models, budget guard, fail closed.

---

## 15. Agent continuation rule

Any PR that starts, completes, rejects or materially changes a T21 milestone must update:

1. `docs/ASUMI_INTELLIGENCE_MASTER_PLAN.md` when the contract changes;
2. `docs/ASUMI_INTELLIGENCE_HANDOFF.md` for current status / next action;
3. `README.md` and help text when user-facing behavior ships;
4. tests in the same PR for behavior changes.

Do not mark a milestone complete based only on code existing; verify tests and Discord-facing acceptance criteria.
