# Dream crons

Scheduled incremental passes over the Karpathy wiki (`~/.mikai/wiki/`), split out of the one-shot `infra/graphiti/dream_bootstrap.py`. Install with `make install-dream-crons`.

## com.mikai.dream-weekly — Sunday 06:00 local

Whole-corpus ontology rebuild: `python3 -m infra.graphiti.dream_bootstrap ontology --max-calls 40` → `wiki-ontology.md`. ~31 interactive LLM calls (~15 min) at current corpus size; bills the Max sub. Fires two hours before `com.mikai.consolidate` (Sunday 08:00) so consolidation reads a fresh ontology.

## com.mikai.dream-monthly — 1st of month, 05:00 local

Wiki compaction: `python3 -m infra.graphiti.dream_bootstrap compact`. Zero LLM calls. Drops duplicate sections (same source + content bytes + matching body prefix — retry artifacts, watcher glitches), keeping the oldest copy. Backs up `wiki.md`, `wiki.index`, `wiki-episodes.log` as `*.pre-compact-<ts>`, rebuilds the derived files, retires `wiki.fts.db` (adapter regrows it), and writes `compact-report-<date>.md` listing what was dropped.

## Why no nightly narrative

Deferred pending use-case validation — no consumer of a daily narrative exists yet (analysis in the parent conversation). `wiki-narrative.md` stays a manual run: `python3 -m infra.graphiti.dream_bootstrap narrative`.

## Operations

- Manual trigger: `launchctl kickstart -k gui/$(id -u)/com.mikai.dream-weekly` (or `…dream-monthly`)
- Disable temporarily: `launchctl bootout gui/$(id -u) "$HOME/Library/Application Support/mikai/launchd/com.mikai.dream-weekly.plist"`; re-enable with `make install-dream-crons`
- Logs: `~/.mikai/logs/dream-{weekly,monthly}.{out,err}.log`
