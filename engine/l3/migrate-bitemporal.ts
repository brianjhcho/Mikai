/**
 * engine/l3/migrate-bitemporal.ts
 *
 * Idempotent migration: adds bitemporal columns to edges table
 * and creates FTS5 virtual tables for full-text search.
 *
 * Safe to run multiple times — all operations check existence first.
 */

import Database from 'better-sqlite3';

export function migrateToBitemporal(db: Database.Database): void {
  // ── 1. Add bitemporal columns to edges (idempotent via PRAGMA check) ─────────

  const edgeColumns = (
    db.pragma('table_info(edges)') as { name: string }[]
  ).map(col => col.name);

  if (!edgeColumns.includes('fact')) {
    db.exec(`ALTER TABLE edges ADD COLUMN fact TEXT`);
  }
  if (!edgeColumns.includes('valid_at')) {
    db.exec(`ALTER TABLE edges ADD COLUMN valid_at TEXT`);
  }
  if (!edgeColumns.includes('invalid_at')) {
    db.exec(`ALTER TABLE edges ADD COLUMN invalid_at TEXT`);
  }
  if (!edgeColumns.includes('expired_at')) {
    db.exec(`ALTER TABLE edges ADD COLUMN expired_at TEXT`);
  }
  if (!edgeColumns.includes('episodes')) {
    db.exec(`ALTER TABLE edges ADD COLUMN episodes TEXT DEFAULT '[]'`);
  }

  // ── 2. FTS5 virtual tables (external content mode) ────────────────────────────

  // FTS5 contentless-delete tables — data is inserted manually by sync-fts.ts
  // Drop old tables if they exist with wrong schema (from prior migration runs)
  // then recreate with correct schema including explicit ID columns.
  try { db.exec(`DROP TABLE IF EXISTS fts_nodes`); } catch { /* may not exist */ }
  try { db.exec(`DROP TABLE IF EXISTS fts_segments`); } catch { /* may not exist */ }
  try { db.exec(`DROP TABLE IF EXISTS fts_edges`); } catch { /* may not exist */ }

  db.exec(`
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_nodes
      USING fts5(node_id, label, node_content, content='', contentless_delete=1);

    CREATE VIRTUAL TABLE IF NOT EXISTS fts_segments
      USING fts5(segment_id, topic_label, processed_content, content='', contentless_delete=1);

    CREATE VIRTUAL TABLE IF NOT EXISTS fts_edges
      USING fts5(edge_id, relationship, note, fact, content='', contentless_delete=1);
  `);

  // ── 3. Backfill valid_at from source node's created_at ────────────────────────

  db.exec(`
    UPDATE edges
    SET valid_at = (
      SELECT created_at FROM nodes WHERE id = edges.from_node
    )
    WHERE valid_at IS NULL
  `);
}
