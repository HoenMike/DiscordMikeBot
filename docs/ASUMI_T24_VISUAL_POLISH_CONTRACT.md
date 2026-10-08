# T24.8 — In-place Dashboard Visual Polish (owner direction 2026-10-08)

**Status:** First scoped PR for owner visual review; NOT a replacement dashboard, NOT approved for production yet.

## Definitive design decision
Owner prefers the existing live **Asumi 3.9.0 Dashboard** (the five-group sidebar and ten task pages) over the subsequently proposed stand-alone prototype/mockup. The prototype is **rejected as an implementation target**. Do not revert to the 3.8.x eight-tab monolith either.

Keep the existing page structure, routes, features, code contracts, labels and workflow. Refine the product in place, with small verifiable CSS/component changes. Do not create a second admin application, new framework, dashboard route, or alternate navigation hierarchy.

## Scope and baseline for first pass
From the actual 2026-10-08 /admin/guilds screenshot:
- Retain left sidebar and topbar. Slightly improve navigation density and active indicator, without moving menu groups or introducing a command palette.
- Preserve dark navy color family. Refine contrast, typography, spacing, border, focus and button hierarchy, and soften surface treatment in existing shared stylesheet.
- Guilds stays a **single existing list/card**, not a radically different analytics dashboard. Use the existing /api/guilds payload (icon, name, ID, member_count, suspended). Show a true status chip, inline icon/letter fallback, small local search and status filter; keep suspend/reopen visible.
- Put the existing destructive Leave action behind a small "•••" menu, with its pre-existing explicit confirmation. Keep API and server permissions unchanged.
- Do not introduce invented metrics, new models, permissions, or features; no new dependencies/build pipelines.
- Mobile still uses existing drawer; list rows stack without hiding administrative controls.

## Acceptance and rollout
- Compare screenshot with the **current** live page, not the rejected concept.
- Verify existing Overview, Feedback, Activity, Monitoring, AI & Search, Tarot, Cabin, Presence and Releases are still usable and share the same tokens.
- Test Guilds search, filters, suspend/reopen confirmation, Leave danger menu (do not actually leave production guild in QA), empty/error states, mobile wrap, keyboard focus and correct status after refresh.
- CI must pass; no production merge/deploy until owner has reviewed this incremental visual direction.
- Future scoped passes: Overview information hierarchy, Feedback legibility, Activity/Monitoring table density, then smaller pages; preserve routes and semantics.

## Checkpoint
- 2026-10-08: UI direction revised after prototype review; implement a small, reviewable branch against 3.9.0.
