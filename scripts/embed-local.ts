#!/usr/bin/env tsx
/**
 * scripts/embed-local.ts
 *
 * Generate local embeddings (Nomic 768-dim) for all nodes and segments
 * that don't have embeddings in vec_nodes / vec_segments yet.
 *
 * Usage: npx tsx scripts/embed-local.ts [--nodes-only] [--segments-only] [--batch-size 50]
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { openDatabase, initDatabase } from '../lib/store-sqlite.js';
import { embedText } from '../lib/embeddings-local.js';

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

// ── Config ───────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const nodesOnly = args.includes('--nodes-only');
const segmentsOnly = args.includes('--segments-only');
const batchSizeArg = args.indexOf('--batch-size');
const BATCH_SIZE = batchSizeArg !== -1 ? parseInt(args[batchSizeArg + 1] ?? '50') : 50;

function toVec(embedding: number[]): Buffer {
  return Buffer.from(new Float32Array(embedding).buffer);
}

// ── DB ───────────────────────────────────────────────────────────────────────

function getDbPath(): string {
  const configPath = path.join(process.env.HOME ?? '', '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.dbPath) return config.dbPath;
  } catch { /* default */ }
  return path.join(process.env.HOME ?? '', '.mikai', 'mikai.db');
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  MIKAI — Local Embedding Generation         ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  const dbPath = getDbPath();
  console.log(`Database: ${dbPath}`);
  const db = openDatabase(dbPath);
  initDatabase(db);

  // Find nodes/segments without embeddings in vec tables
  const existingVecNodes = new Set<string>();
  const existingVecSegs = new Set<string>();

  try {
    const vecNodeRows = db.prepare('SELECT node_id FROM vec_nodes').all() as { node_id: string }[];
    for (const r of vecNodeRows) existingVecNodes.add(r.node_id);
  } catch { /* vec table may be empty */ }

  try {
    const vecSegRows = db.prepare('SELECT segment_id FROM vec_segments').all() as { segment_id: string }[];
    for (const r of vecSegRows) existingVecSegs.add(r.segment_id);
  } catch { /* vec table may be empty */ }

  // ── Embed Nodes ──────────────────────────────────────────────────────────
  if (!segmentsOnly) {
    const allNodes = db.prepare('SELECT id, label, content FROM nodes').all() as { id: string; label: string; content: string }[];
    const needsEmbedding = allNodes.filter(n => !existingVecNodes.has(n.id));
    console.log(`\n── Nodes: ${needsEmbedding.length} need embeddings (${existingVecNodes.size} already done) ──`);

    const insertVec = db.prepare('INSERT OR REPLACE INTO vec_nodes (node_id, embedding) VALUES (?, ?)');
    let done = 0;

    for (let i = 0; i < needsEmbedding.length; i += BATCH_SIZE) {
      const batch = needsEmbedding.slice(i, i + BATCH_SIZE);

      for (const node of batch) {
        const text = `${node.label}: ${node.content}`.slice(0, 512);
        try {
          const embedding = await embedText(text);
          insertVec.run(node.id, toVec(embedding));
          done++;
        } catch (err) {
          console.error(`  Error embedding node ${node.id}:`, (err as Error).message);
        }
      }

      const pct = ((done / needsEmbedding.length) * 100).toFixed(1);
      process.stderr.write(`  Nodes: ${done}/${needsEmbedding.length} (${pct}%)\r`);
    }
    console.log(`  Nodes: ${done}/${needsEmbedding.length} embedded.`);
  }

  // ── Embed Segments ───────────────────────────────────────────────────────
  if (!nodesOnly) {
    const allSegments = db.prepare('SELECT id, topic_label, processed_content FROM segments').all() as { id: string; topic_label: string; processed_content: string }[];
    const needsEmbedding = allSegments.filter(s => !existingVecSegs.has(s.id));
    console.log(`\n── Segments: ${needsEmbedding.length} need embeddings (${existingVecSegs.size} already done) ──`);

    const insertVec = db.prepare('INSERT OR REPLACE INTO vec_segments (segment_id, embedding) VALUES (?, ?)');
    let done = 0;
    const startTime = Date.now();

    for (let i = 0; i < needsEmbedding.length; i += BATCH_SIZE) {
      const batch = needsEmbedding.slice(i, i + BATCH_SIZE);

      for (const seg of batch) {
        const text = `${seg.topic_label}: ${seg.processed_content}`.slice(0, 512);
        try {
          const embedding = await embedText(text);
          insertVec.run(seg.id, toVec(embedding));
          done++;
        } catch (err) {
          console.error(`  Error embedding segment ${seg.id}:`, (err as Error).message);
        }
      }

      const elapsed = (Date.now() - startTime) / 1000;
      const rate = done / elapsed;
      const remaining = (needsEmbedding.length - done) / rate;
      const pct = ((done / needsEmbedding.length) * 100).toFixed(1);
      process.stderr.write(`  Segments: ${done}/${needsEmbedding.length} (${pct}%) — ${rate.toFixed(1)}/s, ~${Math.ceil(remaining)}s remaining\r`);
    }
    console.log(`  Segments: ${done}/${needsEmbedding.length} embedded.`);
  }

  // ── Verify ─────────────────────────────────────────────────────────────
  console.log('\n── Verification ──');
  try {
    const vn = (db.prepare('SELECT COUNT(*) as c FROM vec_nodes').get() as any).c;
    const vs = (db.prepare('SELECT COUNT(*) as c FROM vec_segments').get() as any).c;
    console.log(`  vec_nodes: ${vn}`);
    console.log(`  vec_segments: ${vs}`);
  } catch (e) {
    console.log(`  vec tables: ${(e as Error).message}`);
  }

  console.log('\n✓ Embedding complete. Now run:');
  console.log('  npm run l4    # Thread detection + state classification');

  db.close();
}

main().catch(err => {
  console.error('Embedding failed:', err);
  process.exit(1);
});
