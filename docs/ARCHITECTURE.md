# MIKAI — Architecture

> **Consolidated from:** `ARCHITECTURE.md` (original, Supabase-era — fully rewritten), `GRAPHITI_INTEGRATION.md`, `CURRENT_STACK.md` (Pass 2, 2026-04-16)
> **Authoritative for:** how the system is built today — the port/adapter shape, the Graphiti adapter, the ingestion model, the L4 product layer boundary, the LocalAdapter design posture, and known operational issues.

This doc describes the *how*. For the *what* and *why*, see VISION.md and DECISIONS.md. For volatile state (what's actually on `main` right now), see STATUS.md.

---

## §1 — System shape

MIKAI is built as Ports & Adapters. Product code — the MCP server, the L4 engine, the ingestion daemon — depends on a single interface (`L3Backend`) and never on a specific graph backend. Two adapters implement the port, selected at startup by the `L3_BACKEND` environment variable.

```
             ┌──────────────────────────────────────────┐
             │  Product code (depends only on the port) │
             │                                          │
             │  - Python MCP server (Claude Desktop)    │
             │  - L4 engine (thread/state/next-step)    │
             │  - Ingestion daemon (filesystem + MCP)   │
             └──────────────────────┬───────────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │        L3Backend PORT         │
                    │   (8 methods, domain verbs)   │
                    │                               │
                    │  ingestEpisode, search,       │
                    │  getNode, expand,             │
                    │  edgesBetween, history,       │
                    │  stats, communities           │
                    └──────┬───────────────┬────────┘
                           │               │
              ┌────────────▼─┐         ┌───▼─────────────┐
              │ GraphitiAdapter│         │ LocalAdapter   │
              │ (live)         │         │ (in design)    │
              │                │         │                │
              │ graphiti-core  │         │ embedded graph │
              │ Neo4j 5.26     │         │ local embed    │
              │ DeepSeek V3    │         │ local LLM      │
              │ Voyage voyage-3│         │                │
              └────────────────┘         └────────────────┘
              L3_BACKEND=graphiti         L3_BACKEND=local
              (default)                   (first-class alt)
```

**Port surface (ARCH-024).** Eight methods, all in domain terms — no infrastructure nouns. Product code cannot tell which adapter is running:

- `ingestEpisode(content: Episode) -> IngestResult`
- `search(query: SearchQuery) -> SearchResult[]`
- `getNode(id: NodeId) -> Node`
- `expand(seed: NodeId[], hops: int, limit: int) -> Subgraph`
- `edgesBetween(a: NodeId, b: NodeId) -> Edge[]`
- `history(id: NodeId) -> HistoryEntry[]`
- `stats() -> GraphStats`
- `communities() -> Community[]`

**Why this shape.** Three forces (see ARCH-024): (1) the docs-folder audit surfaced that no formal decision had been recorded rejecting local-first — ARCH-019 adopted Graphiti by momentum, not by an explicit close; (2) a "flip a switch" requirement for privacy-sensitive deployments (ARCH-025) requires both backends to coexist at runtime, which is the definition of Ports & Adapters; (3) building L4 directly against Graphiti's raw API would re-couple the product to an adapter and make the future local-first mode impossible to ship without rewriting L4.

ARCH-024 supersedes ARCH-021 (which had prohibited an abstraction layer). That prior decision was correct for its context — it blocked SQLite re-entanglement during the Graphiti migration. That risk no longer applies because `LocalAdapter` is a clean, first-class build, not a legacy revival.

---

## §2 — The Graphiti adapter

`GraphitiAdapter` is the default and currently the only live adapter. It runs graphiti-core (by Zep) on top of Neo4j 5.26, using DeepSeek V3 for entity extraction and resolution, and Voyage AI `voyage-3` (1024 dimensions) for embeddings. The adapter is exposed via a FastAPI sidecar at `http://localhost:8100` for non-Python clients, and is also called in-process from the Python MCP server (D-040) to avoid the HTTP hop.

**The scaling patch.** graphiti-core's `_resolve_with_llm` in `graphiti_core/utils/maintenance/node_operations.py` spreads `**candidate.attributes` for every candidate returned by hybrid search, with no upper bound. At ~4,500 entities, the resolution prompt exceeded DeepSeek's 131K context window (requesting 2.3M+ tokens). The MIKAI patch caps candidates at 50 and strips attributes from the resolution prompt (name + labels only — the LLM doesn't need full summaries to disambiguate identity). Prompt size drops to a fixed ~1,000 tokens regardless of graph size. Quality impact: minimal. The patch is reproducible via `scripts/apply_graphiti_patch.py` (D-042) and is applied after every `pip install --upgrade graphiti-core`.

**The `DeepSeekClient` adapter.** graphiti-core's base OpenAI client assumes `json_schema` response format. DeepSeek V3 doesn't support it, so the sidecar subclasses `OpenAIGenericClient` and overrides `_generate_response` to use `json_object` mode with the JSON schema injected into the system prompt. The sidecar also uses a `PassthroughReranker` to avoid an OpenAI dependency for cross-encoder reranking.

**The live graph.** As of the last measurement: 6,990 entities, 8,056 edges, 1,158 episodes (1,102 Apple Notes complete, 87 Claude thread turns partial). Hub entities include International Villages (50 edges), Germaine (39), MIKAI (33+), Brian (30), AI (26). Orphan rate: 17.6% (1,233 entities with no edges) — a mix of noise fragments ("A bee", "2327 storage number") and substantive-but-isolated nodes awaiting community detection.

**Cost.** Early import (cold graph, everything new): ~$0.01 per episode. Steady-state (mature graph where Tier 1/2 deterministic resolution handles 80%+ of entities): ~$0.005 per episode. At ~10 new episodes/day this is roughly $1.50/month.

**Details.** Full technical write-up — the 4-step resolution pipeline, cost curves, embedding comparison (Voyage vs. Nomic), best-practices review of graphiti-core, the upstream PR draft — lives in `docs/research/graphiti-review.md`.

---

## §3 — Ingestion — the hybrid model

Ingestion uses a hybrid of three patterns, all converging on a single write path (`L3Backend.ingestEpisode()`). **Mode 1** is filesystem watchers (Python `watchdog` + macOS FSEvents) for local sources with no API — Apple Notes, Claude Code sessions, local files. **Mode 2** is MCP client polling for cloud sources that expose MCP servers (Gmail, Google Calendar, Google Drive). **Mode 3** is a drop folder (`~/.mikai/imports/`) as the manual fallback for everything else. Custom API connectors per source are rejected; MCP standardizes that boundary. See ARCH-023 for the full rationale and build phases.

---

## §4 — The L4 product layer

L4 — thread detection, state classification, next-step inference, intention-behavior gap detection — is a separate product layer **above** the L3Backend port. Per D-041, the port exposes only generic graph primitives (search, node fetch, BFS expand, edges-between, history, stats, episode write, communities). It does **not** implement tension detection, thread detection, state classification, stalled-project surfacing, or next-step inference. Those are L4 concerns.

This separation is load-bearing. Mixing L4 semantics into the port would couple the product layer to a specific adapter (Graphiti's community detection, Graphiti's bitemporal edges) and make either (a) the second adapter impossible to ship, or (b) the L4 design impossible to evolve independently from Graphiti's API. Keeping L4 strictly above the port means the same L4 code works with `GraphitiAdapter` today and `LocalAdapter` later.

L4 is built once, against the port, on a dedicated branch. For the full build spec — the five-paper research integration (ProMemAssist, OmniActions, Inner Thoughts, PPP, MEMTRACK), the pipeline stages (detect → classify → evaluate gate → infer), the hypothesis that state classification may be rule-based (zero LLM) with only next-step inference needing LLM synthesis — see FOUNDATIONS.md §3.

---

## §5 — LocalAdapter (in design)

`LocalAdapter` is a first-class alternate adapter behind the same port. Selected via `L3_BACKEND=local`. Fully on-device: embedded graph store (likely SQLite + `sqlite-vec`, informed by `legacy/sqlite-local`), local embeddings (Nomic via ONNX or equivalent), local LLM for extraction. Zero external service dependency. Same ingestion primitive (filesystem watchers from ARCH-023).

The design posture per ARCH-025 is that this is not a legacy revival, not a fork, not a future migration — it is a supported runtime mode preserved as first-class. The architectural discipline the two-adapter model enforces (port surface stays honest, no Graphiti-specific leaks into product code) is itself a reason to keep both adapters alive. Design input comes from `legacy/sqlite-local` (frozen at `b8f07ee`, v0.3 SQLite implementation); code may be studied and adapted but the branch is never merged into main.

---

## §6 — Known operational issues

- **17.6% orphan entities.** 1,233 of 6,990 Neo4j entities have zero edges. Mix of noise fragments ("A bee", "2327 storage number") and substantive-but-isolated nodes ("Let's Talk", "Alexander technique"). Community detection pass pending. See OPEN.md.
- **18.5% L4 state-classification accuracy on the SQLite era.** The `feat/l4-testing` branch carries the prior L4 implementation, which ran against SQLite. Needs re-evaluation once ported onto the `L3Backend` port. See OPEN.md.
- **Extraction prompt tuned to Brian's writing style.** The reasoning-map extraction prompt was validated on Brian's reflective, framework-heavy corpus. Whether it generalizes to users who write quick action items or operational notes is unresolved. See OPEN.md (O-025, O-035).
- **Graphiti dependency is early-stage (v0.5.x).** API stability is not guaranteed. The patch is load-bearing. Fork trigger conditions documented in D-042 and `docs/research/graphiti-review.md`.
