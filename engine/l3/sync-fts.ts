/**
 * engine/l3/sync-fts.ts
 * Rebuild FTS5 indices from source tables.
 */

import type Database from 'better-sqlite3';

export function syncFtsIndices(db: Database.Database): { nodes: number; segments: number; edges: number } {
  let nodeCount = 0;
  let segCount = 0;
  let edgeCount = 0;

  try {
    db.exec(`DELETE FROM fts_nodes`);
    nodeCount = db.prepare(`
      INSERT INTO fts_nodes(node_id, label, node_content)
      SELECT id, label, content FROM nodes
    `).run().changes;
  } catch (err) {
    console.warn('[sync-fts] fts_nodes unavailable:', (err as Error).message);
  }

  try {
    db.exec(`DELETE FROM fts_segments`);
    segCount = db.prepare(`
      INSERT INTO fts_segments(segment_id, topic_label, processed_content)
      SELECT id, topic_label, processed_content FROM segments
    `).run().changes;
  } catch (err) {
    console.warn('[sync-fts] fts_segments unavailable:', (err as Error).message);
  }

  try {
    db.exec(`DELETE FROM fts_edges`);
    edgeCount = db.prepare(`
      INSERT INTO fts_edges(edge_id, relationship, note, fact)
      SELECT id, relationship, COALESCE(note, ''), COALESCE(fact, '') FROM edges
    `).run().changes;
  } catch (err) {
    console.warn('[sync-fts] fts_edges unavailable:', (err as Error).message);
  }

  return { nodes: nodeCount, segments: segCount, edges: edgeCount };
}
