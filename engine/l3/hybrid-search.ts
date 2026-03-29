/**
 * engine/l3/hybrid-search.ts
 * Hybrid search: Vector + BM25 + RRF + BFS expansion.
 * Graphiti-inspired retrieval pipeline on SQLite + sqlite-vec + FTS5.
 */

import type Database from 'better-sqlite3';
import type { NodeRow, SegmentRow, EdgeRow } from '../../lib/store-sqlite.js';
import type { SearchResult, HybridSearchConfig } from './types.js';
import { DEFAULT_HYBRID_CONFIG } from './types.js';

// ── Helper ────────────────────────────────────────────────────────────────────

function toVec(embedding: number[]): Buffer {
  return Buffer.from(new Float32Array(embedding).buffer);
}

// ── RRF ───────────────────────────────────────────────────────────────────────

/**
 * Reciprocal Rank Fusion. k=1 matches Graphiti's default.
 */
export function rrf(rankedLists: string[][], k: number = 1): Map<string, number> {
  const scores = new Map<string, number>();
  for (const list of rankedLists) {
    for (let i = 0; i < list.length; i++) {
      scores.set(list[i], (scores.get(list[i]) ?? 0) + 1 / (i + k));
    }
  }
  return scores;
}

// ── BM25 (FTS5) ───────────────────────────────────────────────────────────────

/**
 * BM25 search over nodes via FTS5. FTS5 rank is negative; more negative = better.
 * Returns node IDs ordered by relevance.
 */
export function bm25SearchNodes(db: Database.Database, query: string, limit: number): string[] {
  try {
    const rows = db.prepare(`
      SELECT node_id, rank FROM fts_nodes
      WHERE fts_nodes MATCH ?
      ORDER BY rank
      LIMIT ?
    `).all(query, limit) as { node_id: string; rank: number }[];
    return rows.map(r => r.node_id);
  } catch {
    return [];
  }
}

/**
 * BM25 search over segments via FTS5.
 */
export function bm25SearchSegments(db: Database.Database, query: string, limit: number): string[] {
  try {
    const rows = db.prepare(`
      SELECT segment_id, rank FROM fts_segments
      WHERE fts_segments MATCH ?
      ORDER BY rank
      LIMIT ?
    `).all(query, limit) as { segment_id: string; rank: number }[];
    return rows.map(r => r.segment_id);
  } catch {
    return [];
  }
}

/**
 * BM25 search over edges via FTS5.
 */
export function bm25SearchEdges(db: Database.Database, query: string, limit: number): string[] {
  try {
    const rows = db.prepare(`
      SELECT edge_id, rank FROM fts_edges
      WHERE fts_edges MATCH ?
      ORDER BY rank
      LIMIT ?
    `).all(query, limit) as { edge_id: string; rank: number }[];
    return rows.map(r => r.edge_id);
  } catch {
    return [];
  }
}

// ── BFS Expansion ─────────────────────────────────────────────────────────────

export function bfsExpand(
  db: Database.Database,
  seedNodeIds: string[],
  maxDepth: number = 1,
  filterExpired: boolean = true,
): { nodeIds: string[]; edges: EdgeRow[] } {
  const visited = new Set<string>(seedNodeIds);
  const allEdges: EdgeRow[] = [];
  let frontier = [...seedNodeIds];

  for (let depth = 0; depth < maxDepth && frontier.length > 0; depth++) {
    const placeholders = frontier.map(() => '?').join(',');
    let sql = `SELECT * FROM edges WHERE from_node IN (${placeholders}) OR to_node IN (${placeholders})`;
    if (filterExpired) sql += ' AND expired_at IS NULL';

    const edges = db.prepare(sql).all(...frontier, ...frontier) as EdgeRow[];
    const newFrontier: string[] = [];

    for (const edge of edges) {
      allEdges.push(edge);
      for (const nodeId of [edge.from_node, edge.to_node]) {
        if (!visited.has(nodeId)) {
          visited.add(nodeId);
          newFrontier.push(nodeId);
        }
      }
    }
    frontier = newFrontier;
  }

  return { nodeIds: [...visited], edges: allEdges };
}

// ── Hybrid Node Search ────────────────────────────────────────────────────────

export function searchNodesHybrid(
  db: Database.Database,
  query: string,
  embedding: number[],
  limit: number,
): SearchResult<NodeRow>[] {
  // Vector search
  let vectorIds: string[] = [];
  try {
    const vecResults = db.prepare(`
      SELECT node_id, distance FROM vec_nodes
      WHERE embedding MATCH ? AND k = ?
      ORDER BY distance
    `).all(toVec(embedding), limit) as { node_id: string; distance: number }[];
    vectorIds = vecResults.map(r => r.node_id);
  } catch {
    // vec table may not exist yet
  }

  // BM25 search
  const bm25Ids = bm25SearchNodes(db, query, limit);

  // Merge via RRF
  const rrfScores = rrf([vectorIds, bm25Ids]);

  if (rrfScores.size === 0) return [];

  const allIds = [...rrfScores.keys()];
  const placeholders = allIds.map(() => '?').join(',');
  const nodes = db.prepare(`SELECT * FROM nodes WHERE id IN (${placeholders})`).all(...allIds) as NodeRow[];

  return nodes.map(node => ({
    item: { ...node, has_action_verb: Boolean(node.has_action_verb) } as NodeRow,
    score: rrfScores.get(node.id) ?? 0,
    source: (vectorIds.includes(node.id) && bm25Ids.includes(node.id)
      ? 'vector'
      : vectorIds.includes(node.id)
        ? 'vector'
        : 'bm25') as 'vector' | 'bm25',
  })).sort((a, b) => b.score - a.score);
}

// ── Hybrid Segment Search ─────────────────────────────────────────────────────

export function searchSegmentsHybrid(
  db: Database.Database,
  query: string,
  embedding: number[],
  limit: number,
): SearchResult<SegmentRow>[] {
  // Vector search
  let vectorIds: string[] = [];
  try {
    const vecResults = db.prepare(`
      SELECT segment_id, distance FROM vec_segments
      WHERE embedding MATCH ? AND k = ?
      ORDER BY distance
    `).all(toVec(embedding), limit) as { segment_id: string; distance: number }[];
    vectorIds = vecResults.map(r => r.segment_id);
  } catch {
    // vec table may not exist yet
  }

  // BM25 search
  const bm25Ids = bm25SearchSegments(db, query, limit);

  // Merge via RRF
  const rrfScores = rrf([vectorIds, bm25Ids]);

  if (rrfScores.size === 0) return [];

  const allIds = [...rrfScores.keys()];
  const placeholders = allIds.map(() => '?').join(',');
  const segments = db.prepare(`
    SELECT s.*, src.label as source_label, src.type as source_type, src.source as source_origin
    FROM segments s
    LEFT JOIN sources src ON s.source_id = src.id
    WHERE s.id IN (${placeholders})
  `).all(...allIds) as SegmentRow[];

  return segments.map(seg => ({
    item: seg,
    score: rrfScores.get(seg.id) ?? 0,
    source: (vectorIds.includes(seg.id) ? 'vector' : 'bm25') as 'vector' | 'bm25',
  })).sort((a, b) => b.score - a.score);
}

// ── Full Hybrid Graph Search ──────────────────────────────────────────────────

export function hybridGraphSearch(
  db: Database.Database,
  query: string,
  embedding: number[],
  opts?: Partial<HybridSearchConfig>,
): { nodes: NodeRow[]; edges: EdgeRow[]; seeds: string[] } {
  const config: HybridSearchConfig = { ...DEFAULT_HYBRID_CONFIG, ...opts };

  // Step 1: Hybrid node search
  const hybridResults = searchNodesHybrid(db, query, embedding, config.limit * 2);

  if (hybridResults.length === 0) {
    return { nodes: [], edges: [], seeds: [] };
  }

  // Step 2: Top 5 seeds by RRF score
  const seeds = hybridResults.slice(0, 5).map(r => r.item.id);

  // Step 3: BFS expansion
  const { nodeIds: expandedIds, edges } = bfsExpand(
    db,
    seeds,
    config.bfsMaxDepth,
    config.filterExpired,
  );

  // Step 4: Fetch full node data for all expanded nodes
  const allNodeIds = expandedIds.slice(0, config.limit);
  if (allNodeIds.length === 0) {
    return { nodes: [], edges: [], seeds };
  }

  const placeholders = allNodeIds.map(() => '?').join(',');
  const nodes = db.prepare(`SELECT * FROM nodes WHERE id IN (${placeholders})`).all(...allNodeIds) as NodeRow[];

  // Step 5: Fetch edges between all nodes (dedup from BFS edges)
  const nodeIdSet = new Set(allNodeIds);
  const filteredEdges = edges.filter(
    e => nodeIdSet.has(e.from_node) && nodeIdSet.has(e.to_node),
  );

  return {
    nodes: nodes.map(n => ({ ...n, has_action_verb: Boolean(n.has_action_verb) } as NodeRow)),
    edges: filteredEdges,
    seeds,
  };
}
