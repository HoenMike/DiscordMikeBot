# T26 — Asumi Deploy Recovery Queue

Status: code on feature branch; CI + authorized Discord smoke required.

## Why

Discord **does not queue Gateway MESSAGE_CREATE events** when a bot is offline. Asumi currently starts the Discord Gateway and Flask server in the same Render process. A deploy can drop both in-flight and newly sent @Asumi requests.

## User experience

- Online: register an explicit @Asumi conversation in Turso by ID before executing, claim it atomically, then mark done.
- Deploy downtime: Discord keeps the message in the original channel; after READY, Asumi scans bounded recent accessible history to find missed mentions, acknowledges the original message, processes it, removes the temporary acknowledgement.
- Interrupted work: stale processing leases are retried after their 90-second lease. A real prior Asumi reply prevents duplicate execution.
- Only conversation/read-only requests may be replayed. Commands, Tarot draws, Feedback submissions, admin changes and Archive mutations must not execute automatically after a restart.
- No message body or image is persisted in Turso; queue stores IDs, timestamps, status and attempts.
- If Turso is unavailable, **do not claim reliable queueing**. Normal live chat still works, but a redeploy gap cannot be fully recovered.

## Boundaries

- Guild messages explicitly tagging @Asumi only. Mentionless follow-ups and slash interactions missed offline cannot be recovered.
- Require both bot and sender to retain permission to see the channel; bot must have history/read/send permission.
- 15-minute maximum history lookback; first introduction of feature: 2 minutes. Up to 80 accessible channels, 100 newest messages per channel and 60 candidates per pass. Active threads included; archived threads not scanned.
- No replay of past messages older than window or deleted/inaccessible messages. Recovery is best-effort, not zero-downtime.
- Deduplication is via Turso atomic claims and checking existing Discord replies. Progress notes do not count as final replies; only two attempts.
- Do not put non-secret knobs in Render env; see core/constants.py.

## Files

- core/deploy_recovery.py — durable register, CAS claim, heartbeat, history recovery.
- bot_instance.py — on_ready recovery task, on_message register/finish around assistant.
- features/assistant/cog.py — recovery mode blocks state-changing tools.
- tests/test_deploy_recovery.py — security + queue + bounded history tests.
- Turso tables: asumi_deploy_gateway and asumi_deploy_queue. Existing async DB adapter reused.

## Production acceptance checklist

1. Run CI with recovery and old assistant/feedback tests.
2. On a Turso-backed production deployment, verify heartbeat and no fallback to Render ephemeral SQLite.
3. During a controlled deploy, send a user mention asking Asumi to explain a message. Once READY, the bot should reply to the original request without another ping.
4. Check an already answered mention is not repeated, including when old and new containers briefly overlap.
5. Test a request cut off mid-processing, then wait through one lease retry.
6. Confirm commands, Tarot, Feedback, private channel permissions and bot-only mentions do not auto-replay.
7. Record screenshots/log timings; do not declare live-accepted from unit tests alone.

A later true zero-downtime design would decouple the bot worker from Flask and deploy workers with durable jobs and a single active gateway leader.
