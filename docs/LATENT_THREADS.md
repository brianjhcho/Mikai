# Latent-thread detector

## What it does

`infra/mikai_brain/latent_threads.py` closes MIKAI's L4 coverage gap:
today, thread-state tracking only fires on hand-seeded threads under
`~/.mikai/brain/threads/`, but the wiki holds hundreds of hits for
topics that ARE thread-shaped and never got entered (dry eyes, plant
care, proposal-to-Germaine, AI-competency job search).

Pipeline, one run:

1. Parse `~/.mikai/wiki/wiki-ontology.md`.
2. Filter out low-mention, stale, wrong-type, already-tracked, or
   already-proposed entities. This is free — no LLM call.
3. For each survivor: WikiFTS.search(slug, limit=8) for evidence
   snippets, then one interactive-tier LLM call asking "is this
   thread-shaped? what's its state, next step, department?"
4. Accept if `is_thread_shaped=True` AND `confidence >= 0.6`. Write
   `proposed-thread-<slug>.md` into `~/.mikai/brain/inbox/`.
5. Log to `progress.jsonl` (`mode="latent-threads"`).

Proposals never bypass triage. Brian promotes, merges, or deletes them
in the inbox — the same loop that catches entity-proposal noise.

## Confidence gate rationale

The pre-LLM filter is deliberately loose (mentions × recency × type)
because a high-cost second gate — the interactive-tier LLM call —
follows. That call classifies **shape**, not just topic frequency; a
place name with 300 mentions ("Kenya") should not surface as a thread,
because it's a reference token, not a decision surface. The 0.6
confidence floor keeps ambiguous verdicts (0.4–0.5, "maybe thread-
shaped, unclear") out of the inbox. Anything the LLM is only tepid
about is better raised on the next run once the wiki has more context,
than surfaced as noise now.

## Manual invocation

```
make latent-threads-dry     # print candidates + verdicts, write nothing
make latent-threads          # write proposals; ~15 LLM calls max
```

Direct: `python3 -m infra.mikai_brain.latent_threads [--dry-run] [--min-mentions N] [--min-recency-days D] [--limit N] [--verbose]`.

Defaults: `--min-mentions 30`, `--min-recency-days 60`, `--limit 15`.

## Cadence (deferred)

This should run weekly, ideally piggybacking on the Sunday `dream_weekly`
job that rebuilds `wiki-ontology.md`. Cron install is intentionally not
wired up yet — first few passes are manual so Brian can calibrate the
confidence gate and department taxonomy against real verdicts.
