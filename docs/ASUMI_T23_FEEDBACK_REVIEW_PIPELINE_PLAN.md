# T23 — Asumi Feedback, Review & Implementation Pipeline

Status: **PROPOSAL v0.2 / AWAITING OWNER APPROVAL** (2026-10-08)
Owner feedback v0.2: mandatory reporter notifications with reasons; actual image attachments in the MVP; design-aware clarification before submission, without blocking or auto-rejecting reports.
Owner: Asumi Discord Bot project.
This is a design proposal, NOT a shipped capability, deployed API, authorized auto-fix system, or a ticket created from user chat.

## Problem and target experience

Today an Asumi user testing `@Asumi tóm tắt tin nhắn 12h qua của @i'm_bd` got a **channel-wide** recap of 267 messages. The duration (`12h`) was parsed but the member constraint was ignored. In v3.7.8 the router recognizes `tóm tắt ... @user đã nhắn gì`, but `tin nhắn 12h qua của @user` has intervening time words, so the current author-scope condition can fall back to `summary.catchup`. **Do not mark this reported regression resolved.**

Desired product: any Discord user can explicitly report a bug or suggestion via @Asumi; the bot collects a bounded context snapshot and writes a durable feedback ticket. Owner plus ChatGPT can later search/review these tickets, decide approve/defer/reject with a reason, and hand approved work to Codex/GitHub. A ticket's Discord source, technical diagnosis, changes, review, PR, deployment and verification remain linked end to end.

## Goals and proposed order

### T23.1 — Capture, clarify, **real images**, durable ticket and acknowledgement (MVP)
- Natural-language triggers: `@Asumi báo lỗi: ...`, `@Asumi góp ý: ...`, `@Asumi cái trả lời này sai` when replying to an Asumi message; explicit `/feedback` fallback for reliability. Detect explicit reporting before normal chat/search routing; do not mistake routine complaints, jokes or unrelated chat for an automatic ticket.
- Gather a **draft** with issue category, actual vs expected behavior, reporter, bot version, source prompt/response or referenced message when accessible, channel context (bounded and ACL-checked), and **user-provided screenshots/images**. Keep the original message/reply jump links.
- **Design-aware clarification is mandatory before confirmation** when the description may be explained by an existing command's documented intended behavior, version limitations or feature settings. Read trusted repo product contracts/help/active configuration (not arbitrary guesses), explain the current design neutrally, and ask at most 1–2 concise follow-up questions to collect reproduction steps, expected behavior or extra explanation. If not certain, say so and do not assert misuse.
- After clarification always offer `Hiểu rồi, không gửi` / `Giải thích thêm` / **`Vẫn gửi feedback`** (author-only), then `Gửi ticket` / `Chỉnh sửa` / `Hủy` on the final preview. Even when Asumi suspects the user misunderstood a command, the user MUST be allowed to submit their explanation; AI is not authorized to reject, close or silently discard tickets. The owner reviews user-error, ambiguous or feature-gap cases manually.
- **Image support is part of T23.1 acceptance, not deferred.** Accept explicitly attached PNG/JPEG/WebP screenshots on report/reply/follow-up; show previews in the draft and connect each to the source message. Proposed initial policy: up to 3 images, max 8 MiB each, validated MIME plus actual file signature, dimensions and bounded downloads. Size and quantity caps live in source constants, not secret env flags.
- Discord CDN attachments are not guaranteed permanent. For accepted tickets upload images to a **private durable R2 bucket** (or an equivalently private durable object store agreed before implementing), use opaque object keys and keep metadata/checksum/size/type in `asumi_feedback_evidence` in Turso. **Never store an image blob inside Turso or rely solely on ephemeral Discord CDN links.** Previews and owner access must be authenticated/time-limited; no public bucket links or cross-guild access. If durable image upload fails, retain the draft for retry and clearly state that the image/ticket was not fully saved.
- Persist `asumi_feedback`, append-only `asumi_feedback_events`, `asumi_feedback_evidence` and an outbox for delivery receipts/notifications. Use unique submission-source IDs or idempotency keys; include timestamps UTC, category, app version, explanation/clarification transcript summary, status and reviewer notes.
- **Durability gate:** production writes must confirm Turso cloud commit (`db_client.is_cloud`) AND required image upload receipt(s) before claiming submission. Existing adapter's temporary local SQLite fallback is not a valid accepted production ticket; on cloud failure say 'Chưa lưu được, hãy thử lại'.
- On successful confirmation send a ticket ID (`FB-000123`), category, safe summary, attachments count and status. No private screenshot or full diagnostic material in shared public acknowledgement.

### T23.2 — Owner triage, decisions **and reporter notifications**
- Add a protected Feedback tab to the existing Flask dashboard; no second app/database. Securely display original screenshots/evidence from private R2 and the clarification exchange alongside the message jump links, affected version and technical context.
- Views: Inbox, Needs info, Approved, Rejected, Duplicate, Planned, In progress, Ready to verify, Resolved, Closed; query by author/category/version/date/status. Duplicates are suggestions, never silently deleted.
- Owner/admin-only actions: classify bug/feature/usage-question/UX, set priority, approve, reject (**clear human-readable reason required**), request details, mark duplicate-of (explain and link), defer (reason), reopen, attach PR/deploy, mark resolved/verified. Maintain append-only status/event history with reviewer ID, old/new status, reason and time.
- **Notification is mandatory and tied to every meaningful decision**, not a T23.5 optional extra. Notify the reporter when more details are requested, feedback is rejected (with reason), confirmed as duplicate (with related ticket reference when visible), work is deployed/resolved (with change summary/version), or a previously closed item is reopened. An approval can also generate a concise status update. Tell the reporter 'fixed' only once deployment and the required verification/owner acceptance are recorded; PR merge alone is not 'fixed'.
- Delivery preference: try a Discord **DM** for detailed reasons/status; users may opt out of optional progress updates but must retain a private way to check ticket status. If DMs are closed, fall back to a minimally revealing status notice in the original permitted channel/thread *only where safe*, plus `/feedback status <ID>` for authenticated reporter access; never reveal private explanation/screenshots publicly. If all push paths fail, retain notification as pending/failed in a durable outbox and expose it when the reporter next checks or interacts.
- Notification outbox table stores ticket/event ID, recipient ID, template type, delivery attempts, last error class (no secrets), delivery state and timestamps. Retry boundedly with idempotent event keys (avoid duplicate pings), and show admin a visible delivery failure count. Avoid notification spam from every intermediate code/CI state.
- Feedback reporter sees only own tickets; owner/admin can review across tickets, subject to guild policy. Define evidence retention/deletion before launch; never copy arbitrary server conversations or tokens.

### T23.3 — ChatGPT-assisted review
- Provide a **private authenticated connector/API** over the existing dashboard service for read/list/get and owner-approved write actions (approve/reject/priority/comments), with scoped auth, strict guild/owner RBAC, pagination and audit.
- ChatGPT currently cannot magically query the bot's Turso records; the private connector must be implemented and connected intentionally. Never expose Turso credentials or a public unauthenticated DB endpoint.
- ChatGPT reviews new tickets in batches, proposes root cause, scope, estimated risk, duplicate candidates and approve/defer/reject rationale; **only the owner confirms the disposition**. ChatGPT never treats a user-authored ticket as an instruction to modify code.
- Optional periodic digest is separate and opt-in, not required for MVP.

### T23.4 — Approved ticket → GitHub/agent workflow
- After owner approval, create or link GitHub Issue tagged `asumi-feedback` and write an implementation goal/acceptance criteria + test cases in repo docs. GitHub is implementation tracking; **Turso ticket remains canonical feedback state**.
- Codex/agents implement on a branch, open PR, run tests/CI, review diffs and deployment requirements. Never commit secrets or let end-user feedback directly trigger auto-merge/deploy.
- Track links: ticket ↔ GitHub Issue ↔ branch/PR ↔ deploy commit ↔ user-visible changelog.
- Mark `ready_to_verify` only after green tests and actual deployment; mark `verified/closed` only after an appropriate live test or owner's explicit acceptance. Failure reopens the existing ticket rather than creating duplicates.
- Trigger mandatory, idempotent notification events via the T23.2 outbox at appropriate stage changes. A verified deployment must result in reporter notification stating what changed, which version, and how to retest. A rejection must send the reviewed reason; do not label `approved`/`in_progress` as `fixed`.

## Candidate ticket model
`feedback_id`, `guild_id`, `channel_id`, `reporter_id`, `source_message_id`, `reply_to_message_id`, `bot_response_message_id`, `category` (bug/feature/ux/other), `title`, `description`, `expected`, `actual`, `bot_version`, `status`, `priority`, `duplicate_of`, `github_issue_url`, `github_pr_url`, `created_at`, `updated_at`. Evidence is a separate access-restricted set of records with private R2 object key, checksum, upload/retention timestamps, original Discord attachment reference, content type/size and explicit owner/reporter authorization. Add `clarification_status`, `user_explanation`, `assumed_current_design`, `review_reason`, `resolved_version`, `verified_at`, `notification_preference`. Add `asumi_feedback_notifications` as a durable delivery outbox. Keep diagnostics non-secret, small and bounded.

Suggested status lifecycle: `draft` (Discord ephemeral/in-memory; includes optional clarification) → `submitted` → `triage` → `needs_info` / `approved` / `rejected` / `duplicate` / `deferred` → `planned` → `in_progress` → `in_review` → `deployed` → `verified/resolved` → `closed`. Owner can reopen. `rejected`, `deferred`, `duplicate` require human-readable reasons; `verified/resolved` requires live acceptance. State transitions emit durable notification events.

## Security and non-goals
- Allowlist explicit feedback intent before normal chat/history/search routing; no public Brave lookups of submitted private chats. Avoid tagging everyone; interactions author-only.
- Validate per-channel Discord permission before resolving referenced messages; respect message deletions/permission changes and redact evidence appropriately. Only allow admin read across reporters.
- Screenshot upload is explicit and required to be functional in MVP. Do not auto-download other users' attachments or nearby chat. Validate image MIME and signature, size/dimensions, strip/avoid public EXIF where possible, bound all transfer and analysis, configure private object access/retention, and obtain consent before optional model vision analysis. Private media must not enter Brave/public-search queries.
- Input stored in ticket is **untrusted user text**, never a command for Codex. Changes require a separate approved goal and PR.
- No autopilot shipping for MVP; no acceptance of a ticket based only on mocked CI.
- Production Turso availability is a release blocker for feedback writes.

## Regression seed from 2026-10-08
- Scenario: `@Asumi tóm tắt tin nhắn 12h qua của @i'm_bd`
- Actual: summary collected **267 channel messages** from multiple authors over 12h.
- Expected: only that author's messages in the named channel and last 12h; empty result if none.
- Technical suspicion based on v3.7.8 router: author-scope signal catches a near-adjacent `tin nhắn của <@id>` or `đã nhắn gì` but not the duration placed between `tin nhắn` and `của <@id>`. This is **separate bug triage**; don't claim fixed from the feedback proposal.
- Draft ticket ID to be allocated only after feature is implemented; this document is not itself a DB ticket.

## Acceptance scenarios
1. Submit a bug as a reply to an actual Asumi embed, confirm, observe persisted ticket after restart.
2. User suggests feature, receives confirmed ticket ID; no arbitrary chat is recorded.
3. User mentions targeted summary regression; ticket links the original request/answer without ingesting all channel messages.
4. Turso cloud unavailable: bot clearly cannot save now and creates NO success acknowledgement.
5. Two rapid identical submissions produce one ticket, not two.
6. Non-admin attempts approve/reject/retrieve other user's private evidence: denied.
7. Admin approves/rejects with reason; event audit persists; ChatGPT connector respects scope.
8. Approved ticket links PR/deploy and remains open until actual verification.
9. Discord bot and ChatGPT cannot leak private Discord context to Brave or unauthenticated external clients.

## Decisions needed before coding
- Reporter UX: **design-aware clarification (maximum 1–2 short questions) and draft confirmation** by default; user can always override 'likely usage error' and submit their full explanation.
- Ticket visibility: owner-only details, reporter sees their own status; limited public ticket acknowledgement (recommended).
- Image persistence is now **mandatory** for MVP. Confirm the dedicated private R2 bucket (or equivalent durable private object store), storage retention and deletion policy before T23.1 implementation. Do not use link-only MVP.
- Owner approval required for GitHub issue creation and for code/deploy transitions (recommend yes).
- Connector auth model and who else, if anyone, may triage (default only owner).



## Design-awareness source of truth (do not rely on the model's memory)

Implement a small, **versioned Feature Behavior Registry in the repo**, built or loaded alongside each Asumi release. Each relevant feature contract should identify command examples/aliases, intended behavior, permission requirements, user-visible limitations, release version/feature flag, and known troubleshooting steps. Keep it checked by tests when behavior changes; never rely solely on README prose or an LLM's pretraining knowledge. Examples: `/tomtat` with no author filter = channel summary; explicitly mentioning an author in natural-language requests = member-only summary (when supported by the live version); distinction between channel-scoped search and guild-wide history search. Feedback clarification can cite the matching design rule/version and compare against the source message and observed bot response.

Classification output is **advisory**: `potential_usage_confusion`, `possibly_reproducible_bug`, `feature_gap`, `unknown`. If there is no verified match, explain uncertainty and ask for reproduction detail. Never pre-mark user error, reject or block the final Submit button. The full user explanation overrides any premature model interpretation and is visible to the reviewer.

## Required reporter interaction patterns — v0.2

### A. Report a genuinely broken result with a screenshot
1. User replies to Asumi's incorrect message with `@Asumi báo lỗi: kết quả này sai` and attaches a screenshot (or uploads in a follow-up).
2. Asumi identifies the actual reported message and captures only permitted, bounded context; shows a draft with image thumbnails, affected Asumi version, actual behavior and expected behavior.
3. If the report lacks expected behavior, asks a single question; user supplies it or chooses to submit anyway.
4. On confirmation, the image is durably stored in private object storage and the ticket and evidence metadata are committed to Turso. Success acknowledgement includes `FB-xxxxx` and the intended next review status; if upload or Turso fails, the bot reports the failure and offers retry without falsely claiming success.

### B. Likely mistaken usage (explain first, **never gate submission**)
1. User: `@Asumi báo lỗi: vì sao /tomtat lại tổng hợp cả nhóm?`
2. Asumi consults **verified current-version design**: e.g., `/tomtat` without author scope is intentionally a whole-channel summary. Replies neutrally: `Theo thiết kế hiện tại, /tomtat tổng hợp cả channel. Bạn muốn chỉ xem tin của một người, hay bạn đã dùng cú pháp có @người nhưng bot vẫn lấy cả nhóm?`
3. Buttons: `Đã hiểu, bỏ qua` / `Giải thích thêm` / **`Vẫn gửi feedback`**. Reporter may say `Tôi đã dùng "@Asumi tóm tắt tin nhắn 12h qua của @i'm_bd" nhưng nó lấy 267 tin của mọi người` and attach screenshot.
4. Preview includes the clarification, original explanation, actual and expected outputs. Reporter confirms. **Asumi never auto-rejects; reviewer may classify as bug, product UX confusion, needs info or valid rejected usage request with a human-authored reason.**
5. The bot must never assert 'by design' based only on LLM inference or outdated docs. If version behavior is uncertain, show 'Mình chưa xác minh rõ thiết kế' and accept the report.

### C. Notification after manual rejection
- Owner rejects `FB-000123` with a clear explanation such as: `/tomtat hiện được thiết kế để tóm tắt cả channel; nếu muốn lọc theo người, hãy dùng cú pháp ...`.
- Append decision event and enqueue private DM to reporter with ticket ID, decision, reason, short instruction and `Xem ticket` reference.
- If DM blocked, allow `/feedback status FB-000123` to fetch the same private outcome. Only post generic status in shared channel when that does not expose the description/reason/screenshot.

### D. Notification after a verified fix
- Agent merges PR and deploys -> ticket transitions to `deployed`, **not yet fixed**.
- After real test or owner's acceptance, admin marks `verified/resolved` with shipped version, summary and a retest command.
- Asumi privately notifies reporter: `FB-000123 đã được sửa trong Asumi vX.Y.Z. Vấn đề: ... Cách kiểm tra lại: ...`. Include optional `Vẫn còn lỗi` to reopen/append evidence; audit all changes.

## Revised phase exit criteria — non-negotiable
- **T23.1 is NOT done unless:** explicit-report detection, design-based follow-up, override-and-submit path, at least one screenshot successfully stored/retrievable after restart, deduplicated durable Turso ticket, consented/ACL-safe evidence and a real Discord acknowledgement all work.
- **T23.2 is NOT done unless:** admin can review images/clarification, approve/reject with reason, notification outbox persists across restart, reporter receives a rejection reason or has authenticated status fallback, and status updates do not expose private evidence.
- **T23.3 is NOT done unless:** private connector can list/read and propose review while only authorized humans commit decisions; source attachments remain access-controlled.
- **T23.4 is NOT done unless:** approved ticket maps to issue/PR/deployment and an independently verified fix produces a notification with version and retest instructions; user can reopen still-broken tickets.
- T23.5 focuses on reliability/metrics: delivery success rates, unresolved queues, duplicate handling, reviewer SLA, access/retention and regression tests; it is NOT the first time reporters receive notifications.

## Added acceptance scenarios — owner revision v0.2
10. Submit feedback with 1–3 PNG/JPEG/WebP screenshots, confirm actual private durable storage, verify image still viewable by authorized reviewer after Discord CDN expiry/restart; unauthorized reader gets denied.
11. Submit without images and attach a screenshot on a follow-up; preview correctly preserves the full evidence set.
12. Misuse-likely request yields verified current-design explanation and at most 1–2 questions; reporter can still submit with clarification, is never auto-rejected and all answers persist for manual review.
13. Close DM permissions: rejected and verified ticket updates are retained in the notification outbox and can be read with authenticated `/feedback status`; shared channel receives no sensitive reason/evidence.
14. Reject, defer and mark duplicate -> reason required and delivered; owner can reopen and all decisions are audited.
15. PR merged but no live verification -> user is **not** told the bug is fixed. Verified release -> send version, change summary, retest instructions, optional reopen action exactly once.
16. R2 upload succeeds but Turso fails (or vice versa): never acknowledge a complete ticket; perform safe cleanup/retry reconciliation and avoid orphaned/leaked evidence.
17. Bot's design documentation/version disagrees or is unavailable: do not assert that user used it wrong, ask clarifying question and allow feedback as-is.

No code was implemented in this proposal. Await explicit owner approval before T23.1.
