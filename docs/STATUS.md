# MIKAI — Status on main

> **What this file is:** The volatile state-of-the-world doc. It describes what is actually live on `main` right now — not the long-term vision (`CLAUDE.md`), not the architectural decisions (`docs/DECISIONS.md`), not the intellectual foundations (`docs/EPISTEMIC_*.md`). Update this file as main changes. If it contradicts CLAUDE.md, update CLAUDE.md only if the change is a principle, not a state.

**Last meaningful update:** 2026-06-10 (ingestion fixed + automated: graphiti-core pinned, native extraction is now the default per D-052, launchd ingestion daemon live; plus D-051 Pattern B)
**Latest commit on main at writing:** `a19a81c` — fix(ingestion): default to native graphiti extraction; pin graphiti-core

---

## Live on main

### L3 — Knowledge graph (Graphiti adapter)
- **Graphiti sidecar** running as FastAPI at `http://localhost:8100` (infra/graphiti/sidecar/)
- **Neo4j 5.26** via docker-compose (infra/graphiti/docker-compose.yml)
- **~3,370 episodes / ~12,640 entities** in Neo4j (2026-06-10), kept current automatically by the launchd ingestion daemon (Apple Notes + Claude threads). Jumped from ~2,379 after the 2026-06-09→10 catch-up of 954 backlogged Claude turns. Manual catch-up still available via `sync.py --once`.
- **graphiti-core pinned `==0.28.2`** (2026-06-10, D-052) — was unpinned `>=0.5`, floated to 0.28.2, and silently broke ingestion (reserved `summary`, wrote custom attrs as Neo4j Maps). Scaling patch via `scripts/apply_graphiti_patch.py` caps candidate resolution at 50, strips attributes from prompts (D-042)
- **Custom `DeepSeekClient`** adapting DeepSeek V3 to Graphiti's JSON-schema expectations
- **Voyage AI `voyage-3`** for embeddings (1024 dim)

### L3 port (Stage 7, D-050)
- **`L3Backend` ABC** at `infra/graphiti/sidecar/l3/port.py` — 11 async primitives (`ingest_episode`, `ingest_episode_bulk`, `search`, `search_nodes`, `get_node`, `expand`, `edges_between`, `history`, `get_source`, `stats`, `communities`, `close`) + 10 plain dataclass domain types
- **`GraphitiAdapter`** at `sidecar/l3/graphiti_adapter.py` — the only current implementation; encapsulates rate limiting + Stage 6 typed-extraction routing
- **Composition root** `sidecar.l3.make_backend()` reads `MIKAI_L3_BACKEND` (default `graphiti`; `local` raises NotImplementedError until ARCH-025 ships)
- **Product code is port-only.** `grep -r graphiti_core infra/graphiti/sidecar/` outside `l3/graphiti_adapter.py` returns zero hits — the port boundary is enforced by absence.

### Typed extraction (Stage 6, D-049) — DISABLED by default (D-052)
> **Status as of 2026-06-10: OFF by default.** graphiti-core 0.28.2 cannot persist custom node/edge attributes to Neo4j (it writes them as nested Maps Neo4j rejects) and reserves `summary`. Ingestion now uses graphiti **native** extraction. The modules below are intact and revivable behind `MIKAI_TYPED_EXTRACTION=1` — but reviving requires a graphiti-core version that persists custom attributes as flat properties. The chokepoint `extraction/router.py::extraction_params_for()` returns `{}` by default. The live graph is ~99% native edges already (epistemic edges were 15/15,108).

- **Source-conditional Pydantic entity types** at `infra/graphiti/sidecar/extraction/{claude_thread,apple_note,gmail_message,whatsapp_day}.py` plus shared connectors in `common.py` (Person, Place, Project, Concept — identical class objects across sources so Graphiti resolution merges)
- **Epistemic edge types** in `epistemic_edges.py`: CONTRADICTS, SUPPORTS, DEPENDS_ON, PARTIALLY_ANSWERS, UNRESOLVED_TENSION, EXTENDS — each carrying `confidence: float`
- **`edge_type_map.py`** — 29 deliberate typed pairings constraining which edges can connect which entity types
- **Source router** at `extraction/router.py` — wires `entity_types`/`edge_types`/`edge_type_map` into all three `add_episode()` call sites (sync.py, mcp_tools.py add_note, main.py /episode)
- **Negative-example prompt augmentation** in `extraction/prompt_negatives.py` — 10 negatives sourced from the existing noise cluster ("Hearty simple creative", "folly", "The MacNabs"), threaded via `custom_extraction_instructions`
- **Query-time recency-decay overlay** at `sidecar/recency.py` — opt-out via `recency_decay=True` flag on search/get_history tools and the `/search` REST endpoint
- **Status:** code-complete but **bypassed** (see banner above). Never successfully exercised against the live graph at scale — the 0.28.2 persistence bug fired on every typed episode. Reviving is gated on a compatible graphiti-core version.

### Ingestion (Stage 2, ARCH-023 Mode 1)
- **Filesystem daemon** `infra/graphiti/sync.py` — watchdog-based watcher for Apple Notes (via SQLite or AppleScript fallback) + Claude Code JSONL session tails
- **Async token-bucket rate limiter** at `sidecar/rate_limit.py` — gates DeepSeek + Voyage calls (default 60 rpm each, per-bucket env override). Prevents the 429-burst that surfaced as O-041.
- **State checkpoint** at `~/.mikai/sync_state.json` — per-source content-hash dedup (Apple Notes) + byte-offset tail (Claude Code). `--dry-run` is properly dry (regression test in place).
- **launchd ingestion daemon LIVE (2026-06-10).** `com.mikai.ingestion` installed via the D-051 TCC-safe pattern: runner at `~/Library/Application Support/mikai/launchd/sync-runner.sh` (outside `~/Desktop/`), secrets in `~/.mikai/launchd.env`, logs at `~/.mikai/logs/sync.{out,err}.log`; folded into the App-Support `install.sh`. Runs sync.py in watchdog mode — auto-ingests new Claude threads + Apple Notes the moment session/note files change (confirmed: multi-hour stable uptime, real-time per-turn ingestion). Apple Notes needs a one-time Full Disk Access grant on the Homebrew python binary (`/opt/homebrew/Cellar/python@3.12/.../bin/python3.12`) — granted 2026-06-10. Pause with `launchctl bootout gui/$(id -u)/com.mikai.ingestion`.

### MCP server + OAuth (Stage 5, D-048)
- **Python MCP server** at `infra/graphiti/sidecar/mcp_tools.py` (FastMCP, streamable HTTP at `/mcp`) and `mcp_server.py` (stdio transport for Claude Desktop)
- **5 tools:** `search`, `get_history`, `get_stats`, `add_note`, `get_source` — the last returns raw source-episode prose, closing the edges-vs-episodes gap (D-045)
- **Bundled OAuth 2.1 Authorization Server** at `sidecar/oauth.py` — PKCE (S256) + Dynamic Client Registration + JWT bearer tokens, password-gated consent page. Activated by `MIKAI_OAUTH_ENABLED=1`. Lets Claude.ai web + iPhone add MIKAI as a Custom Connector. Live and verified — the live OAuth flow is the access boundary that protects the public Tailscale Funnel URL.
- **Public reachability** via Tailscale Funnel (`brians-macbook-air.tail8e4198.ts.net`); `scripts/preflight.sh --full` checks all 9 surface elements including OAuth discovery and the `/mcp` token gate.
- **Stack auto-starts at login** via `com.mikai.docker-compose` LaunchAgent + a 5-min health probe with `WakeUp=true` (Telegram alert on failure if creds present). Sources at `~/Library/Application Support/mikai/launchd/`; install via `bash "$HOME/Library/Application Support/mikai/launchd/install.sh"`. See D-051 and `docs/MCP_OPERATOR_GUIDE.md`.

### Eval harness (Stage 4 + Stage 6)
- **Stage 4 (intrinsic raters)** — `scripts/eval_nodes.py` (entity extraction quality 1–5) and `scripts/eval_queries.py` (retrieval groundedness). Baseline: `docs/evals/baseline-2026-04-29.md` (entity accuracy 3.10/5 — failing 4.0 threshold; relevance@10 6.4/10 — pass; groundedness 4.2/5 — pass).
- **Stage 6 (precision/recall against gold set)** — `eval/seed_candidates.py` + `eval/label.py` (keyboard CLI, resumable) + `eval/run_l3_eval.py`. Reads acceptance criteria from `docs/STAGE-6-TYPED-EXTRACTION-BRIEF.md`. **Gated on Brian's 200+200 hand-labeling step** — code-complete, scorecard pending labels.

### Repo shape
- `infra/graphiti/` — MIKAI backend: sidecar, daemon, OAuth, extraction schemas, 341-test suite
- `infra/decider/` — FIGS notification interface (D-053). Single Python script + 3 source adapters (iMessage SQLite, Calendar SQLite, Gmail IMAP), validates L4's send/silent decision, dispatches via ntfy.sh, logs to local SQLite for the dismiss/act feedback loop. Directory name is historical; FIGS is the canonical doc reference.
- `eval/` — Stage 6 harness + labeling CLI
- `docs/` — architecture, decisions, status, research, stage briefs, eval scorecards
- `scripts/` — patch automation, eval raters, preflight, dev utilities

### FIGS — notification interface (D-053) — early operational
> **Naming (2026-06-27):** **MIKAI** = backend (L3 graph + L4 reasoning). **FIGS** = the notification interface that consumes MIKAI. Code currently lives at `infra/decider/` for historical reasons; FIGS is the canonical doc name.

- **`infra/decider/mikai_decide.py`** — FIGS V0. Single-script LLM-only notification decider. Per tick: pulls candidate signals from MIKAI (5 semantic lenses via L3 port + a Cypher recency lens for last-24h edges) plus live cross-source events from iMessage/Calendar/Gmail adapters, asks L4 reasoning (Claude via headless `claude -p`, Max-legitimate) whether to send a notification, validates the decision's evidence citations against the prompt context, enforces a cooldown window, and dispatches via ntfy.sh on send.
- **`adapters/imessage.py`** — read-only SQLite query against `~/Library/Messages/chat.db`; requires Full Disk Access (granted).
- **`adapters/calendar.py`** — direct SQLite read of `~/Library/Calendars/Calendar.sqlitedb`. iCloud Calendars sync verified working.
- **`adapters/gmail.py`** — IMAP via Google app password (env vars in `.env.local`). Pulls unread + 24h windowed inbox.
- **Decision log** at `~/.mikai/notification_log.db` — one row per tick (sent or silent), captures prompt hash, decision JSON, reasoning, user response.
- **Verification status:** end-to-end dry-run confirmed cross-source reasoning over real data. ntfy → iPhone dispatch verified via `--test-ntfy`. Real organic notifications gated on (a) more diverse live signal in MIKAI (claude-thread=0 gap — see O-048), and (b) cron-style scheduling (still manual `--force` invocation).

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
- **Always-on ingestion daemon as a LaunchAgent.** Plist template is in place. Install was blocked by TCC restrictions for scripts under `~/Desktop/`; the fix (D-051, 2026-06-04) is to relocate the scripts — not the repo — to `~/Library/Application Support/mikai/launchd/`. The docker-compose LaunchAgent already uses this pattern. Migrating the ingestion plist to the same pattern is the unblocking step; `mikai-sync` runs on demand until then.

---

## Active investigations (near-term)

- **Auto-ingestion coverage** — the 2026-04-18 head-to-head eval (`docs/evals/run-20260418-103324.md`) showed MIKAI's graph carries less recent-conversation detail than Claude.ai's native chat memory, because Claude captures everything by default while MIKAI captures only what's `add_note`-ed. The bottleneck is no longer extraction or retrieval (D-049 + D-045 covered those) — it's ingestion coverage. Pattern B (D-051) is the operational substrate any continuous-capture daemon would run on. Hermes-style architecture (raw-episode hot store + deferred LLM review) is the prior art worth studying.

(Cloud-hosted Neo4j investigation, O-042, closed 2026-06-04 in favor of Pattern B. See D-051.)
- **L4 engine on main** (D-041). `feat/l4-testing` holds prior SQLite-era work; needs a real rewrite onto the new `L3Backend` port. The product layer — task-state classification, thread detection, next-step inference — is where the noonchi moat actually lives. Stage 7 unblocked this work.
- **Stage 6 quality verification** — label the 200+200 gold set via `eval/label.py`, run `eval/run_l3_eval.py`. Estimated ~30–45 min of keyboard time. Until this lands, the "3.10 → ≥4.3" extraction-quality claim is unverified.
- **Head-to-head benchmark against Claude.ai's native memory** — carry-over from `mcp_eval_pending` memory. 6 MIKAI answers collected 2026-04-18; Claude.ai baselines never collected. Re-feasible once Stage 6 verification lands.
- **Claude-thread ingestion gap (O-048).** As of 2026-06-26 the graph has 0 `claude-thread` episodes — the daily Claude.ai web/desktop ingestion never landed (or stopped after 2026-05-21). 1,642 `claude-code` episodes from terminal sessions, and 62 `apple-notes` episodes are healthy. Brian is fixing on a separate branch (cookie-decrypt + internal API, 7-day window). Once landed, the notification decider's fresh-lens will see Claude.ai conversation content directly instead of just meta-references to it.
- **FIGS calibration (D-053).** FIGS's first ticks ran silent — correctly, given the available signal in MIKAI was mostly newsletters + meta-references. Real validation of "L4 reasoning is the right brain" requires (a) richer signal in MIKAI (the claude-thread fix above), (b) actual dismiss/act data accumulating in `notification_log.db`, and (c) scheduling via Routines or local cron. Plan: re-run dry-runs after the claude-thread fix lands; instrument dismiss/act response capture; promote to scheduled execution.

## Future product directions

- **`LocalAdapter`** (ARCH-025) — a fully on-device sibling of `GraphitiAdapter` selected via `MIKAI_L3_BACKEND=local`. Embedded graph store (SQLite + `sqlite-vec`), local embeddings (Nomic via ONNX), local LLM for extraction (e.g. quantized Llama variant). Stage 7's port extraction (D-050) made this implementable as one new ~400-line file with no product-code changes — but the work is **deferred** until one of three triggers fires: (a) MIKAI ships to other users as a downloadable app, (b) content sensitivity demands content never leaves the device, (c) DeepSeek/Voyage become a hard blocker. Today, none of those apply; the option is preserved in the architecture without committing implementation time.

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