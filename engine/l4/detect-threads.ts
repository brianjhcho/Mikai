/**
 * engine/l4/detect-threads.ts
 *
 * Thread detection via hybrid embedding-based clustering.
 * Groups related segments AND nodes across different source types into threads.
 *
 * Algorithm: kNN on vec_segments + vec_nodes → Union-Find clustering → thread creation.
 * Zero LLM — uses only pre-computed embeddings from the L3 pipeline.
 *
 * The L3 graph layer excels at extracting entities from short-form sources
 * (gmail: 1,179 nodes, apple-notes: 412, imessage: 70) while the segment
 * layer excels at chunking long-form sources (perplexity: 14,946, claude: 4,705).
 * Hybrid detection uses BOTH representations so cross-app threads can form
 * between a gmail node and a perplexity segment.
 */

import type Database from 'better-sqlite3';
import { insertThread, insertThreadMembers, updateThread } from './store.js';
import type { ThreadInsert, ThreadMemberInsert } from './types.js';
import { enrichWithGraphSignals } from './graph-enrichment.js';
import { getDomainConfig } from './domain-config.js';
import type { DomainConfig } from './domain-config.js';

// ── Configuration ────────────────────────────────────────────────────────────

const SIMILARITY_THRESHOLD = 0.72;   // cosine similarity to merge items
const CROSS_SOURCE_BONUS = 0.08;     // lower threshold for cross-source matches
const CROSS_LAYER_BONUS = 0.06;      // lower threshold for node↔segment matches
const KNN_K = 15;                    // neighbors to check per item
const MIN_CLUSTER_SIZE = 2;          // minimum items to form a thread
const BATCH_SIZE = 100;              // process items in batches

// Source types to include for node-based detection.
// Gmail excluded: nodes are mostly marketing email subjects that create spam threads.
// Gmail cross-source signal still flows through entity resolution edges.
// iMessage nodes are sparse but contribute cross-source signal.
const NODE_SOURCE_TYPES = new Set(['apple-notes', 'manual', 'imessage']);

// ── Union-Find ───────────────────────────────────────────────────────────────

class UnionFind {
  private parent: Map<string, string> = new Map();
  private rank: Map<string, number> = new Map();

  find(x: string): string {
    if (!this.parent.has(x)) {
      this.parent.set(x, x);
      this.rank.set(x, 0);
    }
    let root = x;
    while (this.parent.get(root) !== root) {
      root = this.parent.get(root)!;
    }
    // Path compression
    let current = x;
    while (current !== root) {
      const next = this.parent.get(current)!;
      this.parent.set(current, root);
      current = next;
    }
    return root;
  }

  union(x: string, y: string): void {
    const rootX = this.find(x);
    const rootY = this.find(y);
    if (rootX === rootY) return;

    const rankX = this.rank.get(rootX)!;
    const rankY = this.rank.get(rootY)!;
    if (rankX < rankY) {
      this.parent.set(rootX, rootY);
    } else if (rankX > rankY) {
      this.parent.set(rootY, rootX);
    } else {
      this.parent.set(rootY, rootX);
      this.rank.set(rootX, rankX + 1);
    }
  }

  clusters(): Map<string, string[]> {
    const groups = new Map<string, string[]>();
    for (const key of this.parent.keys()) {
      const root = this.find(key);
      if (!groups.has(root)) groups.set(root, []);
      groups.get(root)!.push(key);
    }
    return groups;
  }
}

// ── Label Cleanup ────────────────────────────────────────────────────────────

/**
 * Clean raw topic_labels from Perplexity/Claude JSON exports.
 * Strips JSON prefixes like `[Assistant]: [{"step_type":...` and extracts
 * the actual user question or topic.
 */
function cleanTopicLabel(raw: string): string {
  let label = raw.trim();

  // Strip [Assistant]: or [User]: prefix
  label = label.replace(/^\[(Assistant|User)\]:\s*/i, '');

  // If it looks like JSON, try to extract the query/content
  if (label.startsWith('[{') || label.startsWith('{')) {
    try {
      const parsed = JSON.parse(label.startsWith('[') ? label : `[${label}]`);
      const first = Array.isArray(parsed) ? parsed[0] : parsed;
      if (first?.content?.query) return first.content.query.slice(0, 120);
      if (first?.content?.answer) return first.content.answer.slice(0, 120);
      if (first?.content) return (typeof first.content === 'string' ? first.content : JSON.stringify(first.content)).slice(0, 120);
    } catch {
      // Not valid JSON — extract text after JSON-like prefix
      const match = label.match(/"query":\s*"([^"]+)"/);
      if (match) return match[1].slice(0, 120);
      const answerMatch = label.match(/"answer":\s*"([^"]{10,120})/);
      if (answerMatch) return answerMatch[1].slice(0, 120);
    }
  }

  // Strip leading {"answer": or similar partial JSON
  label = label.replace(/^\{"answer":\s*"/, '').replace(/"\s*}$/, '');

  // Truncate to reasonable length
  if (label.length > 120) label = label.slice(0, 120);

  return label || 'Unnamed thread';
}

// ── Types ────────────────────────────────────────────────────────────────────

interface SegmentWithSource {
  id: string;
  source_id: string;
  topic_label: string;
  processed_content: string;
  source_type: string;    // e.g. 'apple-notes', 'gmail', 'imessage'
  source_label: string;
  created_at: string;
}

interface NodeWithSource {
  id: string;
  source_id: string;
  label: string;
  content: string;
  node_type: string;
  source_type: string;
  created_at: string;
}

/** Unified item for clustering — can be either a segment or a node */
interface ClusterItem {
  key: string;            // composite key: "s:{uuid}" or "n:{uuid}"
  type: 'segment' | 'node';
  id: string;             // original table ID
  source_id: string;
  source_type: string;
  label: string;          // topic_label (segment) or label (node)
  content: string;        // processed_content (segment) or content (node)
  created_at: string;
}

function compositeKey(type: 'segment' | 'node', id: string): string {
  return `${type === 'segment' ? 's' : 'n'}:${id}`;
}

function parseCompositeKey(key: string): { type: 'segment' | 'node'; id: string } {
  const prefix = key.slice(0, 2);
  const id = key.slice(2);
  return { type: prefix === 's:' ? 'segment' : 'node', id };
}

// ── Main Detection ───────────────────────────────────────────────────────────

export interface DetectResult {
  threadsCreated: number;
  segmentsThreaded: number;
  skippedAlreadyThreaded: number;
}

export async function detectThreads(db: Database.Database): Promise<DetectResult> {
  // ── 1. Gather unthreaded segments ──────────────────────────────────────────
  const unthreadedSegRaw = db.prepare(`
    SELECT s.id, s.source_id, s.topic_label, s.processed_content, s.created_at,
           src.source as source_type, src.label as source_label
    FROM segments s
    LEFT JOIN sources src ON s.source_id = src.id
    WHERE s.id NOT IN (SELECT segment_id FROM thread_members WHERE segment_id IS NOT NULL)
    ORDER BY s.created_at DESC
  `).all() as SegmentWithSource[];

  const unthreadedSegs = unthreadedSegRaw.filter(s =>
    !s.topic_label.startsWith('[Assistant]:') &&
    !s.topic_label.startsWith('{"') &&
    s.topic_label.length > 5
  );

  // ── 2. Gather unthreaded nodes (L3 graph entities) ────────────────────────
  // Only include high-quality source types — gmail/imessage nodes are too noisy
  const nodeSourcePlaceholders = [...NODE_SOURCE_TYPES].map(() => '?').join(',');
  const unthreadedNodes = db.prepare(`
    SELECT n.id, n.source_id, n.label, n.content, n.node_type, n.created_at,
           src.source as source_type
    FROM nodes n
    LEFT JOIN sources src ON n.source_id = src.id
    WHERE n.id NOT IN (SELECT node_id FROM thread_members WHERE node_id IS NOT NULL)
      AND n.label IS NOT NULL AND LENGTH(n.label) > 3
      AND n.content IS NOT NULL AND LENGTH(n.content) > 10
      AND src.source IN (${nodeSourcePlaceholders})
    ORDER BY n.created_at DESC
  `).all(...NODE_SOURCE_TYPES) as NodeWithSource[];

  // ── 3. Build unified item map ─────────────────────────────────────────────
  const itemMap = new Map<string, ClusterItem>();

  for (const seg of unthreadedSegs) {
    const key = compositeKey('segment', seg.id);
    itemMap.set(key, {
      key,
      type: 'segment',
      id: seg.id,
      source_id: seg.source_id,
      source_type: seg.source_type,
      label: seg.topic_label,
      content: seg.processed_content,
      created_at: seg.created_at,
    });
  }

  for (const node of unthreadedNodes) {
    const key = compositeKey('node', node.id);
    itemMap.set(key, {
      key,
      type: 'node',
      id: node.id,
      source_id: node.source_id,
      source_type: node.source_type,
      label: node.label,
      content: node.content,
      created_at: node.created_at,
    });
  }

  if (itemMap.size === 0) {
    return { threadsCreated: 0, segmentsThreaded: 0, skippedAlreadyThreaded: 0 };
  }

  process.stderr.write(`L4 detect: ${unthreadedSegs.length} segments + ${unthreadedNodes.length} nodes = ${itemMap.size} items\n`);

  // ── 4. Build clusters using Union-Find + kNN on BOTH vec spaces ───────────
  const uf = new UnionFind();

  // Helper: compute effective threshold for two items
  function effectiveThreshold(a: ClusterItem, b: ClusterItem): number {
    let threshold = SIMILARITY_THRESHOLD;
    if (a.source_type !== b.source_type) threshold -= CROSS_SOURCE_BONUS;
    if (a.type !== b.type) threshold -= CROSS_LAYER_BONUS;
    return threshold;
  }

  // Helper: run kNN and merge into Union-Find
  function processKnnResults(
    sourceItem: ClusterItem,
    results: { id: string; distance: number }[],
    neighborType: 'segment' | 'node',
  ): void {
    for (const neighbor of results) {
      const neighborKey = compositeKey(neighborType, neighbor.id);
      const neighborItem = itemMap.get(neighborKey);
      if (!neighborItem) continue; // not in our unthreaded set

      const similarity = 1 - neighbor.distance;
      const threshold = effectiveThreshold(sourceItem, neighborItem);

      if (similarity >= threshold) {
        uf.union(sourceItem.key, neighborKey);
      }
    }
  }

  // ── 4a. Process segments: query vec_segments + vec_nodes ──────────────────
  const segKeys = unthreadedSegs.map(s => compositeKey('segment', s.id));

  for (let i = 0; i < segKeys.length; i += BATCH_SIZE) {
    const batch = segKeys.slice(i, i + BATCH_SIZE);

    for (const key of batch) {
      const item = itemMap.get(key)!;

      // kNN in segment space (segment ↔ segment)
      try {
        let segResults = db.prepare(`
          SELECT segment_id as id, distance FROM vec_segments
          WHERE embedding MATCH (SELECT embedding FROM vec_segments WHERE segment_id = ?)
            AND k = ?
          ORDER BY distance
        `).all(item.id, KNN_K + 1) as { id: string; distance: number }[];
        segResults = segResults.filter(r => r.id !== item.id);
        processKnnResults(item, segResults, 'segment');
      } catch { /* embedding missing, skip */ }

      // kNN in node space (segment ↔ node, cross-layer)
      try {
        const nodeResults = db.prepare(`
          SELECT node_id as id, distance FROM vec_nodes
          WHERE embedding MATCH (SELECT embedding FROM vec_segments WHERE segment_id = ?)
            AND k = ?
          ORDER BY distance
        `).all(item.id, KNN_K) as { id: string; distance: number }[];
        processKnnResults(item, nodeResults, 'node');
      } catch { /* cross-space query failed, skip */ }
    }
  }

  // ── 4b. Process nodes: query vec_nodes + vec_segments ─────────────────────
  const nodeKeys = unthreadedNodes.map(n => compositeKey('node', n.id));

  for (let i = 0; i < nodeKeys.length; i += BATCH_SIZE) {
    const batch = nodeKeys.slice(i, i + BATCH_SIZE);

    for (const key of batch) {
      const item = itemMap.get(key)!;

      // kNN in node space (node ↔ node)
      try {
        let nodeResults = db.prepare(`
          SELECT node_id as id, distance FROM vec_nodes
          WHERE embedding MATCH (SELECT embedding FROM vec_nodes WHERE node_id = ?)
            AND k = ?
          ORDER BY distance
        `).all(item.id, KNN_K + 1) as { id: string; distance: number }[];
        nodeResults = nodeResults.filter(r => r.id !== item.id);
        processKnnResults(item, nodeResults, 'node');
      } catch { /* embedding missing, skip */ }

      // kNN in segment space (node ↔ segment, cross-layer)
      try {
        const segResults = db.prepare(`
          SELECT segment_id as id, distance FROM vec_segments
          WHERE embedding MATCH (SELECT embedding FROM vec_nodes WHERE node_id = ?)
            AND k = ?
          ORDER BY distance
        `).all(item.id, KNN_K) as { id: string; distance: number }[];
        processKnnResults(item, segResults, 'segment');
      } catch { /* cross-space query failed, skip */ }
    }
  }

  // ── 4c. Graph-edge-based merging ───────────────────────────────────────────
  // Walk cross-source edges from entity resolution and merge clusters they connect.
  // This is the Graphiti bridge: if two nodes are connected by an entity resolution
  // edge, their clusters should merge regardless of embedding proximity.
  {
    const crossSourceEdges = db.prepare(`
      SELECT e.from_node, e.to_node FROM edges e
      JOIN nodes n1 ON e.from_node = n1.id
      JOIN nodes n2 ON e.to_node = n2.id
      WHERE n1.source_id != n2.source_id
    `).all() as { from_node: string; to_node: string }[];

    let graphMerges = 0;

    for (const edge of crossSourceEdges) {
      const fromKey = compositeKey('node', edge.from_node);
      const toKey = compositeKey('node', edge.to_node);

      // Both nodes must be in our item map (unthreaded)
      const fromInMap = itemMap.has(fromKey);
      const toInMap = itemMap.has(toKey);

      if (fromInMap && toInMap) {
        // Both unthreaded — merge their clusters directly
        uf.union(fromKey, toKey);
        graphMerges++;
      } else if (fromInMap || toInMap) {
        // One is in map, the other might already be in a cluster via its segments.
        // Find any segments from the same source as the missing node and merge.
        const presentKey = fromInMap ? fromKey : toKey;
        const missingNodeId = fromInMap ? edge.to_node : edge.from_node;

        // Look up the missing node's source_id, find segments from that source in our map
        const missingNode = db.prepare(
          'SELECT source_id FROM nodes WHERE id = ?'
        ).get(missingNodeId) as { source_id: string } | undefined;

        if (missingNode) {
          // Find any segment in our map from the same source
          for (const [key, item] of itemMap) {
            if (item.type === 'segment' && item.source_id === missingNode.source_id) {
              uf.union(presentKey, key);
              graphMerges++;
              break; // one merge per edge is sufficient
            }
          }
        }
      }
    }

    process.stderr.write(`  Graph-edge merges: ${graphMerges} (from ${crossSourceEdges.length} cross-source edges)\n`);
  }

  // ── 5. Build set of valid source IDs to avoid FK constraint failures ──────
  const validSourceIds = new Set<string>();
  const sourceRows = db.prepare('SELECT id FROM sources').all() as { id: string }[];
  for (const row of sourceRows) validSourceIds.add(row.id);

  // ── 6. Extract clusters and create threads ────────────────────────────────
  const clusters = uf.clusters();
  let threadsCreated = 0;
  let segmentsThreaded = 0;

  for (const [, memberKeys] of clusters) {
    if (memberKeys.length < MIN_CLUSTER_SIZE) continue;

    const members = memberKeys
      .map(k => itemMap.get(k))
      .filter((m): m is ClusterItem => m !== undefined);

    if (members.length < MIN_CLUSTER_SIZE) continue;

    // Separate segments and nodes
    const segmentMembers = members.filter(m => m.type === 'segment');
    const nodeMembers = members.filter(m => m.type === 'node');

    // ── View A filter: require at least one anchor node type ──────────────
    // Only create threads anchored by project/decision nodes (or segments
    // from multi-turn research). Clusters of only concept/tension nodes
    // are belief threads — View B (future), not View A.
    const config = getDomainConfig();
    const anchorTypes = new Set(config.anchorNodeTypes);
    const hasAnchorNode = nodeMembers.some(m => {
      // Look up node_type from DB for this node
      const node = db.prepare('SELECT node_type FROM nodes WHERE id = ?').get(m.id) as { node_type: string } | undefined;
      return node && anchorTypes.has(node.node_type);
    });
    // Segments count as anchors if there are enough of them (multi-turn research)
    const hasSegmentAnchor = segmentMembers.length >= 2;

    if (!hasAnchorNode && !hasSegmentAnchor) continue;

    // Compute thread metadata from all members
    const sourceTypes = [...new Set(members.map(m => m.source_type).filter(Boolean))];
    const sourceIds = [...new Set(members.map(m => m.source_id).filter(Boolean))];
    const timestamps = members.map(m => m.created_at).filter(Boolean).sort();

    // Pick label: prefer segment topic_labels (richer), fall back to node labels
    const labelCounts = new Map<string, number>();
    for (const m of segmentMembers) {
      const label = cleanTopicLabel(m.label);
      if (label) labelCounts.set(label, (labelCounts.get(label) ?? 0) + 2); // weight segments higher
    }
    for (const m of nodeMembers) {
      const label = m.label.trim();
      if (label && label.length > 5) labelCounts.set(label, (labelCounts.get(label) ?? 0) + 1);
    }
    const threadLabel = [...labelCounts.entries()]
      .sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'Unnamed thread';

    // Confidence: cross-source and cross-layer get higher confidence
    const hasCrossSource = sourceTypes.length >= 2;
    const hasCrossLayer = segmentMembers.length > 0 && nodeMembers.length > 0;
    const confidence = hasCrossSource && hasCrossLayer ? 0.9
      : hasCrossSource ? 0.8
      : hasCrossLayer ? 0.7
      : sourceTypes.length >= 3 ? 0.85
      : 0.5;

    const memberDescription = [
      segmentMembers.length > 0 ? `${segmentMembers.length} segments` : null,
      nodeMembers.length > 0 ? `${nodeMembers.length} nodes` : null,
    ].filter(Boolean).join(' + ');

    // Create thread
    const threadInsert: ThreadInsert = {
      label: threadLabel,
      summary: `Thread spanning ${sourceTypes.join(', ')} (${memberDescription})`,
      first_seen_at: timestamps[0] ?? new Date().toISOString(),
      last_activity_at: timestamps[timestamps.length - 1] ?? new Date().toISOString(),
      source_count: sourceIds.length,
      source_types: sourceTypes,
      confidence,
    };

    const { id: threadId } = insertThread(db, threadInsert);

    // Link segment members
    if (segmentMembers.length > 0) {
      const segInserts: ThreadMemberInsert[] = segmentMembers.map(m => ({
        thread_id: threadId,
        segment_id: m.id,
        source_id: m.source_id && validSourceIds.has(m.source_id) ? m.source_id : undefined,
        contribution_type: 'evidence' as const,
      }));
      insertThreadMembers(db, segInserts);
    }

    // Link node members (directly from clustering, not just post-hoc source lookup)
    if (nodeMembers.length > 0) {
      const nodeInserts: ThreadMemberInsert[] = nodeMembers.map(m => ({
        thread_id: threadId,
        node_id: m.id,
        source_id: m.source_id && validSourceIds.has(m.source_id) ? m.source_id : undefined,
        contribution_type: 'evidence' as const,
      }));
      insertThreadMembers(db, nodeInserts);
    }

    // Also link any additional nodes from segment sources (preserves existing behavior)
    const segSourceIds = segmentMembers
      .map(m => m.source_id)
      .filter((id): id is string => id !== undefined && validSourceIds.has(id));
    const nodeIdsAlreadyLinked = new Set(nodeMembers.map(m => m.id));

    if (segSourceIds.length > 0) {
      const extraNodes = db.prepare(`
        SELECT id, source_id FROM nodes
        WHERE source_id IN (${segSourceIds.map(() => '?').join(',')})
      `).all(...segSourceIds) as { id: string; source_id: string }[];

      const extraNodeInserts: ThreadMemberInsert[] = extraNodes
        .filter(n => !nodeIdsAlreadyLinked.has(n.id))
        .map(n => ({
          thread_id: threadId,
          node_id: n.id,
          source_id: validSourceIds.has(n.source_id) ? n.source_id : undefined,
          contribution_type: 'evidence' as const,
        }));

      if (extraNodeInserts.length > 0) {
        insertThreadMembers(db, extraNodeInserts);
      }
    }

    // Graph enrichment: check L3 edges between ALL member nodes
    const allNodeIds = [
      ...nodeMembers.map(m => m.id),
      ...(() => {
        if (segSourceIds.length === 0) return [];
        try {
          return (db.prepare(`
            SELECT id FROM nodes
            WHERE source_id IN (${segSourceIds.map(() => '?').join(',')})
          `).all(...segSourceIds) as { id: string }[]).map(r => r.id);
        } catch { return []; }
      })(),
    ];
    const uniqueNodeIds = [...new Set(allNodeIds)];

    if (uniqueNodeIds.length >= 2) {
      const graphSignals = enrichWithGraphSignals(db, uniqueNodeIds);
      if (graphSignals.hasEdges) {
        updateThread(db, threadId, {
          confidence: Math.min(1.0, confidence + graphSignals.graphConfidenceBoost),
          edge_types_within: JSON.stringify(graphSignals.edgeTypes),
        } as any);
      }
    }

    threadsCreated++;
    segmentsThreaded += segmentMembers.length;
  }

  return {
    threadsCreated,
    segmentsThreaded,
    skippedAlreadyThreaded: 0,
  };
}

// ── Incremental Update ───────────────────────────────────────────────────────
// After new items are ingested, try to attach them to existing threads

export async function attachNewItems(db: Database.Database): Promise<{ attached: number; newThreads: number }> {
  const validSources = new Set<string>();
  const srcRows = db.prepare('SELECT id FROM sources').all() as { id: string }[];
  for (const row of srcRows) validSources.add(row.id);

  let attached = 0;

  // ── Attach orphan segments ────────────────────────────────────────────────
  const orphanSegsRaw = db.prepare(`
    SELECT s.id, s.source_id, s.topic_label, s.processed_content,
           src.source as source_type
    FROM segments s
    LEFT JOIN sources src ON s.source_id = src.id
    WHERE s.id NOT IN (SELECT segment_id FROM thread_members WHERE segment_id IS NOT NULL)
  `).all() as SegmentWithSource[];
  const orphanSegs = orphanSegsRaw.filter(s =>
    !s.topic_label.startsWith('[Assistant]:') &&
    !s.topic_label.startsWith('{"') &&
    s.topic_label.length > 5
  );

  for (const orphan of orphanSegs) {
    // Try segment space first, then node space
    const threadId = findNearestThread(db, 'segment', orphan.id, orphan.source_type);
    if (threadId) {
      insertThreadMembers(db, [{
        thread_id: threadId,
        segment_id: orphan.id,
        source_id: orphan.source_id && validSources.has(orphan.source_id) ? orphan.source_id : undefined,
        contribution_type: 'evidence',
      }]);
      updateThreadMetadata(db, threadId, orphan.source_type);
      attached++;
    }
  }

  // ── Attach orphan nodes ───────────────────────────────────────────────────
  const orphanNodes = db.prepare(`
    SELECT n.id, n.source_id, n.label, n.content, n.node_type,
           src.source as source_type
    FROM nodes n
    LEFT JOIN sources src ON n.source_id = src.id
    WHERE n.id NOT IN (SELECT node_id FROM thread_members WHERE node_id IS NOT NULL)
      AND n.label IS NOT NULL AND LENGTH(n.label) > 3
      AND n.content IS NOT NULL AND LENGTH(n.content) > 10
  `).all() as NodeWithSource[];

  for (const orphan of orphanNodes) {
    const threadId = findNearestThread(db, 'node', orphan.id, orphan.source_type);
    if (threadId) {
      insertThreadMembers(db, [{
        thread_id: threadId,
        node_id: orphan.id,
        source_id: orphan.source_id && validSources.has(orphan.source_id) ? orphan.source_id : undefined,
        contribution_type: 'evidence',
      }]);
      updateThreadMetadata(db, threadId, orphan.source_type);
      attached++;
    }
  }

  // Run full detection for remaining orphans to form new clusters
  const result = await detectThreads(db);

  return { attached, newThreads: result.threadsCreated };
}

/** @deprecated Use attachNewItems instead */
export const attachNewSegments = attachNewItems;

// ── Helpers ─────────────────────────────────────────────────────────────────

function findNearestThread(
  db: Database.Database,
  itemType: 'segment' | 'node',
  itemId: string,
  sourceType: string,
): string | null {
  const vecTable = itemType === 'segment' ? 'vec_segments' : 'vec_nodes';
  const idCol = itemType === 'segment' ? 'segment_id' : 'node_id';
  const minThreshold = SIMILARITY_THRESHOLD - CROSS_SOURCE_BONUS - CROSS_LAYER_BONUS;

  // Search same-type vec space
  try {
    const neighbors = db.prepare(`
      SELECT ${idCol} as id, distance FROM ${vecTable}
      WHERE embedding MATCH (SELECT embedding FROM ${vecTable} WHERE ${idCol} = ?)
        AND k = 5
      ORDER BY distance
    `).all(itemId) as { id: string; distance: number }[];

    for (const neighbor of neighbors) {
      if (neighbor.id === itemId) continue;
      const similarity = 1 - neighbor.distance;
      if (similarity < minThreshold) continue;

      const memberCol = itemType === 'segment' ? 'segment_id' : 'node_id';
      const membership = db.prepare(
        `SELECT thread_id FROM thread_members WHERE ${memberCol} = ? LIMIT 1`
      ).get(neighbor.id) as { thread_id: string } | undefined;

      if (membership) return membership.thread_id;
    }
  } catch { /* skip */ }

  // Search cross-type vec space (segment → node or node → segment)
  const crossVecTable = itemType === 'segment' ? 'vec_nodes' : 'vec_segments';
  const crossIdCol = itemType === 'segment' ? 'node_id' : 'segment_id';
  const crossMemberCol = itemType === 'segment' ? 'node_id' : 'segment_id';

  try {
    const crossNeighbors = db.prepare(`
      SELECT ${crossIdCol} as id, distance FROM ${crossVecTable}
      WHERE embedding MATCH (SELECT embedding FROM ${vecTable} WHERE ${idCol} = ?)
        AND k = 5
      ORDER BY distance
    `).all(itemId) as { id: string; distance: number }[];

    for (const neighbor of crossNeighbors) {
      const similarity = 1 - neighbor.distance;
      if (similarity < minThreshold) continue;

      const membership = db.prepare(
        `SELECT thread_id FROM thread_members WHERE ${crossMemberCol} = ? LIMIT 1`
      ).get(neighbor.id) as { thread_id: string } | undefined;

      if (membership) return membership.thread_id;
    }
  } catch { /* skip */ }

  return null;
}

function updateThreadMetadata(db: Database.Database, threadId: string, sourceType: string): void {
  const thread = db.prepare('SELECT * FROM threads WHERE id = ?').get(threadId) as any;
  if (!thread) return;

  const currentTypes: string[] = JSON.parse(thread.source_types || '[]');
  if (sourceType && !currentTypes.includes(sourceType)) {
    currentTypes.push(sourceType);
  }
  updateThread(db, threadId, {
    source_count: thread.source_count + 1,
    source_types: JSON.stringify(currentTypes),
    last_activity_at: new Date().toISOString(),
  } as any);
}
