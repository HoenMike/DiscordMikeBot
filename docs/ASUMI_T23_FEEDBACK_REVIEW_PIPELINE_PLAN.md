# T23 — Asumi Feedback, Review & Implementation Pipeline

Status: **PROPOSAL / AWAITING OWNER APPROVAL** (2026-10-08)
Owner: Asumi Discord Bot project.
This is a design proposal, NOT a shipped capability, deployed API, authorized auto-fix system, or a ticket created from user chat.

## Problem and target experience

Today an Asumi user testing `@Asumi tóm tắt tin nhắn 12h qua của @i'm_bd` got a **channel-wide** recap of 267 messages. The duration (`12h`) was parsed but the member constraint was ignored. In v3.7.8 the router recognizes `tóm tắt ... @user đã nhắn gì`, but `tin nhắn 12h qua của @user` has intervening time words, so the current author-scope condition can fall back to `summary.catchup`. **Do not mark this reported regression resolved.**

Desired product: any Discord user can explicitly report a bug or suggestion via @Asumi; the bot collects a bounded context snapshot and writes a durable feedback ticket. Owner plus ChatGPT can later search/review these tickets, decide approve/defer/reject with a reason, and hand approved work to Codex/GitHub. A ticket's Discord source, technical diagnosis, changes, review, PR, deployment and verification remain linked end to end.

## Goals and proposed order

### T23.1 — Explicit capture + durable ticket (MVP)
- Natural-language triggers: `@Asumi báo lỗi: ...`, `@Asumi góp ý: ...`, `@Asumi cái trả lời này sai` when replying to an Asumi message; explicit `/feedback` fallback for reliability.
- Do not silently treat generic criticism, jokes or unrelated chat as feedback. Collect a draft and use **Confirm / Edit / Cancel** buttons (author-only). No ticket is written until confirmed. If critical details are missing, ask at most one compact follow-up.
- Bug details: report text, optional expected/actual behavior, category, affected Asumi version, reporter/guild/channel, source Discord message IDs and jump URLs, optionally the original bot response and previous user prompt if accessible with valid ACL. Never blanket-ingest channel history.
- Suggested feature details: short goal, why it matters, optional examples/attachments. Respect attachment count/size and avoid retaining volatile Discord CDN links as permanent files. MVP stores Discord jump references; longer-lived private evidence storage (R2) is a later, consent-based goal.
- Persist via a dedicated `asumi_feedback` SQLite/libSQL table, `asumi_feedback_events` append-only audit and optional `asumi_feedback_evidence`. Strong unique keys for trigger source message / idempotency, ticket ID (e.g. `FB-000123`), timestamps UTC, schema version, status.
- **Durability gate:** the existing DB adapter falls back to local SQLite on Turso failure. Production feedback writes must verify `db_client.is_cloud` and a successful cloud commit; on unavailable Turso, report failure and offer retry, NEVER claim accepted or save only to ephemeral Render disk. Keep normal dev SQLite test mode explicit.
- Ticket acknowledgement is concise with ID and Open/Jump link, does not expose private evidence to the whole server.

### T23.2 — Owner triage and moderation dashboard
- Add a protected Feedback tab to existing Flask dashboard; no second app/database.
- Views: Inbox, Needs info, Approved, Rejected, Planned, In progress, Ready to verify, Closed; query by author/category/version/date/status; grouping of suspected duplicates is advisory, not automatic deletion.
- Owner/admin-only actions: classify bug/feature/question, priority, assignee, approve, reject (reason mandatory), request more information, mark duplicate-of, link GitHub issue/PR and change status. Reporters only view their own tickets and public-safe status; no arbitrary moderation by Discord users.
- Use `asumi_feedback_events` to keep actor, old/new status, timestamp, reason and external references. Every decision must be attributable and reversible with audit.
- Retention, cleanup, deletion and privacy rules should be agreed before release. Do not store full raw server history or sensitive tokens; strip Discord role pings/mention side effects and limit copied text.

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
- Optionally notify original Discord thread of important status changes, respecting current channel permissions and notification frequency.

## Candidate ticket model
`feedback_id`, `guild_id`, `channel_id`, `reporter_id`, `source_message_id`, `reply_to_message_id`, `bot_response_message_id`, `category` (bug/feature/ux/other), `title`, `description`, `expected`, `actual`, `bot_version`, `status`, `priority`, `duplicate_of`, `github_issue_url`, `github_pr_url`, `created_at`, `updated_at`. Evidence is a separate access-restricted set of records with source type/URL/text excerpt/size and expiry. Keep diagnostic metadata non-secret, small and bounded.

Suggested status lifecycle: `draft` (Discord ephemeral/in-memory) → `submitted` → `triage` → `approved` / `rejected` / `needs_info` / `deferred` → `planned` → `in_progress` → `in_review` → `deployed` → `verified` → `closed`. Rejected/duplicate tickets keep a reason and can be reopened by admin.

## Security and non-goals
- Allowlist explicit feedback intent before normal chat/history/search routing; no public Brave lookups of submitted private chats. Avoid tagging everyone; interactions author-only.
- Validate per-channel Discord permission before resolving referenced messages; respect message deletions/permission changes and redact evidence appropriately. Only allow admin read across reporters.
- Uploads/attachments are opt-in with caps, malware/size constraints and retention. Do not auto-download all images from surrounding chat or store arbitrary personal content.
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
- Reporter UX: draft confirmation buttons vs immediate submission (recommend confirmation).
- Ticket visibility: owner-only details, reporter sees their own status; limited public ticket acknowledgement (recommended).
- Evidence retention duration / opt-in attachment copying to R2 (recommend link-only MVP).
- Owner approval required for GitHub issue creation and for code/deploy transitions (recommend yes).
- Connector auth model and who else, if anyone, may triage (default only owner).

No code was implemented in this proposal. Await explicit owner approval before T23.1.
