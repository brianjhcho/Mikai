# MIKAI — Status on main

> **What this file is:** The volatile state-of-the-world doc. It describes what is actually live on `main` right now — not the long-term vision (`CLAUDE.md`), not the architectural decisions (`docs/DECISIONS.md`), not the intellectual foundations (`docs/EPISTEMIC_*.md`). Update this file as main changes. If it contradicts CLAUDE.md, update CLAUDE.md only if the change is a principle, not a state.

**Last meaningful update:** 2026-08-14 (Option A flat `sources/` — bucket subdirs deleted; 8-worker parallel two-step ingest verified safe via controlled A/B test [serial vs parallel on same 50 sources, 8.04× speedup, no structural races, semantic drift = LLM temperature not parallelism]; chained backfill of 800 pre-v2 sources + fresh 200 batches running as of writing. Raw corpus recount: 19,054 sections in `wiki-raw/wiki.md`, not 9,691 as prior claim — remaining backlog is ~2× larger than previously reported. New ADRs: ARCH-030, D-060.)
**Prior updates:** 2026-08-13 (Two-step ingest + SCHEMA v3 + 1,091-page normalization) · 2026-08-11 (Karpathy-native wiki substrate, graph deprecated, wiki-raw split) · 2026-08-05 (pure-file Second Brain substrate + FIGS/mikai_shell)
**Latest commit on main at writing:** merge of `ac4c731` (file-based L4 substrate) and `339b569` (mikai_shell v1) plus 2026-08-11 through 2026-08-14 architecture-decision-record additions

## Current substrate state (2026-08-14)
- **~1,300 source files** in `~/.mikai/wiki/sources/` — **FLAT layout** (ARCH-030), no bucket subdirs. Growing live via chained backfill + fresh ingest.
- **~143 concept pages** in `~/.mikai/wiki/concepts/` (10 hand-authored + LLM-authored via auto-mint + synthesize-stubs)
- **Raw corpus: 19,054 sections** in `~/.mikai/wiki-raw/wiki.md` — of which ~1,300 processed into flat sources so far (~7%)
- **SCHEMA.md v3** — Astro-Han canonical shape live
- **10 broken wikilinks** (per 2026-08-14 lint run); 120 orphan concepts flagged for cross-link or demote
- **Two-step ingest** (`smoke_ingest_v2.py`) — production path, 8 workers default (D-060). Env var `MIKAI_WIKI_DIR` overrides target vault (added 2026-08-14 for isolated-test methodology; kept as permanent feature).
- **SHA256 content cache** (`~/.mikai/wiki/.ingest-sha256-cache.json`, D-059) — skips unchanged sections. 199 entries at start of 2026-08-14 chain run; growing as batches complete.
- **Chained batch runner** at `scratchpad/chain_ingest.sh` — sequential 200-source batches with dedup pass between (removes slug-drift duplicates by hash-suffix, keep-newest). Currently running 4 backfill + 1 fresh batch.
- **Wiki backup**: `~/.mikai/wiki-backup-2026-08-14-0828/` (pre-chain snapshot for rollback).
- **kepano/obsidian-skills** installed for Claude Code sessions inside the vault (2026-08-11)
- **Prior Graphiti substrate**: preserved read-only, no new writes since 2026-08-11

## Ranked fix queue (post-Fable-5 retrospective, 2026-08-14 evening)

Full narrative: `docs/INGESTION_PIPELINE_ANALYSIS_2026-08-14.md`. ADRs: ARCH-031, D-062.

1. **D-062 — Wire `claude -p --json-schema` into Pass 1** (`infra/mikai_llm/__init__.py:225-228`). ~30-60 min. Deletes the 25-min cold-start cluster + 4.5% JSON parse-fail class. Test streaming compatibility first.
2. **Pass-2-sees-body + code-owned frontmatter** (`smoke_ingest_v2.py:165-213`, `271-282`). ~half day. Currently Generation writes prose about a source it never read — Overviews are synthesis-of-a-synthesis by construction (P1 structural cap). Also closes broken-link bug in `_write_source_file_from_llm` (writes LLM Touches without `valid_touch_slugs` filter).
3. **ARCH-031 — Context-overflow chunking for long sources.** Raise `MAX_EXCERPT=4000` → `12000` (nashsu `LONG_SOURCE_CHUNK_MIN`). For sources > 40k, port nashsu `analyzeLongSourceInChunks`. ~half day total. **Discovered as major oversight 2026-08-14 evening**: for a 103KB Frostpunk source, LLM only saw first 4KB (~96% content invisible). Applies to ~40% of current 2,115 sources (all Claude threads, Perplexity threads, long notes).
4. **Full 482-slug directory in Pass 1** (`smoke_ingest_B.py:72-108`, currently top-40-only). ~30 min + prompt-cache. Removes rich-get-richer placement bias — at 143 concepts, top-40 was 28% of vocab; at 482 it's 8%. Placement drifts alphabetically because Analysis can't see niche concepts.
5. **A/B measurement pass** on 50-source isolated vaults (`MIKAI_WIKI_DIR` harness), Fable-fixed vs current. ~1 hour. Prove lift before committing quota to more ingest.
6. **Persistent ingest queue** (nashsu-style, replaces `scratchpad/chain_ingest.sh` + `chain_restart.sh`). ~1 day. Crash recovery, per-source retry state, quota backoff. Fixes the "75-min-of-doomed-calls" class we hit 2026-08-14 morning.
7. **Inbox triage LLM-judge pass** — consolidate 8,391-line `concept-inbox.md` into mint/merge/drop decisions. ~half day. Cognee issue #3629's design applied to suggestions.
8. **Poison-pill lane** — quarantine deterministically-failing sources after N retries (currently 1 source out of ~1,200 has been failing json-parse on every attempt). Trivial.

**Total: ~3 days focused work + measurement**, then resume backfill on improved pipeline for remaining 92.7% of the 19,054-section raw corpus.

## Session totals (2026-08-14)

- Sources: 1,108 → **2,115** (+1,007 net through v2 pipeline)
- Concepts: 143 → **482** (+339 auto-minted)
- Cache: 199 → **1,396** entries
- Bucket subdirs: 166 → **0** (ARCH-030 flat migration)
- Concept-inbox: ~5,000 → **8,391** lines (deferred bill for auto-mint)
- Corpus coverage: 1.0% → **7.3%** of 19,054 raw sections
- Wall-clock LLM time: ~2 hours productive across two chain runs
- Backup: `~/.mikai/wiki-backup-2026-08-14-0828/` (pre-chain snapshot)

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

### Claude.ai thread capture + Dream/Wiki runtime (new 2026-06-28)
Two new nightly daemons turn the graph into a self-maintaining model of the user. Full operational reference: `docs/DREAM_WIKI_RUNTIME.md`. Design + contradiction resolution: `MEMORY_ARCHITECTURE.md` (navy-windshield, Parts A–H).
- **`com.mikai.claude-threads` (daily 05:15)** — `infra/graphiti/claude_threads.py` ingests Claude.ai web/desktop conversations (`group_id="claude-thread"`), closing the long-standing claude-thread=0 gap. Auth = the desktop app's `sessionKey` cookie, decrypted with the *stable* `Claude Safe Storage` key cached as `CLAUDE_SAFE_STORAGE_PW` in `launchd.env` (avoids the keychain-hangs-under-launchd trap). Per-conversation watermark in `~/.mikai/claude_threads_state.json`. Backfill: `claude_threads.py --once --all`.
- **`com.mikai.dream` (nightly 06:00)** — `infra/graphiti/dream.py` is one DeepSeek call: reflect the last 7 days of episodes into `~/.mikai/wiki/wiki.md` (`## Who / Now / Tensions / Wants`) + append a revision delta to `log.md`. Karpathy LLM-Wiki + Generative-Agents reflection + MIKAI tension-surfacing. **Graph is read-only to the dream**; the wiki is a disposable, re-derivable projection. No numeric scoring in the prototype (deferred, O-052). First run: 138 episodes → 7.3 KB wiki, 6 live tensions surfaced.
- **Decisions proposed, not yet in `DECISIONS.md`:** ARCH-026 (dual-store), ARCH-027 (dreaming), D-053/054, O-048–052.

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
- `infra/decider/` — Surface Engine notification interface (D-053). Single Python script + 3 source adapters (iMessage SQLite, Calendar SQLite, Gmail IMAP), validates L4's send/silent decision, dispatches via ntfy.sh, logs to local SQLite for the dismiss/act feedback loop. Directory name is historical; Surface Engine is the canonical doc reference.
- `eval/` — Stage 6 harness + labeling CLI
- `docs/` — architecture, decisions, status, research, stage briefs, eval scorecards
- `scripts/` — patch automation, eval raters, preflight, dev utilities

### Surface Engine — notification interface (D-053) — early operational
> **Naming (2026-06-27):** **MIKAI** = backend (L3 graph + L4 reasoning). **Surface Engine** = the notification interface that consumes MIKAI. Code currently lives at `infra/decider/` for historical reasons; Surface Engine is the canonical doc name.

- **`infra/decider/mikai_decide.py`** — Surface Engine V0. Single-script LLM-only notification decider. Per tick: pulls candidate signals from MIKAI (5 semantic lenses via L3 port + a Cypher recency lens for last-24h edges) plus live cross-source events from iMessage/Calendar/Gmail adapters, asks L4 reasoning (Claude via headless `claude -p`, Max-legitimate) whether to send a notification, validates the decision's evidence citations against the prompt context, enforces a cooldown window, and dispatches via ntfy.sh on send.
- **`adapters/imessage.py`** — read-only SQLite query against `~/Library/Messages/chat.db`; requires Full Disk Access (granted).
- **`adapters/calendar.py`** — direct SQLite read of `~/Library/Calendars/Calendar.sqlitedb`. iCloud Calendars sync verified working.
- **`adapters/gmail.py`** — IMAP via Google app password (env vars in `.env.local`). Pulls unread + 24h windowed inbox.
- **Decision log** at `~/.mikai/notification_log.db` — one row per tick (sent or silent), captures prompt hash, decision JSON, reasoning, user response.
- **Verification status:** end-to-end dry-run confirmed cross-source reasoning over real data. ntfy → iPhone dispatch verified via `--test-ntfy`. Real organic notifications gated on (a) more diverse live signal in MIKAI (claude-thread=0 gap — see O-048), and (b) cron-style scheduling (still manual `--force` invocation).

### Surface Engine feedback loop v1 (D-054, 2026-07-13)
- **`notification_events` table** in `~/.mikai/notification_log.db` — event stream keyed on 12-char `notif_id` with types `SENT | TAPPED | DISMISSED_INFERRED`, carrying `dimension`, `action_type`, `source_ids`, `next_step_url`. Indexed on `notif_id` and `(event_type, event_ts)`.
- **Dispatch wiring** in `mikai_decide.py` — every dispatched notification now mints a `notif_id`, logs SENT before ntfy send, and rewrites the ntfy Click header from the raw destination URL to `${TAP_BASE_URL}/t/{notif_id}` so the real URL never leaves this Mac. The LLM output schema now includes an explicit `dimension` field; a `reasoning`-text regex fallback catches tail cases.
- **Tap endpoint** at `infra/decider/tap_endpoint.py` — standalone stdlib HTTP server, runs as `com.mikai.tap-endpoint` LaunchAgent on `0.0.0.0:8210` (port 8200 has an unrelated collision on this Mac). `GET /t/{notif_id}` looks up the SENT row, inserts TAPPED, 302s to real URL. Rejects malformed/unknown IDs at 404 without inserting phantom rows.
- **Dismissal inference cron** at `infra/decider/dismissal_inference.py` — runs as `com.mikai.dismissal-inference` LaunchAgent every 3600s. Marks any SENT older than 24h (env `MIKAI_DISMISS_AFTER_HOURS`) with no matching TAPPED or existing DISMISSED_INFERRED. Idempotent; re-runs are safe.
- **Phase 1 tunnel = LAN only.** `~/.mikai/tap_base_url` holds `http://192.168.88.228:8210`. iPhone taps work on home wifi; cellular taps fall back to no-signal (would-be TAPPED becomes DISMISSED_INFERRED at 24h — false negative, acceptable at this stage). Phase 2 promotes to Tailscale by writing a Tailscale hostname to that same file; no code change.
- **Not yet wired:** the aggregate `tap-rate by dimension / action_type` query is not yet fed back into the Surface Engine prompt as context. That's the second half of the loop — the LLM currently produces the SENT signal but doesn't yet see the TAPPED/DISMISSED signal on the next tick. Landing this is the next work item once ~2 weeks of empirical data have accumulated.
- **Verification:** smoke-tested end-to-end via a simulated tap through the LAN URL (SENT row → 302 to real URL preserved exactly → TAPPED row with correct dimension + action_type). Real iPhone tap gated on wifi + the next organic Surface Engine tick.

### Calendar planner v1 (D-055, 2026-07-13)
- **`calendar_proposals` table** in `~/.mikai/notification_log.db` — separate from `notification_events` because SQLite can't ALTER a CHECK constraint, and the proposal lifecycle (`PROPOSED → APPLIED | REJECTED | EXPIRED`) differs from the append-only event stream. Stores `event_uid`, `calendar_url`, `event_href`, `event_etag`, current/proposed title+description, `candidates_json` (audit of the picks the LLM made), `llm_rationale`, `apply_error`.
- **`infra/decider/caldav_client.py`** — stdlib iCloud CalDAV client (~350 lines). Handles principal + calendar-home discovery via PROPFIND, time-range event queries via REPORT, and PUT with `If-Match: <etag>` for optimistic-concurrency PATCH. Six unit tests cover the highest-risk piece: iCal fold/unfold, escape/unescape, and property replacement inside VEVENT blocks (every line except SUMMARY / DESCRIPTION / LAST-MODIFIED / DTSTAMP is preserved verbatim).
- **`infra/decider/calendar_planner.py`** — orchestrator (~300 lines). Once a day at 08:00 local via `com.mikai.calendar-planner` LaunchAgent: (1) discovers today's editable blocks via CalDAV (sole-attendee only, ≥90 min duration), (2) gathers a candidate pool spanning recent git activity on this repo + `docs/OPEN.md` + optional `~/.mikai/inflight.md` + Surface Engine needs registry, (3) calls DeepSeek V3 for a structured JSON pick (title, description, picks[], rationale), (4) inserts a PROPOSED row, (5) dispatches an ntfy card with `Actions: view, Approve, ...; view, Reject, ...`.
- **Approve/Reject routes** on the existing tap-endpoint (`GET /approve/{proposal_id}` / `GET /reject/{proposal_id}`). Approve refetches the event by UID (etag may drift between propose and approve), PATCHes via CalDAV, marks APPLIED with the new etag, sends confirmation ntfy. Reject just marks REJECTED. Both idempotent by construction — the UPDATE has `WHERE status = 'PROPOSED'`, so a second tap on either route hits 0 rows and returns the resolved-state HTML. Malformed / unknown / expired IDs return 404 or the appropriate confirmation page. Failure inside the CalDAV PATCH records `apply_error` and keeps status PROPOSED so a retry works.
- **Safety heuristic:** no calendar write ever fires without a tap. Auto-EXPIRE at 4h (`MIKAI_PROPOSAL_EXPIRY_H`) is the default if the user taps neither. Meetings with other attendees are strictly out of scope regardless of duration.
- **Credentials:** `MIKAI_ICLOUD_USER` (Apple ID email) + `MIKAI_ICLOUD_APP_PASSWORD` (app-specific password from appleid.apple.com) in `~/.mikai/launchd.env` (chmod 0600, gitignored). Regular iCloud password never enters the system.
- **Verified in isolation:** iCal fold/unfold/escape/property-replace passes 6 unit tests. Tap-endpoint approve/reject routes verified with seeded rows (reject → REJECTED; second reject → "Already rejected"; approve on rejected → "Already rejected"; approve with missing iCloud creds → 500 + apply_error recorded + status stays PROPOSED for retry).
- **Gated on Brian:** end-to-end iCloud verification (real 8am fire, real Approve tap, real block rewrite on iPhone) requires an app-specific password added to `~/.mikai/launchd.env` under the two keys above. Everything else is running.

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
- **Surface Engine calibration (D-053).** Surface Engine's first ticks ran silent — correctly, given the available signal in MIKAI was mostly newsletters + meta-references. Real validation of "L4 reasoning is the right brain" requires (a) richer signal in MIKAI (the claude-thread fix above), (b) actual dismiss/act data accumulating in `notification_log.db`, and (c) scheduling via Routines or local cron. Plan: re-run dry-runs after the claude-thread fix lands; instrument dismiss/act response capture; promote to scheduled execution.

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