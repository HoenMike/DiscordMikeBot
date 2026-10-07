# T21 — Asumi Intelligence Handoff

**Initiative:** Asumi Intelligence / Conversational Core  
**Status:** IMPLEMENTATION IN PROGRESS — Asumi 3.1 vertical slice  
**Planned from:** Asumi 3.0.1, `main` commit `1df48c459cc10fda54b1f652245af1f437006fbd`  
**Primary spec:** `docs/ASUMI_INTELLIGENCE_MASTER_PLAN.md`

---

## Locked release mapping

```text
Asumi 3.1  Conversational Core        IN PROGRESS
Asumi 3.2  Context + Lens             PLANNED (image input required)
Asumi 3.3  Asumi Archive              PLANNED
Asumi 3.4  Intelligence Polish        PLANNED
```

Audio / voice transcription is explicitly excluded unless the owner reopens it.

## Product decision

The next intelligence layer for Asumi makes **`@Asumi ...` natural conversation** the primary AI entrypoint while preserving deterministic commands.

```text
@Asumi tarot daily cho tôi
@Asumi tóm tắt đoạn chat nãy giờ
@Asumi cái link phía trên là gì?
```

For a live session:

```text
(reply to Asumi) giải thích kỹ hơn cái thứ 2
```

No mention/reply => no conversational response.

---

## Non-negotiable contracts

- Existing slash/prefix commands remain.
- Existing mention-as-prefix commands win over conversational routing.
- Assistant is tool-driven; it does not replace Tarot/summary/media engines.
- Tarot cards remain deck-engine controlled.
- No passive full-server message archive.
- Conversation context is bounded.
- Long-term memory is explicit opt-in and later.
- Cloudflare usage is **free-only** and fails closed rather than creating paid usage.
- Clef-flash is planned as a decision/router model, not the main prose model.
- Cloudflare model names/quotas must be re-verified at implementation time.
- Audio/voice transcription is out of scope.

---

## Runtime observations already verified

- `bot_instance.py` uses `commands.when_mentioned_or(...)`.
- `bot_instance.py::on_message` ends in `process_commands(message)`.
- `CommandNotFound` is intentionally silent.
- Current source layout is `core/` + `features/`; README contains some stale old `cogs/` / `services/` references.
- Existing feature modules: `features/embed/`, `features/summary/`, `features/tarot/`, `features/cabin/`.
- Shared current AI client: `core/ai.py`.

---

## Milestone status

```text
T21.0  Baseline + contracts                         COMPLETE (docs)
T21.1  Mention conversational vertical slice       IN PROGRESS
T21.2  Reply continuation + short session          IN PROGRESS
T21.3  Clef decision router                        NOT STARTED
T21.4  Existing feature tool adapters              IN PROGRESS
T21.5  Context Builder v2 / Lens text+link         NOT STARTED
T21.6  Image Lens                                  NOT STARTED
T21.7  Asumi Archive / explicit memory             NOT STARTED
T21.8  Polish + observability + release            NOT STARTED
```

---

## Exact next action

Continue the **Asumi 3.1 / T21.1–T21.4 vertical slice**. The next external dependency is Cloudflare/Clef credentials after the no-key core is verified.

First prove one end-to-end vertical slice:

```text
@Asumi hello
  -> trigger gate
  -> bounded context
  -> minimal assistant route
  -> Discord response
```

Prove these regressions do not occur:

```text
@Asumi tarot
.m tarot
/tarot
normal unmentioned chat
guild suspension behavior
```

The first implementation PR should add `features/assistant/` and tests before broad Cloudflare infrastructure.

---

## Suggested first files

```text
features/assistant/__init__.py
features/assistant/cog.py
features/assistant/trigger.py
features/assistant/context.py
features/assistant/session.py
features/assistant/router.py
features/assistant/tools.py
features/assistant/response.py
tests/test_assistant_trigger.py
tests/test_assistant_session.py
```

Do not create empty modules merely to match this target tree; add them when each milestone needs them.

---

## Update rule

Every T21 implementation PR must update this file with:

- completed milestone/sub-goal;
- important decisions;
- tests run/results;
- known gaps;
- exact next milestone;
- relevant commit/PR references.

This handoff is the source of truth for resuming T21 in a fresh agent/session.
