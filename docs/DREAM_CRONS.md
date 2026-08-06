# Dream crons

Scheduled incremental passes over the Karpathy wiki (`~/.mikai/wiki/`), split out of the one-shot `infra/graphiti/dream_bootstrap.py`. Install with `make install-dream-crons`.

## com.mikai.dream-nightly — 03:00 local daily

Incremental narrative delta: `python3 -m infra.graphiti.dream_bootstrap narrative --incremental --ledger-mode dream-nightly`.

- Reads only wiki sections with `header_ts` newer than the watermark in `~/.mikai/wiki/.narrative-state.json`, then **appends** a 200-500 word first-person delta to `wiki-narrative.md` under a dated `## Δ YYYY-MM-DD` header. Skips (without advancing the watermark) when fewer than 5 new sections exist — the trickle accumulates until there is something to say.
- **Cost:** 1 LLM call per run, ~50-100K tokens in / ~2K out — roughly **1M tokens/month marginal** at 30 runs, billed to the Max sub via `claude -p`.
- **Retention:** dated deltas older than 30 days are truncated on each append, so the file stays bounded.
- **Weekly interaction:** on Sundays the runner does a fresh full-window rebuild (`narrative`, last 30 days, ~5 calls) instead of an incremental append. The rebuild **overwrites** the file — replacing the last week of dated deltas with a coherent full narrative — and resets the watermark, so Monday's delta starts clean. It fires at 03:00, ahead of dream-weekly (06:00) and consolidate (08:00), so both consume a fresh narrative. Any manual full `narrative` run has the same replace-and-reset effect.
- On success the run writes a `mode="dream-nightly"` row to `progress.jsonl` (`--ledger-mode`), which `com.mikai.health-check` watches (max gap 28h — see docs/HEALTH_CHECK.md).

## com.mikai.dream-weekly — Sunday 06:00 local

Whole-corpus ontology rebuild: `python3 -m infra.graphiti.dream_bootstrap ontology --max-calls 40` → `wiki-ontology.md`. ~31 interactive LLM calls (~15 min) at current corpus size; bills the Max sub. Fires two hours before `com.mikai.consolidate` (Sunday 08:00) so consolidation reads a fresh ontology.

## com.mikai.dream-monthly — 1st of month, 05:00 local

Wiki compaction: `python3 -m infra.graphiti.dream_bootstrap compact`. Zero LLM calls. Drops duplicate sections (same source + content bytes + matching body prefix — retry artifacts, watcher glitches), keeping the oldest copy. Backs up `wiki.md`, `wiki.index`, `wiki-episodes.log` as `*.pre-compact-<ts>`, rebuilds the derived files, retires `wiki.fts.db` (adapter regrows it), and writes `compact-report-<date>.md` listing what was dropped.

## Operations

- Manual trigger: `launchctl kickstart -k gui/$(id -u)/com.mikai.dream-nightly` (or `…dream-weekly`, `…dream-monthly`)
- Disable temporarily: `launchctl bootout gui/$(id -u) "$HOME/Library/Application Support/mikai/launchd/com.mikai.dream-nightly.plist"` (same pattern for the others); re-enable with `make install-dream-crons`
- Logs: `~/.mikai/logs/dream-{nightly,weekly,monthly}.{out,err}.log`
- All three write `progress.jsonl` heartbeat rows on success (`--ledger-mode dream-nightly|dream-weekly|dream-monthly`), consumed by `com.mikai.health-check`.

> History: nightly narrative was initially deferred pending use-case validation; it shipped 2026-08-06 as the incremental delta above (approved in the 2026-08 infra pass — delta form keeps the marginal cost at ~1 call/night instead of a full rebuild).
