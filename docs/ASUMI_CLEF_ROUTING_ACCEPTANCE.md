# Asumi Clef Routing — Production Acceptance (T22.3)

**Checkpoint:** 2026-10-08. Clef routing is already implemented in T21/T22.3; this change hardens calibration checks and adds a bounded live smoke. **Not yet live-accepted until an authorized environment runs the smoke and Discord/Brave permissions are verified.**

## Execution path

1. Explicit slash/prefix and locally recognized tools keep precedence.
2. For nontrivial unhandled mention requests, `CloudflareDecisionRouter.from_env()` calls `@cf/cloudflare/clef-flash` through Workers AI if `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` (or `CLOUDFLARE_AUTH_TOKEN`) and the source flag `ASUMI_CLEF_ENABLED` are present.
3. Clef chooses among chat, tarot, summarize, help, web_search, discord_history and archive_search. The Python router rejects missing, malformed, unknown, uncalibrated, NaN/out-of-range or below-threshold answers.
4. No choice can bypass enabled-provider checks or source-specific safety gates; Discord private text must not become a public Brave query. Missing API credentials/timeouts remain local fallback. Reply continuation does not silently re-run tools.
5. Asumi logs `source`, `route_ms` and `clef_ms` without user message bodies or tokens.

## CI (safe, no external calls)

```bash
python -m unittest discover -s tests -p "test_assistant_clef_acceptance.py" -v
python -m unittest discover -s tests -p "test_assistant_source_routing.py" -v
python -m unittest discover -s tests -p "test_assistant_core.py" -v
```

The workflow runs the new unit suite on PRs. CI success is **not** proof of a live authenticated Workers AI request.

## Live Clef-only smoke (explicit, bounded)

In the deployment environment (not in public CI), with existing Cloudflare credentials:

```bash
python scripts/smoke_clef_routing.py --live
```

This runs **three** model classifications to check public web, guild history, and personal Archive routing. It does not call Brave, Discord Search or Archive tools and prints only case labels, route metadata and timing. If Cloudflare credentials are missing, it returns exit status 2; invalid/mismatched routes return exit status 1. Do not add a new public endpoint or put tokens in logs to run it.

**Production gate:** Run the script against configured bot credentials, then from a test channel verify source labels and actual tool outputs for public web, guild history and Archive, including inaccessible channels; check model timeout fallback and quota. No private Discord content should be sent to Brave. Do not mark T22 fully done until the Discord bot-token/ACL and Brave API tests also pass.

## Remaining goals

- T21: Archive Vectorize and overall live regression remain separate.
- T22.5: Multi-source history -> verified public entity -> Brave ranking is **not implemented** in this PR. Cross-source queries require consent validation and must not send raw history to a public provider.
- T24: retain the owner's historical tabbed Dashboard and in-dashboard Feedback tab; do not switch back to sidebar UI.

**Version:** no release bump until deployment/acceptance. No feature flags, provider secrets or quotas moved to Render env. The only required Render fields are external credentials/service IDs, as defined in `AGENTS.md`.
