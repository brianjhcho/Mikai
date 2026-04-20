# MIKAI — Status on main

> **What this file is:** The volatile state-of-the-world doc. It describes what is actually live on `main` right now — not the long-term vision (`CLAUDE.md`), not the architectural decisions (`docs/DECISIONS.md`), not the intellectual foundations (`docs/EPISTEMIC_*.md`). Update this file as main changes. If it contradicts CLAUDE.md, update CLAUDE.md only if the change is a principle, not a state.

**Last meaningful update:** 2026-04-16 (docs-refactor pass 1)
**Latest commit on main at writing:** `828c3cc` — ARCH-023 (hybrid ingestion architecture)

---

## Live on main

### L3 — Knowledge graph (Graphiti adapter)
- **Graphiti sidecar** running as FastAPI at `http://localhost:8100` (infra/graphiti/sidecar/)
- **Neo4j 5.26** via docker-compose (infra/graphiti/docker-compose.yml)
- **6,990 entities** imported from 1,102 Apple Notes + 87 Claude threads (partial)
- **graphiti-core scaling patch** applied via `scripts/apply_graphiti_patch.py` — caps candidate resolution at 50, strips attributes from prompts (D-042)
- **Custom `DeepSeekClient`** adapting DeepSeek V3 to Graphiti's JSON-schema expectations
- **Voyage AI `voyage-3`** for embeddings (1024 dim)

### MCP server
- **Python MCP server** at `infra/graphiti/sidecar/mcp_server.py` (D-040)
- Uses graphiti-core **in-process** (no HTTP hop to sidecar for L3 calls)
- Exposes graph primitives only — tension/thread detection deferred to L4 (D-041)

### Repo shape
- `infra/graphiti/` — the only live infrastructure directory on main
- `docs/` — architecture reference, decisions, status, research
- `scripts/` — patch automation and dev utilities
- Root: `package.json` is identity-only (no Node deps), `.env.example`, this file, `CLAUDE.md`, `AGENTS.md`, `README.md`

---

## In flight (feature branches)

| Branch | Status | What it adds |
|---|---|---|
| `feat/ingestion-automation` | WIP | Mode 1 (filesystem watchers via `watchdog` for Apple Notes, Claude Code) + Mode 3 (drop folder `~/.mikai/imports/`) |
| `feat/ingestion-mcp-client` | 3 commits ahead of main | Mode 2 (MCP client polling for Gmail, Google Calendar, Google Drive) |
| `feat/l4-testing` | Needs rework | L4 pipeline originally written against SQLite; needs porting onto `L3Backend` port (ARCH-024) |

---

## Not yet built

- **`L3Backend` port extraction** (ARCH-024). Currently product code still calls the Graphiti sidecar / graphiti-core directly. The port needs to be extracted before `LocalAdapter` can land.
- **`LocalAdapter`** (ARCH-025). Fully on-device adapter. Design input: `legacy/sqlite-local` (v0.3 SQLite implementation at `b8f07ee`). Not started.
- **L4 engine on main.** `feat/l4-testing` holds prior SQLite-era work; porting and integration pending the port extraction.
- **Automated ingestion daemon on main.** Lives on the two `feat/ingestion-*` branches; neither has merged yet.
- **Eval tooling for graph quality.** Open question (OPEN.md O-020).

---

## Known issues

- **17.6% orphan entities** in the Neo4j graph — mostly noise fragments ("A bee", "2327 storage number") or substantive-but-isolated nodes. Needs community detection pass.
- **Extraction prompt tuned to Brian's reflective writing style** — may not generalize to other users' content (OPEN.md O-025).
- **L4 state-classification accuracy was 18.5%** on the SQLite-era implementation. Must be re-evaluated once ported onto `L3Backend`.

---

## Retired on main (archival only)

- **v0.3 SQLite L3** — preserved on `legacy/sqlite-local` (`b8f07ee`). Design input for `LocalAdapter`, not source material for merge.
- **v0.2 Supabase L3** — preserved on `legacy/supabase` (`2a0bf8c`). Archival only.
- **TypeScript source connectors** (`sources/apple-notes/sync.js`, `sources/gmail/sync.js`, etc.) — replaced by the hybrid ingestion model (ARCH-023).
- **Next.js web layer** — removed per D-039. MCP is the sole product surface.
- **Pre-cleanup 861-line MCP rewrite** — preserved on `wip/2026-04-10-presplit`.
