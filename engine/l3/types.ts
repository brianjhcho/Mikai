/**
 * engine/l3/types.ts
 * L3 Graphiti-inspired upgrade types.
 */

import type { EdgeRow, NodeRow, SegmentRow } from '../../lib/store-sqlite.js';

export interface BiTemporalEdge extends EdgeRow {
  fact: string | null;
  fact_embedding: Buffer | null;
  valid_at: string | null;
  invalid_at: string | null;
  expired_at: string | null;
  episodes: string; // JSON array of source_ids
}

export type SearchSource = 'vector' | 'bm25' | 'bfs';

export interface SearchResult<T = NodeRow | SegmentRow> {
  item: T;
  score: number;
  source: SearchSource;
}

export interface HybridSearchConfig {
  vectorWeight: number;   // default 0.6
  bm25Weight: number;     // default 0.4
  bfsMaxDepth: number;    // default 1
  limit: number;          // default 15
  filterExpired: boolean; // default true
}

export const DEFAULT_HYBRID_CONFIG: HybridSearchConfig = {
  vectorWeight: 0.6,
  bm25Weight: 0.4,
  bfsMaxDepth: 1,
  limit: 15,
  filterExpired: true,
};

// ── Community Detection (Graphiti Phase 2B — DEFERRED) ──────────────────────
// Label propagation communities deferred until cross-source edges > 5,000.
// Current gap (multi-hop transitivity) is solved in L4 detect-threads.ts.
// See O-040 in docs/OPEN_QUESTIONS.md for full analysis.
