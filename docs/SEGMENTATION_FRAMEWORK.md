# Segmentation Framework: Source-Adaptive Normalization for Cross-App Thread Detection

**Created:** 2026-03-29
**Purpose:** Define how MIKAI normalizes heterogeneous data sources into segments of comparable information density, enabling the cross-app thread detection that L4 requires.
**Problem:** L4 detected 1,640 threads but 99.3% are single-source because gmail (50 segments), apple-notes (123), and imessage (~6) are drastically under-segmented compared to perplexity (14,946) and claude-thread (4,705).

---

## Root Causes

Three compounding failures prevent cross-app detection:

1. **Source exclusion** (`build-segments.js:53`): Gmail and iMessage are excluded from the default `ALLOWED_SOURCES` allowlist.
2. **Global word threshold** (`build-segments.js:177`): A 500-word minimum kills 75% of gmail (264 of 461 sources are <500 words) and 100% of Apple Notes (largest note is 122 words).
3. **No source-adaptive splitters**: `smart-split.js` has no `splitGmail()` or `splitIMessage()` — they fall through to `splitGeneric()`, which was designed for long documents.

---

## How Comparable Systems Solve This

### Pattern 1: Canonical Schema Per Source Type (Celonis / OCEL 2.0)

Celonis normalizes SAP, Salesforce, ServiceNow, and Jira into a canonical event format:

```
{ case_id, activity, timestamp, resource }
```

A 3-field SAP transaction and a 50-field Salesforce opportunity both become valid events. There is **no minimum content threshold** — the value is in the link to other events in the same case, not in the content volume.

Each source type gets its own **connector template** — pre-written SQL transformations that map source-specific fields into the canonical schema. The transformation is source-aware; the downstream analytics are source-agnostic.

**OCEL 2.0** (the open standard) goes further: each object type gets its own typed table with type-specific attributes, connected by qualified relationship tables (`ocel_qualifier`: "resolved_by", "triggered_by").

**MIKAI takeaway:** Segments should be the canonical unit. Each source type needs its own adapter (splitter + metadata enricher) that produces segments of comparable *information density*, not comparable *length*.

### Pattern 2: Metadata Enrichment Before Embedding (Anthropic Contextual Retrieval)

Anthropic's Contextual Retrieval (September 2024) showed that prepending a 50-100 token context summary before embedding reduces retrieval failure by **49%**. Combined with BM25, failure drops by **67%**.

The pattern: before embedding any chunk, generate or prepend structured metadata that situates the content:

```
[Email] From: booking@kenyaairways.com | Subject: Flight confirmation | Date: 2026-03-15
Your flight from Toronto to Nairobi is confirmed. Reference: KQ-7382.
```

This transforms a 20-word email into an embedding-rich chunk where the metadata carries the semantic signal needed for cross-source matching.

**Embedding size bias** (Jina AI, 2024): Short texts cluster in a different region of embedding space than long texts about the same topic. Cosine similarity thresholds cannot be applied uniformly across mixed-length inputs. Metadata enrichment brings short texts up to ~100+ tokens, substantially reducing this bias.

**MIKAI takeaway:** Every segment, regardless of source, should have metadata prepended before embedding. This is the single highest-impact change for enabling cross-source thread detection.

### Pattern 3: Aggregate Upward, Never Discard (Glean, Dust, Rewind)

Across every system surveyed, the pattern for below-threshold content is consistent: **aggregate upward, don't discard**.

| System | Short content | Aggregation strategy |
|--------|-------------|---------------------|
| Glean | Slack messages | Aggregate into conversation window (5-10 messages = 1 chunk) |
| Dust.tt | Orphan Notion pages | Flagged but retained |
| Rewind | Quick app switches (empty OCR) | Stored as-is, never matches search |
| Linear | Short issue comments | Attached to parent issue |
| RSS/Atom | Empty `<content>` | Fall back to `<description>` |

No system drops content because it's short. The unit of retrieval adapts to the content.

**MIKAI takeaway:** Apple Notes at 50-120 words should become segments as-is, not be discarded for being <500 words. Individual iMessages should aggregate into conversation windows, not a single mega-document.

### Pattern 4: Three Cross-Source Linking Mechanisms

Research identified three distinct approaches to cross-source linking:

1. **Hub-and-spoke** (Linear): One canonical entity type (Issue) aggregates all external references (PR, Slack thread, design doc). Sources attach to the hub, not to each other.

2. **Identity graph resolution** (Glean): Resolve the same person across systems via email/username alias mapping. This is a *prerequisite* for meaningful cross-source linking — "Brian" in iMessage, "briancho@gmail.com" in Gmail, and the user in Claude threads are the same actor.

3. **Structural normalization** (Activity Streams 2.0 / W3C): Every event maps to `Actor → Verb → Object → Target`. A Slack message, email send, and file edit all become Activity objects with the same schema.

**MIKAI currently uses only embedding similarity** for cross-source linking. This is necessary but insufficient. The research suggests adding:
- Metadata-based linking (temporal proximity + participant overlap)
- Entity resolution (same person across sources)
- Activity normalization (action verbs extracted at sync time already exist — use them as linking signal)

### Pattern 5: Multi-Scale Indexing (AI21, 2025-2026)

Current best practice for heterogeneous corpora is multi-scale indexing:
- Index at 128, 256, and 512 token granularities simultaneously
- Each retrieved chunk votes for its parent document
- RRF aggregates votes across scales (rank-based, not score-based)
- Benchmarks show 1-37% recall improvement over single-scale

**MIKAI takeaway:** Consider indexing segments at multiple granularities, especially for sources like Perplexity (naturally large) vs Apple Notes (naturally small). RRF already exists in `hybrid-search.ts` — extend it to multi-scale.

---

## The Framework: Source-Adaptive Segment Strategy

### Canonical Segment Schema

Every segment, regardless of source, produces:

```typescript
interface CanonicalSegment {
  // Identity
  source_id: string;
  source_type: 'perplexity' | 'claude-thread' | 'manual' | 'gmail' | 'apple-notes' | 'imessage';

  // Content (what gets embedded)
  topic_label: string;                    // human-readable label
  enriched_content: string;               // metadata prefix + processed content
  processed_content: string;              // raw content without metadata (for display)

  // Metadata (structural signal for thread detection)
  participants?: string[];                // people involved (anonymized for imessage)
  action_verbs?: string[];                // extracted action verbs (already exist in sync scripts)
  temporal_anchor: string;                // ISO timestamp
  information_type: 'research' | 'reflection' | 'transaction' | 'conversation' | 'action';
}
```

The `enriched_content` field is what gets embedded. The `processed_content` is what gets displayed. Metadata enrichment happens at segmentation time, not at retrieval time.

### Per-Source Adapter Configuration

| Source | Min Words | Splitter | Enrichment Prefix | Information Type |
|--------|----------|---------|-------------------|-----------------|
| perplexity | 30 | `splitPerplexityThread` (existing) | `[Research] Query: {topic_label} \| Source: Perplexity \| Date: {date}` | research |
| claude-thread | 15 | `splitClaudeThread` (existing) | `[Conversation] Topic: {topic_label} \| Source: Claude \| Date: {date}` | research |
| manual | 20 | `splitMarkdown` (existing) | `[Document] Title: {source_label} \| Date: {date}` | reflection |
| **gmail** | **15** | **`splitGmail` (NEW)** | `[Email] Subject: {subject} \| From: {from} \| To: {to} \| Date: {date}` | transaction |
| **apple-notes** | **10** | **`splitAppleNote` (NEW)** | `[Note] Title: {source_label} \| Date: {date}` | reflection |
| **imessage** | **20** | **`splitIMessage` (NEW)** | `[Message] Participants: {contacts} \| Date: {date}` | conversation |

### Splitter Designs

#### `splitGmail` — One Email = One Segment

Emails are atomic units. Don't split them — enrich them.

```
Strategy:
1. Parse subject, from, to, date from email content/metadata
2. Clean HTML artifacts (already done by cleanContent)
3. If word count >= 15: emit as single segment with metadata prefix
4. If word count < 15: skip (truly empty emails like "OK" or "Thanks")
5. Topic label = email subject line (already stored in source.label)
```

Why 15 words, not 500: A gmail "Your Kenya Airways flight is confirmed. Departure April 2. Reference KQ-7382." is 14 words but contains the behavioral signal that links to the "Kenya trip research" thread in Perplexity. The metadata prefix ("Subject: Flight confirmation | From: booking@kenyaairways.com") carries the embedding signal.

#### `splitAppleNote` — One Note = One Segment

Notes are reflective fragments. They're short by nature.

```
Strategy:
1. Clean the note (strip HTML, normalize whitespace)
2. If word count >= 10: emit as single segment with metadata prefix
3. If word count < 10: skip (truly empty notes)
4. Topic label = first sentence or first 60 characters
```

Why 10 words: Apple Notes in this corpus average 50-120 words. The current 500-word threshold eliminates 100% of them. At 10 words, only trivially empty notes get skipped.

#### `splitIMessage` — Conversation Windows, Not Mega-Document

The current approach groups ALL messages into one document per sync run. This loses conversation structure.

```
Strategy:
1. Parse individual messages from the grouped content
2. Group by conversation thread (same contact/group)
3. Within each conversation, create time-windowed segments:
   - Messages within 2 hours of each other = one segment
   - Gap > 2 hours = new segment
4. Minimum 2 messages per segment (skip isolated "ok" messages)
5. Metadata prefix includes participant names (anonymized)
6. Topic label = first substantive message in the window
```

Why conversation windows: "Should I book the Kenya flights tonight?" / "Yes, the price went up" is one conversation segment. It links to the Perplexity research thread through embedding similarity AND through the metadata ("Kenya flights").

### Threshold Rationale (Informed by Research)

| Threshold | Rationale | Research basis |
|-----------|-----------|---------------|
| No global 500-word minimum | Discards 100% of notes, 75% of emails | Every system surveyed aggregates upward, never discards |
| Per-source minimums (10-30 words) | Filters only truly empty content | Rewind stores even empty OCR segments; Glean indexes single Slack messages |
| Metadata prefix (50-100 tokens) | Enriches short text for embedding quality | Anthropic Contextual Retrieval: 49% failure reduction |
| Source-type in prefix | Helps embedding distinguish content modality | LlamaIndex: per-type parser matrix; Jina: size bias mitigation |

---

## Impact on Thread Detection

### Current State (broken)
```
Thread detection input: 14,946 perplexity + 5,997 manual + 4,705 claude + 50 gmail + 123 notes + ~6 imessage
Cross-source ratio:     14,946 : 50 = 299:1 (perplexity dominates, gmail invisible)
Cross-app threads:      4 / 1,640 = 0.2%
```

### Expected After Fix
```
Thread detection input: 14,946 perplexity + 5,997 manual + 4,705 claude + ~350 gmail + ~75 notes + ~50 imessage
Cross-source ratio:     14,946 : 350 = 43:1 (still perplexity-heavy, but gmail visible)
Cross-app opportunity:  A Remitly transfer email + Kenya travel research in Perplexity + Apple Note about trip planning
```

The metadata enrichment is key: "Kenya" in a gmail subject line + "Kenya Airways" in Perplexity + "Kenya trip" in an Apple Note should cluster when all three have metadata-enriched embeddings carrying the topic signal.

### Changes Needed to `detect-threads.ts`

The cross-source bonus (`CROSS_SOURCE_BONUS = 0.08`, lowering threshold from 0.72 to 0.64) may need adjustment after metadata enrichment changes the embedding landscape. Consider:

1. **Increase cross-source bonus to 0.12-0.15** — metadata-enriched segments from different sources should match more easily
2. **Add metadata-based linking as a secondary signal** — if two segments share a participant name or temporal proximity (<24h), lower the similarity threshold further
3. **Consider the information type** — a `transaction` segment (gmail confirmation) linking to a `research` segment (Perplexity search) is a strong cross-app signal

---

## Implementation Order

1. **Add `splitGmail`, `splitAppleNote`, `splitIMessage` to `smart-split.js`** — new splitters with metadata enrichment
2. **Update `build-segments.js`** — add gmail/imessage to ALLOWED_SOURCES, replace global 500-word threshold with per-source thresholds
3. **Re-run `build-segments` with new sources** — generate segments for gmail/notes/imessage
4. **Re-run `supabase-to-sqlite`** — sync new segments to SQLite
5. **Re-run L4 pipeline** — see if cross-app threads emerge
6. **Evaluate** — measure cross-source thread ratio, check thread quality

---

## Research Sources

### Process Mining & Event Normalization
- Celonis OCPM database tables — docs.celonis.com
- OCEL 2.0 specification — ocel-standard.org
- PM4Py event log normalization — pm4py.fit.fraunhofer.de
- Dirigo extraction pipeline — arXiv:2411.07490

### Enterprise Search & Multi-Source RAG
- Anthropic Contextual Retrieval (September 2024) — anthropic.com/news/contextual-retrieval
- Jina AI size bias in embeddings (2024) — jina.ai
- Adaptive Chunking — arXiv:2603.25333
- LLM text enrichment for embeddings — arXiv:2404.12283
- Cosine similarity critique — arXiv:2403.05440
- AI21 query-dependent chunking — ai21.com/blog

### Platform Architectures
- Glean RAG enterprise search — glean.com/perspectives
- Dust.tt filesystem navigation — dust.tt/blog
- Linear API data model — linear.app/docs
- Notion block data model — notion.com/blog
- Rewind app teardown — kevinchen.co/blog

### Standards
- W3C Activity Streams 2.0 — w3.org/TR/activitystreams-core
- RFC 5256 IMAP THREAD — rfc-editor.org
- JWZ threading algorithm — jwz.org/doc/threading.html

### Memory Systems
- Graphiti/Zep temporal knowledge graph — arXiv:2501.13956
- Mem0 four-tier memory — arXiv:2504.19413
- Microsoft GraphRAG default dataflow — microsoft.github.io/graphrag

---

*This document supersedes the implicit "one size fits all" segmentation approach. The 500-word global threshold was appropriate for Phase 3 (perplexity + manual + claude-thread). For Phase 4+ (cross-app thread detection), source-adaptive normalization is required.*
