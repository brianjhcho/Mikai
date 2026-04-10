#!/usr/bin/env tsx
/**
 * engine/eval/diagnose-l4.ts
 *
 * L4 diagnostic — checks data quality before running eval.
 * Identifies structural problems in threads, segments, and classification.
 *
 * Usage:
 *   npx tsx engine/eval/diagnose-l4.ts
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { openDatabase, initDatabase } from '../../lib/store-sqlite.js';
import { initL4Schema } from '../l4/schema.js';

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

loadEnv();

// ── Diagnostic checks ───────────────────────────────────────────────────────

interface DiagResult {
  name: string;
  status: 'PASS' | 'WARN' | 'FAIL';
  detail: string;
  data?: any;
}

function check(name: string, status: 'PASS' | 'WARN' | 'FAIL', detail: string, data?: any): DiagResult {
  return { name, status, detail, data };
}

async function main() {
  const dbPath = getDbPath();
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  MIKAI L4 Diagnostic                        ║');
  console.log('╚══════════════════════════════════════════════╝\n');
  console.log(`Database: ${dbPath}\n`);

  const db = openDatabase(dbPath);
  initDatabase(db);
  initL4Schema(db);

  const results: DiagResult[] = [];

  // ── 1. Basic counts ───────────────────────────────────────────────────────

  const threadCount = (db.prepare('SELECT COUNT(*) as c FROM threads').get() as any).c;
  const memberCount = (db.prepare('SELECT COUNT(*) as c FROM thread_members').get() as any).c;
  const segmentCount = (db.prepare('SELECT COUNT(*) as c FROM segments').get() as any).c;
  const nodeCount = (db.prepare('SELECT COUNT(*) as c FROM nodes').get() as any).c;
  const sourceCount = (db.prepare('SELECT COUNT(*) as c FROM sources').get() as any).c;
  const edgeCount = (db.prepare('SELECT COUNT(*) as c FROM edges').get() as any).c;

  console.log('── 1. Data Counts ─────────────────────────────');
  console.log(`  Sources:  ${sourceCount}`);
  console.log(`  Nodes:    ${nodeCount}`);
  console.log(`  Segments: ${segmentCount}`);
  console.log(`  Edges:    ${edgeCount}`);
  console.log(`  Threads:  ${threadCount}`);
  console.log(`  Members:  ${memberCount}`);

  if (threadCount === 0) {
    results.push(check('threads_exist', 'FAIL', 'No threads in DB. Run: npm run l4:no-llm'));
    printResults(results);
    db.close();
    return;
  }

  // ── 2. Duplicate segments ─────────────────────────────────────────────────

  console.log('\n── 2. Duplicate Segments ──────────────────────');
  const dupSegs = db.prepare(`
    SELECT processed_content, COUNT(*) as cnt, GROUP_CONCAT(id, ',') as ids
    FROM segments
    GROUP BY processed_content
    HAVING cnt > 1
    ORDER BY cnt DESC
    LIMIT 10
  `).all() as { processed_content: string; cnt: number; ids: string }[];

  const totalDups = db.prepare(`
    SELECT SUM(cnt - 1) as total FROM (
      SELECT COUNT(*) as cnt FROM segments GROUP BY processed_content HAVING cnt > 1
    )
  `).get() as any;

  if (dupSegs.length > 0) {
    console.log(`  ${totalDups.total ?? 0} duplicate segments found (${dupSegs.length} distinct)`);
    for (const d of dupSegs.slice(0, 5)) {
      console.log(`    ${d.cnt}x: "${d.processed_content.slice(0, 80)}..."`);
    }
    results.push(check('duplicate_segments', 'FAIL',
      `${totalDups.total ?? 0} duplicate segments inflate thread sizes and corrupt kNN`,
      { count: totalDups.total, top: dupSegs.slice(0, 3).map(d => ({ count: d.cnt, preview: d.processed_content.slice(0, 60) })) }
    ));
  } else {
    console.log('  No duplicate segments found.');
    results.push(check('duplicate_segments', 'PASS', 'No duplicates'));
  }

  // ── 3. Cross-source thread distribution ───────────────────────────────────

  console.log('\n── 3. Cross-Source Threads ─────────────────────');
  const sourceDistribution = db.prepare(`
    SELECT source_count, COUNT(*) as thread_cnt
    FROM threads
    GROUP BY source_count
    ORDER BY source_count
  `).all() as { source_count: number; thread_cnt: number }[];

  for (const row of sourceDistribution) {
    const pct = ((row.thread_cnt / threadCount) * 100).toFixed(1);
    console.log(`  ${row.source_count} source(s): ${row.thread_cnt} threads (${pct}%)`);
  }

  const multiSourceThreads = sourceDistribution
    .filter(r => r.source_count > 1)
    .reduce((sum, r) => sum + r.thread_cnt, 0);
  const multiSourcePct = ((multiSourceThreads / threadCount) * 100).toFixed(1);

  if (multiSourceThreads < threadCount * 0.05) {
    results.push(check('cross_source', 'FAIL',
      `Only ${multiSourcePct}% multi-source threads. Cross-app detection is broken.`));
  } else if (multiSourceThreads < threadCount * 0.15) {
    results.push(check('cross_source', 'WARN',
      `${multiSourcePct}% multi-source threads. Low but possibly correct for this corpus.`));
  } else {
    results.push(check('cross_source', 'PASS', `${multiSourcePct}% multi-source threads`));
  }

  // ── 4. Entity resolution edge coverage ────────────────────────────────────

  console.log('\n── 4. Entity Resolution Edge Coverage ─────────');
  const crossSourceEdges = db.prepare(`
    SELECT COUNT(*) as c FROM edges e
    JOIN nodes n1 ON e.from_node = n1.id
    JOIN nodes n2 ON e.to_node = n2.id
    WHERE n1.source_id != n2.source_id
  `).get() as any;

  // How many of those edges have at least one node in NODE_SOURCE_TYPES?
  const usableEdges = db.prepare(`
    SELECT COUNT(*) as c FROM edges e
    JOIN nodes n1 ON e.from_node = n1.id
    JOIN nodes n2 ON e.to_node = n2.id
    JOIN sources s1 ON n1.source_id = s1.id
    JOIN sources s2 ON n2.source_id = s2.id
    WHERE n1.source_id != n2.source_id
      AND (s1.source IN ('apple-notes', 'manual') OR s2.source IN ('apple-notes', 'manual'))
  `).get() as any;

  // How many have BOTH nodes in NODE_SOURCE_TYPES?
  const bothUsable = db.prepare(`
    SELECT COUNT(*) as c FROM edges e
    JOIN nodes n1 ON e.from_node = n1.id
    JOIN nodes n2 ON e.to_node = n2.id
    JOIN sources s1 ON n1.source_id = s1.id
    JOIN sources s2 ON n2.source_id = s2.id
    WHERE n1.source_id != n2.source_id
      AND s1.source IN ('apple-notes', 'manual')
      AND s2.source IN ('apple-notes', 'manual')
  `).get() as any;

  console.log(`  Total cross-source edges:       ${crossSourceEdges.c}`);
  console.log(`  With >= 1 node in apple-notes/manual: ${usableEdges.c}`);
  console.log(`  With BOTH nodes in apple-notes/manual: ${bothUsable.c}`);
  console.log(`  Edges completely invisible to L4: ${crossSourceEdges.c - usableEdges.c}`);

  // Show what source types are being excluded
  const edgeSourceTypes = db.prepare(`
    SELECT s1.source as from_source, s2.source as to_source, COUNT(*) as cnt
    FROM edges e
    JOIN nodes n1 ON e.from_node = n1.id
    JOIN nodes n2 ON e.to_node = n2.id
    JOIN sources s1 ON n1.source_id = s1.id
    JOIN sources s2 ON n2.source_id = s2.id
    WHERE n1.source_id != n2.source_id
    GROUP BY s1.source, s2.source
    ORDER BY cnt DESC
  `).all() as { from_source: string; to_source: string; cnt: number }[];

  console.log('  Edge distribution by source pair:');
  for (const row of edgeSourceTypes) {
    const inFilter = ['apple-notes', 'manual'];
    const fromIn = inFilter.includes(row.from_source) ? '✓' : '✗';
    const toIn = inFilter.includes(row.to_source) ? '✓' : '✗';
    console.log(`    ${fromIn}${row.from_source} ↔ ${toIn}${row.to_source}: ${row.cnt} edges`);
  }

  if (crossSourceEdges.c > 0 && usableEdges.c / crossSourceEdges.c < 0.3) {
    results.push(check('edge_coverage', 'FAIL',
      `${((1 - usableEdges.c / crossSourceEdges.c) * 100).toFixed(0)}% of entity resolution edges are invisible to L4 due to NODE_SOURCE_TYPES filter`));
  } else {
    results.push(check('edge_coverage', 'PASS', 'Most entity resolution edges are usable'));
  }

  // ── 5. Nodes by source type (what's being excluded) ───────────────────────

  console.log('\n── 5. Nodes by Source Type ─────────────────────');
  const nodesBySource = db.prepare(`
    SELECT src.source, COUNT(*) as cnt
    FROM nodes n
    JOIN sources src ON n.source_id = src.id
    GROUP BY src.source
    ORDER BY cnt DESC
  `).all() as { source: string; cnt: number }[];

  let includedNodes = 0;
  let excludedNodes = 0;
  for (const row of nodesBySource) {
    const inFilter = ['apple-notes', 'manual'].includes(row.source);
    const marker = inFilter ? '✓ IN' : '✗ OUT';
    console.log(`  ${marker}  ${row.source}: ${row.cnt} nodes`);
    if (inFilter) includedNodes += row.cnt;
    else excludedNodes += row.cnt;
  }
  console.log(`  Included: ${includedNodes} | Excluded: ${excludedNodes} (${((excludedNodes / (includedNodes + excludedNodes)) * 100).toFixed(0)}% lost)`);

  if (excludedNodes > includedNodes * 2) {
    results.push(check('node_coverage', 'WARN',
      `${excludedNodes} nodes excluded by NODE_SOURCE_TYPES filter. Consider expanding to include gmail/perplexity nodes.`));
  }

  // ── 6. State classification sanity ────────────────────────────────────────

  console.log('\n── 6. State Classification Sanity ──────────────');

  // Check: "acting" threads that are only from perplexity (research, not acting)
  const actingPerplexity = db.prepare(`
    SELECT COUNT(*) as c FROM threads
    WHERE state = 'acting' AND source_types = '["perplexity"]'
  `).get() as any;

  const actingTotal = db.prepare(`
    SELECT COUNT(*) as c FROM threads WHERE state = 'acting'
  `).get() as any;

  console.log(`  "acting" threads from only perplexity: ${actingPerplexity.c}/${actingTotal.c}`);

  if (actingPerplexity.c > actingTotal.c * 0.3) {
    results.push(check('state_acting_accuracy', 'FAIL',
      `${actingPerplexity.c}/${actingTotal.c} "acting" threads are perplexity-only. Research ≠ acting. Classification is misfiring on action keywords in research content.`));
  } else {
    results.push(check('state_acting_accuracy', 'PASS', 'Acting state distribution looks reasonable'));
  }

  // Check: "completed" threads — what source types?
  const completedSources = db.prepare(`
    SELECT source_types, COUNT(*) as cnt FROM threads
    WHERE state = 'completed'
    GROUP BY source_types
    ORDER BY cnt DESC
    LIMIT 5
  `).get() as any;
  if (completedSources) {
    console.log(`  Top "completed" source: ${completedSources.source_types} (${completedSources.cnt})`);
  }

  // ── 7. Thread size distribution ───────────────────────────────────────────

  console.log('\n── 7. Thread Size Distribution ─────────────────');
  const sizeDistribution = db.prepare(`
    SELECT
      CASE
        WHEN member_count = 1 THEN '1 (singleton)'
        WHEN member_count BETWEEN 2 AND 5 THEN '2-5'
        WHEN member_count BETWEEN 6 AND 15 THEN '6-15'
        WHEN member_count BETWEEN 16 AND 50 THEN '16-50'
        ELSE '50+'
      END as bucket,
      COUNT(*) as cnt
    FROM (
      SELECT tm.thread_id, COUNT(*) as member_count
      FROM thread_members tm
      GROUP BY tm.thread_id
    )
    GROUP BY bucket
    ORDER BY
      CASE bucket
        WHEN '1 (singleton)' THEN 1
        WHEN '2-5' THEN 2
        WHEN '6-15' THEN 3
        WHEN '16-50' THEN 4
        ELSE 5
      END
  `).all() as { bucket: string; cnt: number }[];

  for (const row of sizeDistribution) {
    console.log(`  ${row.bucket} members: ${row.cnt} threads`);
  }

  // ── 8. Thread label quality ───────────────────────────────────────────────

  console.log('\n── 8. Thread Label Quality (sample) ───────────');
  const sampleThreads = db.prepare(`
    SELECT t.id, t.label, t.state, t.source_count, t.confidence,
           (SELECT COUNT(*) FROM thread_members tm WHERE tm.thread_id = t.id) as member_count
    FROM threads t
    ORDER BY RANDOM()
    LIMIT 15
  `).all() as any[];

  for (const t of sampleThreads) {
    const truncated = t.label.length > 60;
    const isQueryText = t.label.includes('?') || t.label.toLowerCase().startsWith('what ') || t.label.toLowerCase().startsWith('how ');
    const marker = truncated || isQueryText ? '⚠' : '✓';
    console.log(`  ${marker} [${t.state}] "${t.label.slice(0, 70)}${truncated ? '...' : ''}" (${t.member_count} members, ${t.source_count} sources)`);
  }

  // ── 9. Sample thread deep inspection ──────────────────────────────────────

  console.log('\n── 9. Deep Inspection (3 random threads) ──────');
  const deepSample = db.prepare(`
    SELECT t.id, t.label, t.state, t.source_types, t.confidence, t.source_count
    FROM threads t
    ORDER BY RANDOM()
    LIMIT 3
  `).all() as any[];

  for (const t of deepSample) {
    console.log(`\n  Thread: "${t.label.slice(0, 70)}"`);
    console.log(`  State: ${t.state} | Sources: ${t.source_types} | Confidence: ${t.confidence}`);

    const members = db.prepare(`
      SELECT tm.segment_id, tm.node_id, tm.contribution_type
      FROM thread_members tm
      WHERE tm.thread_id = ?
    `).all(t.id) as any[];

    const segIds = members.filter((m: any) => m.segment_id).map((m: any) => m.segment_id);
    const nodeIds = members.filter((m: any) => m.node_id).map((m: any) => m.node_id);

    console.log(`  Members: ${segIds.length} segments, ${nodeIds.length} nodes`);

    // Show segment previews
    if (segIds.length > 0) {
      const placeholders = segIds.slice(0, 4).map(() => '?').join(',');
      const segs = db.prepare(`
        SELECT topic_label, substr(processed_content, 1, 120) as preview, source_id
        FROM segments WHERE id IN (${placeholders})
      `).all(...segIds.slice(0, 4)) as any[];

      const uniqueContent = new Set(segs.map((s: any) => s.preview));
      if (uniqueContent.size < segs.length) {
        console.log(`  ⚠ DUPLICATES: ${segs.length} segments but only ${uniqueContent.size} unique`);
      }

      for (const s of segs) {
        console.log(`    [${s.topic_label.slice(0, 40)}] ${s.preview.slice(0, 80)}...`);
      }
    }

    // Show node previews
    if (nodeIds.length > 0) {
      const placeholders = nodeIds.slice(0, 3).map(() => '?').join(',');
      const nodes = db.prepare(`
        SELECT label, node_type FROM nodes WHERE id IN (${placeholders})
      `).all(...nodeIds.slice(0, 3)) as any[];

      for (const n of nodes) {
        console.log(`    [${n.node_type}] ${n.label}`);
      }
    }
  }

  // ── 10. Segments not in any thread ────────────────────────────────────────

  console.log('\n── 10. Orphan Coverage ────────────────────────');
  const orphanSegs = (db.prepare(`
    SELECT COUNT(*) as c FROM segments
    WHERE id NOT IN (SELECT segment_id FROM thread_members WHERE segment_id IS NOT NULL)
  `).get() as any).c;
  const orphanNodes = (db.prepare(`
    SELECT COUNT(*) as c FROM nodes
    WHERE id NOT IN (SELECT node_id FROM thread_members WHERE node_id IS NOT NULL)
  `).get() as any).c;

  console.log(`  Segments not in any thread: ${orphanSegs}/${segmentCount} (${((orphanSegs / segmentCount) * 100).toFixed(1)}%)`);
  console.log(`  Nodes not in any thread:    ${orphanNodes}/${nodeCount} (${((orphanNodes / nodeCount) * 100).toFixed(1)}%)`);

  // ── Summary ───────────────────────────────────────────────────────────────

  printResults(results);

  db.close();
}

function printResults(results: DiagResult[]): void {
  console.log('\n══════════════════════════════════════════════');
  console.log('  DIAGNOSTIC SUMMARY');
  console.log('══════════════════════════════════════════════\n');

  const fails = results.filter(r => r.status === 'FAIL');
  const warns = results.filter(r => r.status === 'WARN');
  const passes = results.filter(r => r.status === 'PASS');

  for (const r of fails) {
    console.log(`  ✗ FAIL  ${r.name}: ${r.detail}`);
  }
  for (const r of warns) {
    console.log(`  ⚠ WARN  ${r.name}: ${r.detail}`);
  }
  for (const r of passes) {
    console.log(`  ✓ PASS  ${r.name}: ${r.detail}`);
  }

  console.log(`\n  ${passes.length} passed, ${warns.length} warnings, ${fails.length} failures`);

  if (fails.length > 0) {
    console.log('\n── Recommended Fixes (in order) ───────────────');
    for (const f of fails) {
      switch (f.name) {
        case 'threads_exist':
          console.log('  1. Run the pipeline: npm run l4:no-llm');
          break;
        case 'duplicate_segments':
          console.log('  1. Deduplicate segments: DELETE duplicates keeping one per content hash');
          console.log('     Then rebuild segment embeddings and re-run thread detection');
          break;
        case 'cross_source':
          console.log('  2. Expand NODE_SOURCE_TYPES in detect-threads.ts to include more source types');
          console.log('     Or: fix graph-edge merging to work with segment-level items, not just nodes');
          break;
        case 'edge_coverage':
          console.log('  3. Entity resolution edges are wasted because NODE_SOURCE_TYPES excludes');
          console.log('     the source types they connect. Either expand the filter or make graph-edge');
          console.log('     merging resolve through segments (not just nodes) in the item map.');
          break;
        case 'state_acting_accuracy':
          console.log('  4. Action patterns in classify-state.ts fire on research content.');
          console.log('     Fix: require source_type != perplexity for "acting" classification,');
          console.log('     or weight action signals lower for research-only threads.');
          break;
      }
    }
  }
}

main().catch(err => {
  console.error('Diagnostic failed:', err);
  process.exit(1);
});
