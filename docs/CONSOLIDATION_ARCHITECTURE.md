# MIKAI concept-promotion: strategic brief

## 1. Stress-test his reasoning

The target — LLM decides which concepts get pages, no per-item human review — is right, but for a narrower reason than "LLM judgment is good enough." The evidence is already on disk: 2 active entities and 24 proposals rotting in an inbox. That's the standard fate of review queues; Path-1-style gating has empirically failed in this system. Manual review *is* the wrong bottleneck. Correct diagnosis.

Two wobbles:

**He's underestimating the canonicalization tax — badly.** Proper nouns are self-canonicalizing; "germaine" names itself. Concepts don't have natural boundaries. Is it "Agent Memory," "Memory Consolidation," or "Dual-memory problem"? An LLM asked in three different sessions will mint all three pages, and the graph fragments silently. Wikipedia's hard-won lesson was that the notability decision was cheap compared to the redirect/disambiguation apparatus that keeps one topic = one page. Concept promotion without a canonicalization layer produces a worse outcome than no promotion: duplicated near-synonym pages that split retrieval mass.

**He's slightly overestimating LLM salience judgment — on the consistency axis, not the quality axis.** A frontier model shown good evidence (frequency, thread spread, recency, goal context) makes reasonable one-shot "worthy concept" calls. What it cannot do is hold a stable threshold across thousands of independent calls over months. Uncalibrated per-item judgment drifts. The fix is structural: make the *score* deterministic and let the LLM do only what needs language understanding (boundary drawing, merge adjudication, page authoring). "LLM decides" should mean "LLM operates inside a deterministic scoring-and-policy harness," not "LLM freelances the whole decision."

One reframe he hasn't fully stated: "worthy" is not a property of the concept. It's a property of (concept × current goals × time). Salience is non-stationary — "Graphiti patching" was page-worthy in May and is ambient now. So the system needs demotion as a first-class, cheap operation. Once demotion is cheap, promotion errors are cheap, and full automation stops being risky. That's the real unlock, more than better judgment.

## 2. The name he's circling

**Consolidation.** Call the layer the *consolidation layer*; the score it computes is a consolidation priority. The term comes from systems-level memory consolidation — the hippocampus-to-neocortex transfer where selected episodic traces get promoted into durable semantic structure (McClelland, McNaughton & O'Reilly's complementary learning systems, 1995, is the canonical framing). That is literally what this layer does: episodic wiki prose → stable semantic pages. The obvious candidates all fail on scope: *salience* and *attention* are moment-scoped (what's prominent right now), *relevance* is query-scoped (relative to one information need), *importance* is scoped to nothing. Consolidation is promotion-scoped — it names the decision to make something durable, and it comes with usable theory attached: Anderson & Schooler's rational analysis of memory (1991) says the promotion criterion should be *need probability* — consolidate what you'll need again — which is exactly the objective function Section 5b formalizes.

## 3. Literature lineage — pre-LLM

- **Xanadu.** Every span universally addressable, bidirectional links, transclusion instead of copies. Broke by demanding the canonical address space up front — no incremental bootstrap, never shipped at scale.
- **Wikipedia.** Notability policy decides page existence; redirects make many names resolve to one page; humans adjudicate disputes at AfD. Breaks without a crowd — the deliberation machinery doesn't scale down to one person, and notability (external coverage) is a proxy that doesn't exist for personal salience.
- **Roam Research.** Any `[[bracketed]]` phrase instantly becomes a page — zero promotion threshold, naming flexibility by user habit. Breaks into the hairball: no salience gate means every mention is a node and the graph carries no signal (Brian's ENTITY_MODEL.md already names this failure).
- **Zettelkasten / Luhmann.** The human is the salience *and* canonicalization function — deciding at write time whether a note earns an ID and where it branches. Worked for 90k cards; costs decades of daily curation, which is precisely the labor Brian refuses to spend.
- **org-mode.** Hierarchical outline plus tags plus agenda views; promotion = manual refile of a heading. Same failure as Zettelkasten: structure quality equals user diligence; nothing automates the judgment.
- **PageRank / HITS.** Importance from link topology, fully automatic, no editor. Breaks on personal corpora twice: link density doesn't exist yet (links are this system's *output*, so topology can't bootstrap it), and authority ≠ goal-relevance-to-you.

## 4. Literature lineage — post-LLM

- **MemGPT** (Packer et al., 2023). The LLM self-manages a memory hierarchy, paging facts between working context and archival storage. Promotion decisions are per-conversation and myopic — no global corpus view, so what gets consolidated depends on which session happened to touch it.
- **HippoRAG** (2024). Hippocampal-index framing: LLM-extracted entity graph + Personalized PageRank for multi-hop retrieval. It extracts *everything* — it builds an index but never decides what deserves to exist; noise compounds, and it's entity-centric, weak on abstract concepts.
- **GraphRAG** (Microsoft, 2024). Entity extraction → Leiden community detection → LLM-authored community summaries. This is the closest thing to auto-authored concept pages that exists; it breaks on maintenance — full-corpus rebuilds, community boundaries that shift between runs, summaries that aren't incrementally updatable or human-editable.
- **RAPTOR** (Sarthi et al., 2024). Recursive embedding-cluster-summarize into a tree of abstractions. Clusters are latent and unnamed — there's no addressable page a human can open, link to, or correct; the tree also wants rebuilding rather than incremental growth.
- **Mem0 / Cognee / Mnemosyne.** Product memory layers: extraction pipelines into fact stores or graphs. They promote at fact granularity with no scarcity — every extracted triple persists, no notability analogue — so the store grows without a salience gate (and Mem0 v3 dropped its graph store entirely).
- **Anthropic contextual retrieval** (2024). LLM prepends situating context to each chunk before BM25/embedding indexing. Genuinely improves retrieval of what exists; entirely orthogonal to consolidation — it never decides that anything deserves a page.

The pattern across both eras: pre-LLM systems had good *gates* powered by expensive humans; post-LLM systems have cheap authorship and **no gate at all**. Brian is building the missing quadrant — cheap authorship behind a real gate. GraphRAG is the nearest neighbor; his delta is incremental maintenance, human-legible pages, and a personal (not corpus-statistical) salience function.

## 5. The two sub-problems

**(a) Naming flexibility.** What works in production is the Wikipedia redirect model implemented as entity linking: one canonical slug per concept, an append-only `aliases:` list in frontmatter, and a mandatory resolution pass before any mint. Pipeline: exact/normalized alias-table match → embedding kNN over existing concept names+aliases for candidates → LLM adjudicates merge-vs-new *only when candidates exist*. The load-bearing disciplines: the LLM is never allowed to mint a name without first attempting resolution; aliases are cheap and append-only; merges and renames are logged and reversible. This extends the "shortest unambiguous name wins" rule already in ENTITY_MODEL.md from people to concepts.

**(b) Salience functional form.** A weighted log-linear activation with a hard novelty gate:

**S(c, t) = w₁·log(density) + w₂·Σᵢ (t − tᵢ)^(−d) + w₃·spread + w₄·max-sim(c, active goals ∪ profile)** — promote when S crosses a threshold with hysteresis (promote high, demote low, dead zone between, so pages don't flap).

Term by term: density = total mentions in wiki.md; the second term is frequency-with-recency-decay — this is verbatim ACT-R base-level activation, the closest prior art, justified by Anderson & Schooler's finding that it tracks need probability; spread = count of *distinct threads/sources* mentioning c, which is his existing "≥2 threads" entity rule generalized and matters more than raw density (one obsessive week ≠ durable concept — burstiness discounts, like df vs tf in IR); the goal term is embedding similarity against L4's current task states and long-term goal statements, which is what makes the score *his* rather than corpus-statistical. Everything in S is deterministic and inspectable. The LLM enters only after the gate fires.

## 6. Path 1 vs Path 2

**Path 2.** The 24 stuck proposals already falsified Path 1's loop: approval queues rot, and approvals only yield binary labels on system-chosen candidates — biased, low-information feedback that converges slowly. Path 2 gets dense signal immediately — a ranked exemplar set from Brian *defines* the target function directly and is exactly the form (few-shot exemplars + stated reasons) that both the weight-fitting and the LLM judge consume best.

**First 20 decisions, operationally.** Brian seeds ~10 exemplars ("these deserve pages, roughly this order, here's why in one line each") plus 5 explicit negatives. The system fits S's weights to reproduce that ranking, then proposes the next 20 candidates as a *ranked batch* — not an inbox — each with an evidence card: density, thread spread, first/last seen, three sample excerpts, nearest existing concepts with similarity scores, proposed canonical name + aliases. Brian reviews the batch in one sitting; verdicts are accept / reject / rename / merge-into, each with a one-line reason. Disagreements resolve one way: Brian wins, and his reason is written into a promotion-policy doc the LLM judge reads on every future call (constitution-style, like his existing DECISIONS.md pattern). After ~20 verdicts, per-item review ends: the policy doc + exemplars replace the human gate, and Brian drops to sampled audits (one candidate in ten) plus unconditional demotion rights. Demotion-is-cheap is what makes removing the human safe.

## Diagram spec

**Overall shape:** a left-to-right funnel-then-fan — wide at the corpus, narrowing through the gate, fanning back out into retrieval. Two feedback arrows sweep underneath, right to left. One glance should read: "everything flows right; two loops flow back."

**Legend (top-right):** solid grey rectangles = deterministic; purple rounded boxes with dashed borders = LLM-called; small amber valve icon = human touchpoint; small white side-tabs = literature annotations.

**Main flow, left to right:**

1. **Cylinder: `wiki.md` (27MB, 8k sections)** — with `wiki.fts.db` as a small attached disk icon.
2. **Grey rect: Signal extraction** — sublabels: mention density, thread spread, recency curve. Deterministic, runs from FTS5.
3. **Grey rect: Consolidation scoring `S(c,t)`** — the formula's four terms listed as four small input ports on its left edge; the fourth port (goal-alignment) receives feedback arrow A. Side-tab: *ACT-R base-level activation*. Behind this box, a faded ghost silhouette of a person at a card file, labeled *"Luhmann / org-mode: the human this replaces."*
4. **Gate glyph: Threshold + hysteresis** — drawn as a literal valve/funnel neck; the amber human icon sits *beside* it (not inline) labeled "sampled audit, 1-in-10," receiving a thin dotted tap-off line.
5. **Purple rounded: Canonicalization** — internally split: grey strip "alias table + embedding kNN" feeding purple strip "LLM merge adjudication." Side-tab: *Wikipedia redirects*. A small "mint new name" exit only from the purple strip, annotated "only after resolution fails."
6. **Purple rounded: Concept-page authoring** — output icon: a markdown file with frontmatter. Side-tab: *GraphRAG community summaries*.
7. **Grey rect: Wikilink insertion** — deterministic rewrite pass over wiki.md. Side-tab: *Roam* with a small warning glyph, caption "no gate = hairball." A dashed grey box hangs below it: *"later: link-topology reinforcement (PageRank)"* with a dashed arrow back into scoring, annotated "only after link density exists — bootstrap order matters."
8. **Grey rect: Retrieval consumption** — BM25 + concept pages, feeding a small L4/cockpit chip. Side-tab: *Anthropic contextual retrieval* placed here (retrieval-side, explicitly outside the gate).

**Feedback loop A (bottom, right→left, blue):** from the **L4/cockpit chip** back to scoring's fourth input port. Label: "active task states + long-term goals → goal-alignment term." Deterministic styling.

**Feedback loop B (bottom, lower arc, amber):** from the human audit valve back to two targets — the gate (threshold tuning) and both purple boxes (via a small scroll icon labeled **"promotion-policy doc"** in the arrow's path). Label: "accept/reject/rename verdicts → written rules the LLM judge reads." The scroll icon is the visual anchor: verdicts become text, text conditions the LLM.

**MemGPT / HippoRAG / RAPTOR / Mem0** don't slot into the flow; place them in a small strip below the legend labeled "adjacent, not in-path: no gate," each with a one-word reason (myopic / extracts-all / unnamed clusters / no scarcity). Their absence from the pipeline is itself the point the diagram should make.