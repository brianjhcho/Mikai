# legacy/ — the Neo4j-era dream

Archived 2026-08-15. Nothing here runs. Nothing here is imported by live
code. Kept for reference, not revival.

These three modules were the v1 "dream": a synthesis pass that read
episodes out of the **Neo4j graph** and compiled them into a single flat
`~/.mikai/wiki/wiki.md`. That substrate is deprecated — MIKAI's wiki is
now the Karpathy-shape vault at `~/.mikai/wiki/` (`concepts/` +
`sources/`), built by file-based passes that never touch a graph store.

| File | Was | Superseded by |
|---|---|---|
| `dream_graph.py` | Nightly one-LLM-call synthesis over 7 days of Neo4j episodes → `wiki.md`. Ran as `com.mikai.dream` at 06:00. | `ingest_source.py` (compile-on-ingest), `karpathy_rerender.py` (page shape), `dream_lint.py` (structural pass), `dream_pass.py` (semantic consolidation) |
| `full_corpus_dream.py` | One-off map-reduce over *every* episode in Neo4j to seed the wiki. DeepSeek V3, 8-way parallel, 240K-char chunks. | `dream_bootstrap.py` (`narrative` / `ontology` / `user-model` / `compact` passes) |
| `consolidation.py` | Called from `dream_graph.py` between Echoes and the wiki write. Only consumer was `dream_graph.py`. | `dream_pass.py` |

The move was prescribed by `docs/DREAM_PASS.md` §header, which named
`dream.py` as the doc's original home and specified relocation here.

## Why they can't just be re-enabled

1. **No graph to read.** Neo4j is not running and is not coming back as
   the substrate. Both graph modules die at `localhost:7687`.
2. **Wrong output path.** `dream_graph.py` writes `~/.mikai/wiki/wiki.md`.
   That file no longer exists in the vault — raw capture moved to
   `~/.mikai/wiki-raw/`, and the vault root now holds `concepts/` and
   `sources/`. A successful run would drop a stray flat file into an
   Obsidian vault that nothing reads.
3. **Wrong provider.** Both graph modules construct their own DeepSeek
   client (`base_url=https://api.deepseek.com`) instead of routing through
   `infra.mikai_llm`. MIKAI runs on the Claude Max subscription; every
   live call site uses `mikai_llm.chat(tier="interactive")`.

## Not deprecated — don't confuse these

`dream_bootstrap.py`, `dream_pass.py`, `dream_apply.py`, `dream_lint.py`,
and `karpathy_rerender.py` are all **current**. They live one directory up,
are file-based, and route their LLM traffic through the shim. The
`com.mikai.dream-nightly` / `-weekly` / `-monthly` LaunchAgents drive
`dream_bootstrap.py` and are part of the live design.

The job that was retired is `com.mikai.dream` (singular) — the 06:00
`dream-runner.sh` → `dream.py --days 7` path.
