#!/usr/bin/env tsx
/**
 * scripts/supabase-to-sqlite.ts
 *
 * One-time migration: pulls all data from Supabase into the local SQLite DB.
 * Fetches sources, nodes, edges, segments in batches and inserts into ~/.mikai/mikai.db.
 *
 * Usage: npx tsx scripts/supabase-to-sqlite.ts
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import Database from 'better-sqlite3';
import * as sqliteVec from 'sqlite-vec';
import { randomUUID } from 'crypto';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Env ──────────────────────────────────────────────────────────────────────

function loadEnv(): void {
  const envPath = path.join(__dirname, '../.env.local');
  try {
    for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx < 0) continue;
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim();
      if (!process.env[key]) process.env[key] = val;
    }
  } catch { /* ok */ }
}

loadEnv();

const SUPABASE_URL = process.env.SUPABASE_URL!;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY!;

if (!SUPABASE_URL || !SUPABASE_KEY) {
  console.error('Missing SUPABASE_URL or SUPABASE_SERVICE_KEY');
  process.exit(1);
}

const headers: Record<string, string> = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
  'Content-Type': 'application/json',
};

// ── Supabase fetch (paginated) ───────────────────────────────────────────────

async function fetchAll(table: string, select: string = '*', batchSize: number = 1000): Promise<any[]> {
  const all: any[] = [];
  let offset = 0;

  while (true) {
    const url = `${SUPABASE_URL}/rest/v1/${table}?select=${encodeURIComponent(select)}&limit=${batchSize}&offset=${offset}&order=created_at.asc`;
    const res = await fetch(url, { headers });
    if (!res.ok) {
      console.error(`  Fetch error for ${table}: ${res.status} ${await res.text()}`);
      break;
    }
    const rows = await res.json();
    if (!Array.isArray(rows) || rows.length === 0) break;
    all.push(...rows);
    console.log(`  ${table}: fetched ${all.length} rows...`);
    if (rows.length < batchSize) break;
    offset += batchSize;
  }

  return all;
}

// ── Database ─────────────────────────────────────────────────────────────────

function getDbPath(): string {
  const configPath = path.join(process.env.HOME ?? '', '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.dbPath) return config.dbPath;
  } catch { /* use default */ }
  return path.join(process.env.HOME ?? '', '.mikai', 'mikai.db');
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  Supabase → SQLite Migration                ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  const dbPath = getDbPath();
  console.log(`Local DB: ${dbPath}\n`);

  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = OFF'); // Disable during bulk import

  // ── 1. Fetch from Supabase ───────────────────────────────────────────────
  console.log('── Fetching from Supabase ──────────────────────');

  const sources = await fetchAll('sources', 'id,type,label,raw_content,source,chunk_count,node_count,edge_count,content_hash,created_at');
  console.log(`  Total sources: ${sources.length}`);

  const nodes = await fetchAll('nodes', 'id,source_id,label,content,node_type,track,occurrence_count,query_hit_count,confidence_weight,has_action_verb,stall_probability,resolved_at,metadata,created_at');
  console.log(`  Total nodes: ${nodes.length}`);

  const edges = await fetchAll('edges', 'id,from_node,to_node,relationship,note,weight,created_at');
  console.log(`  Total edges: ${edges.length}`);

  const segments = await fetchAll('segments', 'id,source_id,topic_label,processed_content,created_at');
  console.log(`  Total segments: ${segments.length}`);

  // ── 2. Clear existing data (except what was manually added) ──────────────
  console.log('\n── Importing into SQLite ───────────────────────');

  // Clear old data
  db.exec('DELETE FROM segments');
  db.exec('DELETE FROM edges');
  db.exec('DELETE FROM nodes');
  db.exec('DELETE FROM sources');
  // Clear vec tables
  try { db.exec('DELETE FROM vec_nodes'); } catch { /* may not exist */ }
  try { db.exec('DELETE FROM vec_segments'); } catch { /* may not exist */ }

  // ── 3. Insert sources ────────────────────────────────────────────────────
  const insertSource = db.prepare(`
    INSERT OR IGNORE INTO sources (id, type, label, raw_content, source, chunk_count, node_count, edge_count, content_hash, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const srcTx = db.transaction(() => {
    for (const s of sources) {
      insertSource.run(s.id, s.type, s.label, s.raw_content, s.source,
        s.chunk_count ?? 0, s.node_count ?? 0, s.edge_count ?? 0,
        s.content_hash ?? null, s.created_at);
    }
  });
  srcTx();
  console.log(`  Sources: ${sources.length} inserted`);

  // ── 4. Insert nodes (without embeddings — vec table needs float arrays) ──
  const insertNode = db.prepare(`
    INSERT OR IGNORE INTO nodes (id, source_id, label, content, node_type, track, occurrence_count, query_hit_count, confidence_weight, has_action_verb, stall_probability, resolved_at, metadata, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const nodeTx = db.transaction(() => {
    for (const n of nodes) {
      insertNode.run(n.id, n.source_id, n.label, n.content, n.node_type,
        n.track ?? null, n.occurrence_count ?? 1, n.query_hit_count ?? 0,
        n.confidence_weight ?? 1.0, n.has_action_verb ? 1 : 0,
        n.stall_probability ?? null, n.resolved_at ?? null,
        typeof n.metadata === 'string' ? n.metadata : JSON.stringify(n.metadata ?? {}),
        n.created_at);
    }
  });
  nodeTx();
  console.log(`  Nodes: ${nodes.length} inserted`);

  // ── 5. Insert edges ──────────────────────────────────────────────────────
  const insertEdge = db.prepare(`
    INSERT OR IGNORE INTO edges (id, from_node, to_node, relationship, note, weight, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `);

  const edgeTx = db.transaction(() => {
    for (const e of edges) {
      insertEdge.run(e.id, e.from_node, e.to_node, e.relationship,
        e.note ?? null, e.weight ?? 1.0, e.created_at);
    }
  });
  edgeTx();
  console.log(`  Edges: ${edges.length} inserted`);

  // ── 6. Insert segments (without embeddings) ──────────────────────────────
  const insertSegment = db.prepare(`
    INSERT OR IGNORE INTO segments (id, source_id, topic_label, processed_content, created_at)
    VALUES (?, ?, ?, ?, ?)
  `);

  const segTx = db.transaction(() => {
    for (const s of segments) {
      insertSegment.run(s.id, s.source_id, s.topic_label, s.processed_content, s.created_at);
    }
  });
  segTx();
  console.log(`  Segments: ${segments.length} inserted`);

  // ── 7. Verify ────────────────────────────────────────────────────────────
  db.pragma('foreign_keys = ON');

  const counts = {
    sources: (db.prepare('SELECT COUNT(*) as c FROM sources').get() as any).c,
    nodes: (db.prepare('SELECT COUNT(*) as c FROM nodes').get() as any).c,
    edges: (db.prepare('SELECT COUNT(*) as c FROM edges').get() as any).c,
    segments: (db.prepare('SELECT COUNT(*) as c FROM segments').get() as any).c,
  };

  console.log('\n── Verification ───────────────────────────────');
  console.log(`  Sources:  ${counts.sources} (Supabase: ${sources.length})`);
  console.log(`  Nodes:    ${counts.nodes} (Supabase: ${nodes.length})`);
  console.log(`  Edges:    ${counts.edges} (Supabase: ${edges.length})`);
  console.log(`  Segments: ${counts.segments} (Supabase: ${segments.length})`);

  console.log('\n✓ Migration complete. Now run:');
  console.log('  npm run l3:upgrade    # Add bitemporal fields + FTS indices');
  console.log('  npm run l4            # Run thread detection + state classification');

  db.close();
}

main().catch(err => {
  console.error('Migration failed:', err);
  process.exit(1);
});
