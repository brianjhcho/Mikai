# MIKAI Dream Pass vs Anthropic Dreaming and Adjacent Research

**Date:** 2026-09-13
**Scope:** MIKAI's ARCH-035 dream pass (recursive Louvain community detection on wikilink graph + LLM-adjudicated cluster consolidation + retire-not-delete) compared against Anthropic's formalized "dreaming" (Auto Dream / AutoDream) and the closest research systems.

## TL;DR

- **Anthropic DOES have a formalized "dreaming" feature** — announced as Claude Auto Dream / AutoDream at Anthropic's developer conference. It's a **product research preview**, not a peer-reviewed paper. Runs offline between agent sessions, reviews up to 100 past sessions + persistent memory, reorganizes memory (dedupe, resolve contradictions, prune stale).
- **Closest MIKAI-aligned reference**: Anthropic Auto Dream (both are offline scheduled memory consolidation on persistent stores). Generative Agents (Park 2023) is second-closest — reflection = cluster memories + synthesize higher-order summaries.
- **Where MIKAI diverges**: (a) file-based Karpathy substrate vs Anthropic's structured memory records; (b) graph-based Louvain community detection on the wikilink graph, which no cited reference uses at this scale; (c) retire-not-delete with cross-reference rewriting is Wikipedia-style, more explicit than Auto Dream's "merge duplicates" description.
- **Biggest risk**: MIKAI treats consolidation as a graph-cluster problem, but the reference systems treat it as a session-transcript problem. Our approach depends on the wikilink graph being dense enough to reveal true clusters (Louvain fails on sparse graphs). Detectable via first-run cluster distribution — we already saw the bimodal distribution problem in the sample.
- **Recommended reference to borrow from most heavily**: Anthropic Auto Dream's **contradiction resolution** — MIKAI has no explicit contradiction-detection step, only synonym merging. Adding it would strengthen the dream pass.

## Comparison table

| System | Mechanism | MIKAI comparison | Verdict |
|---|---|---|---|
| **Anthropic Auto Dream** (research preview, 2026) | Offline scheduled ~24h; reviews sessions + memory store; LLM merges duplicates, resolves contradictions, prunes stale references | MIKAI: offline, cluster-based (Louvain), LLM adjudicates PROMOTE-HUB / MERGE-CREATE-HUB / KEEP-INDEPENDENT; adds retire stubs + cross-ref rewrite; no contradiction resolution | MIKAI-aligned; MIKAI diverges on the graph-cluster approach + retire-not-delete |
| **Generative Agents** (Park et al., Stanford, 2023) | Periodic reflection: cluster last 100 observations, LLM generates 3 high-level questions, synthesizes higher-order reflections stored in memory stream | MIKAI: cluster the entire vault (not last N observations), consolidate into denser hubs (not generate questions or summaries) | MIKAI-adjacent; different target: reflections augment the stream; MIKAI actively compresses the stream |
| **Voyager** (Wang et al., NVIDIA, 2023) | Skill library indexed by embedding of natural-language descriptions; top-5 relevant skills retrieved per task; skills accumulate but no explicit consolidation | MIKAI: consolidate library over time (retire redundant skills), not just accumulate | MIKAI-adjacent; Voyager is retrieval, no consolidation |
| **Reflexion** (Shinn et al., NEU + MIT, 2023) | Self-critique loop: agent reflects on failure trace, generates verbal reinforcement, retries | Different problem — Reflexion is task-level failure recovery, MIKAI is corpus-level knowledge consolidation | MIKAI-diverges (different problem entirely) |
| **MemGPT** (Packer et al., UC Berkeley, 2023) | Tiered memory: main context + external store; LLM pages memories in/out via function calls; no periodic consolidation | MIKAI doesn't do tiering; MIKAI consolidates the persistent store itself | MIKAI-diverges (retrieval architecture, not consolidation) |
| **Karpathy llm-wiki gist** (Karpathy, 2026-04) | Wiki over LLM-generated pages; explicitly says "over time, the wiki should crystallize into a small number of very dense, canonical pages that everything references"; leaves consolidation mechanism to implementer | MIKAI implements the crystallization Karpathy describes via Louvain + LLM adjudication | MIKAI-aligned; MIKAI implements Karpathy's underspecified consolidation step |
| **Louvain community detection** (Blondel et al., UCL, 2008) | Modularity-optimizing graph partitioning; O(n log n) practical performance; standard for community detection | MIKAI applies Louvain to the wikilink graph; recursive sub-clustering for 50+ blobs (planned) | PROVEN algorithm; MIKAI's application to wiki-consolidation is a novel use |

## Detailed notes

### Anthropic Auto Dream (a.k.a. Claude Dreaming)

Announced at Anthropic's developer conference (2026). **Not a peer-reviewed paper**, but described in product docs and community posts (MindStudio, LetsDataScience, Softpage, dev.to). Available as a research preview requiring developer access. A community re-implementation lives at `github.com/grandamenium/dream-skill` for Claude Code users who want the same pattern without developer-preview access.

**What it does**:
1. Runs offline between agent sessions (scheduled, ~24 hour trigger)
2. Reviews up to 100 past agent-session transcripts + the agent's persistent memory store
3. Uses the LLM to reorganize memory:
   - Merge duplicate entries
   - Resolve contradictions (favor most recent)
   - Prune stale references
4. Produces a new, consolidated memory store

**Neuroscience framing** used in Anthropic's own descriptions: the "consolidation" step parallels slow-wave sleep; "pattern extraction" step parallels REM-integration.

**Where MIKAI aligns**: both are offline scheduled consolidation on a persistent store, both use LLM for the reasoning step, both target duplicate merging.

**Where MIKAI diverges**:
- Auto Dream reviews **session transcripts**; MIKAI reviews the **wiki graph itself** (concepts + their wikilink adjacency).
- Auto Dream doesn't describe a graph-based clustering step; it appears to be transcript-driven LLM reorganization.
- MIKAI has explicit **retire-not-delete** with `retired_to:` frontmatter and cross-reference rewriting (Wikipedia redirect model). Auto Dream's docs describe merging but don't specify link-integrity semantics.
- Auto Dream includes **contradiction resolution** as an explicit step. **MIKAI does not.** This is a real gap — worth borrowing.

### Generative Agents (Park et al., 2023)

Simulated 25 agents in a small town using GPT-3.5. Introduced the memory-stream + reflection architecture that most subsequent agent designs borrow from.

**Reflection mechanism**:
- Periodically (couple of times per simulated day) the agent looks at its last 100 memories
- LLM proposes 3 high-level questions those memories could answer
- LLM synthesizes reflections (e.g., "Klaus has been eating alone and seems withdrawn")
- Reflections stored back in the memory stream at higher importance

**Retrieval scoring**: weighted mix of recency (exponential decay) + relevance (embedding cosine) + importance (LLM-rated 1-10).

**Alignment with MIKAI**: both cluster related items and synthesize higher-order structure via LLM. Both use embeddings + LLM.

**Divergence**: Generative Agents adds reflections *on top of* the stream (augmentation). MIKAI *replaces* redundant leaf concepts with denser canonical hubs (compression). Different move: augment vs compress.

### Voyager (Wang et al., 2023)

Minecraft agent. Skill library of JavaScript functions indexed by embedding of natural-language descriptions. Top-5 relevant skills retrieved per task.

**No explicit consolidation step.** Skills accumulate; there's no pruning, no merging. The paper notes catastrophic forgetting is alleviated by *not modifying* the library, but that's the opposite of what MIKAI needs.

**Alignment**: shared premise (an accumulating library benefits from indexed retrieval).
**Divergence**: MIKAI actively consolidates; Voyager doesn't.

### Reflexion (Shinn et al., 2023)

Task-level self-critique. Agent tries a task, fails, LLM generates verbal reinforcement, agent retries. Not consolidation. Cited only because "reflect" is in the name and it sometimes gets grouped with dreaming/consolidation work — it's a different problem entirely.

### MemGPT (Packer et al., 2023)

Tiered memory: fast in-context main store + slower external store. LLM manages paging via function calls. No periodic reorganization.

**Divergence from MIKAI**: MemGPT is a *retrieval* architecture (where to put memory). MIKAI's dream pass is a *reorganization* architecture (how to consolidate memory). Different layers of the stack — could compose.

### Karpathy's llm-wiki gist (2026-04)

The reference architecture MIKAI clones. Says explicitly: *"over time, the wiki should crystallize into a small number of very dense, canonical pages that everything references."*

**Doesn't specify HOW** to crystallize — leaves the consolidation mechanism to the implementer. MIKAI's ARCH-035 (Louvain + LLM adjudication) IS one implementation of the underspecified crystallization step.

### Louvain community detection (Blondel et al., 2008)

Standard modularity-optimization graph algorithm. O(n log n) in practice. Widely deployed in academic + industrial graph analysis.

**Novel MIKAI application**: no cited system uses Louvain on a **LLM-generated wiki's wikilink graph** for the purpose of driving KB consolidation. Generative Agents clusters memories in embedding space (not graph structure). Auto Dream clusters (implicitly) at session-transcript level. **Louvain-on-wikilinks is MIKAI's novel bet.**

## What MIKAI does that has no clear reference implementation — explicit creative bets

1. **Louvain community detection on the wikilink graph** as the primary clustering signal. Generative Agents uses embedding clustering. Auto Dream uses transcript review. Neither is graph-topology-based on the KB itself.
2. **Recursive sub-clustering** for large blobs (planned in ARCH-035's refined form). No reference cites this pattern; it's our answer to the bimodal-cluster problem the sample exposed.
3. **PROMOTE-HUB vs MERGE-CREATE-HUB vs KEEP-INDEPENDENT** as the three consolidation verdicts. This taxonomy is our own — Auto Dream merges duplicates without a "promote hub" concept, and Generative Agents doesn't consolidate at all.
4. **Retire-not-delete with cross-reference rewriting** — Wikipedia has this; Auto Dream doesn't explicitly. We inherited from nashsu's `rewriteCrossReferences`.

## Biggest risks

1. **Wikilink-graph density**: Louvain assumes meaningful graph structure. If MIKAI's wiki-graph is sparse or hub-mania-dominated (as our sample showed: 13 clusters at 50+ nodes = hub-mania blobs), naive Louvain produces useless partitions. Detected in the sample; fixed via recursive sub-clustering.
2. **No contradiction resolution**: Auto Dream has this; MIKAI doesn't. When two concept pages assert conflicting claims (e.g., different dates for the same event, opposing opinions Brian expressed over years), MIKAI's merge just concatenates — Auto Dream would resolve toward the newer entry.
3. **Cluster-verdict prompt bias**: our LLM prompt tends toward KEEP-INDEPENDENT unless the cluster is very homogeneous (see sample: cluster 2's 9-entity graph correctly stayed KEEP-INDEPENDENT, but cluster 1 with 4 members only absorbed 1). Auto Dream may over-merge; MIKAI may under-merge.

## Recommended reference to borrow from most heavily

**Anthropic Auto Dream's contradiction resolution step.** It's the one clear feature MIKAI lacks. Concrete integration:
- Add a **contradiction-detection LLM pass** after the cluster consolidation step
- For each canonical hub, ask the LLM: "Are there conflicting claims in the merged body? If so, favor the most recent source (highest `updated:` frontmatter) and note the retired position with a `## Historical Positions` section."
- This turns MIKAI's dream pass from "compression" into "compression + reconciliation" — closer to Auto Dream's full semantics.

## Sources

- Anthropic Auto Dream / Claude Dreaming: [MindStudio blog](https://www.mindstudio.ai/blog/claude-dreaming-feature-self-improving-agent-memory), [Softpage summary](https://www.softpagecms.com/2026/05/23/anthropic-claude-dreaming-agent-memory-consolidation/), [community re-implementation `dream-skill`](https://github.com/grandamenium/dream-skill), [DEV Community deep-dive](https://dev.to/akari_iku/does-claude-code-need-sleep-inside-the-unreleased-auto-dream-feature-2n7m)
- Generative Agents: Park et al., 2023 — see [DeepLearning.AI: The Batch summary](https://www.deeplearning.ai/the-batch/the-generative-agents-that-mimic-human-behavior-in-a-simulated-town), [MemX glossary](https://memx.app/glossary/generative-agents/)
- Voyager: Wang et al., 2023 — [arXiv:2305.16291](https://arxiv.org/abs/2305.16291), [project page voyager.minedojo.org](https://voyager.minedojo.org/)
- Louvain community detection: Blondel et al., "Fast unfolding of communities in large networks," Journal of Statistical Mechanics 2008
- Karpathy llm-wiki gist: 2026-04, https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- MIKAI decisions: ARCH-035 in `docs/DECISIONS.md`; sample results in `/tmp/dream-pass-sample-report.md`
