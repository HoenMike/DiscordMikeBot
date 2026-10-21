# Asumi AI Usage & Cost Monitor — owner guide

Status: **TEST BRANCH / not deployed or live accepted**. Fast natural-language usage route is being integrated alongside the existing `/ai_cost` command. Source: https://ai.google.dev/gemini-api/docs/pricing (consult before changing prices). This is a **Gemini text Standard Paid Tier cost estimate**, not a Cloud Billing invoice.

## Discord quick report

The application owner runs the private slash command **/ai_cost** from any channel; results are ephemeral and do not interrupt the conversation or Dungeon Misfits.

- /ai_cost — last 7 days, requests/model, input/output/thinking/cached tokens, estimated USD/VND spend, 30-day run-rate.
- /ai_cost days:30 — last 30 days.
- /ai_cost days:30 prepay_vnd:150000 — add a *manual* prepaid wallet balance to estimate how many months of usage it covers.
- /ai_cost days:30 prepay_vnd:150000 credits_vnd:1298530 — include manually confirmed eligible GCP credits in an explicitly conditional runway scenario. Do NOT enter these credits until Google Cloud Billing shows they apply to Gemini API.
- /ai_cost days:7 fx_vnd:26000 — choose assumed exchange rate.

Nothing is automatically fetched from or written to Google Billing. The balances supplied at query time are NOT stored as account credentials or authoritative balances. No data is backfilled: the ledger begins recording at deployment.

## Web Dashboard (existing historical admin)

After merge/deploy, sign in at /admin and select **AI Usage**, or bookmark /admin?tab=ai-usage. The tab lazy-fetches GET /api/admin/ai-usage?days=7|30 and displays today's UTC request/cost subtotal, 7/30-day token and error counts, model/provider/feature breakdown, and a Chart.js daily price trend. Unlike a new dashboard app, this is part of the old classic tab bar and leaves Feedback/Tarot in place.

The right-side calculator lets the owner manually enter *remaining* prepaid VND, *eligible and unexpired* GCP credit VND (if verified in Google Cloud Billing), and an assumed FX rate. It derives theoretical days/months from the observed 30-day spend rate. No balance is retrieved from Google; figures are not written to Turso or used as a billing cap. An early sample under 3 days or missing prices means projections are tentative/incomplete.

The page never runs an LLM call. Unauthorized API access gives 401, invalid windows 400, and Turso errors 503; no unavailable DB is interpreted as 0đ. Mobile viewing and live production reconciliation are outstanding release gates.

## What is stored

Instrumented: every call that passes through the common async **core.ai.bounded_ai_generate** Gemini SDK wrapper, including failed attempts and fallbacks. Current Gemini coverage: assistant conversation, Tarot, Cabin, Summary/QA (future Dungeon DM if it uses this wrapper). **Cloudflare Clef** attempts are also recorded by model, routing task, latency and success/failure, but no token or cost is invented for Clef.

Turso record: UTC timestamp, provider, task bucket, requested model, model returned by the provider when available, success/failure, token counts from usage_metadata, micro-USD estimated cost, error class and latency.

No prompts, answers, full message text, Discord user IDs, channel IDs, model raw payload or tokens/credentials are stored. Request timeouts without reliable provider token metadata have **UNKNOWN billing**, not $0. New/unpriced model IDs remain **UNPRICED**, not $0.

**Not included in priced projected totals:** Cloudflare Clef/Workers AI (request counts tracked but not provider-specific Neurons), Brave, Render, non-Gemini SDK calls, audio/images, taxes, Google Search grounding, cache storage and requests missing usage metadata. Google Cloud Billing is authoritative. The projection may be a lower bound.

## Price model (October 2026)

Gemini 3.8 Flash standard text: $0.75/M input, $3.75/M output (including thinking), $0.075/M cached input; 2027-01-01 price increases to $1.50/$7.50/$0.15 respectively. Gemini 3.6/3.7 Flash use the same schedules. Gemini 3.5 Flash Lite: $0.30/M input, $2.50/M output, $0.03/M cached. Gemini 3.1 Flash Lite: $0.25/M input, $1.50/M output, $0.025/M cached. Gemini 3.5 Flash: $1.50/M input, $9.00/M output, $0.15/M cached. Other model pricing is not guessed.

The Google usage metadata prompt-token total already includes cached tokens: bill noncached and cached separately. Count both candidate and thinking tokens at the output rate. Record the estimated price at call time to preserve history as published prices change.

The report calculates 30-day run-rate = observed (rolling 7d or 30d) estimated cost / observation-window days × 30. A short observation window is **not** a long-term guarantee. Paid Tier RPM/RPD is not free-call allocation. Credits may expire; whether they actually offset API charges must be verified in Cloud Billing. Prepay is required to remain active even when eligible credits are available.

## Storage and privacy

On production with Turso auth configured, if Turso is unavailable telemetry **does not switch to ephemeral SQLite**. Normal AI replies must still work, but data may be missing; the report must show an explicit DB error rather than claiming that missing events were free. Local SQLite is permitted for isolated dev/tests.

No new dashboard is built. No unsolicited cost alert or DM is enabled. This feature never changes routing, model selection, Tarot UX or gameplay channels.

## QA / live acceptance

1. Run python -m unittest discover -s tests -p "test_ai_usage_cost.py" -v, plus relevant Assistant/Tarot/Summary tests.
2. Verify the AI Cost workflow CI and slash command syncing, including unauthorized-users ephemeral denial and bot-owner authorization.
3. On a live test guild, trigger normal chat, Tarot and Summary; then use /ai_cost and check model/task and token totals.
4. Fail a model once and confirm attempt-level tracking/fallback; simulate Turso outage and check no local split-brain ledger.
5. Compare the usage numbers with AI Studio/GCP Billing for the same UTC interval. Billing can lag and credit eligibility is separate from a price estimate.
6. Verify Discord mobile presentation, long model names and absence of channel-wide reports.
7. Mark LIVE_ACCEPTED only after actual deploy and owner testing.

## Future improvements (separate scopes)

- Owner opt-in daily/weekly budget warning; no unrequested DMs.
- Provider-specific metering for Cloudflare Workers/Clef and Brave, kept separate from Google charges.
- Authorized read-only Google Billing export reconciliation to distinguish real invoice, prepaid wallet and promotional credits.
- Cost/latency-aware model routing after 1–2 weeks of measured usage, not speculative "free quota".
- Read-only monitoring tab in the **existing** classic Dashboard only with design approval.
