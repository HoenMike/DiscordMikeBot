# Codex Reset Watch — opt-in Discord role alerts

Status: PR / not deployed. Guild owner must configure and enable in Discord.
Feature package: features/codex_watch/
Policy defaults: core/constants.py

## Goal

Send brief Vietnamese Codex reset notices into a Discord channel and ping
the selected role (including BANKED announcements). Never send real pings on
startup, setup, preview, CI, or PR creation. No extra bot/webhook/LLM required.

## Admin setup (guild only, Manage Server permission)

1. Make a Codex role and #codex-alerts channel.
2. Grant Asumi View Channel and Send Messages. Make role mentionable or give
   bot Mention All Roles permission. The bot only uses the selected role,
   never @everyone or @here.
3. Run /codex-watch setup with channel:#codex-alerts role:@Codex.
   Saves config in Turso with enabled=OFF, even if previously ON.
4. Run /codex-watch preview. This is ephemeral and never pings.
5. Run /codex-watch enable after review. Only NEW posts after this time
   may trigger role pings. ALL alert categories (including banked) tag role.
6. /codex-watch status and /codex-watch disable inspect and stop delivery.

If Turso is unavailable Watch fails closed (no alert sent). Do not assume
missing data means the reset happened. Bot downtime may miss brief events.

## Source and classification policy

- Poll every five minutes only when at least one guild is enabled.
- Fixed allowlisted, bounded HTTPS GET endpoints:
  https://codex-reset.com/api/feed (primary Tibo post mirror)
  https://didcodexreset.com/openapi/v1/records?page=1&pageSize=10
    (second Tibo post mirror, public API quota 60 requests/hour)
  https://codex-reset.com/api/forecast (statistical model)
  https://codex.gussuriworks.com/en (second statistical model)
- Reject stale feeds, invalid timestamps, non-Tibo X URLs, mismatched status
  ID or very old posts (older than three days).
- Classify using text attributed to Tibo; never trust tracker enum alone.
  Deduplicate cross-source results by canonical X post ID: two mirrors of
  the same Tibo tweet are one source event, not two independent proofs.
  The original tweet URL is preserved; direct X auth is not guaranteed.
- Exclude Day 8 / Reset alone, jokes, polls, generic preference statements,
  and the banked-only phrase Confirmed landed across all accounts.
- Explicit BANKED grants must NOT be confused with automatic global reset.
- Global reset landing by EOD is a future commitment, not completion.
  Completion requires explicitly processed/propagated language.
- Forecast warning is unofficial: >75% from TWO independently updated
  experimental models. Do not treat tracker commitment score (83%),
  poll scores or personal usage % as probabilities. If second source changes
  layout or loses timestamp, do not emit prediction.
- Parse EOD using speaker's LA calendar date first, then convert to Vietnam
  time. PDT vs PST ambiguity is displayed as such.

## Dedupe and delivery

Turso tables:
  asumi_codex_watch (per guild; channel, role, enabled, active_after)
  asumi_codex_watch_delivery (per guild+event_key; lease/status/message_id)

Atomic claim prevents duplicate pings across bot restarts or concurrent
workers. Events grouped by LA date and state (announced/completed/banked/
changed). Advancement to new state may ping again. Failed delivery retries
after a lease. A crash between Discord accepting a send and marking it
delivered can still cause a duplicate; no exactly-once claim.

## Discord rendering and link onebox policy

A message contains only a short text alert, canonical X link and ONE role
mention using the Discord role ID syntax <@&role_id>. Only configured role is
allowed in allowed_mentions; user mentions and @everyone are disabled.

Canonical URL displays inside angle brackets, e.g.
  <https://x.com/thsottiaux/status/2109812360596865224>

The send also uses suppress_embeds=True so Discord cannot add an oversized
link preview card. Preview uses ephemeral response, AllowedMentions.none()
and suppress_embeds=True; cannot ping anyone.

## Release/QA

CI: .github/workflows/asumi-codex-watch.yml
Runs compile and deterministic tests for false positives, timestamps,
banked/global, forecast, and role-only/no-onebox sends.

A merged PR alone DOES NOT activate alerts. After deployment run setup,
preview, then enable. Live acceptance must independently verify Discord
permissions, notification visibility, no onebox, disable, and dedupe.
