# Dungeon Misfits — T30 Engine Spike (NO RELEASE)

Status: experimental offline rules prototype, not a Discord feature.

This branch intentionally contains **no Discord cog registration, commands, Gemini calls,
Turso writes, admin dashboard, bot version bump, changelog, or patch notes.**

## Run locally

```bash
python -m unittest discover -s tests -p 'test_dnd_engine.py' -v
python -m scripts.simulate_dnd
```

Engine: `features/dnd/engine.py`. Uses only Python standard library.
The sample consists of fictional Scout/Tank and Mike; no other real users are referenced.

## What is already testable?

- Four attributes, eight points total, capped and validated
- Party of 2–5, original classes with strictly allowlisted abilities
- Typed single-action intents per round; no freeform LLM interpretation yet
- d20 checks, initiative, damage, Focus, zone targeting, enemy telegraph
- Simultaneous assist -> +2 bounded synergy; guard if AFK
- Win/defeat/party retreat, immutable states, recorded dice, state hashes
- Stable replay for same seed/state; order of Discord submissions cannot affect rolls

## Explicit blockers before live Discord play

1. Current `core/db.py` can fallback from Turso to local SQLite and its ordinary
   `execute` method does not make a multi-statement round commit atomic.
   Implement a game-specific transactional CAS/event+outbox repository with
   integration tests on **both** backends; production must fail closed on Turso outage.
2. Scene/room state machine, exploration puzzles, content versioning and round timeouts.
3. Channel-scoped `/dnd` commands, ACL, lobby UI and Discord 3-second acknowledgements.
4. AI intent parser/narrator behind strict allowlists (no AI authority over HP/loot).
5. Concurrent workers, restart/replay, stale button and outbox tests.
6. Balancing simulation across 2/3/5 players and real playtests.

No production exposure, no auto-deploy, no release-note/version changes from this spike.
