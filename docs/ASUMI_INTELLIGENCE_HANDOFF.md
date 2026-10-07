# T21 — Asumi Intelligence Handoff

**Initiative:** Asumi Intelligence / Conversational Core  
**Status:** ASUMI 3.3.0 ARCHIVE CORE — implemented; live validation pending  
**Planned from:** Asumi 3.0.1, `main` commit `1df48c459cc10fda54b1f652245af1f437006fbd`  
**Primary spec:** `docs/ASUMI_INTELLIGENCE_MASTER_PLAN.md`

---

## Locked release mapping

```text
Asumi 3.1  Conversational Core        COMPLETE
Asumi 3.2  Context + Lens             IMPLEMENTED; LIVE VERIFY
Asumi 3.3  Asumi Archive              CORE IMPLEMENTED; SEMANTIC PENDING
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
T21.1  Mention conversational vertical slice       COMPLETE
T21.2  Reply continuation + short session          COMPLETE
T21.3  Clef decision router                        IMPLEMENTED; credentials configured
T21.4  Existing feature tool adapters              COMPLETE (Help/Tarot/Summary)
T21.5  Context Builder v2 / Lens text+link         IMPLEMENTED; LIVE VERIFY
T21.6  Image Lens                                  IMPLEMENTED; LIVE VERIFY
T21.7  Asumi Archive / explicit memory             CORE IMPLEMENTED; LIVE VERIFY
T21.8  Polish + observability + release            NOT STARTED
```

---

## 3.3 Archive Core implementation

Implementation PR: **#29 — feat: Asumi 3.3 Archive Core**.

Owner explicitly advanced to 3.3 before every 3.2 edge case was live-accepted. Keep the remaining 3.2 regressions in the final polish matrix; they no longer block Archive development.

3.3.0 ships:
- explicit Save / Search / Forget tools;
- user-owned records keyed by owner_user_id;
- source text + author + guild/channel/message IDs + Jump to Message;
- link/embed/attachment metadata;
- dedupe of the same Discord source per owner;
- bare save guard: no reply/link/attachment means nothing is persisted;
- search result cap of 5 in Discord;
- deterministic routing, so Archive actions do not spend Clef/Gemini quota;
- DB failure degrades with a user-visible message and no confirmed mutation.

Storage:
- canonical Archive DB = existing core.db adapter (Turso Cloud / SQLite fallback);
- D1 is no longer planned as a second canonical source;
- Vectorize remains a derived semantic-search enhancement after live acceptance;
- R2 remains optional for media binary retention; 3.3.0 stores metadata/URLs only.

Live acceptance matrix:

```text
1. reply a normal user message -> @Asumi nhớ cái này
   -> returns Archive #ID + Jump to Message

2. repeat save of the same source
   -> returns the same Archive item, no duplicate row

3. @Asumi nhớ cái này without reply/link/attachment
   -> refuses and tells user how to select a source

4. @Asumi tìm lại <keywords / author>
   -> returns only that user's matching Archive items

5. @Asumi archive của tôi
   -> returns latest items

6. @Asumi quên #ID
   -> deletes user's own item

7. another user tries the same #ID
   -> cannot retrieve/delete the first user's item

8. save an image/link
   -> source metadata is searchable; no media binary is copied

9. reply latest Asumi response -> "nhớ cái này"
   -> explicit Archive Save wins over session continuation
```

After core live acceptance, decide whether semantic misses justify 3.3.x Vectorize. Do not add Vectorize/R2 just because the roadmap mentioned them.

## 3.2.1 Tarot UX follow-up

During 3.2 live testing, the Daily result exposed a presentation issue: the AI-pending state was visually hidden below a tall Reading Board. 3.2.1 moves the pending status above the board and compacts one-card final results. Re-run the Tarot live case in the acceptance matrix after deploy.

## Exact next action

**Deploy Asumi 3.2.0 and run the live edge-case matrix below.** Do not start Archive until reply/context/image behavior is accepted.

```text
1. @Asumi hello
   -> normal conversational response

2. reply latest Asumi response: "ý thứ 2 là sao?"
   -> source=session_followup, no Clef/tool reroute

2b. @Asumi tarot daily -> complete/flip the reading -> reply Reading Board: "lá này nghĩa sao?"
   -> same session, no new draw, current edited Reading Board is used as context

2c. force a long Asumi answer that splits into 2+ messages -> reply chunk 1
   -> still continues the same session

3. another user replies to that Asumi response
   -> must NOT inherit the original user's session

4. reply an older Asumi response from the same user
   -> must NOT continue the live session

5. reply a normal user message/link + @Asumi "cái này nói gì?"
   -> replied message + URL/embed metadata are context

6. upload PNG/JPG/WEBP + @Asumi "lỗi gì đây?"
   -> image is understood

7. reply the image answer: "vậy sửa chỗ nào?"
   -> previous image remains available from in-memory session

8. @Asumi "game Theo gửi phía trên là gì?"
   -> bounded recent history is fetched; no full-channel dump
```

Dashboard validation:
- Asumi AI detail should show `context_ms`, `reply_context`, `recent_messages`, `images`, `session_images`.
- Prompt/response bodies remain empty in telemetry.

Archive development has started by explicit owner request. Remaining 3.2 checks roll into the final regression matrix.

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

## 3.2 implementation result

- Added `features/assistant/context.py` as the single bounded Context Builder.
- Reply target is resolved from Discord reference and passed to the AI only for the current request.
- Recent channel history is fetched only for contextual/referential cues and is bounded by message count + character budget.
- Live reply continuation bypasses Clef/tool routing to avoid accidental new Tarot/Summary actions.
- Command bridge captures up to a bounded set of bot output message IDs for natural-language tools; Tarot/Summary outputs therefore become valid continuation targets.
- Multi-message conversational responses keep all chunk IDs as valid reply targets.
- For tool sessions, Context Builder reads the replied bot message live instead of trusting an old snapshot, so an edited/flipped Tarot Reading Board can contribute its current embed/image.
- URLs from current/reply/recent context enable Gemini URL Context; Discord embed/attachment metadata is also captured.
- PNG/JPEG/WEBP attachments are passed as multimodal parts.
- Up to two images can remain in RAM inside the 20-minute session for follow-up; they are not persisted.
- A 5-minute cleanup loop actively prunes expired sessions so image bytes do not remain in RAM indefinitely after TTL.
- Added tests for other-user isolation, expired/old reply behavior, image attachment/reply/session carry-over, image-only routing, URL context and embed metadata.
- Environment defaults document context/image bounds; no new secret is required.

## 3.1.2 dashboard telemetry

- Reuses the existing ActivityLogger + Admin Dashboard; no new DB table.
- Adds activity type `assistant` and dashboard filter **Asumi AI**.
- Stores performance metadata only: route/Clef/AI/send/total latency, model, attempts, source, intent, request id, query/response character counts.
- Does **not** persist conversational prompt/response bodies.
- The activity table shows total duration plus compact model / AI / Clef timing; full breakdown is available in the existing detail modal.
- Production 3.1.1 validation observed greeting path: route 2ms, Clef 0ms, AI ~3.24s, Discord send ~0.43s, total ~3.67s with `gemini-3.5-flash-lite`.

Next live verification: after 3.1.2 deploy, send one `@Asumi hello` and confirm a new **Asumi AI** row appears in the dashboard. Then test one ambiguous request that actually invokes Clef and verify non-zero `clef_ms`.

## 3.1.1 latency finding

Render production log showed the first conversational request reaching `gemini-3.1-flash-lite` and timing out after about 12 seconds before fallback. The hotfix:
- stops using the data model as conversational primary;
- defaults chat to `gemini-3.5-flash-lite`;
- skips Clef for obvious greetings/test pings;
- caps chat generation to 6 seconds/model and 2 attempts;
- adds per-stage timing telemetry.

Next live verification should test one obvious chat request and one ambiguous request that really invokes Clef, then inspect `[Asumi Timing]` lines.

## 3.1 implementation result

- Added `features/assistant/` conversational package.
- Command-first dispatch is wired in `bot_instance.py`.
- Reply session is bounded in-memory (default 20 minutes / 4 turns).
- Closed command bridge routes Help, Tarot Daily/launcher and Summary/Catch-up through existing commands so checks/cooldowns remain authoritative.
- Clef-flash REST adapter is optional and disabled without credentials.
- Offline unit harness passed deterministic router, session, command bridge, Clef confidence/failure fallback and adapter parsing.
- Live Discord/Gemini/Clef smoke test still requires deployment credentials/runtime.

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
