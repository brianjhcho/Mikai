#!/usr/bin/env tsx
/**
 * CLI runner for L3 entity resolution.
 * Creates cross-source edges between semantically equivalent entities.
 *
 * Usage:
 *   npx tsx engine/l3/run-entity-resolution.ts
 *   npx tsx engine/l3/run-entity-resolution.ts --force    # re-resolve all nodes
 *   npm run l3:resolve
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import Database from 'better-sqlite3';
import * as sqliteVec from 'sqlite-vec';

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
  } catch {}
}

function getDbPath(): string {
  const configPath = path.join(process.env.HOME ?? '', '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.dbPath) return config.dbPath;
  } catch {}
  return path.join(process.env.HOME ?? '', '.mikai', 'mikai.db');
}

async function main() {
  loadEnv();

  const args = process.argv.slice(2);
  const forceAll = args.includes('--force');

  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  MIKAI L3 — Entity Resolution               ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  const dbPath = getDbPath();
  console.log(`Database: ${dbPath}`);

  const db = new Database(dbPath);
  sqliteVec.load(db);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  const { resolveEntities } = await import('./entity-resolution.js');

  const result = await resolveEntities(db, { forceAll });

  console.log('\n── Results ────────────────────────────────────');
  console.log(`  Nodes processed: ${result.nodesProcessed}`);
  console.log(`  Edges created: ${result.edgesCreated}`);
  console.log(`  Strong matches: ${result.strongMatches}`);
  console.log(`  Weak matches: ${result.weakMatches}`);
  console.log(`  Skipped (already resolved): ${result.skippedAlreadyResolved}`);
  console.log(`  Duration: ${(result.durationMs / 1000).toFixed(1)}s`);

  db.close();
}

main().catch(err => {
  console.error('Entity resolution failed:', err);
  process.exit(1);
});
