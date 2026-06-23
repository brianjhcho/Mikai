# MIKAI — Worktree Coordination

> **Authoritative for:** how multiple Claude conversations across MIKAI worktrees stay coordinated without stepping on each other.
> **Origin:** Surfaced 2026-06-23 when `pointed-expert` (strategic research) and `pear-seashore` (product) were running concurrently and needed to share findings without merge conflicts.
> **Audience:** any Claude session opened on a MIKAI worktree, and Brian himself when context-switching between worktrees.

---

## Why this doc exists

MIKAI is structured around git worktrees so several Claude conversations can run in parallel on different concerns — research, product, MCP work, ingestion, etc. Without explicit coordination, parallel sessions create three failure modes:

1. **Merge conflicts on shared docs** — two sessions both editing `STATUS.md`, `OPEN.md`, `FOUNDATIONS.md`, or `DECISIONS.md`.
2. **Duplicate work** — same problem solved twice in two branches, then merged with rework cost.
3. **Knowledge drift** — one session has strategic context that another doesn't, so its decisions are uninformed.

The patterns below resolve all three at low overhead.

---

## Worktree snapshot (as of 2026-06-23)

The `git worktree list` output at this writing:

```
/Users/briancho/Desktop/MIKAI                                main
/Users/briancho/.superset/worktrees/MIKAI/mcp-layer          mcp-layer
/Users/briancho/.superset/worktrees/MIKAI/motley-reader      motley-reader
/Users/briancho/.superset/worktrees/MIKAI/navy-windshield    navy-windshield
/Users/briancho/.superset/worktrees/MIKAI/pear-seashore      pear-seashore
/Users/briancho/.superset/worktrees/MIKAI/pointed-expert     pointed-expert
/Users/briancho/Desktop/MIKAI/.omc/worktrees/mikai/phase-b   feat/phase-b-local-expand
/Users/briancho/Desktop/MIKAI/.omc/worktrees/mikai/phase-c   feat/phase-c-cloud-polish
```

The snapshot drifts — don't rely on it. Refresh with `git worktree list` at session start.

**Convention:** every active worktree should have a *single* responsibility. If two worktrees share a concern, one of them is stale and should be pruned (`git worktree remove`).

---

## The three communication channels

Each channel has a different speed/durability/audit-trail tradeoff. Pick by what's needed.

### Channel 1 — Memory dir (instant, no git)

**Location:** `~/.claude/projects/-Users-briancho-Desktop-MIKAI/memory/`

**Visible to:** every Claude conversation on the MIKAI project, automatically, on the next message.

**Use for:** strategic context that all conversations need *right now* — decisions, terminology choices, candidate technologies under evaluation, unresolved questions that gate work, cross-cutting reminders.

**Mechanics:**
- Write a memory file with the standard frontmatter (`name`, `description`, `metadata.type`).
- Add a one-line pointer entry to `MEMORY.md` in the same dir.
- Other sessions see the new entry on their next message; no rebase or pull required.

**Limits:** the memory dir is local to this user — not shared with collaborators (if any), not committed to the repo, not durable across machine wipes. It's a fast cache, not a system of record.

### Channel 2 — `docs/` files via main (slow, git-durable)

**Location:** `docs/` directory in any worktree; reaches other worktrees via commit + rebase.

**Visible to:** any worktree that has rebased onto the branch carrying the change. Once merged to `main`, every worktree sees it after `git fetch && git rebase origin/main`.

**Use for:** durable project state that should survive memory wipes and become part of the project's permanent record — `STATUS.md` updates, `DECISIONS.md` entries, new `OPEN.md` questions, `FOUNDATIONS.md` revisions, research notes.

**Mechanics:**
- Edit `docs/` files in your worktree.
- Commit with a clear conventional-commits-style message (`docs:` or `docs(scope):`).
- Push the branch if other worktrees need it before main-merge, or merge to main for the durable answer.
- Other worktrees rebase to pick it up.

**This is the system of record.** Anything important should land here eventually, even if it started in a memory entry.

### Channel 3 — Direct file read across worktrees (emergency only)

**Location:** absolute paths to another worktree's files, e.g. `/Users/briancho/.superset/worktrees/MIKAI/pointed-expert/docs/research/whatever.md`.

**Visible to:** any session, immediately, but reads uncommitted state from another worktree.

**Use for:** emergency cross-reference when commit + rebase is too slow and a memory entry is too lossy. Should be rare.

**Don't make this a habit.** It couples sessions to each other's working state and creates implicit dependencies that break the moment the donor worktree commits or moves.

---

## Per-worktree ownership

When two or more worktrees are active simultaneously, assign each a non-overlapping area of responsibility. Examples that worked in practice:

| Worktree | Owns | Doesn't touch |
|---|---|---|
| `pointed-expert` (2026-06) | Strategic research, `docs/research/`, OPEN.md additions, FOUNDATIONS.md revisions | Product code, MCP layer, ingestion |
| `pear-seashore` (2026-06) | Product surface | Strategy docs, research files |
| `mcp-layer` | MCP server code (`infra/graphiti/sidecar/mcp_*.py`) | Anything outside the MCP boundary |
| `feat/phase-b-local-expand` | iMessage + local files watchers | Other ingestion modes |

Convention: at session start, the operator (Brian) tells the Claude session what other worktrees are active and what they're working on. The session avoids those areas.

---

## Common workflows

### Workflow A — Share strategic findings from one session to all others

1. Write the synthesis to `docs/research/<topic>-<yyyy-mm>.md` in your worktree.
2. Write a memory entry summarising the key decision/finding in `~/.claude/projects/-Users-briancho-Desktop-MIKAI/memory/<slug>.md`.
3. Append a pointer to `MEMORY.md` in the same dir.
4. (Optional) Commit the research file + push the branch; or merge to main if the finding is settled enough to be project-permanent.
5. Other sessions see the memory entry on their next message; the research file when they rebase.

This is the pattern executed on 2026-06-23 — see `docs/research/strategic-research-2026-06.md` and the four memory entries with `name: intervention-timing-term` / `cognee-mnemosyne-localadapter` / `strategic-noun-unresolved` / `worktree-coordination-pattern`.

### Workflow B — Log a new unresolved question for all sessions

1. Append the question to `docs/OPEN.md` as `O-NNN` in the appropriate priority section.
2. Commit; merge to main if settled, otherwise push the branch and have other sessions rebase.
3. (Optional) If the question is load-bearing for cross-cutting decisions, also write a memory entry that flags it.

### Workflow C — Update STATUS.md after a milestone lands on main

1. Only the worktree that did the merge updates `STATUS.md`.
2. Other worktrees rebase on main to see it.
3. Avoid two worktrees writing `STATUS.md` in the same window — coordinate explicitly if both have meaningful state to record.

### Workflow D — Heavy sweep (deepinit, mass refactor, schema migration)

1. **Pause all other worktrees first.** Tell their sessions to hold writes until further notice, or close those conversations.
2. Run the sweep in one worktree.
3. Commit + merge to main.
4. Other worktrees rebase before resuming.

Skipping this protocol is the most reliable way to generate merge conflicts.

---

## Pre-flight ritual (every new conversation)

At the top of each Claude session on a worktree, run:

```bash
git fetch origin
git log origin/main --oneline -10
git status
```

This shows: (a) what's landed on main since last session, (b) whether the current worktree is clean or has pending work. Decide what to do based on what's changed.

If active parallel work exists in other worktrees, the operator should also tell the session what those worktrees own, so the session knows what to avoid.

---

## Anti-patterns

- **Two worktrees concurrently editing `STATUS.md`, `OPEN.md`, `DECISIONS.md`, or `FOUNDATIONS.md`.** One should be the owner per session; the other reads only.
- **Running `/oh-my-claudecode:deepinit` or any full-repo doc sweep while other worktrees are active.** Touches too many files; near-guaranteed conflict.
- **Putting strategic findings only in memory entries with no `docs/` durable record.** Memory entries are local and ephemeral; if the user wipes them or switches machines, the finding is lost.
- **Direct cross-worktree path reads as a normal pattern.** Couples sessions to uncommitted state; breaks the moment the donor worktree shifts.
- **Naming worktrees vaguely** (`navy-windshield`, `motley-reader`, etc. — the OMC-default scheme). Hard to know what they're for at a glance. When a worktree is created for a specific concern, prefer a descriptive branch name (`feat/l4-port`, `feat/mcp-rewrite`).

---

## Cross-references

- Memory entry `worktree-coordination-pattern` — TL;DR version of this doc, auto-loaded into every session.
- `docs/research/strategic-research-2026-06.md` — example of the Channel 1 + Channel 2 pattern in practice.
- `docs/STATUS.md` — the system of record for "what's on main."
- `CLAUDE.md` — global project guardrails; this doc supplements but doesn't override.
