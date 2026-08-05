# Surface Engine LaunchAgents

> **Per D-051 (TCC-safe pattern):** these files are **templates**. The canonical install location is `~/Library/Application Support/mikai/launchd/` — outside `~/Desktop/` and `~/Documents/` so launchd-spawned bash can `exec` them without TCC blocking. The repo holds the source of truth; the deployed copies are derived.

## Files

| File | Purpose |
|---|---|
| `com.mikai.figs-decide.plist` | LaunchAgent: runs Surface Engine decider 3x daily (07:00, 12:00, 18:00 local) |
| `com.mikai.figs-brief.plist` | LaunchAgent: writes the Calendar daily brief at 06:30 local |
| `figs-decide-runner.sh` | Wrapper script the decide LaunchAgent invokes |
| `figs-brief-runner.sh` | Wrapper script the brief LaunchAgent invokes |

## Install (or reinstall after edits)

```bash
LAUNCHD_DIR="$HOME/Library/Application Support/mikai/launchd"
REPO_LAUNCHD="$(git rev-parse --show-toplevel)/infra/decider/launchd"

mkdir -p "$LAUNCHD_DIR"
cp "$REPO_LAUNCHD"/com.mikai.figs-decide.plist "$LAUNCHD_DIR/"
cp "$REPO_LAUNCHD"/com.mikai.figs-brief.plist  "$LAUNCHD_DIR/"
cp "$REPO_LAUNCHD"/figs-decide-runner.sh       "$LAUNCHD_DIR/"
cp "$REPO_LAUNCHD"/figs-brief-runner.sh        "$LAUNCHD_DIR/"
chmod +x "$LAUNCHD_DIR"/figs-*.sh

for label in com.mikai.figs-decide com.mikai.figs-brief; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$LAUNCHD_DIR/$label.plist"
done

launchctl list | grep mikai.figs
```

## Required environment

`~/.mikai/launchd.env` must contain at minimum:

```
MIKAI_NTFY_TOPIC="mikai-<your-topic>"
MIKAI_GMAIL_USER="you@gmail.com"
MIKAI_GMAIL_APP_PASSWORD="<16-char google app password>"
```

The runners source this file at every invocation. **They also `unset ANTHROPIC_API_KEY` before calling `claude -p`** — having that env var set causes `claude` to refuse first-party OAuth and fall back to API billing, which fails for Surface Engine' headless prompts. The Graphiti-side runners (sync, claude-threads, dream) need `ANTHROPIC_API_KEY` for the DeepSeek/Voyage path, so the unset must be per-runner, not global.

## Path-dependency to fix on merge to main

Both runner scripts hardcode:

```
REPO="$HOME/.superset/worktrees/MIKAI/pear-seashore"
```

When Surface Engine lands on `main` (i.e., on `~/Desktop/MIKAI`), update both files:

```
REPO="$HOME/Desktop/MIKAI"
```

Then re-run the install steps above. There's no symlink trick to avoid this — launchd-spawned shells don't follow worktrees automatically.

## Pause / debug

```bash
# Pause a single agent
launchctl bootout "gui/$(id -u)/com.mikai.figs-decide"
launchctl bootout "gui/$(id -u)/com.mikai.figs-brief"

# Force a run now (without waiting for the schedule)
launchctl kickstart -k "gui/$(id -u)/com.mikai.figs-decide"

# Tail logs
tail -f ~/.mikai/logs/figs-decide.out.log
tail -f ~/.mikai/logs/figs-decide.err.log
tail -f ~/.mikai/logs/figs-brief.out.log
```

## Cadence reasoning

- **07:00, 12:00, 18:00 local for figs-decide**: morning briefing (start of day, before workday), midday (mid-attention window), evening review (end of day, after work). Cooldown of 2h in `mikai_decide.py` prevents back-to-back sends if a tick lags. PPP paper's 30%-dismiss-rate ceiling (CMU Nov 2025) implies ≤3 ticks/day is the right operating point for single-user systems.
- **06:30 local for figs-brief**: earlier than the 07:00 decide tick so the Calendar event is already there before the first ntfy notification fires.
