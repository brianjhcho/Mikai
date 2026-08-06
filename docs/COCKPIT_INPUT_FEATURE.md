# Cockpit input: the ask path

*2026-08-06 · Design decision. Inputs: Brian's feature prompt, `docs/RETRIEVAL_STACK.md`, `docs/COCKPIT_ORGANIZATION_TRADEOFF.md`, `docs/ENTITY_MODEL.md`, the live brain at `~/.mikai/brain/`.*

## 1. Disambiguation

Brian is asking for a **query surface**: type free text — "I've been researching Black Forest Labs..." — and get reasoning already grounded in *him*: the entities he's been circling, adjacent threads, his standing preferences, without restating any of it. The underlying claim is correct and already MIKAI's thesis: an LLM predicts text; the substrate's job is to hand it the structure it can't infer. Nothing on main does this. The cockpit is a portrait — it answers "where is my life," read-only, and `COCKPIT_ORGANIZATION_TRADEOFF` §4 deliberately kept it that way. `mikai_exec` acts on an *existing thread* through a scoped channel; it takes a slug, not a question. `consolidate` rewrites priorities weekly; it takes no input at all. In scope: free text in → retrieval → composed prompt → grounded answer out. Out of scope: acting on the answer (that stays `mikai_exec`'s), ambient capture of what Brian is doing right now, and automatic learning of his phrasings. New capability in one sentence: **a read path where an arbitrary question is answered through the substrate instead of around it.**

## 2. Missing pieces vs already-built

- **(a) Input surface** — thin. A CLI first; the cockpit textarea comes later (see §5) so the portrait register isn't reopened prematurely.
- **(b) Context composer** — *the one genuinely new module.* Bundle WikiIndex/FTS5 hits, matching `brain/entities/` files, thread frontmatter, and BRAIN.md priorities into one prompt via the `mikai_llm` shim. New glue, but every input exists.
- **(c) Profile injection** — thin. A static `PROFILE.md`; BRAIN.md's priorities section is already half of it.
- **(d) Repeat-pattern learning** — unbuilt, and mostly research (§3.iii).
- **(e) Ambient signal ingestion** — unbuilt, out of scope (§3.ii).
- **(f) Concept clustering / triangulation** — unbuilt; this is vectors, and `RETRIEVAL_STACK` §5's triggers haven't fired.

Verdict: (b) is the work. (a) and (c) are wrappers. (d)–(f) are deferred, not designed around.

## 3. Holes in Brian's reasoning

**(i) "Triangulate what I'm hovering around" implies clustering we deferred.** Section-level cosine would surface *mentions* — exactly the ambient-presence noise `ENTITY_MODEL` §5 rejects. Cheapest partial: triangulate at read time. The consumer is an LLM that iterates probes — the load-bearing argument of `RETRIEVAL_STACK` §4 — so hand it top-k FTS5 sections plus entity files and ask it to name the cluster. 80% of the felt effect, zero plumbing.

**(ii) Browser tabs / active app need OS integrations that don't exist.** TCC dialogs, Screen Recording grants, an extension Brian has explicitly scope-avoided. Cheapest partial: the ambient signal *already lands* — Claude-thread ingestion, Apple Notes, git activity. A Black Forest Labs research session is in the wiki within a day. Recency-weight retrieval; skip the OS.

**(iii) Repeat-pattern learning is a research problem wearing a feature costume.** Extracting "when Brian says X he means Y" from N interactions needs labeled examples or an active-learning loop; v0-as-ML is a trap. But the *meta-insight is still worth a v0* — as curation, not learning: a periodic LLM pass over the ask log that *proposes* profile lines ("you asked for 'concise' in 7 of 9 prompts") into `inbox/` for `triage`, the exact pattern the hydrator uses so the Bethany-class hallucination can't self-install. Position: build the proposal pass, never silent learning.

**(iv) The profile rots.** A hand-maintained file drifts into flattery and stale facts. Same fix as (iii): keep `PROFILE.md` under one page, and let the (iii) pass double as its freshness audit. A profile that is *reviewed on a cadence* is a living document; one that is merely written is sediment.

## 4. Minimum viable prototype

`mikai_ask`. One command: accepts free text; retrieves — FTS5 top-k over the wiki, entity-name matches against `brain/entities/`, active-thread frontmatter, BRAIN.md priorities head; composes one prompt of retrieved context + `PROFILE.md` + query; calls `mikai_llm.chat(tier="interactive")`; prints the answer; appends a `mode="ask"` row to `progress.jsonl` (which also seeds §3.iii's corpus and §5's probe-miss evidence). Files: `infra/mikai_ask/{__init__,core,main}.py`, `~/.mikai/brain/PROFILE.md` (hand-written, ≤1 page), a Makefile target, tests beside the module. Honest estimate: **6–10 hours** — 4–6 for the composer and retrieval glue, 1 for the profile, 2 for tests. Everything past this is polish; the felt experience of "MIKAI understands me" lives entirely in whether the composer picks the right ten sections.

## 5. What the MVP defers, and the triggers

| Deferred | Trigger to build |
|---|---|
| Cockpit textarea | ~2 weeks of CLI use proves the composer; then add as quiet input, portrait register intact per `COCKPIT_ORGANIZATION_TRADEOFF` |
| Vectors / clustering | `RETRIEVAL_STACK` §5 triggers stand; ask-log probe-misses are now trigger-2 evidence |
| Repeat-pattern proposal pass | ≥50 logged asks; ships as inbox proposals only |
| Ambient (tabs, active app) | Ask transcripts show "what was I just reading" queries failing against ingested signal |
| Voice / screen | No trigger in sight; revisit only behind a product-direction change |
