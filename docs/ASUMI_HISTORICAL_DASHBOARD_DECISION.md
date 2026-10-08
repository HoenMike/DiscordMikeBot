# Dashboard baseline correction — 2026-10-08

## Owner decision (authoritative)

The desired Dashboard is the **historical tabbed admin UI** that existed before Asumi 3.9.0 / T24, not the 3.9.0 five-group sidebar, and not the standalone HTML prototype. The actual pre-T24 implementation remains in `web/templates/dashboard.html`, with eight tabs: Activity, Presence, Version, Tarot, Cabin, Guilds, Overview and Console Logs.

This clarification supersedes the sidebar direction in T24 planning and the unmerged PR #55. **Do not replace the UI with a new shell, new framework, mockup, or navigation scheme.** The next task is incremental improvements INSIDE the original historical template, under separate reviews.

## Restoration implementation

- `/admin` serves `web/templates/dashboard.html` again. The original tab layout, filters, controls and identity stay recognizable.
- Existing `/admin/feedback` (T23 Feedback Center) and `/admin/feedback/<ticket>` stay functional; historical topbar already links to Feedback Inbox.
- Newer bookmarked `/admin/guilds`, `/admin/monitoring`, `/admin/tarot`, etc. redirect to `/admin?tab=<historical-tab>`. Unavailable exact old counterparts map conservatively (AI & Search → Activity, Monitoring → Logs).
- `/admin/legacy` redirects to `/admin`. CSRF protection and legacy-page request header compatibility are retained.
- Keep Discord bot features, Turso/R2 data, ticket numbering, AI proposal owner approvals, OAuth and final-only DM notifications unchanged. No database migration. Previously implemented 3.9.0 sidebar files can remain unused for now to simplify rollback; do not promote them to the homepage again.

## Next UI/UX polish — inside historical template only

1. **P1**: Improve crowded Activity and Logs table readability, filtering ergonomics and avoid wasteful background polling. Retain current layout/tab positions and behavior.
2. **P2**: Guilds: refine existing list rows, status visibility and destructive-action affordance without converting the page to a new sidebar-driven UI or overwhelming stats cards.
3. **P3**: Tarot, Cabin, Presence and Version: typography, spacing, button hierarchy and mobile scroll, keeping existing controls.
4. **P4**: T23 Feedback Center visual harmony with the classic header/palette, preserving proposal/review workflow.
5. Test desktop/mobile rendering, JavaScript, CSRF, actions, and rollback at each incremental PR. Do not deploy major visual changes without a user review.

## Checkpoint

- User preference clarified on 2026-10-08: revert primary UI to `dashboard.html`, then improve the familiar dashboard rather than rebuilding.
- PR #55 (3.9 sidebar polish) closed without merge.
- Restoration PR in progress. No changes to production until merged and Render deployment confirmed.


## T24.9 — Feedback integrated into the classic Admin tabs (2026-10-08)

**Owner requirement:** Feedback must be *inside the historical main Dashboard*, not on its own Admin page. Implement it as the ninth tab next to Activity/Presence/Version/Tarot/Cabin/Guilds/Overview/Logs, retaining the native classic tab bar and top header.

- The Feedback tab lazily mounts the existing authenticated Feedback Center in a chrome-free same-origin iframe, inside the old Dashboard content area. This is deliberate containment of its existing independent CSS/JS and private screenshot/AI review workflow; it is **not** the rejected T24 sidebar or an independent navigation experience. No duplicated sidebar/header in the embedded view.
- `/admin/feedback` and `/admin/feedback/<ticket-id>` redirect to `/admin?tab=feedback[&ticket=<id>]`. Old deep links remain useful; selecting ticket inside the view updates the parent URL through checked same-origin postMessage. Back/Forward restores ticket context.
- Private `/admin/_feedback/embed` is login-protected and no-store; ticket API, CSRF and server-side permissions remain exactly as before. Do not duplicate review permissions in frontend.
- All other eight classic tabs remain unchanged. Do not replace historic Dashboard with newer sidebar. New feedback data loads only when Feedback is selected.
- If later extracting Feedback as a native component, keep this same tab-only UX and feature parity; do not make a separate admin shell again.

**QA gate:** Test 8 classic tab workflows + new Feedback tab, mobile nested scrolling, old redirects, image evidence from Turso/R2, proposal accept/dismiss, history and final-only DM policy. Do not change any real ticket just to test UI without the owner choosing one.
