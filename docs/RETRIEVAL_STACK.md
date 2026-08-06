# Retrieval stack for the wiki substrate

*2026-08-05 · Decision doc. Question: after the Graphiti→wiki pivot, which retrieval layers does the substrate need — offset index, FTS5, vectors? Baseline inputs: `docs/COCKPIT_STRUCTURE_RESEARCH.md`, `docs/COCKPIT_ORGANIZATION_TRADEOFF.md`, `docs/ENTITY_MODEL.md`. Corpus: 8,048 dated sections, 27MB, single `wiki.md`, growing toward 50–100MB.*

## 1. What the comparables actually use

- **Obsidian** — core search scans a metadata cache; [Omnisearch](https://community.obsidian.md/plugins/omnisearch) adds a BM25 inverted index; [Smart Connections](https://smartconnections.app/smart-connections/) adds *local* embeddings (bge-micro, 384-dim, cached on disk).
- **Notion** — server-side keyword search; Notion AI Q&A layers hosted embeddings on top. *(General knowledge; not fetched.)*
- **mem.ai** — server-side embeddings drive [ambient recall and AI collections](https://get.mem.ai/blog/organize-your-notes-with-ai-using-collections); retrieval is the product.
- **Reflect** — [client-side embedding index](https://reflect.app/blog/ai-search) for semantic search and similar-notes; small local model, no server round-trip.
- **Roam** — plain keyword/fuzzy string match; [widely judged its weakest surface](https://alvistor.com/comparing-roamresearch-graph-view-with-logseq-obsidian-and-others/).
- **Anytype** — embedded [tantivy](https://github.com/quickwit-oss/tantivy) (Rust Lucene: inverted index + BM25) via [anyproto/tantivy-go](https://pkg.go.dev/github.com/anyproto/tantivy-go), beside its object/type index.
- **Logseq** — keyword/fuzzy over a local SQLite-backed full-text index in the desktop app.
- **Zep/Graphiti** — [hybrid BM25 + cosine + graph BFS, RRF-fused](https://help.getzep.com/graphiti/working-with-data/searching); zero LLM calls at query time. This is what we left.
- **Karpathy's LLM wiki** — [no index at all](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2): the agent reads `index.md` and greps/navigates. Retrieval *is* the LLM.
- **Claude Projects** — full-context stuffing until a threshold, then [automatic RAG chunk retrieval](https://support.claude.com/en/articles/11473015-retrieval-augmented-generation-rag-for-projects).
- **ChatGPT memory** — saved memories injected into the system prompt; chat-history referencing is shallow and [cannot actually search the full history](https://embracethered.com/blog/posts/2025/chatgpt-how-does-chat-history-memory-preferences-work/).
- **Cursor** — Merkle-tree sync + chunk embeddings in Turbopuffer; [pure vector retrieval](https://cursor.com/blog/secure-codebase-indexing) at million-chunk scale.

The pattern: local single-user tools ship an **inverted keyword index as the floor** (Anytype, Logseq, Omnisearch). Embeddings appear either as cheap client-side models (Reflect, Smart Connections) or where a *human* types one query and gets one shot. Tools whose reader is an LLM (Karpathy, Claude Projects below threshold, ChatGPT) lean on stuffing and navigation, because an LLM can iterate probes.

## 2. What Graphiti gave up, and what recovers it

| Lost | Substitute | Verdict |
|---|---|---|
| Bitemporal edges (valid-time + ingest-time, per-fact invalidation) | Dated sections give event time; git history of `wiki.md` gives transaction time; supersession happens narratively in dream/ontology rewrites | **Different-and-fine** for a personal corpus — but per-fact invalidation is gone; contradictions persist until a rewrite pass notices |
| Typed relations | `entities:` frontmatter binary edges (ENTITY_MODEL §5) | **Worse, and deliberately so** — the causal-claim test replaced the type system; no retrieval layer restores this |
| Entity resolution at ingest | Query-time LLM resolution + `entities/*.md` canonical slugs; FTS5 makes alias→sections cheap | **Worse, degrades with scale** — this is the one real debt |
| Vector search (Voyage) | Layer 3 exactly | **Recoverable whenever we choose** — the only loss with a drop-in restoration |

## 3. The three layers at 8K episodes

**Offset index (Path 2, building).** Solves: windowed reads by date/source/name without loading 27MB; the MCP context-blowout problem. Doesn't solve: any content query. Cost: in flight, ~free ongoing (rebuild in seconds). Without it: every consumer reads or blind-greps the whole file — non-optional, correctly prioritized.

**FTS5.** Solves: ranked keyword retrieval — BM25 returns the *best* 10 sections for "moss pole," not all 300 mentions for the LLM to triage; makes entity-alias lookup instant. Doesn't solve: paraphrase/pronoun queries ("who's she"). Cost: ~4 hours; index is a disposable derived artifact rebuilt from `wiki.md` (no sync problem); ~10MB storage, seconds/week compute. Without it: grep stays fast (27MB is nothing for grep) but *unranked* — the failure mode is triage load, not latency.

**Vector embeddings.** Solves: semantic recall and fuzzy entity resolution — the genuine Graphiti restoration. Doesn't solve: precision; worse, section-level cosine surfaces *mentions*, exactly the ambient-presence noise ENTITY_MODEL §5 exists to reject. Cost: 1–2 days including embed-on-ingest plumbing; local model (Reflect/Smart-Connections pattern) keeps it API-free; ~12MB storage; note that at 8K sections brute-force cosine is <10ms — **no FAISS/HNSW ever needed below ~1M sections**, so "ANN index" should leave the vocabulary. Without it: recall depends on the LLM issuing good keyword probes — and every MIKAI consumer *is* an LLM, which is why this substitute works here and wouldn't in mem.ai.

## 4. Recommendation

**Path 2 now + FTS5 next + vectors deferred.**

Load-bearing reason: MIKAI's retrieval consumer is always an LLM that can iterate — the Karpathy/Claude-Projects lesson — so the binding constraint is not semantic recall but *ranked candidate selection*: giving the model the right 10 sections instead of 300. FTS5 is the cheapest layer that fixes that, it's the floor every comparable local tool ships (Anytype, Logseq, Omnisearch), and its index is disposable — zero substrate risk. Vectors are the only layer with real ongoing plumbing (embed-on-ingest), and their marginal value today is covered by LLM probe iteration.

Cost accepted, explicitly: some "who's she" paraphrase queries will miss when the LLM probes badly, and those misses are silent. We are also accepting that query-time entity resolution keeps degrading until vectors land.

## 5. What changes the answer

Three concrete triggers, any one of which promotes vectors from deferred to next: (1) **the ontology/dream pass starts doing entity resolution across the whole corpus nightly** — at that point the LLM re-reads candidate sections every night to resolve names, and a one-time embedding per section becomes strictly cheaper than repeated reads; (2) **MCP transcript review shows probe-miss failures** — Claude issuing 4+ grep/FTS probes and still answering "not found" for content that exists under different wording; (3) **corpus passes ~100MB / 30K sections**, where mention-count per keyword makes even BM25 top-10 mostly noise and semantic clustering starts paying. Conversely, nothing on the horizon reprioritizes FTS5 downward — grep stays fast to 500MB+, but ranking is a triage problem, not a speed problem, and it exists today.
