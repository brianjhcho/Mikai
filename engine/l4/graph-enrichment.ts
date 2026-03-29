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
  };

  if (memberNodeIds.length < 2) return empty;

  // Query edges where both endpoints are within this thread's members
  const placeholders = memberNodeIds.map(() => '?').join(',');
  let edges: { edge_type: string; count: number }[];
  try {
    edges = db.prepare(`
      SELECT edge_type, COUNT(*) as count FROM edges
      WHERE from_node IN (${placeholders}) AND to_node IN (${placeholders})
      GROUP BY edge_type
    `).all(...memberNodeIds, ...memberNodeIds) as { edge_type: string; count: number }[];
  } catch {
    return empty;
  }

  if (edges.length === 0) return empty;

  const edgeTypes = edges.map(e => e.edge_type);
  const totalEdges = edges.reduce((sum, e) => sum + e.count, 0);

  // Confidence boost: graph edges between members = structurally related, not just semantically similar
  // More edges = higher confidence, capped at 0.15
  const graphConfidenceBoost = Math.min(0.15, totalEdges * 0.03);

  return {
    hasEdges: true,
    edgeTypes,
    edgeCount: totalEdges,
    graphConfidenceBoost,
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
