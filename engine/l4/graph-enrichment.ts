/**
 * engine/l4/graph-enrichment.ts
 *
 * Post-clustering graph signal extraction.
 * After Union-Find produces candidate threads from embedding proximity,
 * this module queries L3 edges between member nodes to enrich thread
 * quality and inform state classification.
 *
 * Design: embedding proximity is the foundation (memory-layer agnostic),
 * graph connectivity is the enrichment layer. If L3 is swapped for
 * Graphiti/Cognee, only this file needs to change.
 *
 * Research basis: Hybrid approach from docs/L4_RESEARCH_INTEGRATION.md
 */

import type Database from 'better-sqlite3';
import type { GraphSignals } from './types.js';

// Edge types that signal specific reasoning states
const CONTRADICTION_TYPES = new Set(['contradicts', 'unresolved_tension']);
const DEPENDENCY_TYPES = new Set(['depends_on']);
const SUPPORT_TYPES = new Set(['supports', 'extends', 'partially_answers']);

/**
 * Query L3 edges between a set of node IDs to extract graph-level signals.
 * Returns enrichment data that can boost thread confidence and inform
 * state classification.
 */
export function enrichWithGraphSignals(
  db: Database.Database,
  memberNodeIds: string[],
): GraphSignals {
  const empty: GraphSignals = {
    hasEdges: false,
    edgeTypes: [],
    edgeCount: 0,
    graphConfidenceBoost: 0,
    newestEdgeAt: null,
    oldestEdgeAt: null,
    invalidatedEdgeCount: 0,
    validEdgeCount: 0,
    edgeAgeDays: Infinity,
  };

  if (memberNodeIds.length < 2) return empty;

  // Query edges where both endpoints are within this thread's members
  const placeholders = memberNodeIds.map(() => '?').join(',');
  let edges: { relationship: string; count: number }[];
  try {
    edges = db.prepare(`
      SELECT relationship, COUNT(*) as count FROM edges
      WHERE from_node IN (${placeholders}) AND to_node IN (${placeholders})
      GROUP BY relationship
    `).all(...memberNodeIds, ...memberNodeIds) as { relationship: string; count: number }[];
  } catch {
    return empty;
  }

  if (edges.length === 0) return empty;

  const edgeTypes = edges.map(e => e.relationship);
  const totalEdges = edges.reduce((sum, e) => sum + e.count, 0);

  // Confidence boost: graph edges between members = structurally related, not just semantically similar
  // More edges = higher confidence, capped at 0.15
  const graphConfidenceBoost = Math.min(0.15, totalEdges * 0.03);

  // Temporal signals from edge valid_at / invalid_at
  let temporalStats: {
    newest: string | null; oldest: string | null;
    invalidated: number; valid: number;
  } = { newest: null, oldest: null, invalidated: 0, valid: 0 };

  try {
    const temporal = db.prepare(`
      SELECT
        MAX(valid_at) as newest,
        MIN(valid_at) as oldest,
        SUM(CASE WHEN invalid_at IS NOT NULL THEN 1 ELSE 0 END) as invalidated,
        SUM(CASE WHEN invalid_at IS NULL THEN 1 ELSE 0 END) as valid
      FROM edges
      WHERE from_node IN (${placeholders}) AND to_node IN (${placeholders})
    `).get(...memberNodeIds, ...memberNodeIds) as any;

    if (temporal) {
      temporalStats = {
        newest: temporal.newest,
        oldest: temporal.oldest,
        invalidated: temporal.invalidated ?? 0,
        valid: temporal.valid ?? 0,
      };
    }
  } catch { /* temporal columns may not exist in older DBs */ }

  const now = Date.now();
  const newestTime = temporalStats.newest ? new Date(temporalStats.newest).getTime() : 0;
  const edgeAgeDays = newestTime > 0 ? (now - newestTime) / (1000 * 60 * 60 * 24) : Infinity;

  return {
    hasEdges: true,
    edgeTypes,
    edgeCount: totalEdges,
    graphConfidenceBoost,
    newestEdgeAt: temporalStats.newest,
    oldestEdgeAt: temporalStats.oldest,
    invalidatedEdgeCount: temporalStats.invalidated,
    validEdgeCount: temporalStats.valid,
    edgeAgeDays,
  };
}

/**
 * Extract classification-relevant signals from graph edge types.
 * Used by classify-state.ts to augment rule-based classification.
 */
export function extractGraphClassificationSignals(edgeTypes: string[]): {
  has_contradiction_edges: boolean;
  has_dependency_chain: boolean;
  has_support_chain: boolean;
} {
  return {
    has_contradiction_edges: edgeTypes.some(t => CONTRADICTION_TYPES.has(t)),
    has_dependency_chain: edgeTypes.some(t => DEPENDENCY_TYPES.has(t)),
    has_support_chain: edgeTypes.some(t => SUPPORT_TYPES.has(t)),
  };
}
