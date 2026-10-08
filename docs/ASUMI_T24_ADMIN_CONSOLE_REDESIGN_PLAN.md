# T24 — Asumi Admin Console 2.0 / UX & Information Architecture Plan

**Status:** PROPOSED, waiting for owner approval. Planning only; no runtime/dashboard code changed.
**Baseline:** main as inspected on 2026-10-08. Keep the Flask app, authentication and existing data stores.
**Decision:** No separate Request Review approval UI. ChatGPT only creates proposals. The owner decides within the Feedback ticket detail view.

## 1. Current-state audit

- web/templates/dashboard.html: ~3,009 lines of combined HTML, CSS and JavaScript. Eight equal top-level horizontal tabs (Activity, Presence, Version, Tarot, Cabin, Guilds, Overview, Console Logs), default landing is the activity table.
- Feedback uses another /admin/feedback page with its own CSS, layout and return-to-dashboard link. It already has ticket list, evidence, history, ChatGPT proposals, owner accept/dismiss, status change and GitHub issue/PR handoff.
- Global dashboard refresh loads /api/stats and /api/activities every 3 seconds, even if current tab does not require interaction data.
- Dense toolbars and fixed-height/overflow-hidden root make the console hard to scan and mobile navigation awkward.
- Existing privileged operations include clear logs/history, reset cooldowns, change presence, stop Cabin sessions, suspend/leave guild, and feedback review. API authentication exists, but older write routes need a systematic CSRF, validation and audit review.
- Data sources: /api/stats, /api/activities, /api/guilds, /api/tarot/*, /api/cabin/*, /api/presence, /api/version, /api/admin/feedback/*.
- Product issue: rare configuration actions, operational diagnostics and daily workflows are given the same visual weight. Changing colors alone cannot fix it.

## 2. Information architecture

**Five collapsible sidebar groups, not ten flat equal-priority tabs.** Desktop: sidebar + page title/toolbar + focused content. Mobile: drawer navigation with full-page content. Keep browser-refreshable, shareable URLs and a common top bar (bot status, current version, refresh, account/logout).

| Group | Page | Proposed route | Purpose |
| --- | --- | --- | --- |
| Workspace | Tổng quan | /admin | Online/health, pending tickets, recent incidents, useful quick links |
| Workspace | Feedback | /admin/feedback | Unified inbox, status queues, ticket search and filtering |
| Workspace | Ticket detail (drilldown) | /admin/feedback/<ticket-id> | Evidence, owner decision, AI proposal, implementation and audit timeline |
| Quan sát | Tương tác | /admin/activity | Filter/search traces, timings, errors, private detail drawer |
| Quan sát | Sức khỏe & Logs | /admin/monitoring | Health, uptime, errors, console, integration diagnostics |
| Tính năng | AI & Search | /admin/assistant | Assistant/Brave/Discord History/Archive/Clef/Vectorize routing and safe telemetry |
| Tính năng | Tarot | /admin/tarot | Rating metrics, cooldown lists and reset actions |
| Tính năng | Cabin | /admin/cabin | Active sessions, immunity shields and authorized management |
| Cộng đồng | Máy chủ | /admin/guilds | Participating guilds, suspend/unsuspend/leave |
| Hệ thống | Trạng thái Bot | /admin/presence | Presence preview/editor, auto-rotation and presets |
| Hệ thống | Phiên bản & kết nối | /admin/releases | Version/changelog; read-only provider/MCP health and authorization if available |

This means ten focused primary pages plus ticket drilldown, distributed over five sections, with only current context expanded. Do not create top-level entries for every low-level setting. Preserve /admin and /admin/feedback old bookmarks.

## 3. Page-level requirements

### 3.1 Tổng quan — essential, P0
- One simple status summary with last-updated indicator: Bot Online/Offline, guild count, live latency, recent errors (if sourced), pending feedback; avoid more than 4–5 prominent cards.
- Action queue: unreviewed feedback and other genuine operator actions, not an indiscriminate feed of activity logs.
- Latest significant events and shortcuts to Feedback, Logs and Presence.
- Uptime/RAM as subordinate operational details. Never show invented historical uptime or success percentages.
- If an API fails, show stale/error and preserve unrelated widgets.

### 3.2 Feedback — essential, P0
**Inbox:** tabs/presets for Needs Action, In Progress, Waiting Verification, Done, All, Deleted. Search ticket #N/title; filters for status, priority, category and date where supported; concise rows (#, title, status, reporter, age, evidence and pending proposal cue). Build backend pagination/bounded filtering instead of expanding the current client-only 100-item list.

**Ticket detail:** persistent URL, title/status/category/author/source jump-link, expected-vs-actual and clarification, private R2 image evidence, technical metadata. Prominent owner actions: Approve, Request Info, Defer, Reject, Duplicate, then stage progression. For negative decisions, explain required reason and show a meaningful confirmation. A separate **ChatGPT proposal card inside the same ticket** shows suggestion, reasoning, creation time, Accept or Dismiss; the AI never approves itself. Track GitHub Issue/PR/deployed version, verified gate and append-only audit timeline. Show relation to deleted/replaced old ticket without resurrecting old approval.

**Notification rule:** approvals, work-in-progress and deploys do NOT DM reporters. Only final verified/Done and terminal reject/cancel/duplicate DM, with relevant reason/retest details. This policy is proposed in existing PR #51; do not silently overwrite its unmerged state. The Discord user owns self-service (/feedback mine/status/edit/delete), not a redundant web admin request page.

### 3.3 Tương tác — P1
- Newest-first table: date, type, user/guild, action, result, duration, drilldown. Minimal visible filters and advanced filters folded away.
- Bounded server pagination; filter by type, success/error, time and search term.
- Detail drawer shows the existing permitted input/output and assistant/search timing metadata; maintain privacy and escaping.
- Move copy/debug/export/delete/clear into contextual menus; clear needs confirmation and server audit.
- Do not re-fetch full activity data while this route is inactive.

### 3.4 Sức khỏe & Logs — P1
- Health: current uptime, latency, RAM, Discord connectivity, data age (not fake historical SLA).
- Console: independently scrollable logs with severity/search, copy, controlled clearing, no endless full-buffer rerender.
- Diagnostics: existing provider health metadata only; distinguish configured, enabled, live-verified and unavailable for Turso, R2, Brave, Clef, Vectorize, MCP. Do not expose secrets or private chat content. Any missing metric needs a separately scoped safe backend endpoint.
- Refresh only active views, pause when hidden and show last success/error.

### 3.5 AI & Search — P2
- Show real existing assistant traces and tool/provider paths, fallback/error reasons, recorded latency/quota signals.
- Distinguish Brave public web, explicit Discord History, Archive and optional Clef/Vectorize. Never imply a provider is enabled just because code exists.
- Keep configuration authority in core/constants.py; secrets in deployment environment; no second editable quota/flag store.
- No automatic server history indexing or sending private Discord content to Brave. If telemetry does not exist, label as unavailable rather than simulate statistics.

### 3.6 Tarot — P1
- Quality/ratings summary, user cooldown search/list, reset one user; bulk reset behind danger confirmation.
- Preserve currently working commands and APIs; correct loading/empty/error/result states.

### 3.7 Cabin — P1
- Overview of live sessions/shields, separated Session and Shield views.
- Clearly identify user/guild target before stop/remove/toggle. Filter and permission-check without changing feature behavior.

### 3.8 Máy chủ — P1
- Guild list with backed metrics, current status and available actions.
- Suspend/unsuspend; Leave Guild requires prominent target confirmation and server authorization. No accidental bulk actions.

### 3.9 Trạng thái Bot — P1
- Live preview, presence type, activity text, auto-rotation, presets, explicit Save/Apply.
- Explain save success vs Discord apply failure. Remove stale hardcoded old version labels in presets.

### 3.10 Phiên bản & kết nối — P2
- Compact release summary and changelog timeline from /api/version.
- Read-only integration/connector diagnostics plus MCP authorization/revoke where secure API exists; no secret-value editor or automatic deploy button.

## 4. Shared UI & implementation policy

- Unified base Jinja admin layout, one consistent palette/type scale and accessible components (page header, navigation, table, ticket cards, detail sheet, buttons, badges, filters, toast, loading/empty/error/confirmation).
- Calm density and clear hierarchy, no oversized card wall; primary actions visible and rare/danger actions grouped away.
- Desktop sidebar collapses; tablet compact navigation; mobile drawer with single-column screens and safe action placement; keyboard navigation, focus, contrast, reduced-motion and accessible dialogs.
- Replace web/templates/dashboard.html monolith with a base layout, templates/admin pages, partials and modular static CSS/JS. Reuse Flask/Jinja + existing API and data contracts; no React rewrite/microfrontend or second web service without a demonstrated need.
- Back/forward navigation and direct URL refresh must work. Preserve old links and permission boundaries, private R2 evidence, OAuth, Turso event history and numbered tickets.
- Review every modifying endpoint for CSRF, auth, request validation, actor/action audit and idempotent safe submission. Legacy forms must not become silently exposed to third-party web pages.
- Load data on demand per active page, cancel/ignore obsolete responses, avoid overlapping 3-second fetch loops, pause on hidden pages; manual refresh and last-updated/error indicators.
- No new free/premium provider consumption, new archive indexing or non-secret Render flags. Existing constant/policy authority stays unchanged.

## 5. Goal sequence (focused PR per goal)

| Goal | Deliverable | Gate |
| --- | --- | --- |
| T24.0 | Current-state audit, this plan, route/action/API inventory and desktop/tablet/mobile baseline | Owner approves IA and scope |
| T24.1 | Shared shell, sidebar, responsive navigation, common design tokens and route skeleton | Old links, auth, refresh/back/mobile navigation pass |
| T24.2 | Action-first overview, scoped polling and truthful health/feedback summary | No unconditional activity poll; stale/error/loading clear |
| T24.3 | Unified Feedback inbox and deep-linked ticket detail, inline ChatGPT proposals, status/implementation timeline | Ticket #N, evidence, owner-only review, final-notification policy regression |
| T24.4 | Activity + Monitoring modular pages | Logs/filters preserved; safe clear, redaction and no background over-poll |
| T24.5 | Feature pages for Tarot, Cabin, and AI/Search diagnostics | Existing mutations tested; missing telemetry never invented |
| T24.6 | Guilds, Presence, Releases/Connections | Dangerous actions confirmed, Discord apply result real |
| T24.7 | Cross-page accessibility, auth/CSRF/privacy audit, regression and mobile/live smoke, remove legacy duplicate UI | CI green; deploy/live explicitly verified; rollback possible |

Each implementation goal: one manageable PR, update handoff/this plan, preserve existing behavior by default, include tests and failure cases, record next steps. No unrelated architecture rewrite. Do not merge all pages in one PR.

## 6. Mandatory acceptance scenarios

1. Mobile admin opens /admin: meaningful bot state and pending tickets before long logs. All navigation works via drawer.
2. Admin opens ticket #15 directly, sees screenshot/context, accepts or dismisses ChatGPT proposal *within the ticket*; merely receiving an AI proposal changes no ticket status.
3. Approve sends no reporter DM; Done requires actual deployed+verified; reject/duplicate sends one final DM. No duplicate notifications from old outbox records.
4. User edits ticket: new #N created, old soft-deleted; Dashboard shows replacement linkage/history without treating old as completed.
5. Guild Leave, global Tarot reset, clear logs/actions have intentional confirmation, CSRF and actor audit.
6. Assistant/Search diagnoses provider paths without leaking private messages, tokens or inventing search quota counts.
7. Direct-link refresh, browser Back, mobile at 390px and desktop at >=1280px work; errors from R2/Turso do not break unrelated pages.
8. Legacy endpoints/bookmarks continue to work while old monolithic template is retired in stages.

## 7. Dependencies, decisions and checkpoint

- PR #51 (terminal-only feedback DM) is open separately as of this planning audit; reconcile before implementing T24.3.
- Current feedback has its own style and CSRF token flow; reuse verified backend methods rather than create a second review API.
- New routes are **proposals**; implement only after owner approval. Preserve code-level semantics of current feature modules.
- To approve: five-group navigation, targeted pages above, AI & Search P2, and incremental Flask/Jinja refactor (not a full React rewrite).
- **2026-10-08 checkpoint:** audit and documentation drafted. Runtime UI untouched. Next step is owner review → T24.0 acceptance / T24.1 shell. Maintain source of truth in repository so future sessions can resume.
