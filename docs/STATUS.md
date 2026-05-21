# MIKAI — Status on main

> **What this file is:** The volatile state-of-the-world doc. It describes what is actually live on `main` right now — not the long-term vision (`CLAUDE.md`), not the architectural decisions (`docs/DECISIONS.md`), not the intellectual foundations (`docs/EPISTEMIC_*.md`). Update this file as main changes. If it contradicts CLAUDE.md, update CLAUDE.md only if the change is a principle, not a state.

**Last meaningful update:** 2026-05-21 (Stage 2 + Stage 4 + Stage 5 + Stage 6 reconciliation pass)
**Latest commit on main at writing:** `c0c9098` — Merge `feat/stage-5-mcp-oauth` (incl. stage-4 eval scorecards) into main

---

## Live on main

### L3 — Knowledge graph (Graphiti adapter)
- **Graphiti sidecar** running as FastAPI at `http://localhost:8100` (infra/graphiti/sidecar/)
- **Neo4j 5.26** via docker-compose (infra/graphiti/docker-compose.yml)
- **~2,371 episodes** in Neo4j as of 2026-05-19 ingestion (1,108 Apple Notes + ~767 Claude conversations + new content from the catch-up daemon run); `mikai-sync` shell function in `~/.zshrc` runs `sync.py --once` on demand
- **graphiti-core scaling patch** applied via `scripts/apply_graphiti_patch.py` — caps candidate resolution at 50, strips attributes from prompts (D-042)
- **Custom `DeepSeekClient`** adapting DeepSeek V3 to Graphiti's JSON-schema expectations
- **Voyage AI `voyage-3`** for embeddings (1024 dim)

### Typed extraction (Stage 6, D-049)
- **Source-conditional Pydantic entity types** at `infra/graphiti/sidecar/extraction/{claude_thread,apple_note,gmail_message,whatsapp_day}.py` plus shared connectors in `common.py` (Person, Place, Project, Concept — identical class objects across sources so Graphiti resolution merges)
- **Epistemic edge types** in `epistemic_edges.py`: CONTRADICTS, SUPPORTS, DEPENDS_ON, PARTIALLY_ANSWERS, UNRESOLVED_TENSION, EXTENDS — each carrying `confidence: float`
- **`edge_type_map.py`** — 29 deliberate typed pairings constraining which edges can connect which entity types
- **Source router** at `extraction/router.py` — wires `entity_types`/`edge_types`/`edge_type_map` into all three `add_episode()` call sites (sync.py, mcp_tools.py add_note, main.py /episode)
- **Negative-example prompt augmentation** in `extraction/prompt_negatives.py` — 10 negatives sourced from the existing noise cluster ("Hearty simple creative", "folly", "The MacNabs"), threaded via `custom_extraction_instructions`
- **Query-time recency-decay overlay** at `sidecar/recency.py` — opt-out via `recency_decay=True` flag on search/get_history tools and the `/search` REST endpoint
- **Status:** code-complete on main; **not yet exercised against the live graph** — the existing ~2,371 episodes were extracted under the old (pre-typing) prompt. Future ingestions use the new pipeline; re-extraction of the corpus is a separately-gated step.

### Ingestion (Stage 2, ARCH-023 Mode 1)
- **Filesystem daemon** `infra/graphiti/sync.py` — watchdog-based watcher for Apple Notes (via SQLite or AppleScript fallback) + Claude Code JSONL session tails
- **Async token-bucket rate limiter** at `sidecar/rate_limit.py` — gates DeepSeek + Voyage calls (default 60 rpm each, per-bucket env override). Prevents the 429-burst that surfaced as O-041.
- **State checkpoint** at `~/.mikai/sync_state.json` — per-source content-hash dedup (Apple Notes) + byte-offset tail (Claude Code). `--dry-run` is properly dry (regression test in place).
- **launchd plist template** at `infra/graphiti/launchd/` — not currently installed because the repo lives under `~/Desktop/` which macOS TCC blocks for LaunchAgents. Manual refresh via the `mikai-sync` zsh function instead.

### MCP server + OAuth (Stage 5, D-048)
- **Python MCP server** at `infra/graphiti/sidecar/mcp_tools.py` (FastMCP, streamable HTTP at `/mcp`) and `mcp_server.py` (stdio transport for Claude Desktop)
- **5 tools:** `search`, `get_history`, `get_stats`, `add_note`, `get_source` — the last returns raw source-episode prose, closing the edges-vs-episodes gap (D-045)
- **Bundled OAuth 2.1 Authorization Server** at `sidecar/oauth.py` — PKCE (S256) + Dynamic Client Registration + JWT bearer tokens, password-gated consent page. Activated by `MIKAI_OAUTH_ENABLED=1`. Lets Claude.ai web + iPhone add MIKAI as a Custom Connector. Live and verified — the live OAuth flow is the access boundary that protects the public Tailscale Funnel URL.
- **Public reachability** via Tailscale Funnel (`brians-macbook-air.tail8e4198.ts.net`); `scripts/preflight.sh --full` checks all 9 surface elements including OAuth discovery and the `/mcp` token gate.

### Eval harness (Stage 4 + Stage 6)
- **Stage 4 (intrinsic raters)** — `scripts/eval_nodes.py` (entity extraction quality 1–5) and `scripts/eval_queries.py` (retrieval groundedness). Baseline: `docs/evals/baseline-2026-04-29.md` (entity accuracy 3.10/5 — failing 4.0 threshold; relevance@10 6.4/10 — pass; groundedness 4.2/5 — pass).
- **Stage 6 (precision/recall against gold set)** — `eval/seed_candidates.py` + `eval/label.py` (keyboard CLI, resumable) + `eval/run_l3_eval.py`. Reads acceptance criteria from `docs/STAGE-6-TYPED-EXTRACTION-BRIEF.md`. **Gated on Brian's 200+200 hand-labeling step** — code-complete, scorecard pending labels.

### Repo shape
- `infra/graphiti/` — sidecar, daemon, OAuth, extraction schemas, 341-test suite
- `eval/` — Stage 6 harness + labeling CLI
- `docs/` — architecture, decisions, status, research, stage briefs, eval scorecards
- `scripts/` — patch automation, eval raters, preflight, dev utilities

---

## In flight (feature branches)

| Branch | Status | What it adds |
|---|---|---|
| `feat/ingestion-mcp-client` | 7 commits ahead of main | Mode 2 (MCP client polling for Gmail, Google Calendar, Google Drive). Not yet merged; Mode 1 daemon on main covers Apple Notes + Claude Code. |
| `feat/l4-testing` | Needs rework | L4 pipeline originally written against SQLite; needs porting onto `L3Backend` port (ARCH-024). The product layer — task-state awareness, thread detection, next-step inference. |
| `feat/phase-b-local-expand` | 11 ahead | iMessage reader + local files watcher (Mode 1 expansion). Tests in place; not yet merged to main. |
| `feat/phase-c-cloud-polish` | 9 ahead | Launchd plist template work (now superseded by Stage 2's templates already on main; branch may be retired). |

---

## Gated work (code-complete, awaiting a human step)

- **Stage 6 quality measurement.** Eval harness exists; needs ~30–45 min of Brian's keyboard time labeling 200 entities + 200 edges via `eval/label.py`. Until then the "3.10 → ≥4.3" claim is unverified.
- **Re-extraction of the existing corpus under the typed pipeline.** The current ~2,371 episodes were extracted before typing landed. Re-extraction would cost ~$15–25 in DeepSeek/Voyage credits and ~60 min, and is gated on (a) Brian's approval and (b) ideally Stage 6 labels confirming the new pipeline measurably outperforms.
- **Always-on ingestion daemon as a LaunchAgent.** Plist template is in place. Install blocked by macOS TCC restrictions for repos under `~/Desktop/`. Workarounds (grant Full Disk Access to bash+python, or move the repo to `~/MIKAI/`) are documented. For now, `mikai-sync` runs on demand.

---

## Not yet built

- **`L3Backend` port extraction** (ARCH-024). Product code still calls Graphiti directly. Port extraction is the prerequisite for `LocalAdapter` (ARCH-025).
- **`LocalAdapter`** (ARCH-025). Fully on-device adapter. Design input: `legacy/sqlite-local`. Not started.
- **L4 engine on main** (D-041). `feat/l4-testing` holds prior SQLite-era work; needs the port extraction + a real rewrite.
- **Head-to-head benchmark against Claude.ai's native memory** (carry-over from the MCP eval pending memory). Was attempted 2026-04-18 with 6 MIKAI answers collected; baselines never collected. Re-feasible once typed extraction is verified.

---

## Known issues

- **Extraction quality is unverified post-Stage 6.** The Stage 4 baseline measured 3.10/5 against the *pre-typing* graph. Stage 6 schemas + edges + negatives are wired but the existing graph hasn't been re-extracted, so the live `search`/`get_source` results still reflect pre-Stage-6 extraction. Quality lift is unmeasured until re-extract + label + eval.
- **~15.1% entity-isolated** in Neo4j (1,493 of 9,920 entities at the 2,371-episode mark have no entity-to-entity `RELATES_TO` edge). Down from 17.6%, but persistent. Stage 6's typed extraction is expected to reduce this on future ingestions; existing isolated entities require re-extraction or community detection to address.
- **Extraction prompt tuned to Brian's reflective writing style** — may not generalize to other users' content (OPEN.md O-025). Stage 6's source-conditional schemas mitigate this somewhat (different schemas per source); still single-user assumption.
- **`docs/evals/baseline-2026-04-29.md` is the only scorecard so far.** Stage 6 will produce a new one at `docs/evals/stage6-YYYY-MM-DD.md` after labeling.

---

## Retired on main (archival only)

- **v0.3 SQLite L3** — preserved on `legacy/sqlite-local` (`b8f07ee`). Design input for `LocalAdapter`, not source material for merge.
- **v0.2 Supabase L3** — preserved on `legacy/supabase` (`2a0bf8c`). Archival only.
- **TypeScript source connectors** (`sources/apple-notes/sync.js`, `sources/gmail/sync.js`, etc.) — replaced by the hybrid ingestion model (ARCH-023).
- **Next.js web layer** — removed per D-039. MCP is the sole product surface.
- **Pre-cleanup 861-line MCP rewrite** — preserved on `wip/2026-04-10-presplit`.
</content>
</invoke>