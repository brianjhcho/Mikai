/**
 * engine/l4/detect-threads.ts
 *
 * Thread detection via embedding-based clustering.
 * Groups related segments across different source types into threads.
 *
 * Algorithm: kNN on vec_segments → Union-Find clustering → thread creation.
 * Zero LLM — uses only pre-computed embeddings from the L3 pipeline.
 */

import type Database from 'better-sqlite3';
import { insertThread, insertThreadMembers, updateThread } from './store.js';
import type { ThreadInsert, ThreadMemberInsert } from './types.js';
import { enrichWithGraphSignals } from './graph-enrichment.js';

// ── Configuration ────────────────────────────────────────────────────────────

const SIMILARITY_THRESHOLD = 0.72;   // cosine similarity to merge segments
const CROSS_SOURCE_BONUS = 0.08;     // lower threshold for cross-source matches
const KNN_K = 15;                    // neighbors to check per segment
const MIN_CLUSTER_SIZE = 2;          // minimum segments to form a thread
const BATCH_SIZE = 100;              // process segments in batches

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

// ── Main Detection ───────────────────────────────────────────────────────────

export interface DetectResult {
  threadsCreated: number;
  segmentsThreaded: number;
  skippedAlreadyThreaded: number;
}

export async function detectThreads(db: Database.Database): Promise<DetectResult> {
  // 1. Find unthreaded segments (not yet in thread_members)
  const unthreadedRaw = db.prepare(`
    SELECT s.id, s.source_id, s.topic_label, s.processed_content, s.created_at,
           src.source as source_type, src.label as source_label
    FROM segments s
    LEFT JOIN sources src ON s.source_id = src.id
    WHERE s.id NOT IN (SELECT segment_id FROM thread_members WHERE segment_id IS NOT NULL)
    ORDER BY s.created_at DESC
  `).all() as SegmentWithSource[];

  // Filter out noise segments (raw assistant responses used as topic labels)
  const unthreaded = unthreadedRaw.filter(s =>
    !s.topic_label.startsWith('[Assistant]:') &&
    !s.topic_label.startsWith('{"') &&
    s.topic_label.length > 5
  );

  if (unthreaded.length === 0) {
    return { threadsCreated: 0, segmentsThreaded: 0, skippedAlreadyThreaded: 0 };
  }

  const segmentMap = new Map<string, SegmentWithSource>();
  for (const seg of unthreaded) {
    segmentMap.set(seg.id, seg);
  }

  // 2. Build clusters using Union-Find + kNN similarity
  const uf = new UnionFind();
  const segmentIds = unthreaded.map(s => s.id);

  // Process in batches to avoid memory issues
  for (let i = 0; i < segmentIds.length; i += BATCH_SIZE) {
    const batch = segmentIds.slice(i, i + BATCH_SIZE);

    for (const segId of batch) {
      // Get kNN for this segment from vec_segments
      let knnResults: { segment_id: string; distance: number }[];
      try {
        // Try the simpler kNN pattern that sqlite-vec supports
        knnResults = db.prepare(`
          SELECT segment_id, distance FROM vec_segments
          WHERE embedding MATCH (SELECT embedding FROM vec_segments WHERE segment_id = ?)
            AND k = ?
          ORDER BY distance
        `).all(segId, KNN_K + 1) as { segment_id: string; distance: number }[];
        // Remove self-match
        knnResults = knnResults.filter(r => r.segment_id !== segId);
      } catch {
        // If vec query fails for this segment, skip it
        continue;
      }

      for (const neighbor of knnResults) {
        // Only consider unthreaded segments
        if (!segmentMap.has(neighbor.segment_id)) continue;

        const similarity = 1 - neighbor.distance; // cosine distance → similarity
        const seg = segmentMap.get(segId)!;
        const neighborSeg = segmentMap.get(neighbor.segment_id)!;

        // Cross-source matches get a bonus (lower threshold)
        const isCrossSource = seg.source_type !== neighborSeg.source_type;
        const threshold = isCrossSource
          ? SIMILARITY_THRESHOLD - CROSS_SOURCE_BONUS
          : SIMILARITY_THRESHOLD;

        if (similarity >= threshold) {
          uf.union(segId, neighbor.segment_id);
        }
      }
    }
  }

  // 3. Build set of valid source IDs to avoid FK constraint failures
  const validSourceIds = new Set<string>();
  const sourceRows = db.prepare('SELECT id FROM sources').all() as { id: string }[];
  for (const row of sourceRows) validSourceIds.add(row.id);

  // 4. Extract clusters and create threads
  const clusters = uf.clusters();
  let threadsCreated = 0;
  let segmentsThreaded = 0;

  for (const [, memberIds] of clusters) {
    if (memberIds.length < MIN_CLUSTER_SIZE) continue;

    const members = memberIds
      .map(id => segmentMap.get(id))
      .filter((s): s is SegmentWithSource => s !== undefined);

    if (members.length < MIN_CLUSTER_SIZE) continue;

    // Compute thread metadata
    const sourceTypes = [...new Set(members.map(m => m.source_type).filter(Boolean))];
    const sourceIds = [...new Set(members.map(m => m.source_id).filter(Boolean))];
    const timestamps = members.map(m => m.created_at).filter(Boolean).sort();

    // Pick label: most frequent CLEAN topic_label in the cluster
    const labelCounts = new Map<string, number>();
    for (const m of members) {
      const label = cleanTopicLabel(m.topic_label);
      if (label) labelCounts.set(label, (labelCounts.get(label) ?? 0) + 1);
    }
    const threadLabel = [...labelCounts.entries()]
      .sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'Unnamed thread';

    // Cross-source threads get higher confidence
    const confidence = sourceTypes.length >= 3 ? 0.85
      : sourceTypes.length >= 2 ? 0.7
      : 0.5;

    // Create thread
    const threadInsert: ThreadInsert = {
      label: threadLabel,
      summary: `Thread spanning ${sourceTypes.join(', ')} (${members.length} segments)`,
      first_seen_at: timestamps[0] ?? new Date().toISOString(),
      last_activity_at: timestamps[timestamps.length - 1] ?? new Date().toISOString(),
      source_count: sourceIds.length,
      source_types: sourceTypes,
      confidence,
    };

    const { id: threadId } = insertThread(db, threadInsert);

    // Link members (validate source_ids to avoid FK constraint failures)
    const memberInserts: ThreadMemberInsert[] = [];
    for (const m of members) {
      memberInserts.push({
        thread_id: threadId,
        segment_id: m.id,
        source_id: m.source_id && validSourceIds.has(m.source_id) ? m.source_id : undefined,
        contribution_type: 'evidence',
      });
    }
    insertThreadMembers(db, memberInserts);

    // Also link nodes from these sources to the thread
    const validSourceIdsForQuery = sourceIds.filter(id => validSourceIds.has(id));
    const nodeRows = validSourceIdsForQuery.length > 0
      ? db.prepare(`
          SELECT id, source_id FROM nodes
          WHERE source_id IN (${validSourceIdsForQuery.map(() => '?').join(',')})
        `).all(...validSourceIdsForQuery) as { id: string; source_id: string }[]
      : [];

    if (nodeRows.length > 0) {
      const nodeMembers: ThreadMemberInsert[] = nodeRows.map(n => ({
        thread_id: threadId,
        node_id: n.id,
        source_id: validSourceIds.has(n.source_id) ? n.source_id : undefined,
        contribution_type: 'evidence' as const,
      }));
      insertThreadMembers(db, nodeMembers);

      // Graph enrichment: check L3 edges between member nodes
      const memberNodeIds = nodeRows.map(n => n.id);
      const graphSignals = enrichWithGraphSignals(db, memberNodeIds);
      if (graphSignals.hasEdges) {
        updateThread(db, threadId, {
          confidence: Math.min(1.0, confidence + graphSignals.graphConfidenceBoost),
          edge_types_within: JSON.stringify(graphSignals.edgeTypes),
        } as any);
      }
    }

    threadsCreated++;
    segmentsThreaded += members.length;
  }

  return {
    threadsCreated,
    segmentsThreaded,
    skippedAlreadyThreaded: 0,
  };
}

// ── Incremental Update ───────────────────────────────────────────────────────
// After new segments are ingested, try to attach them to existing threads

export async function attachNewSegments(db: Database.Database): Promise<{ attached: number; newThreads: number }> {
  // Build valid source ID set to avoid FK constraint failures
  const validSources = new Set<string>();
  const srcRows = db.prepare('SELECT id FROM sources').all() as { id: string }[];
  for (const row of srcRows) validSources.add(row.id);

  // Find segments not in any thread (filter noise labels)
  const orphansRaw = db.prepare(`
    SELECT s.id, s.source_id, s.topic_label, s.processed_content,
           src.source as source_type
    FROM segments s
    LEFT JOIN sources src ON s.source_id = src.id
    WHERE s.id NOT IN (SELECT segment_id FROM thread_members WHERE segment_id IS NOT NULL)
  `).all() as SegmentWithSource[];
  const orphans = orphansRaw.filter(s =>
    !s.topic_label.startsWith('[Assistant]:') &&
    !s.topic_label.startsWith('{"') &&
    s.topic_label.length > 5
  );

  let attached = 0;

  for (const orphan of orphans) {
    // Find nearest segments that ARE in threads
    let neighbors: { segment_id: string; distance: number }[];
    try {
      neighbors = db.prepare(`
        SELECT segment_id, distance FROM vec_segments
        WHERE embedding MATCH (SELECT embedding FROM vec_segments WHERE segment_id = ?)
          AND k = 5
        ORDER BY distance
      `).all(orphan.id) as { segment_id: string; distance: number }[];
      neighbors = neighbors.filter(r => r.segment_id !== orphan.id);
    } catch {
      continue;
    }

    for (const neighbor of neighbors) {
      const similarity = 1 - neighbor.distance;
      if (similarity < SIMILARITY_THRESHOLD - CROSS_SOURCE_BONUS) continue;

      // Check if this neighbor belongs to a thread
      const membership = db.prepare(`
        SELECT thread_id FROM thread_members WHERE segment_id = ? LIMIT 1
      `).get(neighbor.segment_id) as { thread_id: string } | undefined;

      if (membership) {
        insertThreadMembers(db, [{
          thread_id: membership.thread_id,
          segment_id: orphan.id,
          source_id: orphan.source_id && validSources.has(orphan.source_id) ? orphan.source_id : undefined,
          contribution_type: 'evidence',
        }]);

        // Update thread metadata
        const thread = db.prepare('SELECT * FROM threads WHERE id = ?').get(membership.thread_id) as any;
        if (thread) {
          const currentTypes: string[] = JSON.parse(thread.source_types || '[]');
          if (orphan.source_type && !currentTypes.includes(orphan.source_type)) {
            currentTypes.push(orphan.source_type);
          }
          updateThread(db, membership.thread_id, {
            source_count: thread.source_count + 1,
            source_types: JSON.stringify(currentTypes),
            last_activity_at: new Date().toISOString(),
          } as any);
        }

        attached++;
        break; // Attached to first matching thread
      }
    }
  }

  // Run full detection for remaining orphans to form new clusters
  const result = await detectThreads(db);

  return { attached, newThreads: result.threadsCreated };
}
