#!/usr/bin/env tsx
/**
 * engine/l3/run-l3-upgrade.ts
 * CLI for L3 Graphiti-inspired upgrade: migration + FTS sync.
 *
 * Usage:
 *   npx tsx engine/l3/run-l3-upgrade.ts              # full upgrade
 *   npx tsx engine/l3/run-l3-upgrade.ts --migrate-only
 *   npx tsx engine/l3/run-l3-upgrade.ts --sync-fts-only
 *   npm run l3:upgrade
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { openDatabase, initDatabase } from '../../lib/store-sqlite.js';
import { migrateToBitemporal } from './migrate-bitemporal.js';
import { syncFtsIndices } from './sync-fts.js';

// ── Env loader ───────────────────────────────────────────────────────────────

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function loadEnv(): void {
  const envPath = path.join(__dirname, '../../.env.local');
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
  } catch {
    // .env.local not found — env assumed already set
  }
}

loadEnv();

// ── Database ─────────────────────────────────────────────────────────────────

function getDbPath(): string {
  const configPath = path.join(process.env.HOME ?? '', '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.db_path) return config.db_path;
  } catch {
    // Use default
  }
  return path.join(process.env.HOME ?? '', '.mikai', 'mikai.db');
}

// ── CLI ──────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const migrateOnly = args.includes('--migrate-only');
const syncFtsOnly = args.includes('--sync-fts-only');

async function main(): Promise<void> {
  const startTime = Date.now();
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  MIKAI L3 — Graphiti-inspired Upgrade       ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  // Open database
  const dbPath = getDbPath();
  console.log(`Database: ${dbPath}`);
  const db = openDatabase(dbPath);
  initDatabase(db);
  console.log('L3 schema initialized.\n');

  // ── Stage 1: Bitemporal Migration ────────────────────────────────────────
  if (!syncFtsOnly) {
    console.log('── Stage 1: Bitemporal Migration ──────────────');
    const t1 = Date.now();
    migrateToBitemporal(db);
    console.log(`  Bitemporal columns added (idempotent).`);
    console.log(`  FTS5 virtual tables created (idempotent).`);
    console.log(`  Duration: ${Date.now() - t1}ms\n`);

    if (migrateOnly) {
      printStats(db);
      db.close();
      return;
    }
  }

  // ── Stage 2: FTS Sync ────────────────────────────────────────────────────
  if (!migrateOnly) {
    console.log('── Stage 2: FTS Index Sync ─────────────────────');
    const t2 = Date.now();
    const ftsCounts = syncFtsIndices(db);
    console.log(`  fts_nodes:    ${ftsCounts.nodes} rows`);
    console.log(`  fts_segments: ${ftsCounts.segments} rows`);
    console.log(`  fts_edges:    ${ftsCounts.edges} rows`);
    console.log(`  Duration: ${Date.now() - t2}ms\n`);
  }

  // ── Summary ──────────────────────────────────────────────────────────────
  printStats(db);
  console.log(`\nTotal upgrade time: ${Date.now() - startTime}ms`);

  db.close();
}

function printStats(db: any): void {
  console.log('── L3 Stats ──────────────────────────────────');

  try {
    const totalEdges = (db.prepare('SELECT COUNT(*) as count FROM edges').get() as { count: number }).count;
    const edgesWithValidAt = (db.prepare('SELECT COUNT(*) as count FROM edges WHERE valid_at IS NOT NULL').get() as { count: number }).count;
    console.log(`  Total edges: ${totalEdges}`);
    console.log(`  Edges with valid_at: ${edgesWithValidAt}`);
  } catch {
    console.log('  (edges table stats unavailable)');
  }

  for (const table of ['fts_nodes', 'fts_segments', 'fts_edges']) {
    try {
      const count = (db.prepare(`SELECT COUNT(*) as count FROM ${table}`).get() as { count: number }).count;
      console.log(`  ${table}: ${count} rows`);
    } catch {
      console.log(`  ${table}: unavailable`);
    }
  }
}

main().catch(err => {
  console.error('L3 upgrade failed:', err);
  process.exit(1);
});
