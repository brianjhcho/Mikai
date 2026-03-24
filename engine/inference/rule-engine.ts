/**
 * engine/inference/rule-engine.ts
 *
 * Stalled immediate desire rule engine — Track B inference layer.
 *
 * Takes pre-computed feature columns from the nodes table and returns
 * a stall_probability score between 0.0 and 1.0. Feeds into the
 * predictions table and classifier training loop.
 *
 * D-026: LLM reserved for Track A extraction, terminal synthesis, NLG.
 *        Everything else is ML infrastructure (feature → rule engine → classifier).
 */

import { supabase } from '../../lib/supabase.js';

export interface NodeWithFeatures {
  id: string;
  label: string;
  content: string;
  node_type: string;
  occurrence_count: number;
  query_hit_count: number;
  confidence_weight: number;
  has_action_verb: boolean;
  stall_probability: number | null;
  days_since_first_seen: number;
  resolved_at: string | null;
}

export interface StalledNode {
  id: string;
  label: string;
  node_type: string;
  stall_probability: number;
  source_label: string | null;
  occurrence_count: number;
  has_action_verb: boolean;
}

/**
 * Score a node's stall probability using hand-tuned rules.
 * Returns a value between 0.0 and 1.0.
 *
 * High-confidence rule: all four conditions met → 0.8
 * Otherwise: weighted combination of available signals.
 */
export function scoreNode(node: NodeWithFeatures): number {
  // High-confidence stall rule
  if (
    node.occurrence_count >= 2 &&
    node.days_since_first_seen > 14 &&
    node.has_action_verb === true &&
    node.resolved_at === null
  ) {
    return 0.8;
  }

  // Weighted signal combination
  const actionVerbScore = node.has_action_verb ? 0.3 : 0.0;
  const recurrenceScore = Math.min(node.occurrence_count / 5, 1.0) * 0.3;
  const staleness = node.days_since_first_seen > 7 ? 0.2 : 0.0;
  const hitBoost = node.query_hit_count > 0 ? 0.1 : 0.0;
  const confidenceMultiplier = node.confidence_weight; // 0.5–1.0

  return Math.min(
    (actionVerbScore + recurrenceScore + staleness + hitBoost) * confidenceMultiplier,
    1.0,
  );
}

/**
 * Fetch nodes with stall_probability > 0.5, ordered by score descending.
 * Joins source label via a second query.
 */
export async function getTopStalledNodes(limit = 10): Promise<StalledNode[]> {
  const { data: nodes, error } = await supabase
    .from('nodes')
    .select('id, label, node_type, stall_probability, source_id, occurrence_count, has_action_verb')
    .gt('stall_probability', 0.5)
    .order('stall_probability', { ascending: false })
    .limit(limit);

  if (error || !nodes) return [];

  // Fetch source labels
  const sourceIds = [...new Set(nodes.map((n) => n.source_id).filter(Boolean))] as string[];
  const sourceMap = new Map<string, string>();

  if (sourceIds.length > 0) {
    const { data: sources } = await supabase
      .from('sources')
      .select('id, label')
      .in('id', sourceIds);

    for (const s of sources ?? []) {
      sourceMap.set(s.id, s.label);
    }
  }

  return nodes.map((n) => ({
    id: n.id,
    label: n.label,
    node_type: n.node_type,
    stall_probability: n.stall_probability ?? 0,
    source_label: n.source_id ? (sourceMap.get(n.source_id) ?? null) : null,
    occurrence_count: n.occurrence_count ?? 1,
    has_action_verb: n.has_action_verb ?? false,
  }));
}
