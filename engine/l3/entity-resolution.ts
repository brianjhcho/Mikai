/**
 * engine/l3/entity-resolution.ts
 *
 * Graphiti entity resolution — the missing Phase 2 capability.
 *
 * After extraction, each source's nodes exist in isolation. Entity resolution
 * searches the existing graph for semantically equivalent entities from OTHER
 * sources and creates cross-source edges.
 *
 * This is the mechanism that makes the graph source-agnostic: whether a user
 * writes one mega-note with 1200 ideas or 120 small notes, the resulting graph
 * converges to the same structure because entity resolution links equivalent
 * concepts across extraction boundaries.
 *
 * Algorithm (following Graphiti's pattern):
 *   1. For each unresolved node, search existing graph (vec kNN + BM25 + RRF)
 *   2. Filter candidates to cross-source matches only
 *   3. Score matches and create typed edges above threshold
 *   4. Track resolved nodes to avoid redundant work
 *
 * Zero LLM (V1). Uses pre-computed embeddings + FTS5 for matching.
 * V2: Add Haiku disambiguation for ambiguous matches.
 */

import type Database from 'better-sqlite3';
import { randomUUID } from 'crypto';
import { rrf, bm25SearchNodes } from './hybrid-search.js';

// ── Configuration ────────────────────────────────────────────────────────────

const STRONG_MATCH_SCORE = 1.2;   // RRF score threshold for strong entity match
const WEAK_MATCH_SCORE = 0.7;     // RRF score threshold for weak entity match
const KNN_K = 10;                 // neighbors to check per entity
const BM25_K = 10;                // BM25 candidates per entity
const MAX_EDGES_PER_NODE = 3;     // cap cross-source edges per node (avoid fan-out)
const BATCH_LOG_INTERVAL = 100;   // log progress every N nodes

// ── Types ────────────────────────────────────────────────────────────────────

interface NodeInfo {
  id: string;
  source_id: string;
  source_type: string;
  label: string;
  content: string;
  node_type: string;
  created_at: string;
}

interface CandidateMatch {
  node: NodeInfo;
  rrfScore: number;
  vecSimilarity: number;
}

export interface ResolutionResult {
  nodesProcessed: number;
  edgesCreated: number;
  strongMatches: number;
  weakMatches: number;
  skippedAlreadyResolved: number;
  durationMs: number;
}

// ── Relationship inference ───────────────────────────────────────────────────

/**
 * Infer the appropriate edge relationship type from node types.
 * Uses the existing L3 edge vocabulary so classification signals work.
 */
function inferRelationship(
  sourceType: string,
  targetType: string,
  isStrong: boolean,
): string {
  // question/tension matched by concept/decision → partially_answers
  if (
    (sourceType === 'question' || sourceType === 'tension') &&
    (targetType === 'concept' || targetType === 'decision')
  ) {
    return 'partially_answers';
  }

  // concept/decision answering a question/tension → partially_answers
  if (
    (sourceType === 'concept' || sourceType === 'decision') &&
    (targetType === 'question' || targetType === 'tension')
  ) {
    return 'partially_answers';
  }

  // project related to concept/decision → depends_on
  if (sourceType === 'project' && (targetType === 'concept' || targetType === 'decision')) {
    return 'depends_on';
  }

  // tension ↔ tension across sources → supports (validates the tension exists)
  if (sourceType === 'tension' && targetType === 'tension') {
    return 'supports';
  }

  // Default: extends (the most general cross-source relationship)
  return isStrong ? 'supports' : 'extends';
}

// ── Core resolution ──────────────────────────────────────────────────────────

/**
 * Find candidate entity matches for a given node using hybrid search.
 * Returns candidates from DIFFERENT sources only, ranked by RRF score.
 */
function findCandidates(
  db: Database.Database,
  node: NodeInfo,
  sourceIdMap: Map<string, string>, // nodeId → sourceId
  sourceTypeMap: Map<string, string>, // nodeId → sourceType
): CandidateMatch[] {
  // 1. kNN on vec_nodes (cross-space search using stored embedding)
  let vecRanking: string[] = [];
  const vecDistances = new Map<string, number>();

  try {
    const vecResults = db.prepare(`
      SELECT node_id, distance FROM vec_nodes
      WHERE embedding MATCH (SELECT embedding FROM vec_nodes WHERE node_id = ?)
        AND k = ?
      ORDER BY distance
    `).all(node.id, KNN_K + 1) as { node_id: string; distance: number }[];

    for (const r of vecResults) {
      if (r.node_id === node.id) continue;
      vecRanking.push(r.node_id);
      vecDistances.set(r.node_id, r.distance);
    }
  } catch {
    // Node not in vec table, skip kNN
  }

  // 2. BM25 on fts_nodes using label as query
  // Clean label for FTS5 query (escape special chars)
  const ftsQuery = node.label
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const bm25Ranking = ftsQuery.length >= 3 ? bm25SearchNodes(db, ftsQuery, BM25_K) : [];

  // 3. RRF merge
  const rrfScores = rrf([vecRanking, bm25Ranking]);

  if (rrfScores.size === 0) return [];

  // 4. Filter to cross-source only and build candidates
  const candidates: CandidateMatch[] = [];

  for (const [candidateId, score] of rrfScores) {
    const candidateSourceId = sourceIdMap.get(candidateId);
    if (!candidateSourceId) continue;

    // Must be from a different source document
    if (candidateSourceId === node.source_id) continue;

    // Retrieve candidate node info
    const candidateNode = db.prepare(
      'SELECT id, source_id, label, content, node_type, created_at FROM nodes WHERE id = ?'
    ).get(candidateId) as NodeInfo | undefined;

    if (!candidateNode) continue;

    const candidateSourceType = sourceTypeMap.get(candidateId) ?? '';
    candidateNode.source_type = candidateSourceType;

    candidates.push({
      node: candidateNode,
      rrfScore: score,
      vecSimilarity: 1 - (vecDistances.get(candidateId) ?? 1),
    });
  }

  // Sort by RRF score descending, cap at MAX_EDGES_PER_NODE
  return candidates
    .sort((a, b) => b.rrfScore - a.rrfScore)
    .slice(0, MAX_EDGES_PER_NODE);
}

/**
 * Check if a cross-source edge already exists between two nodes.
 */
function edgeExists(db: Database.Database, fromNode: string, toNode: string): boolean {
  const row = db.prepare(`
    SELECT 1 FROM edges
    WHERE (from_node = ? AND to_node = ?) OR (from_node = ? AND to_node = ?)
    LIMIT 1
  `).get(fromNode, toNode, toNode, fromNode);
  return row !== undefined;
}

// ── Main entry point ─────────────────────────────────────────────────────────

/**
 * Run entity resolution across the entire graph.
 * Creates cross-source edges between semantically equivalent entities.
 *
 * Idempotent: checks for existing edges before creating new ones.
 * Can be run incrementally (only processes nodes not yet resolved).
 */
export async function resolveEntities(
  db: Database.Database,
  opts?: { forceAll?: boolean; sourceTypes?: string[] },
): Promise<ResolutionResult> {
  const startMs = Date.now();
  const forceAll = opts?.forceAll ?? false;

  // ── 1. Pre-load source mappings ──────────────────────────────────────────
  const sourceIdMap = new Map<string, string>();   // nodeId → sourceId
  const sourceTypeMap = new Map<string, string>(); // nodeId → sourceType

  const allNodes = db.prepare(`
    SELECT n.id, n.source_id, src.source as source_type
    FROM nodes n
    LEFT JOIN sources src ON n.source_id = src.id
  `).all() as { id: string; source_id: string; source_type: string }[];

  for (const n of allNodes) {
    sourceIdMap.set(n.id, n.source_id);
    sourceTypeMap.set(n.id, n.source_type ?? '');
  }

  // ── 2. Find nodes to resolve ─────────────────────────────────────────────
  // "Unresolved" = nodes that don't yet have any cross-source edges
  let nodesToResolve: NodeInfo[];

  const sourceFilter = opts?.sourceTypes
    ? `AND src.source IN (${opts.sourceTypes.map(() => '?').join(',')})`
    : '';
  const sourceFilterParams = opts?.sourceTypes ?? [];

  if (forceAll) {
    nodesToResolve = db.prepare(`
      SELECT n.id, n.source_id, n.label, n.content, n.node_type, n.created_at,
             src.source as source_type
      FROM nodes n
      LEFT JOIN sources src ON n.source_id = src.id
      WHERE n.label IS NOT NULL AND LENGTH(n.label) > 3
        AND n.content IS NOT NULL AND LENGTH(n.content) > 10
        ${sourceFilter}
      ORDER BY n.created_at DESC
    `).all(...sourceFilterParams) as NodeInfo[];
  } else {
    // Only nodes without cross-source edges
    nodesToResolve = db.prepare(`
      SELECT n.id, n.source_id, n.label, n.content, n.node_type, n.created_at,
             src.source as source_type
      FROM nodes n
      LEFT JOIN sources src ON n.source_id = src.id
      WHERE n.label IS NOT NULL AND LENGTH(n.label) > 3
        AND n.content IS NOT NULL AND LENGTH(n.content) > 10
        ${sourceFilter}
        AND n.id NOT IN (
          SELECT e.from_node FROM edges e
          JOIN nodes n1 ON e.from_node = n1.id
          JOIN nodes n2 ON e.to_node = n2.id
          WHERE n1.source_id != n2.source_id
          UNION
          SELECT e.to_node FROM edges e
          JOIN nodes n1 ON e.from_node = n1.id
          JOIN nodes n2 ON e.to_node = n2.id
          WHERE n1.source_id != n2.source_id
        )
      ORDER BY n.created_at DESC
    `).all(...sourceFilterParams) as NodeInfo[];
  }

  process.stderr.write(`Entity resolution: ${nodesToResolve.length} nodes to process\n`);

  // ── 3. Resolve each node ─────────────────────────────────────────────────
  let edgesCreated = 0;
  let strongMatches = 0;
  let weakMatches = 0;
  let skipped = 0;

  const insertEdge = db.prepare(`
    INSERT INTO edges (id, from_node, to_node, relationship, note, weight, fact, valid_at, episodes)
    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
  `);

  for (let i = 0; i < nodesToResolve.length; i++) {
    const node = nodesToResolve[i];

    // Progress logging
    if (i > 0 && i % BATCH_LOG_INTERVAL === 0) {
      process.stderr.write(`  ...resolved ${i}/${nodesToResolve.length} (${edgesCreated} edges created)\n`);
    }

    const candidates = findCandidates(db, node, sourceIdMap, sourceTypeMap);

    for (const candidate of candidates) {
      // Skip if edge already exists (idempotent)
      if (edgeExists(db, node.id, candidate.node.id)) {
        skipped++;
        continue;
      }

      const isStrong = candidate.rrfScore >= STRONG_MATCH_SCORE;
      const isWeak = candidate.rrfScore >= WEAK_MATCH_SCORE;

      if (!isWeak) continue;

      const relationship = inferRelationship(
        node.node_type,
        candidate.node.node_type,
        isStrong,
      );

      const note = `Entity resolution: ${node.source_type} ↔ ${candidate.node.source_type} (RRF=${candidate.rrfScore.toFixed(2)}, vec=${candidate.vecSimilarity.toFixed(3)})`;
      const weight = isStrong ? 0.8 : 0.5;
      const fact = `"${node.label}" relates to "${candidate.node.label}"`;
      const episodes = JSON.stringify([node.source_id, candidate.node.source_id].filter(Boolean));

      insertEdge.run(
        randomUUID(),
        node.id,
        candidate.node.id,
        relationship,
        note,
        weight,
        fact,
        episodes,
      );

      edgesCreated++;
      if (isStrong) strongMatches++;
      else weakMatches++;
    }
  }

  const durationMs = Date.now() - startMs;

  process.stderr.write(
    `Entity resolution complete: ${edgesCreated} edges created ` +
    `(${strongMatches} strong, ${weakMatches} weak) in ${(durationMs / 1000).toFixed(1)}s\n`
  );

  return {
    nodesProcessed: nodesToResolve.length,
    edgesCreated,
    strongMatches,
    weakMatches,
    skippedAlreadyResolved: skipped,
    durationMs,
  };
}

// ── CLI entry point ──────────────────────────────────────────────────────────

export async function runEntityResolution(db: Database.Database): Promise<ResolutionResult> {
  return resolveEntities(db, { forceAll: false });
}
