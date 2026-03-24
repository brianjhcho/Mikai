# MIKAI Daily Sync Scheduler

Runs the full sync pipeline — iMessage → Gmail → build-graph — once per day at 06:00 local time via macOS launchd.

---

## Install the launchd job

Registers the job to run automatically at 06:00 daily:

```bash
cp engine/scheduler/com.mikai.daily-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mikai.daily-sync.plist
```

Or use the npm shortcut:

```bash
npm run scheduler:install
```

---

## Verify it is loaded

```bash
launchctl list | grep mikai
```

A row with `com.mikai.daily-sync` confirms the job is registered. The first column shows the last exit code (`-` means it has not run yet).

---

## Test manually

```bash
npm run scheduler:run
```

Or run the script directly:

```bash
bash engine/scheduler/daily-sync.sh
```

Both write output to `engine/scheduler/logs/daily-sync-YYYY-MM-DD.log`.

---

## Tail logs

```bash
tail -f engine/scheduler/logs/daily-sync-$(date +%Y-%m-%d).log
```

launchd's own stdout/stderr are written separately:

```bash
tail -f engine/scheduler/logs/launchd-stdout.log
tail -f engine/scheduler/logs/launchd-stderr.log
```

---

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.mikai.daily-sync.plist
rm ~/Library/LaunchAgents/com.mikai.daily-sync.plist
```

---

## Troubleshooting

### `npm: command not found` or `tsx: command not found`

launchd launches with a minimal `PATH`. The plist already includes `/opt/homebrew/bin` and `/usr/local/bin`, which covers most Homebrew and nvm setups. If npm is installed elsewhere, edit the `PATH` value in `com.mikai.daily-sync.plist` and reload:

```bash
launchctl unload ~/Library/LaunchAgents/com.mikai.daily-sync.plist
cp engine/scheduler/com.mikai.daily-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mikai.daily-sync.plist
```

To find the correct path for npm:

```bash
which npm
```

### Permission denied on `chat.db`

iMessage sync reads `~/Library/Messages/chat.db`. macOS Full Disk Access is required for the process running the script.

Go to **System Settings → Privacy & Security → Full Disk Access** and add Terminal (or whichever app runs launchd agents for your user).

### Gmail OAuth token expired

The Gmail sync uses a stored OAuth refresh token. If it has expired:

1. Delete the cached token file (path printed in the sync error log).
2. Re-run `npm run sync:gmail` interactively to re-authorize in the browser.
3. The new token is cached automatically for subsequent scheduled runs.

### Job ran but nothing synced

Check the dated log file for per-stage exit codes:

```bash
cat engine/scheduler/logs/daily-sync-$(date +%Y-%m-%d).log
```

Each stage logs `OK` or `FAILED (exit N) — continuing`. A non-zero exit code from npm usually means a missing dependency or misconfigured environment variable — check `.env` at the project root.
