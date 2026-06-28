# MIKAI — Dream + Wiki Runtime (operational reference)

**Status:** Live on `main` (built 2026-06-28). Prototype — base assumptions intact, numeric machinery deferred.
**Design rationale & contradiction resolution:** `MEMORY_ARCHITECTURE.md` Parts A–H on the `navy-windshield` worktree (the epistemic-design branch).
**This doc:** how the two new nightly daemons actually run, and how to operate/debug them.

---

## What this adds to MIKAI

Two new launchd daemons sit on top of the existing L3 substrate (Graphiti + Neo4j),
turning it from a queryable graph into a **self-maintaining model of the user**:

1. **Capture** — `claude_threads.py` pulls Claude.ai web/desktop conversations into
   the graph daily. (Closes the `claude-thread = 0 episodes` gap — that source was
   never being ingested; the "Claude.ai connector" was the outbound MCP connector,
   not an ingestion path.)
2. **Dream** — `dream.py` nightly reflects the last 7 days of episodes into a
   human-readable **wiki** (`~/.mikai/wiki/wiki.md`) — what the user wants, values,
   is doing, and is conflicted about. Read whole by any LLM to understand the user.

```
Claude.ai threads ─┐
Claude Code  ──────┤→ EPISODES → Graphiti/Neo4j ──→ dream.py ──→ ~/.mikai/wiki/wiki.md
Apple Notes  ──────┘  (capture)   (substrate)       (reflect)     (projection, read whole)
```

The graph is the **immutable substrate**; the wiki is a **disposable projection**
re-derived every night. Nothing the dream writes is authoritative — it's all
re-derivable from the graph.

---

## Component 1 — Claude.ai thread capture (`infra/graphiti/claude_threads.py`)

**Source.** Claude.ai conversation *content is not stored locally* (the desktop
app's IndexedDB holds only telemetry), so the only source is the claude.ai
internal web API: `GET /api/organizations/{org}/chat_conversations` (list) and
`.../{uuid}?tree=True&rendering_mode=raw` (messages).

**Auth (self-renewing).** Decrypts the live `sessionKey` cookie from the Claude
desktop app's `Cookies` SQLite using the `Claude Safe Storage` AES key (Chromium
v10: PBKDF2-HMAC-SHA1, salt `saltysalt`, 1003 iters, 16-byte key → AES-128-CBC,
16-space IV). The desktop app refreshes that cookie as you use it, so there is no
monthly token re-paste.

- **Keychain-under-launchd hang:** `security find-generic-password` blocks under a
  LaunchAgent (auth prompt can't render). Fix: the Safe Storage password is
  *stable* (set once at app install), so it's cached as `CLAUDE_SAFE_STORAGE_PW`
  in `~/.mikai/launchd.env`; runtime decrypt uses it, no keychain call.
- **Fallbacks:** `CLAUDE_SESSION_KEY` env var skips decryption entirely.
- **Cloudflare gotcha:** the per-conversation endpoint 403s without
  `Referer` / `Origin` / `anthropic-client-platform: web_claude_ai` headers.

**Ingestion.** One episode per message, `group_id="claude-thread"`, per-message
`reference_time`, 2s inter-episode delay — mirrors `sync.py`'s Claude Code path.
Per-conversation watermark in `~/.mikai/claude_threads_state.json` → idempotent.

**Run:**
```
python claude_threads.py --once --since-days 7   # daily job does this
python claude_threads.py --once --all            # one-time full backfill (~279 convs)
python claude_threads.py --once --dry-run        # log only, no writes
```

**Schedule:** `com.mikai.claude-threads` — RunAtLoad + daily 05:15.

---

## Component 2 — Dream synthesis (`infra/graphiti/dream.py`)

**What it does (one DeepSeek call).** Read `wiki.md` → pull the last 7 days of
`claude-thread` episodes from Neo4j → rewrite the wiki under four rules → write
`wiki.md`, append a delta to `log.md`. The graph is never touched.

**The four rules (the "schema"):**
1. **Surface tensions, don't resolve them.** Two incompatible goals/beliefs held
   at once → both recorded under `## Tensions`. (MIKAI's priority-0 signal.)
2. **Weight depth over volume.** Reflections/decisions/wants > fragments; recurring
   > one-off — except a single pivotal life event.
3. **Mark movement.** State changes (exploring→decided→acting→stalled) and belief
   revisions are called out.
4. **Ground, don't invent.** Use only the provided material.

**No numeric scoring** (confidence/importance/decay) in the prototype — salience is
an in-prompt instruction. Deferred to `MEMORY_ARCHITECTURE.md` O-052.

**Run:**
```
python dream.py --dry-run            # print proposed wiki.md, write nothing
python dream.py --days 7             # live: write wiki.md + append log.md
python dream.py --group claude-thread --group claude-code   # widen the stream
```

**Schedule:** `com.mikai.dream` — RunAtLoad + nightly 06:00 (after the 05:15
capture, so it dreams over fresh data).

**Lineage / fidelity:** Karpathy LLM Wiki (LLM-owned markdown, read whole) +
Generative Agents *reflection* (synthesis over a recent memory stream) + MIKAI
tension-surfacing. See `MEMORY_ARCHITECTURE.md` Part H.

---

## The wiki store (`~/.mikai/wiki/`)

```
wiki.md   # read whole. Sections:
          #   ## Who      — current self-model: values, working style
          #   ## Now      — active threads/projects + state
          #   ## Tensions — held, unresolved contradictions (never collapsed)
          #   ## Wants    — inferred goals/desires (certainty in words, not numbers)
log.md    # append-only per-dream "what changed" delta = the revision record
```

**Sensitivity note.** `wiki.md` is a model of the user's identity (can include
relationship, health, finances). Per `EPISTEMIC_DESIGN.md` §"Core Ethical
Constraint," this is the artifact that consent/transparency policy must govern.
Local-only, on the user's machine.

---

## launchd topology (Pattern B — laptop-as-home-server, D-051)

All under `~/Library/Application Support/mikai/launchd/`, installed via `install.sh`
(`launchctl bootstrap gui/$UID`). Secrets in `~/.mikai/launchd.env`; logs in
`~/.mikai/logs/`.

| Label | Trigger | Does |
|---|---|---|
| `com.mikai.docker-compose` | login | brings up Neo4j + sidecar |
| `com.mikai.health-probe` | every 5 min + wake | stack health |
| `com.mikai.ingestion` | continuous (watchdog) | Apple Notes + Claude Code → graph (`sync.py`) |
| `com.mikai.claude-threads` | login + daily 05:15 | Claude.ai threads → graph (`claude_threads.py`) **[new]** |
| `com.mikai.dream` | login + nightly 06:00 | reflect graph → `wiki.md` (`dream.py`) **[new]** |

**Debug:** `tail -f ~/.mikai/logs/{claude-threads,dream}.err.log` ·
`launchctl kickstart -k gui/$(id -u)/com.mikai.dream` to force a run.

---

## Status & deferred work

- **Built & verified** (dry-run + live + under launchd): both daemons; first dream
  reflected 138 episodes → a 7.3 KB wiki surfacing 6 live tensions.
- **Decisions pending ratification** into `DECISIONS.md` (proposed in
  `MEMORY_ARCHITECTURE.md`): ARCH-026 (dual-store), ARCH-027 (dreaming),
  D-053/054, O-048–052.
- **Deferred "as the system develops":** numeric confidence/importance (O-052),
  decay/tiers, promote-to-graph (O-049), hybrid retrieval, importance-triggered
  cadence, and the information-metabolism / loss-function profile model.
