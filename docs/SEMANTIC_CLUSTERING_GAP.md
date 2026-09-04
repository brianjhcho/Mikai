I've verified the key empirical facts against the live ledger before writing. Three load-bearing findings: `weighted yoga` **is** in the ledger — rank 3049, S=6.27, 348 mentions, spread=2, G=0.08 with the *correct* best-goal match ("posture and workout optimization"); the top-10 S cutoff is ~12.1, all conversation filler; and the entire G column lives in a 0.03–0.11 noise band (`ingested` G=0.04 vs `weighted yoga` G=0.08 — no discriminative power). Here is the brief.

---

# Why the Weighted-Yoga Thread Never Reached the Wiki — Architecture Brief

## 1. Is Brian's mental model of Karpathy correct?

Half correct, and the half that's wrong is the mechanism, not the outcome.

What Brian expects — `[[posture]]` as an entry point that gathers weighted yoga, mobility, shoulder restriction, deadlift progression — **is** what Karpathy's system produces. But wikilinks are not what produces it. In Karpathy's scheme (and, to the best of my recollection, in all four implementations from the earlier research turn — flsteven87/llm-wiki-mcp, lucasastorian/llmwiki, rohitg00/agentmemory, akitaonrails/ai-memory; hedging on per-repo details, but the structural pattern is consistent), the flow is: **new content arrives → an LLM reads it → the LLM decides which existing pages it belongs to → the LLM edits those pages and adds links.** The semantic clustering happens inside the LLM's judgment at *write time*, usually assisted by embedding search over existing pages to shortlist candidates. Wikilinks are the *residue* of that judgment — the output, never the engine. There is no string-extraction stage anywhere in Karpathy's loop.

MIKAI adopted Karpathy's artifact shape (the ~50-line TL;DR/Why/Notes/Sources page, `karpathy_rerender.py`) but replaced Karpathy's engine with n-gram frequency statistics. `render_karpathy_page` even computes "related concepts" by slug-token overlap — string matching again. So MIKAI produces Karpathy-*shaped* pages about non-Karpathy concepts: `ingested`, `assistant`, `right`. Brian is not misunderstanding the wiki-link structure; he's assuming the LLM-at-write-time router exists because the page format implies it. It was never built. That's the whole answer to "am I understanding Karpathy incorrectly": the format survived the port; the semantic router didn't.

Note also that Karpathy's LLM router does the clustering *incrementally per-item* — it never needs a global "find all body-improvement threads" pass, because every thread was filed under `[[posture]]` the day it was written. Query-time synthesis (Path C in CONCEPT_NAVIGATION_DEFERRED.md) then just reads the page. MIKAI has neither the write-time router nor thread-level query-time retrieval, which is why the gap is visible from both ends.

## 2. Why the Weighted Yoga thread specifically wasn't extracted

Tracing through `dream_bootstrap.py`:

**Extraction — partially succeeded, contrary to the framing.** "Weighted yoga" fails the capitalized pass (`_NGRAM_RE` requires every word capitalized; the thread title capitalizes only "Weighted") but passes the lowercase pass, and the ledger confirms it: **rank 3049, S=6.27, base=4.27, spread=2, 348 mentions.** `posture` is rank 285 (S=9.50, 292 mentions), `scapula` rank 589, `chest` rank 553. Sub-terms all present. v003's extraction fix worked. The failure moved downstream.

**Ranking — this is where it dies, for a structural reason, not a tuning reason.** S is a *global per-token corpus statistic* with no unit of "thread." The weighted-yoga evidence is 800+ turns **concentrated in essentially one conversation**: spread=2 (it appears in only two source streams), and base activation over 348 sections of one thread is 4.27, versus `ingested` at base=7.61, spread=9, 9,475 mentions — because infrastructure vocabulary appears in *every* section of *every* stream. The property that makes weighted-yoga a real topic — 803 turns of sustained, focused attention in one place — is precisely the property S penalizes (low spread, bounded section count), and the property that makes `assistant` garbage — uniform smear across the corpus — is what S rewards. No reweighting fixes this; concentration-in-a-coherent-unit isn't measured by any term.

**The G-axis fired correctly and still couldn't help.** `weighted yoga`'s best-goal is *"posture and workout optimization"* — the matching worked. But G=0.08, in a column whose entire range is ~0.03–0.11 (`ingested` scores 0.04; `Yoga Alignment` best-matches *"taking care of parents"* at 0.11). Binary token-set cosine with pooled context sets thousands of tokens wide compresses everything into noise — the denominator `sqrt(|ctx|·|goal|)` is dominated by context-set size, not topical alignment. So top-10-by-G promotion picked system-prompt artifacts (`toggle-rode`, `solo-builder`) over a correct 0.08. The v003 ledger note ("every G-promoted page best-matched MIKAI and ambient computing") is this same failure.

**Would the hand-authored page have pulled the thread in? No — structurally impossible, not just missing.** The pipeline is strictly one-directional: corpus → candidates → scores → pages. Nothing reads `concepts/*.md` back. `run_promote`'s candidate sources are ontology + n-grams; an existing page is not a candidate source, its `aliases:` frontmatter is never fed to `find_mention_records`, and even if it were, matching is whole-word string match — a turn saying "single-arm KB lunges" contains no substring of "posture-and-workout." And `mikai_ask`'s BM25 top-8 doesn't consult pages either. The hand page is a leaf with no inbound edge from ingestion and no outbound edge into retrieval. There is no attractor mechanism: a page cannot accumulate semantically-related evidence, only string-matching evidence, and only when the promotion pass happens to re-run its exact name.

## 3. The gap Brian is naming

**One sentence: MIKAI has no abstraction layer that maps many episodes to one latent topic — every mechanism in the pipeline operates on surface strings, so a concept that exists only at the level of paraphrase ("improving my body") can never be represented, scored, or retrieved as a unit.**

The technical vocabulary: **thematic abstraction / concept induction**, implemented as *embed → cluster → LLM-label*, plus **hierarchical / multi-resolution retrieval** at query time. The prior art from earlier briefs, and what each does differently:

- **Anthropic's Clio** — LLM-summarize each unit (for Clio, a conversation; note the unit is the *thread*, exactly Brian's instinct), embed the summaries, cluster, LLM-name each cluster. The LLM labels *clusters of evidence*, never free-generates themes. Extraction step: semantic, thread-level. This is the closest match to MIKAI's need.
- **GraphRAG (Microsoft, 2024)** — entity graph → community detection (Leiden) → pre-written *community summaries*; "global" queries answered by map-reduce over community summaries rather than chunk retrieval. Its lesson: precompute the abstraction, retrieve at the abstraction level.
- **RAPTOR (Sarthi et al., 2024)** — recursive embed-cluster-summarize into a tree; retrieval searches *all levels*, so "what's my exercise philosophy" hits a high node while "what weight is my deadlift" hits a leaf. Its lesson: queries arrive at different abstraction levels; the index should too.
- **HippoRAG** — KG + Personalized PageRank for multi-hop association at retrieval time. Less central here; its lesson is cheap associative *expansion* from a seed concept.

Common to all four, against MIKAI today: at extraction they operate on **embeddings of content units** (threads/chunks), not on recurring surface strings; at retrieval they return **precomputed abstractions** (cluster labels, community summaries, tree nodes) that a query can hit even with zero lexical overlap. MIKAI's n-grams give it a vocabulary; these systems build a *topology*.

## 4. The fifth primitive

E1–E4 all assume the candidate *already exists as a string* and adjudicate its worth. The fifth primitive is upstream of all of them:

**E5 — Semantic assignment: an embedding-space membership map from content units (threads, notes) to concepts, with LLM labeling of unclaimed clusters.**

Where it slots: `extract → alias-fold → `**`E5 assign/cluster`**` → score → promote → render`. Concretely, E5 changes what "c" *is*: today a concept is a string with a regex-defined mention set; after E5 a concept is a **cluster of units** with a name. Scoring then runs over membership sets instead of string matches — S's inputs (timestamps, streams) come from member units, which fixes §2's ranking failure as a side effect, because an 803-turn thread contributes as a *massive coherent member*, not as diluted per-token noise.

- **Consumes:** (a) thread-level units — derivable today, since section names already encode `claude-thread::<title>::<idx>`; (b) one Voyage embedding per unit (embed the thread title + a sample of turns, or an LLM micro-summary per Clio); (c) existing concept pages — including hand-authored ones — embedded from their TL;DR + aliases + notes, acting as **cluster seeds/attractors**. This is the missing back-edge: writing `posture-and-workout.md` *should* change the next dream pass, and under E5 it does.
- **Produces:** (a) a membership map `unit → [concepts]` (a unit may belong to several); (b) for units claiming no existing concept, clusters of the residue; (c) cached artifacts, per house convention — deterministic given the cache, auditable in the ledger ("member threads" column).
- **LLM entry points, both bounded:** (1) label residue clusters with ≥N member units, Clio-style — the LLM names evidence it can cite, never invents themes; (2) optionally, per-thread micro-summaries to embed (cleaner vectors than raw turns). Assignment itself is cosine + threshold — deterministic; the ambiguous band can use the existing `consolidation.py` adjudication pattern.

E5 is also what CONCEPT_NAVIGATION_DEFERRED.md's Option B was missing a mechanism for: it answers "what counts as a concept worth a page" empirically — a cluster with enough members — instead of doctrinally.

## 5. Three builds, ordered by expected impact on Brian's complaint

**Build A — Thread units + page-as-attractor assignment.** *(the back-edge; ~3–4h)*
(a) Parse thread IDs out of existing section names to form units (a thread = one unit; an Apple note = one unit). Voyage-embed each unit (title + sampled turns) and each existing concept page (TL;DR + aliases + notes). Assign unit→page at cosine ≥ threshold; write assignments into each page's Sources as *thread-level* wikilinks with turn counts and date spans, and store the membership map for retrieval.
(b) This is literally Brian's ask: `[[posture-and-workout]]` becomes the entry point to the weighted-yoga thread *because they're semantically similar*, with zero string overlap required. Hand-authoring a page becomes a real steering input.
(c) **Falsifiable:** after one run, `posture-and-workout.md` lists both "Weighted yoga for flexibility and alignment" (803 turns, 2026-07-01→08-08) and "Forward head posture root causes" (93 turns) in Sources. If either is missed, the build failed.

**Build B — Residue clustering + labeling (Clio-lite concept induction).** *(~4h, needs A's unit embeddings)*
(a) Cluster the thread units *not* claimed by any page (agglomerative or HDBSCAN over a few hundred vectors — trivial scale). For clusters with ≥3 units, one bounded LLM call names the cluster and writes a quarantined `Inferred (unconfirmed)` page citing member thread IDs — the §3-of-MVP-diagnosis quarantine design, applied to themes. Salience for these concepts computes over member units.
(b) This generates the pages nobody hand-authored — it's the machine producing what I hand-wrote yesterday, from evidence. It's also the only mechanism that can ever surface "improving my body" as a concept, since that string never occurs.
(c) **Falsifiable:** run with `posture-and-workout.md` deleted. A cluster containing both posture threads (plus the 2019/2022 Apple-notes workout material, if the embeddings are good) emerges and gets labeled with an exercise/posture/body name. If yoga threads scatter across clusters or the label is generic ("personal notes"), the build failed.

**Build C — Thread-aware two-stage retrieval in `mikai_ask`.** *(~3h given A's index)*
(a) Replace flat BM25-top-8 with: stage 1 — embed the query, retrieve top-K units (threads + concept pages) by cosine from A's index; stage 2 — BM25 *within* the winning threads to pick turns; synthesize with thread titles cited. Concept-page hits expand the query with their aliases and member threads.
(b) This is the "on-demand thread-level synthesis" half of Brian's ask, and it's Path C (query-time synthesis, already chosen 2026-08-07) finally given the retrieval substrate it assumed. It also makes ask-quality independent of whether promotion ever ranked the topic.
(c) **Falsifiable:** ask "what's my current posture and workout program?" Today, BM25 returns fragments (the compressed weekly-synthesis line, at best). After: the answer cites the weighted-yoga thread by name and contains ≥3 facts that exist only inside it (deadlift 135→200, axial-elongation cue, single-arm KB lunges for glute medius). Run the same ask before and after; diff the citations.

Order rationale: A creates the unit and the attractor edge (smallest build, directly answers "why isn't my thread under the posture link"); B needs A's embeddings and removes the dependence on hand-authoring; C consumes A's index and closes the loop at ask-time. All three leave E1–E4 and the deterministic ledger intact — E5 changes what gets scored, not how scoring works.

---

**What this means, plainly:** You weren't misreading Karpathy's output — you were assuming his engine came with the page format. His engine is an LLM deciding, at write time, which page each new conversation belongs to. MIKAI swapped that engine for string counting, so an 803-turn thread about your body ranked 3,049th behind the word "ingested." The fix isn't better weights; it's giving the system a notion of *thread* and an embedding-space map from threads to pages — after which your hand-written posture page stops being a dead leaf and starts acting as a magnet.