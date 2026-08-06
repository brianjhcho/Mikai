# Health check — cron-fleet heartbeat

`infra/mikai_brain/health.py`, scheduled as `com.mikai.health-check` (08:15 daily, 15 min after the Sunday consolidate window). Install: `make install-health-check`.

## What it catches

Every scheduled job writes a `ledger.run(mode=..., did=...)` row to `~/.mikai/brain/state/progress.jsonl` when it completes. The health check reads that ledger and asserts each expected mode has a row newer than its window:

| mode | max gap |
|---|---|
| consolidate | 200h |
| dream-weekly | 200h |
| dream-monthly | 800h |
| dream-nightly | 28h |
| ingestion | 12h |
| claude-threads | 30h |

A job that is silent past its window — crashed runner, unloaded-by-accident plist, expired cookie, never-seen mode — triggers **one ntfy POST** (`MIKAI_NTFY_TOPIC`): title `MIKAI health: N job(s) silent`, body listing each stale job with its last-seen timestamp. All green: no notification, but the check self-logs `mode="health-check"` so the heartbeat itself has a trace. Modes whose plist is not in `launchctl list` are skipped, so deliberately unloading a job silences its check too.

Manual run: `python3 -m infra.mikai_brain.health --dry-run` (prints the report, dispatches nothing).

## Adding an expected cadence

Add one `Cadence(mode, max_gap_hours, plist_label)` line to `EXPECTED` in `infra/mikai_brain/health.py`, and make sure the job actually calls `ledger.run(mode=...)` on success (dream jobs: pass `--ledger-mode <mode>` in the runner).

## Disabling temporarily

- One job's check: unload that job's plist (skipped automatically), or comment out its `Cadence` line.
- The whole heartbeat: `launchctl bootout gui/$(id -u) "$HOME/Library/Application Support/mikai/launchd/com.mikai.health-check.plist"`; re-enable with `make install-health-check`.

Logs: `~/.mikai/logs/health-check.{out,err}.log`.
