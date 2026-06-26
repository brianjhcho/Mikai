# MIKAI Notification Decider — V0

LLM-only notification decider. Pulls context from Graphiti, asks Claude
"should we notify Brian right now?", dispatches via ntfy.sh if yes.

This is the entire product surface. There is no UI. Notifications ARE the UI.

## Architecture (in one diagram)

```
   ┌──────────────────┐
   │ Graphiti @ :8100 │   ─── /search, /stats
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐         ┌────────────────────┐
   │  build_prompt()  │ ◀──────│ recent decisions    │
   └────────┬─────────┘         │ (~/.mikai/...db)    │
            │                   └────────────────────┘
            ▼
   ┌──────────────────────────┐
   │  claude -p ...           │   ─── Max plan, first-party OAuth
   │  (Max-legitimate)        │
   └────────┬─────────────────┘
            │
            ▼
   ┌──────────────────────────┐
   │  validate_decision()     │   ─── evidence UUIDs must exist
   └────────┬─────────────────┘
            │
            ▼ (if send)
   ┌──────────────────────────┐
   │  POST ntfy.sh/$TOPIC      │   ─── arrives on iPhone + Mac
   └──────────────────────────┘
```

## One-time setup

### 1. Pick an ntfy topic name (long + unguessable)

ntfy.sh topics are public. Anyone who guesses your topic name can read your
notifications. Use a long random string.

```bash
export MIKAI_NTFY_TOPIC="mikai-$(uuidgen | tr 'A-Z' 'a-z' | cut -c1-12)"
echo "Your topic: $MIKAI_NTFY_TOPIC"
```

Persist it in your shell config:

```bash
echo "export MIKAI_NTFY_TOPIC=\"$MIKAI_NTFY_TOPIC\"" >> ~/.zshrc
```

### 2. Install ntfy on iPhone

1. Open App Store → search "ntfy" → install (free, by Philipp Heckel).
2. Open the app → tap "+" → "Subscribe to topic".
3. Enter your topic name. Tap Subscribe.

### 3. (Optional) Install ntfy on Mac for native notifications there too

```bash
brew install --cask ntfy
# Then subscribe in the Mac app to the same topic
```

(Without this, Mac will not receive ntfy notifications. Brian's plan is
iPhone-first so this is optional.)

### 4. Initialize the local log

```bash
python infra/decider/mikai_decide.py --init
```

This creates `~/.mikai/notification_log.db`.

## Verify the path works

```bash
python infra/decider/mikai_decide.py --test-ntfy
```

You should see a notification on your iPhone within 5 seconds reading:
"MIKAI test — If you see this on iPhone or Mac, ntfy is working. Swipe to dismiss."

Swipe left, tap Clear. Standard iOS notification dismiss.

If you do **not** see the notification within ~10 seconds, the most likely problems are:
- `MIKAI_NTFY_TOPIC` not set or different in the script's env vs your shell
- iPhone has notifications disabled for ntfy app
- iPhone has Focus mode that blocks ntfy
- Topic name in the iPhone app doesn't match the one being POSTed to

## Run a real tick

A dry-run shows the prompt + Claude's decision but does NOT dispatch and does NOT log:

```bash
python infra/decider/mikai_decide.py --dry-run --show-prompt
```

A real tick (cooldown enforced, logs to SQLite):

```bash
python infra/decider/mikai_decide.py
```

Force-ignore cooldown:

```bash
python infra/decider/mikai_decide.py --force
```

## What you should see

- If Claude decides to send: a notification arrives on iPhone, the log row has `sent=1`.
- If Claude decides silence: no notification, the log row has `sent=0` and a `reasoning` field with Claude's stated reason.
- If anything fails: stderr explains, log row has `not_sent_reason` set.

## Inspect the log

```bash
sqlite3 ~/.mikai/notification_log.db \
  "SELECT tick_ts, sent, title, user_response, not_sent_reason FROM notification_log ORDER BY id DESC LIMIT 20"
```

## Cooldown

Default 2 hours between actual sends. Configure via `MIKAI_COOLDOWN_HOURS`. The
cooldown prevents the LLM from "machine-gunning" multiple notifications in a single
hour, even if it thinks each is important.

## Configuration (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `MIKAI_NTFY_TOPIC` | (required) | Your ntfy topic name |
| `MIKAI_NTFY_BASE` | `https://ntfy.sh` | Override to self-hosted ntfy server |
| `MIKAI_GRAPHITI_URL` | `http://localhost:8100` | Graphiti sidecar URL |
| `MIKAI_DB_PATH` | `~/.mikai/notification_log.db` | Local SQLite log location |
| `MIKAI_COOLDOWN_HOURS` | `2` | Hours to wait between sends |

## Scheduling (Claude Code Routines)

To run every 4 hours via Claude Code Routines (Max-legitimate cron):

```
claude /cron_create mikai-decide "0 */4 * * *" -- \
  python /Users/briancho/.superset/worktrees/MIKAI/pear-seashore/infra/decider/mikai_decide.py
```

(Confirm cron syntax with `claude /cron_create --help`. The exact syntax may have
changed since this README was written.)

## When to upgrade

This V0 is the minimum that works. Upgrade only when a specific failure mode hurts.

| Failure mode | Upgrade |
|---|---|
| iPhone notifications can't be acted on (no buttons) | Switch dispatch to `terminal-notifier` on Mac + ntfy Action Buttons on iOS |
| Privacy: ntfy.sh sees notification content | Self-host ntfy on Pattern B laptop (~1 hour) |
| Dismiss/act feedback doesn't reach the LLM | Wire ntfy webhook back into a log endpoint |
| LLM dismiss rate refuses to drop below 30% after weeks | Train LightGBM ranker on log → feed score as one feature into next prompt |
| Latency too slow for "right now" alerts | Add reactive triggers (new-episode-arrival webhook) alongside cron |

Each upgrade is independent. Don't pre-build them.

## What this does NOT include

By design, V0 omits:

- Action buttons on notifications (iOS swipe-dismiss only)
- Inline reply
- Native Swift app on iOS (would unlock full UNUserNotificationCenter API)
- Self-hosted ntfy (notification content goes through ntfy.sh)
- LightGBM/bandit learning layer (LLM in-context is the only learning)
- Identity folder schema, curator skill, project recipes — none of those
- Web UI / dashboard / inbox

Each of those is real work, none of it is required to test the thesis.
