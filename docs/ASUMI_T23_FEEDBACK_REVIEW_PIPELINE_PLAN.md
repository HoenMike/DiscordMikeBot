# T23 — Asumi Feedback, Review & Implementation Pipeline

Status: **Asumi T23.1–3 deployed in 3.8.2; 3.8.3 final usability/acceptance changes under PR** (2026-10-08). No ticket is approved automatically.
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

Owner has authorized beginning T23. Code is under review in draft PR #45; deployment remains blocked on private R2 provisioning, live Turso/R2 verification and acceptance. Track milestones in GitHub issue #46.


## T23.1 implementation handoff — first PR (2026-10-08)

Branch: `feat/asumi-t23-1-feedback-mvp` (not yet in main, do not claim live). Files:
- `features/feedback/policy.py`: explicit report intent and version-aware, overrideable troubleshooting from checked-in behavior contracts; never automatic rejection
- `features/feedback/cog.py`: Discord member-only clarification and preview buttons; /feedback report + /feedback status; additional screenshot replies; no production source-code changes triggered by tickets
- `features/feedback/evidence.py`: image type/actual signature validation, dimensions/size caps, EXIF-free PNG re-encoding, private R2 upload and cleanup
- `features/feedback/store.py`: Turso-only tickets with atomic JSON evidence manifest, audit trigger and notification-outbox schema. Never acknowledge ephemeral SQLite fallback.
- `bot_instance.py`: feedback intake precedence before the Assistant Cog; existing command precedence retained
- `tests/test_feedback_t23.py`: report classification, design-aware clarification, image validation/R2, durable-only idempotent storage, wizard and cleanup regressions
- CI `.github/workflows/asumi-search.yml` includes `features/feedback/**` and tests.
- Non-secret policies in `core/constants.py`. Required **secret/deployment** values for image persistence are `ASUMI_FEEDBACK_R2_BUCKET`, `CLOUDFLARE_ACCOUNT_ID`, `ASUMI_FEEDBACK_R2_ACCESS_KEY_ID`, `ASUMI_FEEDBACK_R2_SECRET_ACCESS_KEY`; never put these credentials into source.

**Release gates not yet met:**
1. Finish CI/codereview and test Discord native button/slash command flow, especially 2h session TTL and attachment follow-ups.
2. Confirm a **private dedicated R2 bucket**, scoped S3 API token and values in Render; R2 may have costs and must not be publicly accessible. No image ticket acceptance before upload receipt.
3. Confirm production Turso cloud writes, deduplication and screenshot retrieval after restart. Reconcile orphaned R2 objects on partial failure.
4. Finish T23.2 owner review, notification delivery/reasons/closed-DM fallback; it is NOT delivered in T23.1.
5. Never mark T23 done merely because this implementation branch/CI is green; require a real Discord reporter-to-admin acceptance test.

Potential follow-up: add owner-only dashboard listing and private R2 image reader, then manual approve/reject with mandatory reasons and outbox delivery; only after this can ChatGPT-side triage/agent workflow be connected.

Tracking: [T23 parent issue #46](https://github.com/HoenMike/DiscordMikeBot/issues/46), [T23.1 draft PR #45](https://github.com/HoenMike/DiscordMikeBot/pull/45).


## Engineering continuation checkpoint — 2026-10-08 ~12:15 ICT

**Draft PR #45, NOT MERGED or LIVE.** Code implemented for T23.1 feedback wizard/Turso+R2, T23.2 admin UI/review+DM outbox, T23.3 bearer API/OpenAPI, T23.4 owner-approved issue/PR linkage, T23.5 delivery metrics/DB regression. CI passed on earlier changes; always re-check latest commit. Real Discord acceptance still required.

Cloudflare account now contains a new PRIVATE APAC bucket `asumi-feedback-evidence` (managed r2.dev public access disabled). Non-secret Render environment `ASUMI_FEEDBACK_R2_BUCKET` and `CLOUDFLARE_ACCOUNT_ID` were set; this triggers a deployment of existing main, **not the draft PR**.

**Blocking owner action**: Cloudflare account token management endpoint returned 9109 Unauthorized; cannot create a secure R2 S3 key. Owner must generate a bucket-scoped R2 **Object Read & Write** API token and set secret environment variables `ASUMI_FEEDBACK_R2_ACCESS_KEY_ID` and `ASUMI_FEEDBACK_R2_SECRET_ACCESS_KEY` in Render. Never paste credentials into GitHub/chat. For T23.3, separately configure a random strong `ASUMI_FEEDBACK_CONNECTOR_TOKEN` and connect the private plugin. Avoid adding arbitrary tokens or using broad Cloudflare admin credentials.

**Remaining pre-merge reviews**: enforce owner auth and actual cross-event approval (a simple request flag is not proof of owner approval); inspect any DB schema migrations for existing tables; audit private evidence serving, Slack/Discord permissions and UI rendering; review DM retries/idempotency; add end-to-end tests and live screenshot confirmation. Do not equate CI mocks with production verification. T23.4 currently supports linking approved issues/PRs, not automatic agent execution/auto-merge.


## 2026-10-08 — T23.3–T23.5 owner-gated completion work (Asumi 3.8.1)

Branch `feat/asumi-t23-review-handoff-completion`. Implementation includes:
- Authenticated ChatGPT *proposal* endpoint `POST /api/feedback-connector/v1/tickets/{id}/proposals`. AI can draft `approved/rejected/deferred/needs_info/duplicate` recommendation and reason, but **cannot update the ticket**.
- Turso table `asumi_feedback_review_proposals` with `pending → accepted/dismissed` audit. Owner-only admin inbox displays proposals, and an explicit CSRF-protected click decides. Dismissing a proposal does not reject the user ticket; accepting applies the proposed status and reason and triggers notification.
- ChatGPT/OpenAPI contract exposes **read ticket, list tickets, propose only**. The existing direct connector review/link-write handlers remain hard-disabled (403). No assistant/agent can approve automatically.
- `/feedback reopen` is reporter-only, requires explanation, and works only for previously reviewed/closed tickets.
- Dashboard supports safe GitHub Issue draft copying and Issue/PR/release links for already approved tickets. No auto-create/merge/deploy from untrusted user feedback.
- Durable notification outbox resolves the **historical event reason** instead of showing a later status's reason.
- Source message jump links, exact GitHub URL validation, regression tests and version update.

**Owner expressly deferred FB-01401CE0D1 after initially approving it.** It MUST remain `submitted` until owner gives a fresh explicit go-ahead **after T23 completion**. A one-off approval hook that was briefly drafted on a separate unmerged branch was removed; it is NOT in main or this branch. The member-summary bug fix is likewise postponed and unmerged.

**Still external/blocking to complete fully:** ChatGPT Plugin cannot access the REST API until owner connects/authenticates an actual private integration and a scoped `ASUMI_FEEDBACK_CONNECTOR_TOKEN` is configured on Render. This workflow must never expose database credentials, allow public ticket access, or use a ticket's text as an instruction. GitHub Issue creation and code implementation remain explicit owner-approved downstream actions.

**Acceptance gates:** CI + deploy only establish code availability. Do live test from ChatGPT connector → proposal → owner confirmation in Dashboard → Turso ticket status and single private DM; rejection and verified statuses must show the correct reason. No auto approval of FB-01401CE0D1.


### Private MCP bridge details

The T23.3 backend now also serves **MCP Streamable HTTP JSON** at
`https://discordmikebot.onrender.com/api/feedback-connector/mcp`, authenticated with
the SAME strong `ASUMI_FEEDBACK_CONNECTOR_TOKEN` Render Bearer credential as the REST connector.
Exposed tools: `list_feedback_tickets`, `get_feedback_ticket`, `propose_feedback_review`.
It has **no** tool for approving, rejecting, deploying, or creating GitHub issues.
The plugin package and actual user connection need a separate confirmation and
compatible host credential flow. Never bundle a bearer token in `mcp.json` or GitHub.
CI verifies MCP JSON-RPC initialize/list/call, strips R2 private keys and requires
proposal-only behavior. Live connected-plugin validation is still pending.


## 2026-10-08 — User enabled ASUMI_FEEDBACK_CONNECTOR_TOKEN; OAuth migration for plugin

Screenshot confirms Render has the new `ASUMI_FEEDBACK_CONNECTOR_TOKEN` secret. Do not read/reveal it. **Important integration discovery:** ChatGPT plugin packaging with `mcp.json` and a remote HTTPS server does NOT automatically forward Render environment secrets to ChatGPT. The initial `/api/feedback-connector/mcp` was bearer-key protected and therefore could not complete a ChatGPT linking handshake. The official ChatGPT MCP auth path is OAuth 2.1 (or no auth, which is inappropriate for private Discord tickets).

The `feat/t23-oauth-mcp-connection` branch adds:
- OAuth protected-resource metadata and authorization-server metadata
- ChatGPT-restricted dynamic registration, PKCE authorization-code flow, explicit logged-in owner consent
- Access + refresh tokens stored as hashes in Turso Cloud, bounded TTL and scope, OAuth-protected MCP
- Owner-only token revocation and regression tests
- MCP tools remain strictly `list_feedback_tickets`, `get_feedback_ticket`, `propose_feedback_review`; no approval or rejection tool. FB-01401CE0D1 still `submitted`.

After CI/deploy, owner completes a single *ChatGPT plugin connection* and Asumi Dashboard login on the consent page. No Render key is pasted into chat. Actual connection success must be verified by reading the real FB ticket through MCP, without changing its status.


## T23.5 final acceptance addendum — 3.8.3

**Sequential ticket IDs (owner requested):**
- Internal `ticket_id=FB-UUID` stays immutable. Add table `asumi_feedback_numbers(number INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id UNIQUE)`; SQL trigger assigns the number in the SAME write as the ticket.
- On startup run idempotent ordered backfill for existing legacy tickets, sorted by `created_at, ticket_id`. Never reset or recompute existing numbers. New requests receive the next monotonically increasing number; gaps remain gaps if IDs were removed, never renumber.
- Discord submit, `/feedback status`, admin inbox and DM use human-readable `#1`/ `#15`; old `FB-` IDs keep working. ChatGPT MCP supports `#N` in its tools.
- User's previously submitted `FB-01401CE0D1` is expected to become `#1` only if it is the oldest feedback when migration runs; verify actual number through MCP after deploy, do not invent the mapping before reading production.

**Screenshot to AI:** owner-authenticated `get_feedback_evidence` tool reads private R2 object by manifest index only, checks ticket guild path and stored SHA-256 checksum, produces bounded JPEG preview via MCP ImageContent. No public R2 URL or bucket keys returned to model. Test rejects cross-guild or tampered files.

**Full reviewer flow:**
1. Reporter submits report/image and sees `#N`.
2. ChatGPT Web lists ticket, reads text and private image, researches verified current design/code. It may propose an outcome and reason, but never approve.
3. Owner opens Feedback Inbox, reads AI suggestion, clicks **Chấp nhận đề xuất** (or direct status change with confirmation). Dismissing proposal leaves reporter ticket unchanged.
4. Notification outbox sends DM in Vietnamese with `#N` and exact historical reason. If DM unavailable, reporter can check `/feedback status #N`.
5. After owner approval, implementation can proceed via GitHub Issue/PR; only mark `verified` after deployment + live owner acceptance and release version. DM reports fixed version. Reporter may reopen or answer needs-info.
6. Real acceptance still pending until owner has exercised owner-confirmed decision + DM in Discord. Do not auto-approve FB-01401CE0D1.

**Live limitations:** GitHub Issue drafting/linking is supported, but unattended Codex task creation/automatic deployment is deliberately NOT enabled, for code/reporter privacy and approval safety.


## T23.6 — Feedback Center & My Tickets (owner-requested UX, v3.8.4)

Owner reported the original admin page was crowded, difficult to moderate, had a persistent generic review form, and no user-facing feedback history or ticket lifecycle.

- **Admin Dashboard:** Rebuild as responsive review inbox with status totals, search/filter, concise ticket cards, actual protected R2 image thumbnails, decision rail with contextual quick actions, AI proposal accept/dismiss, history timeline and GitHub handoff behind expandable details. User-submitted text rendered via DOM `textContent`, never unsafe HTML injection. All actions require login/CSRF and explicit click; report contents do not grant approval.
- **Discord user:** `/feedback mine` is ephemeral and scoped to the requesting Discord account AND guild. Page through tickets, see statuses/reasons, and optionally show previously deleted reports. User can delete with explicit confirmation: DB status `deleted`, `deleted_at`, history and evidence remain durable for admin audit and privacy investigations.
- **Edit/supersede:** User may revise any non-deleted ticket explicitly via modal; never mutate old report text. Atomic `INSERT INTO asumi_feedback ... SELECT original...` writes a fresh `FB-` ID and next `#N`, clones old evidence metadata, and an AFTER INSERT trigger marks original ticket `deleted` with `replaced_by_ticket_id`; new ticket links back via `replaces_ticket_id`. Owner review decisions on the old ticket remain in append-only audit but **are not inherited** by the new ticket. The original owner-approved ticket can thus be superseded only by the reporter's explicit edit action, never AI or automatic migration.
- **Proposal hygiene:** Any pending AI review proposal on deleted/replaced ticket is atomically dismissed, to avoid accidentally approving stale content; user deletion/replacement does not create an approved ticket.
- **Migration:** Existing Turso rows get nullable lifecycle fields via PRAGMA + ALTER TABLE, no data loss, no renumbering, no R2 deletion. Re-running initialization should be idempotent.
- **Quality gates:** CI migration on legacy 3.8.3 SQLite, owner/guild ACL, real Discord View/Select/Modal instantiation, evidence reuse, original-state/audit preservation, old proposal dismissal, review guard and JS syntax. Then Render deploy + production no-mutation smoke; opt-in user acceptance for revised/delete UI.
- **Ticket #1:** Its current status must not be changed merely by this release. No test should approve, delete or replace the real production feedback.
