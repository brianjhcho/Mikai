/**
 * engine/l3/invalidate-edges.ts
 *
 * Graphiti Phase 3: Edge invalidation — mark contradicted/superseded facts as expired.
 *
 * Zero LLM. Uses existing edge relationships + temporal ordering to detect when
 * a newer thought supersedes an older one. Sets `invalid_at` on the older edge
 * but never deletes — full audit trail preserved (Graphiti pattern).
 *
 * Invalidation patterns:
 *   1. Contradiction: A contradicts B → older gets invalid_at
 *   2. Decision supersession: two decisions from same node on same topic → older invalidated
 *   3. Temporal decay: edges from resolved/completed nodes get invalid_at
 *
 * This feeds L4 state classification: threads with only invalidated edges
 * are "evolved past" (not stalled). Threads with fresh valid edges are active.
 */

import type Database from 'better-sqlite3';

// ── Types ───────────────────────────────────────────────────────────────────

export interface InvalidationResult {
  contradictionInvalidations: number;
  supersessionInvalidations: number;
  alreadyInvalidated: number;
  totalEdgesScanned: number;
  durationMs: number;
}

// ── Pattern 1: Contradiction invalidation ───────────────────────────────────

/**
 * When edge A→B has relationship "contradicts", the older of A and B's
 * outgoing edges on the same topic should be marked invalid.
 *
 * Logic: if node A (newer) contradicts node B (older), then B's claims
 * are superseded. Mark edges FROM B as invalid_at = A's valid_at.
 */
function invalidateContradictions(db: Database.Database): number {
  // Find all contradiction edges with temporal data
  const contradictions = db.prepare(`
    SELECT e.id, e.from_node, e.to_node, e.valid_at,
           n1.created_at as from_created, n1.label as from_label,
           n2.created_at as to_created, n2.label as to_label
    FROM edges e
    JOIN nodes n1 ON e.from_node = n1.id
    JOIN nodes n2 ON e.to_node = n2.id
    WHERE e.relationship = 'contradicts'
      AND e.invalid_at IS NULL
  `).all() as {
    id: string; from_node: string; to_node: string; valid_at: string;
    from_created: string; to_created: string;
    from_label: string; to_label: string;
  }[];

  if (contradictions.length === 0) return 0;

  let invalidated = 0;

  const markInvalid = db.prepare(`
    UPDATE edges SET invalid_at = ? WHERE id = ? AND invalid_at IS NULL
  `);

  const getOutgoingEdges = db.prepare(`
    SELECT id, relationship, valid_at FROM edges
    WHERE from_node = ? AND invalid_at IS NULL AND relationship != 'contradicts'
  `);

  for (const c of contradictions) {
    // Determine which node is older (the superseded one)
    const fromTime = new Date(c.from_created).getTime();
    const toTime = new Date(c.to_created).getTime();

    const olderNodeId = fromTime < toTime ? c.from_node : c.to_node;
    const newerCreatedAt = fromTime < toTime ? c.to_created : c.from_created;

    // Mark outgoing edges from the older node as invalidated
    // (its claims are superseded by the contradiction)
    const olderEdges = getOutgoingEdges.all(olderNodeId) as {
      id: string; relationship: string; valid_at: string;
    }[];

    for (const edge of olderEdges) {
      markInvalid.run(newerCreatedAt, edge.id);
      invalidated++;
    }
  }

  return invalidated;
}

// ── Pattern 2: Decision supersession ────────────────────────────────────────

/**
 * When the same source has multiple "decision" nodes that share a common
 * neighbor (via extends/supports/depends_on), the older decision's edges
 * may be superseded by the newer one.
 *
 * Example: Node A (2024): "decided to use JWT" → Node C (topic)
 *          Node B (2025): "decided to use refresh tokens" → Node C (topic)
 *          → A's edge to C gets invalid_at = B's created_at
 */
function invalidateSupersededDecisions(db: Database.Database): number {
  // Find decision nodes that share a common target
  const decisionPairs = db.prepare(`
    SELECT e1.id as older_edge_id, e1.from_node as older_node,
           e2.from_node as newer_node, e2.valid_at as newer_valid_at,
           n1.created_at as older_created, n2.created_at as newer_created,
           n1.label as older_label, n2.label as newer_label
    FROM edges e1
    JOIN edges e2 ON e1.to_node = e2.to_node
      AND e1.from_node != e2.from_node
    JOIN nodes n1 ON e1.from_node = n1.id
    JOIN nodes n2 ON e2.from_node = n2.id
    WHERE n1.node_type = 'decision'
      AND n2.node_type = 'decision'
      AND n1.created_at < n2.created_at
      AND e1.invalid_at IS NULL
      AND e1.relationship IN ('extends', 'supports', 'depends_on', 'partially_answers')
      AND e2.relationship IN ('extends', 'supports', 'depends_on', 'partially_answers')
  `).all() as {
    older_edge_id: string; older_node: string; newer_node: string;
    newer_valid_at: string; older_created: string; newer_created: string;
    older_label: string; newer_label: string;
  }[];

  if (decisionPairs.length === 0) return 0;

  let invalidated = 0;
  const seen = new Set<string>(); // avoid double-invalidating

  const markInvalid = db.prepare(`
    UPDATE edges SET invalid_at = ? WHERE id = ? AND invalid_at IS NULL
  `);

  for (const pair of decisionPairs) {
    if (seen.has(pair.older_edge_id)) continue;
    seen.add(pair.older_edge_id);

    markInvalid.run(pair.newer_created, pair.older_edge_id);
    invalidated++;
  }

  return invalidated;
}

// ── Main entry point ────────────────────────────────────────────────────────

export async function invalidateEdges(
  db: Database.Database,
): Promise<InvalidationResult> {
  const startMs = Date.now();

  // Count already invalidated
  const alreadyInvalidated = (db.prepare(
    'SELECT COUNT(*) as c FROM edges WHERE invalid_at IS NOT NULL'
  ).get() as any).c;

  const totalEdges = (db.prepare(
    'SELECT COUNT(*) as c FROM edges'
  ).get() as any).c;

  process.stderr.write(`Edge invalidation: ${totalEdges} edges, ${alreadyInvalidated} already invalidated\n`);

  // Run invalidation patterns in a transaction
  const result = db.transaction(() => {
    const contradictions = invalidateContradictions(db);
    const supersessions = invalidateSupersededDecisions(db);
    return { contradictions, supersessions };
  })();

  const durationMs = Date.now() - startMs;

  process.stderr.write(
    `Edge invalidation complete: ${result.contradictions} contradiction + ` +
    `${result.supersessions} supersession invalidations in ${durationMs}ms\n`
  );

  return {
    contradictionInvalidations: result.contradictions,
    supersessionInvalidations: result.supersessions,
    alreadyInvalidated,
    totalEdgesScanned: totalEdges,
    durationMs,
  };
}
