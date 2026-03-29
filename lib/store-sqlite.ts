/**
 * lib/store-sqlite.ts
 *
 * Local-first SQLite storage backend for MIKAI.
 * Uses better-sqlite3 + sqlite-vec for vector search.
 *
 * This module is the ONLY storage backend for the `npx @mikai/mcp` path.
 * The existing Supabase path (npm run scripts) remains untouched.
 */

import Database from 'better-sqlite3';
import * as sqliteVec from 'sqlite-vec';
import { randomUUID } from 'crypto';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SourceRow {
  id: string;
  type: string;
  label: string;
  raw_content: string;
  source: string;
  chunk_count: number;
  node_count: number;
  edge_count: number;
  content_hash: string | null;
  created_at: string;
}

export interface SourceInsert {
  type: string;
  label: string;
  raw_content: string;
  source: string;
  content_hash?: string;
  chunk_count?: number;
}

export interface NodeRow {
  id: string;
  source_id: string;
  label: string;
  content: string;
  node_type: string;
  track: string | null;
  occurrence_count: number;
  query_hit_count: number;
  confidence_weight: number;
  has_action_verb: boolean;
  stall_probability: number | null;
  resolved_at: string | null;
  created_at: string;
  similarity?: number;
}

export interface NodeInsert {
  source_id: string;
  label: string;
  content: string;
  node_type: string;
  embedding: number[];
  track?: string;
  has_action_verb?: boolean;
  confidence_weight?: number;
  stall_probability?: number;
}

export interface EdgeRow {
  id: string;
  from_node: string;
  to_node: string;
  relationship: string;
  note: string | null;
  weight: number;
  created_at: string;
  fact: string | null;
  valid_at: string | null;
  invalid_at: string | null;
  expired_at: string | null;
  episodes: string;
}

export interface EdgeInsert {
  from_node: string;
  to_node: string;
  relationship: string;
  note?: string;
  fact?: string;
  valid_at?: string;
  invalid_at?: string;
}

export interface SegmentRow {
  id: string;
  source_id: string;
  topic_label: string;
  processed_content: string;
  created_at: string;
  similarity?: number;
  source_label?: string;
  source_type?: string;
  source_origin?: string;
}

export interface SegmentInsert {
  source_id: string;
  topic_label: string;
  processed_content: string;
  embedding: number[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function toVec(embedding: number[]): Buffer {
  return Buffer.from(new Float32Array(embedding).buffer);
}

// ── Database Init ─────────────────────────────────────────────────────────────

export function openDatabase(dbPath: string): Database.Database {
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  sqliteVec.load(db);
  return db;
}

export function initDatabase(db: Database.Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS sources (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      type TEXT NOT NULL,
      label TEXT,
      raw_content TEXT NOT NULL,
      source TEXT,
      chunk_count INTEGER DEFAULT 0,
      node_count INTEGER DEFAULT 0,
      edge_count INTEGER DEFAULT 0,
      content_hash TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS nodes (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      source_id TEXT REFERENCES sources(id) ON DELETE CASCADE,
      label TEXT NOT NULL,
      content TEXT NOT NULL,
      node_type TEXT NOT NULL,
      track TEXT,
      occurrence_count INTEGER DEFAULT 1,
      query_hit_count INTEGER DEFAULT 0,
      confidence_weight REAL DEFAULT 1.0,
      has_action_verb INTEGER DEFAULT 0,
      stall_probability REAL,
      resolved_at TEXT,
      metadata TEXT DEFAULT '{}',
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS edges (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      from_node TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
      to_node TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
      relationship TEXT NOT NULL,
      note TEXT,
      weight REAL DEFAULT 1.0,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS segments (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      source_id TEXT REFERENCES sources(id) ON DELETE CASCADE,
      topic_label TEXT NOT NULL,
      processed_content TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS extraction_logs (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      source_id TEXT,
      operation TEXT,
      model TEXT,
      duration_ms INTEGER,
      error TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_nodes_source_id ON nodes(source_id);
    CREATE INDEX IF NOT EXISTS idx_nodes_node_type ON nodes(node_type);
    CREATE INDEX IF NOT EXISTS idx_nodes_track ON nodes(track);
    CREATE INDEX IF NOT EXISTS idx_nodes_stall ON nodes(stall_probability) WHERE stall_probability > 0.5;
    CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node);
    CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node);
    CREATE INDEX IF NOT EXISTS idx_segments_source ON segments(source_id);
    CREATE INDEX IF NOT EXISTS idx_sources_chunk ON sources(chunk_count);
  `);

  // Create sqlite-vec virtual tables for vector search (768-dim for Nomic)
  db.exec(`
    CREATE VIRTUAL TABLE IF NOT EXISTS vec_nodes USING vec0(
      node_id TEXT PRIMARY KEY,
      embedding float[768]
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS vec_segments USING vec0(
      segment_id TEXT PRIMARY KEY,
      embedding float[768]
    );
  `);
}

// ── Sources ───────────────────────────────────────────────────────────────────

export function insertSource(db: Database.Database, row: SourceInsert): { id: string } {
  const id = randomUUID();
  db.prepare(`
    INSERT INTO sources (id, type, label, raw_content, source, content_hash, chunk_count)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(id, row.type, row.label, row.raw_content, row.source, row.content_hash ?? null, row.chunk_count ?? 0);
  return { id };
}

export function updateSource(db: Database.Database, id: string, values: Partial<SourceRow>): void {
  const sets: string[] = [];
  const params: any[] = [];
  for (const [key, val] of Object.entries(values)) {
    if (key === 'id') continue;
    sets.push(`${key} = ?`);
    params.push(val);
  }
  if (sets.length === 0) return;
  params.push(id);
  db.prepare(`UPDATE sources SET ${sets.join(', ')} WHERE id = ?`).run(...params);
}

export function getSourcesToProcess(db: Database.Database, opts: {
  requireChunks?: boolean;
  excludeProcessed?: boolean;
  sourceFilter?: string[];
  limit?: number;
  sourceId?: string;
  rebuild?: boolean;
}): SourceRow[] {
  let sql = 'SELECT * FROM sources WHERE raw_content IS NOT NULL';
  const params: any[] = [];

  if (opts.sourceId) {
    sql += ' AND id = ?';
    params.push(opts.sourceId);
  } else {
    if (opts.requireChunks !== false) {
      sql += ' AND chunk_count > 0';
    }
    if (opts.excludeProcessed !== false && !opts.rebuild) {
      sql += ' AND node_count = 0';
    }
    if (opts.sourceFilter && opts.sourceFilter.length > 0) {
      sql += ` AND source IN (${opts.sourceFilter.map(() => '?').join(',')})`;
      params.push(...opts.sourceFilter);
    }
  }

  sql += ` LIMIT ${opts.limit ?? 10}`;
  return db.prepare(sql).all(...params) as SourceRow[];
}

// ── Nodes ─────────────────────────────────────────────────────────────────────

export function insertNodes(db: Database.Database, rows: NodeInsert[]): { id: string; label: string }[] {
  const insertNode = db.prepare(`
    INSERT INTO nodes (id, source_id, label, content, node_type, track, has_action_verb, confidence_weight, stall_probability)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  const insertVec = db.prepare(`
    INSERT INTO vec_nodes (node_id, embedding) VALUES (?, ?)
  `);

  const results: { id: string; label: string }[] = [];

  const tx = db.transaction(() => {
    for (const row of rows) {
      const id = randomUUID();
      insertNode.run(
        id, row.source_id, row.label, row.content, row.node_type,
        row.track ?? null, row.has_action_verb ? 1 : 0,
        row.confidence_weight ?? 1.0, row.stall_probability ?? null
      );
      insertVec.run(id, toVec(row.embedding));
      results.push({ id, label: row.label });
    }
  });
  tx();

  return results;
}

export function deleteNodesBySource(db: Database.Database, sourceId: string): void {
  // Get node IDs first to delete from vec table
  const nodeIds = db.prepare('SELECT id FROM nodes WHERE source_id = ?').all(sourceId) as { id: string }[];
  if (nodeIds.length > 0) {
    const deleteVec = db.prepare('DELETE FROM vec_nodes WHERE node_id = ?');
    const tx = db.transaction(() => {
      for (const { id } of nodeIds) deleteVec.run(id);
    });
    tx();
  }
  db.prepare('DELETE FROM nodes WHERE source_id = ?').run(sourceId);
}

export function updateNode(db: Database.Database, id: string, values: Partial<NodeRow>): void {
  const sets: string[] = [];
  const params: any[] = [];
  for (const [key, val] of Object.entries(values)) {
    if (key === 'id' || key === 'similarity') continue;
    sets.push(`${key} = ?`);
    params.push(key === 'has_action_verb' ? (val ? 1 : 0) : val);
  }
  if (sets.length === 0) return;
  params.push(id);
  db.prepare(`UPDATE nodes SET ${sets.join(', ')} WHERE id = ?`).run(...params);
}

export function getNodesByType(db: Database.Database, type: string, limit: number): NodeRow[] {
  return db.prepare('SELECT * FROM nodes WHERE node_type = ? LIMIT ?').all(type, limit * 3) as NodeRow[];
}

export function getNodesAboveStall(db: Database.Database, threshold: number, limit: number): NodeRow[] {
  return db.prepare(
    'SELECT * FROM nodes WHERE stall_probability > ? ORDER BY stall_probability DESC LIMIT ?'
  ).all(threshold, limit) as NodeRow[];
}

// ── Vector Search ─────────────────────────────────────────────────────────────

export function searchNodes(db: Database.Database, embedding: number[], limit: number = 5): (NodeRow & { similarity: number })[] {
  const vecResults = db.prepare(`
    SELECT node_id, distance FROM vec_nodes
    WHERE embedding MATCH ? AND k = ?
    ORDER BY distance
  `).all(toVec(embedding), limit) as { node_id: string; distance: number }[];

  if (vecResults.length === 0) return [];

  const ids = vecResults.map(r => r.node_id);
  const distMap = new Map(vecResults.map(r => [r.node_id, r.distance]));

  const placeholders = ids.map(() => '?').join(',');
  const nodes = db.prepare(`SELECT * FROM nodes WHERE id IN (${placeholders})`).all(...ids) as NodeRow[];

  return nodes.map(n => ({
    ...n,
    has_action_verb: Boolean(n.has_action_verb),
    similarity: 1 - (distMap.get(n.id) ?? 1), // cosine distance → similarity
  })).sort((a, b) => b.similarity - a.similarity);
}

export function searchSegments(db: Database.Database, embedding: number[], limit: number = 8): SegmentRow[] {
  const vecResults = db.prepare(`
    SELECT segment_id, distance FROM vec_segments
    WHERE embedding MATCH ? AND k = ?
    ORDER BY distance
  `).all(toVec(embedding), limit) as { segment_id: string; distance: number }[];

  if (vecResults.length === 0) return [];

  const ids = vecResults.map(r => r.segment_id);
  const distMap = new Map(vecResults.map(r => [r.segment_id, r.distance]));

  const placeholders = ids.map(() => '?').join(',');
  const segments = db.prepare(`
    SELECT s.*, src.label as source_label, src.type as source_type, src.source as source_origin
    FROM segments s
    LEFT JOIN sources src ON s.source_id = src.id
    WHERE s.id IN (${placeholders})
  `).all(...ids) as SegmentRow[];

  return segments.map(s => ({
    ...s,
    similarity: 1 - (distMap.get(s.id) ?? 1),
  })).sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0));
}

// ── Edges ─────────────────────────────────────────────────────────────────────

export function insertEdge(db: Database.Database, row: EdgeInsert): { id: string } | null {
  try {
    const id = randomUUID();
    db.prepare(`
      INSERT INTO edges (id, from_node, to_node, relationship, note, fact, valid_at, invalid_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      id,
      row.from_node,
      row.to_node,
      row.relationship,
      row.note ?? null,
      row.fact ?? null,
      row.valid_at ?? null,
      row.invalid_at ?? null,
    );
    return { id };
  } catch {
    return null;
  }
}

export function expireEdge(db: Database.Database, edgeId: string, invalidAt: string): void {
  db.prepare(`
    UPDATE edges SET expired_at = datetime('now'), invalid_at = ? WHERE id = ?
  `).run(invalidAt, edgeId);
}

export function getEdgesBetweenNodes(db: Database.Database, nodeId1: string, nodeId2: string): EdgeRow[] {
  return db.prepare(`
    SELECT * FROM edges
    WHERE (from_node = ? AND to_node = ?) OR (from_node = ? AND to_node = ?)
    ORDER BY created_at DESC
  `).all(nodeId1, nodeId2, nodeId2, nodeId1) as EdgeRow[];
}

export function getActiveEdges(db: Database.Database, nodeIds: string[]): EdgeRow[] {
  if (nodeIds.length === 0) return [];
  const placeholders = nodeIds.map(() => '?').join(',');
  return db.prepare(`
    SELECT * FROM edges
    WHERE (from_node IN (${placeholders}) OR to_node IN (${placeholders}))
      AND expired_at IS NULL
  `).all(...nodeIds, ...nodeIds) as EdgeRow[];
}

export function getEdgesTouchingNodes(db: Database.Database, nodeIds: string[]): EdgeRow[] {
  if (nodeIds.length === 0) return [];
  const placeholders = nodeIds.map(() => '?').join(',');
  return db.prepare(`
    SELECT * FROM edges
    WHERE from_node IN (${placeholders}) OR to_node IN (${placeholders})
  `).all(...nodeIds, ...nodeIds) as EdgeRow[];
}

// ── Segments ──────────────────────────────────────────────────────────────────

export function insertSegments(db: Database.Database, rows: SegmentInsert[]): void {
  const insertSeg = db.prepare(`
    INSERT INTO segments (id, source_id, topic_label, processed_content)
    VALUES (?, ?, ?, ?)
  `);
  const insertVec = db.prepare(`
    INSERT INTO vec_segments (segment_id, embedding) VALUES (?, ?)
  `);

  const tx = db.transaction(() => {
    for (const row of rows) {
      const id = randomUUID();
      insertSeg.run(id, row.source_id, row.topic_label, row.processed_content);
      insertVec.run(id, toVec(row.embedding));
    }
  });
  tx();
}

// ── Rule Engine (Score All Nodes) ─────────────────────────────────────────────

export function scoreAllNodes(db: Database.Database): number {
  const nodes = db.prepare(`
    SELECT id, occurrence_count, query_hit_count, confidence_weight,
           has_action_verb, stall_probability, resolved_at,
           CAST((julianday('now') - julianday(created_at)) AS INTEGER) as days_since
    FROM nodes WHERE resolved_at IS NULL
  `).all() as any[];

  const update = db.prepare('UPDATE nodes SET stall_probability = ? WHERE id = ?');
  let scored = 0;

  const tx = db.transaction(() => {
    for (const node of nodes) {
      const score = scoreNode(node);
      update.run(score, node.id);
      scored++;
    }
  });
  tx();
  return scored;
}

function scoreNode(node: any): number {
  // High-confidence stall rule (mirrors engine/inference/rule-engine.ts)
  if (
    node.occurrence_count >= 2 &&
    node.days_since > 14 &&
    node.has_action_verb &&
    node.resolved_at === null
  ) {
    return 0.8;
  }

  // Weighted combination
  const actionVerbScore = node.has_action_verb ? 0.3 : 0;
  const recurrence = Math.min(node.occurrence_count / 5, 1) * 0.3;
  const staleness = node.days_since > 7 ? 0.2 : 0;
  const hitBoost = node.query_hit_count > 0 ? 0.1 : 0;

  return (actionVerbScore + recurrence + staleness + hitBoost) * (node.confidence_weight ?? 1.0);
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export function getStats(db: Database.Database): {
  totalSources: number;
  totalNodes: number;
  totalSegments: number;
  sourcesByType: Record<string, number>;
  lastIngestion: string | null;
  lastSegmentation: string | null;
} {
  const totalSources = (db.prepare('SELECT COUNT(*) as c FROM sources').get() as any).c;
  const totalNodes = (db.prepare('SELECT COUNT(*) as c FROM nodes').get() as any).c;
  const totalSegments = (db.prepare('SELECT COUNT(*) as c FROM segments').get() as any).c;

  const typeRows = db.prepare('SELECT source, COUNT(*) as c FROM sources GROUP BY source').all() as { source: string; c: number }[];
  const sourcesByType: Record<string, number> = {};
  for (const row of typeRows) sourcesByType[row.source ?? 'unknown'] = row.c;

  const lastIngestion = (db.prepare('SELECT created_at FROM sources ORDER BY created_at DESC LIMIT 1').get() as any)?.created_at ?? null;
  const lastSegmentation = (db.prepare('SELECT created_at FROM segments ORDER BY created_at DESC LIMIT 1').get() as any)?.created_at ?? null;

  return { totalSources, totalNodes, totalSegments, sourcesByType, lastIngestion, lastSegmentation };
}
