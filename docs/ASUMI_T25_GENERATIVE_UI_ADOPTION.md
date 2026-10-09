# T25 — Generative UI adoption for Asumi (proposal + gated delivery)

**Checkpoint:** 2026-10-09. Owner wants [Thesys OpenUI](https://github.com/thesysdev/openui) to help Asumi deliver **ChatGPT-like rich output directly inside ordinary Discord chat replies**, not inside the Admin Dashboard. Discord cannot directly embed the OpenUI React runtime in a message; use native Components V2 and/or server-rendered images as the in-channel bridge. This is a proposal, **not an implemented rendering runtime**. Functional bugfixes to History, Brave routing and Feedback belong to the separate T25.0 regression patch.

## Non-negotiable product/technical contracts

- Discord messages cannot directly render React/OpenUI. Do not send OpenUI markup or raw HTML to Discord and call it an interactive message.
- Runtime is currently pinned to `discord.py==2.4.0`. Discord Components V2 require a library upgrade and a separate compatibility pass; **do not silently replace existing embeds/layouts**.
- The owner explicitly wants the original `web/templates/dashboard.html` and **Feedback as a tab inside that dashboard**. Do not switch to the rejected sidebar or build a parallel admin shell.
- Keep permission checks, CSRF, private image access, AI proposal approval, terminal-only notifications and numbered tickets. Generated UI must never execute owner-only operations without backend authorization.
- Keep social preview/proxy/yt-dlp fallback logic independent of OpenUI: a renderer does not fix a fetch/metadata problem.
- Search privacy: never send message contents or guessed entities from private Discord history to Brave.

## Goals

### T25.0 — Bugfix readiness (PR branch fix/asumi-20261009-search-feedback-ux)
- Discord History: when first/last message refers to `t`, `tôi`, `mình`, etc., search the requester. Explicitly tagged human wins. Anonymous/multi-author requests retain safe clarification.
- Named public tournament schedules (`khi nào CKTG bắt đầu`) route to Brave automatically under the existing cost/privacy gates, even if Clef times out or is absent. No invented dates or confirmation loops.
- Feedback: an unfinished draft is no longer a dead end; offer replace/keep/cancel. Existing drafts stay intact until the reporter explicitly chooses. Stale views are rejected.
- Unit regression is mandatory; live Discord Search and Brave API results still require a credentialed smoke.

### T25.1 — Native Discord UX (future, separate PR)
- Upgrade discord.py from 2.4 to a version with Components V2, after checking compatibility with Tarot, Feedback, social embeds, views and slash commands.
- Build small native, deterministic response components: source links and pagination for search, compact ticket actions, Tarot menus.
- Do not render arbitrary model-authored components. Maintain a strict allowlist and per-user interaction permissions.
- Keep embeds or existing buttons as fallbacks in incompatible contexts.

### T25.2 — In-message rich visual response pilot (OWNER'S ACTUAL REQUEST; future, separate PR)
**Clarification 2026-10-09:** The owner wants Asumi's **replies in ordinary Discord text channels** to look like ChatGPT's rich message UI (metric cards, colored warning labels, AQI timeline charts, tables and well-structured source notes), **not** an OpenUI-powered Admin Dashboard. The AQI Biên Hòa examples are presentation references. Preserve the historical dashboard as-is; a dashboard experiment is not the request.

Discord does not render OpenUI/React/HTML/JavaScript directly inside message bodies. Possible delivery options, in priority order:
1. **Discord-native Components V2** for interactive messages (text, containers, separators, media and buttons). This requires a separately validated discord.py upgrade from 2.4.0. Charts and arbitrary responsive card grids are *not* native widgets.
2. **Render rich report layouts to PNG/WebP** using a server-side browser or controlled HTML/SVG/image generator, then attach as Discord media in the actual reply. Include an accessible plain-text summary and source URLs outside/in addition to the image; image text is not selectable and cannot implement OpenUI interactions.
3. **Hybrid reply**: compact native header/summary + rich dynamically rendered chart/cards as an image + real Discord buttons for refresh, time ranges, previous/next data or sources. Buttons re-run authenticated server-side commands; they do not control React pixels inside an attached image.

Architecture proposal: Clef intent classification → trusted domain data adapters (IQAir/model/official sources) → validated structured report schema (with timestamp, observational vs forecast provenance) → OpenUI Lang/component allowlist **only if it adds value** → controlled renderer (Chromium/screenshot or standalone SVG/image renderer) → Discord media + native interaction. **Do not send raw OpenUI markup to Discord or accept arbitrary model-authored HTML/JS as executable.**

Pilot: AQI Biên Hòa in a normal channel, with a mobile-legible 800–1200 px dark-theme report: AQI/PM2.5 observation card, forecast trend as static chart, contrasting observation vs model estimates, data update time and clickable evidence links in the Discord message. Make the report fit attachment limits. Track generation latency, cloud rendering costs, fallback reliability and errors. When rendering fails, return the data-grounded text answer.

For fixed, repetitive report formats, a typed report template + native plotting is likely cheaper and more reliable than prompting an LLM to generate the full OpenUI layout for every message. Test OpenUI as an optional compositional layer rather than a hard dependency.

### T25.3 — Optional Discord Activity (deferred)
- Discord Embedded App SDK runs a **separate iframe Activity view within Discord**, not inline React in the message timeline. Use this only if the owner wants real clickable React/OpenUI charts/forms and accepts launching an Activity.
- Require identity binding, guild authorization, backend safety checks and a separate threat-model review. An Activity is **not** the substitute for ordinary in-channel rich replies.

### T25.4 — Dashboard remains unchanged
- The historical tabbed dashboard + integrated Feedback tab is a separate product surface. Do not pivot this UI goal into an unrelated dashboard rebuild. The prior 'OpenUI isolated web pilot inside Admin Dashboard' direction was an incorrect interpretation and is superseded.

## Acceptance checklist

1. `python -m unittest discover -s tests -p "test_assistant_temporal_history.py" -v`
2. `python -m unittest discover -s tests -p "test_assistant_source_routing.py" -v`
3. `python -m unittest discover -s tests -p "test_feedback_t23.py" -v`
4. CI and compileall clean; no changes to dashboard shell, API permissions, R2/Turso schemas or notification policy.
5. Live authorized smoke: self first/last with Jump to Message, CKTG search with fresh dated sources, draft replace and stale button rejection.
6. Do not call T25.1/T25.2/T25.3/T25.4 shipped until separate implementation and user-facing review have taken place.
