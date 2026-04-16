# MIKAI — agent context

> **AI agents working on this repo:** The authoritative session context is `CLAUDE.md`. Read that first. This file mirrors the key facts for non-Claude agents (codex, etc.) but may lag CLAUDE.md between updates — when in doubt, trust CLAUDE.md.

## Purpose
MIKAI is a task-state awareness engine ("noonchi") — the AI that knows where you are in your thinking across apps and tells you what to do next.

## Architecture in one paragraph

Two conceptual layers: **L3** is a bitemporal knowledge graph; **L4** is task-state awareness (thread detection, state classification, next-step inference — the product). L3 is accessed through an `L3Backend` port (ARCH-024). Two adapters exist on main: `GraphitiAdapter` (default, FastAPI sidecar at `:8100` + Neo4j) and `LocalAdapter` (first-class alternate, fully on-device per ARCH-025). Ingestion is hybrid (ARCH-023): filesystem watchers + MCP client polling + drop folder, all converging on `L3Backend.ingestEpisode()`. Product code depends only on the port, never on adapter-specific infrastructure.

## Where to look for what
- `docs/STATUS.md` — what's actually live on main right now
- `docs/DECISIONS.md` — append-only architecture decision log (ARCH-*, D-*)
- `docs/GRAPHITI_INTEGRATION.md` — Graphiti adapter technical details and the scaling patch
- `docs/L4_RESEARCH_INTEGRATION.md` — L4 design spec
- `docs/EPISTEMIC_EDGE_VOCABULARY.md` — node/edge taxonomy
- `docs/NOONCHI_STRATEGIC_ANALYSIS.md` — product framing / why noonchi is the moat
- `docs/ARCHITECTURE_GAPS.md`, `docs/OPEN_QUESTIONS.md` — known gaps and unresolved questions

## Repository layout

| Path | Purpose |
|------|---------|
| `infra/graphiti/` | Graphiti adapter infra (Neo4j docker-compose, FastAPI sidecar, Python MCP server, import scripts) |
| `docs/` | Architecture reference, decision log, status, research docs |
| `scripts/` | Reproducible patches and dev utilities (e.g., `apply_graphiti_patch.py`) |
| `private/` | Strategy docs (gitignored) |
| `.env.example` | Environment variables including `L3_BACKEND` selector |

## Rules agents must follow
1. Depend on the `L3Backend` port, not on adapters. No direct Cypher, no direct SQLite, no direct sidecar HTTP calls from product code.
2. Do not leak adapter-specific types into port signatures.
3. Do not merge from `legacy/sqlite-local` or `legacy/supabase` into main. Those branches are design input, not source material.
4. After every build task, report both a technical summary (for commit message) and a plain-English explanation (for Brian).
