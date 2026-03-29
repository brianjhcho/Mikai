#!/usr/bin/env tsx
/**
 * engine/l4/backfill-sources.ts
 *
 * One-time backfill: creates missing `sources` rows for segments that have
 * a source_id in the segments table but no corresponding row in sources.
 *
 * Root cause: the local-files sync wrote segments with source_ids from
 * .synced.json but never inserted the source record into the sources table.
 * This left ~12K segments (mostly Perplexity exports) invisible to L4's
 * cross-source thread detection.
 *
 * Usage:
 *   npx tsx engine/l4/backfill-sources.ts              # dry run
 *   npx tsx engine/l4/backfill-sources.ts --apply       # apply changes
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { openDatabase, initDatabase } from '../../lib/store-sqlite.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SYNCED_PATH = path.join(__dirname, '../../sources/local-files/.synced.json');
const apply = process.argv.includes('--apply');

function getDbPath(): string {
  const configPath = path.join(process.env.HOME ?? '', '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.db_path) return config.db_path;
  } catch { /* default */ }
  return path.join(process.env.HOME ?? '', '.mikai', 'mikai.db');
}

function inferSourceType(filePath: string): string {
  if (filePath.includes('/perplexity/')) return 'perplexity';
  if (filePath.includes('/claude/') || filePath.includes('/claude-thread/')) return 'claude-thread';
  if (filePath.includes('/apple-notes/')) return 'apple-notes';
  if (filePath.includes('/gmail/')) return 'gmail';
  if (filePath.includes('/imessage/')) return 'imessage';
  return 'manual';
}

async function main() {
  console.log(apply ? '=== APPLYING BACKFILL ===' : '=== DRY RUN (pass --apply to commit) ===');

  // Load synced.json
  if (!fs.existsSync(SYNCED_PATH)) {
    console.error(`Synced file not found: ${SYNCED_PATH}`);
    process.exit(1);
  }
  const synced: Record<string, { source_id?: string; label?: string; synced_at?: string }> =
    JSON.parse(fs.readFileSync(SYNCED_PATH, 'utf8'));

  // Build map: source_id → { type, label, path }
  const sourceMap = new Map<string, { type: string; label: string; path: string }>();
  for (const [filePath, entry] of Object.entries(synced)) {
    if (!entry.source_id) continue;
    if (sourceMap.has(entry.source_id)) continue;
    sourceMap.set(entry.source_id, {
      type: inferSourceType(filePath),
      label: entry.label || path.basename(filePath, path.extname(filePath)),
      path: filePath,
    });
  }

  console.log(`Found ${sourceMap.size} source_ids in .synced.json`);

  // Open database
  const db = openDatabase(getDbPath());
  initDatabase(db);

  // Find which source_ids are missing from the sources table
  const existingIds = new Set<string>();
  const rows = db.prepare('SELECT id FROM sources').all() as { id: string }[];
  for (const row of rows) existingIds.add(row.id);

  const missing: { id: string; type: string; label: string }[] = [];
  for (const [id, info] of sourceMap) {
    if (!existingIds.has(id)) {
      missing.push({ id, type: info.type, label: info.label });
    }
  }

  console.log(`Existing sources: ${existingIds.size}`);
  console.log(`Missing sources to backfill: ${missing.length}`);

  // Count by type
  const byType: Record<string, number> = {};
  for (const m of missing) {
    byType[m.type] = (byType[m.type] ?? 0) + 1;
  }
  console.log(`By type: ${JSON.stringify(byType)}`);

  // Count affected segments
  const orphanSegments = (db.prepare(`
    SELECT COUNT(*) as c FROM segments
    WHERE source_id NOT IN (SELECT id FROM sources)
    AND source_id IS NOT NULL
  `).get() as any).c;
  console.log(`Orphan segments that will be fixed: ${orphanSegments}`);

  if (!apply) {
    console.log('\nDry run complete. Pass --apply to insert missing sources.');
    db.close();
    return;
  }

  // Insert missing sources
  const insertStmt = db.prepare(`
    INSERT INTO sources (id, type, source, label, raw_content, created_at)
    VALUES (?, ?, ?, ?, '', datetime('now'))
  `);

  const tx = db.transaction(() => {
    for (const m of missing) {
      insertStmt.run(m.id, m.type, m.type, m.label);
    }
  });
  tx();

  console.log(`\nInserted ${missing.length} sources.`);

  // Verify
  const remaining = (db.prepare(`
    SELECT COUNT(*) as c FROM segments
    WHERE source_id NOT IN (SELECT id FROM sources)
    AND source_id IS NOT NULL
  `).get() as any).c;
  console.log(`Remaining orphan segments: ${remaining}`);

  db.close();
  console.log('Done.');
}

main().catch(err => {
  console.error('Backfill failed:', err);
  process.exit(1);
});
