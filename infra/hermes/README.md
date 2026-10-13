# Hermes as MIKAI's hands

MIKAI is the brain (task-state, salience, wiki). Hermes Agent (Nous Research,
open source) is the hands: the conversational channel and the harness. The
Surface Engine keeps ntfy push for salience interruptions; Hermes is where
Brian converses and replies.

Nothing in this directory is code. Hermes is installed and configured outside
the repo, in `~/.hermes/`. This file records how, so it can be reproduced.

## Install (done 2026-10-13)

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o install.sh
bash install.sh --non-interactive --skip-browser --skip-computer-use
```

- Installs to `~/.hermes/` (code in `~/.hermes/hermes-agent`, pinned uv and
  Python under `~/.hermes/tools`). System Python 3.9 is untouched.
- Adds `~/.local/bin` to PATH in `~/.zprofile`.
- `--non-interactive` skips the setup wizard and the gateway service install,
  so nothing runs in the background.
- Installed version: v0.21.7 (2026.9.24).

## Model: Claude subscription, no API key

```bash
hermes plugins install claude-subscription-directsdk
hermes plugins enable claude-subscription-directsdk-experimental
```

`~/.hermes/config.yaml`:

```yaml
model:
  default: "sonnet"
  provider: "claude-subscription-directsdk-experimental"
```

The plugin runs every turn through the official `claude` CLI that is already
logged in (`claude auth status` → `authMethod: claude.ai`). Per the plugin docs,
turns draw on the subscription's Agent SDK allowance "at exactly the
`claude -p` / Agent SDK rate", the same pool as `claude -p` and interactive
use. Keep "extra usage" disabled on the Claude account to avoid overage.
Docs: https://hermes-agent.nousresearch.com/docs/plugins/claude-subscription-directsdk

Backup of the pre-MIKAI config: `~/.hermes/config.yaml.bak-pre-mikai`.

## MIKAI as an MCP server

Appended to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  mikai:
    command: "node"
    args: ["/Users/briancho/.superset/worktrees/MIKAI/pear-seashore/infra/mikai-mcp/dist/src/index.js"]
    env:
      MIKAI_WIKI_ROOT: "/Users/briancho/.mikai/wiki-mikai-parallel-test"
      OLLAMA_HOST: "http://localhost:11434"
```

`dist/` is gitignored; rebuild with `npm install && npm run build` in
`infra/mikai-mcp/` if it is missing. Hermes exposes the tools as
`mcp_mikai_<tool>`.

Check: `hermes mcp test mikai` (10 tools discovered on 2026-10-13).

Smoke test (one turn, verified 2026-10-13):

```bash
hermes -z "Call the mikai_get_stalled_threads tool and list each stalled thread's title and state." --usage-file usage.json
```

A trivial turn used ~62K tokens, mostly Hermes's own system prompt (58 bundled
skills plus tool schemas). Trim toolsets/skills before running it on a schedule.

## iMessage (not yet connected)

Hermes supports two iMessage bridges:

| Bridge | How it works | Fit for MIKAI |
|---|---|---|
| **BlueBubbles** (recommended) | Free, open-source server on a Mac that drives Messages.app. Local; message content stays on the Mac. | Matches the trust positioning. Needs a Mac that stays awake and logged in, plus an Apple ID signed into Messages on it. |
| **Photon** | Managed cloud service; no Mac needed. | Message content passes through Photon's servers. Conflicts with "your data stays on your disk". |

The open question is identity. BlueBubbles sends as whatever Apple ID is signed
into Messages.app on that Mac. On Brian's only Mac that is his own Apple ID, so
Hermes would be texting from Brian to Brian. For a clean "text MIKAI" thread,
MIKAI needs its own Apple ID signed into Messages on a Mac that stays awake:
a spare Mac, or a second macOS user (which needs BlueBubbles's Private API
helper to send in the background).

### Brian's steps

1. Decide the identity: a dedicated Apple ID for MIKAI (recommended) on a spare
   Mac, or accept self-messaging on this Mac.
2. Install BlueBubbles Server from https://bluebubbles.app on that Mac, sign
   Messages.app into the chosen Apple ID, and grant BlueBubbles **Full Disk
   Access** and **Automation** (Messages) in System Settings → Privacy & Security.
3. In BlueBubbles → Settings → API, copy the Server URL and password.
4. Add to `~/.hermes/.env` (never commit):
   ```
   BLUEBUBBLES_SERVER_URL=http://<mac-ip>:1234
   BLUEBUBBLES_PASSWORD=<from BlueBubbles>
   BLUEBUBBLES_ALLOWED_USERS=<Brian's phone number or Apple ID email>
   BLUEBUBBLES_HOME_CHANNEL=<Brian's phone number or Apple ID email>
   ```
5. Enable the platform in `~/.hermes/config.yaml`:
   ```yaml
   platforms:
     bluebubbles:
       enabled: true
   ```
6. Run `hermes gateway setup`, then `hermes gateway run` (foreground) to test,
   and `hermes pairing approve bluebubbles <CODE>` for the first DM.
7. Only after that works: `hermes gateway install` to run it as a service.

Docs: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/bluebubbles

## Not done on purpose

- No gateway or background service installed; no message has been sent.
- ntfy stays with the Surface Engine (`infra/decider/`); Hermes's ntfy platform
  is not enabled.
- No Hermes memory-provider plugin yet. MIKAI is connected over MCP only.
