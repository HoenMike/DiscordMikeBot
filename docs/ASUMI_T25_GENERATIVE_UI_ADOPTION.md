### 2026-10-09 owner correction — Tarot visual baseline

The original Tarot card board and interactive flip workflow are the approved baseline.
The T25 one-card Insight PNG replacement and `tarot_reading.txt` preview are rolled back
in **Asumi 3.13.3**. Final readings render in the original board + separate Discord
embed. Long text is readable via ephemeral Discord pagination, not a TXT attachment.
The historical T25.1b native file component was deliberately superseded for Tarot;
native Components V2 Search continues independently.

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

### T25.1 — Native Discord UX (implementation in stages)

**T25.1a — Asumi 3.13.0, native Search pilot:** upgrade discord.py 2.4.0 → 2.7.1 and render read-only, non-fuel Brave answers as native `LayoutView → Container → TextDisplay/Separator/TextDisplay`. Keep answer-first bold takeaway and numbered [1] [2] citations. No `content` or `embed` alongside a V2 view. Existing specialised factual sources (fuel/weather), Tarot, Feedback, social embed and other commands retain V1 behavior. On Discord HTTP 400 explicitly rejecting V2, use a single legacy embed fallback; do not retry ambiguous network failures to avoid duplicate answers. Controlled rollback is `ASUMI_SEARCH_NATIVE_V2_ENABLED=False` in `core/constants.py` and redeploy.

**T25.1b — Asumi 3.13.1 (code in PR):** one-card Tarot **📖 Đọc đầy đủ** opens a read-only V2 `LayoutView` as a new ephemeral response; it never converts the existing V1 Tarot draw/flip message. Long readings show a native File component referencing `tarot_reading.txt`; the complete reading remains in the original public Tarot message. Explicit HTTP 400 → old embed fallback. The author-only follow-up, why and clarifier restrictions remain unchanged.

**T25.1c — Still pending:** native Search pagination/interactive read-only actions where useful, full mobile/desktop visual acceptance, and regression for interactions. Do not claim that T25.1 is complete merely because the foundation and Search pilot shipped.

- Never allow AI to emit arbitrary component definitions. Continue using a code-owned allowlist of approved UI builders.
- Legacy embed/button views remain fully supported; do not convert existing interaction messages in place because the V2 flag is irreversible.

### T25.2 — In-message rich visual response pilot (Tarot one-card implemented in feature branch; live acceptance pending)
**Clarification 2026-10-09:** The owner wants Asumi's **replies in ordinary Discord text channels** to look like ChatGPT's rich message UI (metric cards, colored warning labels, AQI timeline charts, tables and well-structured source notes), **not** an OpenUI-powered Admin Dashboard. The AQI Biên Hòa examples are presentation references. Preserve the historical dashboard as-is; a dashboard experiment is not the request.

Discord does not render OpenUI/React/HTML/JavaScript directly inside message bodies. Possible delivery options, in priority order:
1. **Discord-native Components V2** for interactive messages (text, containers, separators, media and buttons). This requires a separately validated discord.py upgrade from 2.4.0. Charts and arbitrary responsive card grids are *not* native widgets.
2. **Render rich report layouts to PNG/WebP** using a server-side browser or controlled HTML/SVG/image generator, then attach as Discord media in the actual reply. Include an accessible plain-text summary and source URLs outside/in addition to the image; image text is not selectable and cannot implement OpenUI interactions.
3. **Hybrid reply**: compact native header/summary + rich dynamically rendered chart/cards as an image + real Discord buttons for refresh, time ranges, previous/next data or sources. Buttons re-run authenticated server-side commands; they do not control React pixels inside an attached image.

Architecture proposal: Clef intent classification → trusted domain data adapters (IQAir/model/official sources) → validated structured report schema (with timestamp, observational vs forecast provenance) → OpenUI Lang/component allowlist **only if it adds value** → controlled renderer (Chromium/screenshot or standalone SVG/image renderer) → Discord media + native interaction. **Do not send raw OpenUI markup to Discord or accept arbitrary model-authored HTML/JS as executable.**

**Tarot pilot (Asumi 3.11.0, branch `feat/asumi-t25-tarot-rich-search-answers`):** Daily, Single and Yes/No one-card results produce a compact 1200×760 inline Pillow-rendered image from the existing real card art + `RecapCardState` (no extra AI call), with a short accessible embed and a `📖 Đọc đầy đủ` button for channel viewers. Existing multi-card boards/clarifiers stay available. The complete one-card reading also ships as a durable `tarot_reading.txt` attachment readable by authorized viewers after the ephemeral controls expire, and any viewer can open it via the `Đọc đầy đủ` button while the View is active. This preserves public-reading behavior. This is **not** the OpenUI library itself; Discord does not run React in message bodies. Full release requires CI, merge, Render deploy and a Discord mobile/desktop screenshot smoke. 
   
**Next pilot (not implemented):** AQI Biên Hòa in a normal channel, with a mobile-legible 800–1200 px dark-theme report: AQI/PM2.5 observation card, forecast trend as static chart, contrasting observation vs model estimates, data update time and clickable evidence links in the Discord message. Make the report fit attachment limits. Track generation latency, cloud rendering costs, fallback reliability and errors. When rendering fails, return the data-grounded text answer.

For fixed, repetitive report formats, a typed report template + native plotting is likely cheaper and more reliable than prompting an LLM to generate the full OpenUI layout for every message. Test OpenUI as an optional compositional layer rather than a hard dependency.

### T25.3 — Optional Discord Activity (deferred)
- Discord Embedded App SDK runs a **separate iframe Activity view within Discord**, not inline React in the message timeline. Use this only if the owner wants real clickable React/OpenUI charts/forms and accepts launching an Activity.
- Require identity binding, guild authorization, backend safety checks and a separate threat-model review. An Activity is **not** the substitute for ordinary in-channel rich replies.

### T25.4 — Dashboard remains unchanged
- The historical tabbed dashboard + integrated Feedback tab is a separate product surface. Do not pivot this UI goal into an unrelated dashboard rebuild. The prior 'OpenUI isolated web pilot inside Admin Dashboard' direction was an incorrect interpretation and is superseded.

### T25.5 — Search answer synthesis as a background tool (Asumi 3.11.0 feature branch)

- Root cause: `_execute_web_search` previously synthesized answers only for Clef + `local_fresh_public`; the `local_public_event_schedule` CKTG route and explicit web requests skipped synthesis and showed raw Brave results.
- For **all non-fuel public Brave searches**, run grounded synthesis from bounded Brave snippets/public page evidence with a direct-answer-first prompt. Never send private Discord context.
- UI (Asumi 3.11.1): **bold the answer-first takeaway**, use a separate short paragraph for explanation, and place at most two clickable numeric citations as `[1] · [2]` at the bottom. Hide source titles, hostnames, verification headings and raw snippets. If synthesis fails, say that the answer could not be verified, not a fake date.
- Structured fuel, weather and other source-specific verified providers retain their behavior; quota, cooldown and private context gates remain.
- Later: source quality ranking, contradictory-date checks, structured answer schema with confidence and provenance, latency instrumentation. Do not claim model-synthesized text to be externally verified.

## Acceptance checklist

1. `python -m unittest discover -s tests -p "test_assistant_temporal_history.py" -v`
2. `python -m unittest discover -s tests -p "test_assistant_source_routing.py" -v`
3. `python -m unittest discover -s tests -p "test_feedback_t23.py" -v`
4. CI and compileall clean; no changes to dashboard shell, API permissions, R2/Turso schemas or notification policy.
5. Live authorized smoke: self first/last with Jump to Message, CKTG search with fresh dated sources, draft replace and stale button rejection.
6. Do not call T25.1/T25.2/T25.3/T25.4 shipped until separate implementation and user-facing review have taken place.
