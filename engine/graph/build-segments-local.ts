#!/usr/bin/env tsx
/**
 * engine/graph/build-segments-local.ts
 *
 * Local-first segmentation pipeline. Replaces the Supabase + Voyage AI path.
 * Reads sources from SQLite, splits with smart-split.js, embeds with
 * Nomic nomic-embed-text-v1.5 (768-dim, local ONNX), writes segments +
 * embeddings directly to SQLite.
 *
 * Usage:
 *   npx tsx engine/graph/build-segments-local.ts
 *   npx tsx engine/graph/build-segments-local.ts --rebuild
 *   npx tsx engine/graph/build-segments-local.ts --sources gmail,apple-notes
 *   npx tsx engine/graph/build-segments-local.ts --preview
 *   npm run build-segments:local
 *   npm run build-segments:local:rebuild
 *
 * Default sources: all (apple-notes, perplexity, manual, claude-thread, gmail, imessage)
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { openDatabase, initDatabase } from '../../lib/store-sqlite.js';
import { embedDocuments } from '../../lib/embeddings-local.js';
import { smartSplit } from './smart-split.js';
import { randomUUID } from 'crypto';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── CLI options ──────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const flag = (name: string) => args.includes(name);
const option = (name: string, def: string) => {
  const i = args.indexOf(name);
  return i !== -1 && args[i + 1] ? args[i + 1] : def;
};

const REBUILD = flag('--rebuild');
const PREVIEW = flag('--preview');
const BATCH_SIZE = parseInt(option('--batch-size', '20'), 10);
const SOURCES_RAW = option('--sources', 'apple-notes,perplexity,manual,claude-thread,gmail,imessage');
const ALLOWED_SOURCES = new Set(SOURCES_RAW.split(',').map(s => s.trim()));

// Per-source minimum word thresholds (from SEGMENTATION_FRAMEWORK.md)
const MIN_WORDS: Record<string, number> = {
  'perplexity': 30,
  'claude-thread': 15,
  'manual': 20,
  'gmail': 15,
  'apple-notes': 10,
  'imessage': 20,
};

// ── Env ──────────────────────────────────────────────────────────────────────

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

// ── DB ───────────────────────────────────────────────────────────────────────

function getDbPath(): string {
  const configPath = path.join(process.env.HOME ?? '', '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.dbPath) return config.dbPath;
  } catch {}
  return path.join(process.env.HOME ?? '', '.mikai', 'mikai.db');
}

function toVec(embedding: number[]): Buffer {
  return Buffer.from(new Float32Array(embedding).buffer);
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  loadEnv();

  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  MIKAI — Local Segmentation Pipeline        ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  const dbPath = getDbPath();
  console.log(`Database: ${dbPath}`);
  console.log(`Sources: ${[...ALLOWED_SOURCES].join(', ')}`);
  console.log(`Rebuild: ${REBUILD}\n`);

  const db = openDatabase(dbPath);
  initDatabase(db);

  // ── Find sources to segment ────────────────────────────────────────────

  // Get already-segmented source IDs
  const segmentedIds = new Set<string>();
  if (!REBUILD) {
    const existing = db.prepare('SELECT DISTINCT source_id FROM segments').all() as { source_id: string }[];
    for (const r of existing) segmentedIds.add(r.source_id);
  }

  // Query sources from allowed types
  const sourcePlaceholders = [...ALLOWED_SOURCES].map(() => '?').join(',');
  const allSources = db.prepare(`
    SELECT id, label, source, raw_content, created_at
    FROM sources
    WHERE raw_content IS NOT NULL
      AND source IN (${sourcePlaceholders})
    ORDER BY created_at DESC
  `).all(...ALLOWED_SOURCES) as {
    id: string; label: string; source: string; raw_content: string; created_at: string;
  }[];

  const sources = allSources.filter(s => REBUILD || !segmentedIds.has(s.id));

  if (sources.length === 0) {
    console.log('No sources to segment. All sources have segments. Use --rebuild to re-segment.');
    db.close();
    return;
  }

  console.log(`${sources.length} source(s) to segment${REBUILD ? ' (rebuild mode)' : ''}\n`);

  // ── Process sources ────────────────────────────────────────────────────

  let totalSegments = 0;
  let totalSkipped = 0;
  let failed = 0;

  const insertSegment = db.prepare(`
    INSERT INTO segments (id, source_id, topic_label, processed_content, created_at)
    VALUES (?, ?, ?, ?, datetime('now'))
  `);

  const insertVec = db.prepare(`
    INSERT OR REPLACE INTO vec_segments (segment_id, embedding) VALUES (?, ?)
  `);

  const deleteSegments = db.prepare('DELETE FROM segments WHERE source_id = ?');
  const deleteVecs = db.prepare(`
    DELETE FROM vec_segments WHERE segment_id IN (
      SELECT id FROM segments WHERE source_id = ?
    )
  `);

  for (let i = 0; i < sources.length; i++) {
    const source = sources[i];
    const label = `"${source.label?.slice(0, 60)}" (${source.source})`;

    // Check word count against per-source threshold
    const wordCount = source.raw_content.split(/\s+/).filter(Boolean).length;
    const threshold = MIN_WORDS[source.source] ?? 50;

    if (wordCount < threshold) {
      totalSkipped++;
      continue;
    }

    try {
      // Split using source-type-aware splitter
      const segments = smartSplit(source.raw_content, source.source);

      if (segments.length === 0) {
        continue;
      }

      if (PREVIEW) {
        console.log(`  ${label} → ${segments.length} segment(s):`);
        for (const seg of segments) {
          console.log(`    [${seg.topic_label}] ${seg.condensed_content.slice(0, 120)}...`);
        }
        continue;
      }

      // Delete old segments if rebuilding
      if (REBUILD && segmentedIds.has(source.id)) {
        deleteVecs.run(source.id);
        deleteSegments.run(source.id);
      }

      // Generate local embeddings (Nomic 768-dim)
      const embeddings = await embedDocuments(segments.map(s => s.condensed_content));

      // Write segments + embeddings to SQLite
      const tx = db.transaction(() => {
        for (let j = 0; j < segments.length; j++) {
          const segId = randomUUID();
          insertSegment.run(
            segId,
            source.id,
            segments[j].topic_label.trim(),
            segments[j].condensed_content.trim(),
          );
          insertVec.run(segId, toVec(embeddings[j]));
        }
      });
      tx();

      totalSegments += segments.length;
      console.log(`  ${label} → ${segments.length} segment(s)`);

    } catch (err) {
      console.error(`  ${label} → FAILED: ${(err as Error).message}`);
      failed++;
    }

    // Progress
    if ((i + 1) % 50 === 0 || i === sources.length - 1) {
      console.log(`\n  [${i + 1}/${sources.length} sources, ${totalSegments} segments]\n`);
    }
  }

  if (!PREVIEW) {
    console.log(`\n── Results ────────────────────────────────────`);
    console.log(`  Sources processed: ${sources.length - totalSkipped - failed}`);
    console.log(`  Sources skipped (below threshold): ${totalSkipped}`);
    console.log(`  Sources failed: ${failed}`);
    console.log(`  Segments created: ${totalSegments}`);

    // Verify
    const segCount = (db.prepare('SELECT COUNT(*) as c FROM segments').get() as any).c;
    const vecCount = (db.prepare('SELECT COUNT(*) as c FROM vec_segments').get() as any).c;
    console.log(`\n  Total segments in DB: ${segCount}`);
    console.log(`  Total segment embeddings: ${vecCount}`);
  }

  db.close();
}

main().catch(err => {
  console.error('Segmentation failed:', err);
  process.exit(1);
});
