#!/usr/bin/env tsx
/**
 * engine/l4/run-l4-pipeline.ts
 *
 * CLI entrypoint for the L4 task-state awareness pipeline.
 *
 * Stages:
 *   1. detect   — cluster segments into threads (zero LLM)
 *   2. classify — assign states to threads (zero LLM)
 *   3. infer    — generate next steps (one Haiku call per thread)
 *
 * Usage:
 *   npx tsx engine/l4/run-l4-pipeline.ts              # full pipeline
 *   npx tsx engine/l4/run-l4-pipeline.ts --detect-only
 *   npx tsx engine/l4/run-l4-pipeline.ts --skip-infer  # detect + classify only
 *   npx tsx engine/l4/run-l4-pipeline.ts --infer-only   # re-run inference on existing threads
 *   npx tsx engine/l4/run-l4-pipeline.ts --skip-resolve # skip entity resolution (Stage 0)
 *   npm run l4                                          # via package.json script
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { openDatabase, initDatabase } from '../../lib/store-sqlite.js';
import { initL4Schema } from './schema.js';
import { detectThreads, attachNewSegments } from './detect-threads.js';
import { classifyThreadStates } from './classify-state.js';
import { evaluateForDelivery } from './evaluate-delivery.js';
import { inferNextSteps } from './infer-next-step.js';
import { getL4Stats, insertDeliveryEvent } from './store.js';

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
const detectOnly = args.includes('--detect-only');
const classifyOnly = args.includes('--classify-only');
const inferOnly = args.includes('--infer-only');
const skipInfer = args.includes('--skip-infer');
const skipResolve = args.includes('--skip-resolve');

async function main(): Promise<void> {
  const startTime = Date.now();
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  MIKAI L4 — Task-State Awareness Pipeline   ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  // Open database
  const dbPath = getDbPath();
  console.log(`Database: ${dbPath}`);
  const db = openDatabase(dbPath);
  initDatabase(db);   // Ensure L3 tables exist
  initL4Schema(db);   // Ensure L4 tables exist
  console.log('L4 schema initialized.\n');

  // ── Stage 0: Entity Resolution (create cross-source edges in L3 graph) ──
  if (!inferOnly && !classifyOnly && !skipResolve) {
    console.log('── Stage 0: Entity Resolution ──────────────────');
    const startMs = Date.now();
    const { resolveEntities } = await import('../l3/entity-resolution.js');
    const resolveResult = await resolveEntities(db);
    console.log(`  Cross-source edges created: ${resolveResult.edgesCreated}`);
    console.log(`  Strong matches: ${resolveResult.strongMatches}`);
    console.log(`  Weak matches: ${resolveResult.weakMatches}`);
    console.log(`  Duration: ${((Date.now() - startMs) / 1000).toFixed(1)}s\n`);
  }

  // ── Stage 1: Detect Threads ──────────────────────────────────────────────
  if (!classifyOnly && !inferOnly) {
    console.log('── Stage 1: Thread Detection ──────────────────');
    const t1 = Date.now();

    // First try to attach orphans to existing threads
    const attachResult = await attachNewSegments(db);
    console.log(`  Attached ${attachResult.attached} segments to existing threads`);
    console.log(`  Created ${attachResult.newThreads} new threads from remaining segments`);
    console.log(`  Duration: ${Date.now() - t1}ms\n`);

    if (detectOnly) {
      printStats(db);
      db.close();
      return;
    }
  }

  // ── Stage 2: Classify States ─────────────────────────────────────────────
  if (!detectOnly && !inferOnly) {
    console.log('── Stage 2: State Classification ──────────────');
    const t2 = Date.now();

    const classResult = await classifyThreadStates(db);
    console.log(`  Classified ${classResult.threadsClassified} threads`);
    console.log(`  State changes: ${classResult.stateChanges}`);
    console.log(`  By state: ${JSON.stringify(classResult.byState)}`);
    console.log(`  Duration: ${Date.now() - t2}ms\n`);

    if (classifyOnly) {
      printStats(db);
      db.close();
      return;
    }
  }

  // ── Stage 3: Evaluation Gate (Sumimasen) ─────────────────────────────────
  let deliverableThreadIds: string[] | null = null;

  if (!detectOnly && !classifyOnly && !skipInfer) {
    console.log('── Stage 3: Evaluation Gate (Sumimasen) ───────');
    const tGate = Date.now();

    const evalResult = await evaluateForDelivery(db);
    deliverableThreadIds = evalResult.deliverableThreadIds;
    console.log(`  Evaluated ${evalResult.evaluated} threads`);
    console.log(`  Passed gate: ${deliverableThreadIds.length}`);
    console.log(`  Filtered: ${evalResult.filtered}`);
    console.log(`  Duration: ${Date.now() - tGate}ms\n`);
  }

  // ── Stage 4: Next-Step Inference (only gated threads) ───────────────────
  if (!detectOnly && !classifyOnly && !skipInfer && deliverableThreadIds && deliverableThreadIds.length > 0) {
    console.log('── Stage 4: Next-Step Inference (Haiku) ───────');
    const t4 = Date.now();

    const inferResult = await inferNextSteps(db, deliverableThreadIds);
    console.log(`  Processed ${inferResult.threadsProcessed} threads`);
    console.log(`  Next steps generated: ${inferResult.nextStepsGenerated}`);
    console.log(`  Errors: ${inferResult.errors}`);

    // Log delivery events for PPP training signal collection
    let deliveryEventsLogged = 0;
    for (const result of inferResult.results ?? []) {
      const threadRow = db.prepare('SELECT delivery_score FROM threads WHERE id = ?').get(result.thread_id) as { delivery_score: number } | undefined;
      insertDeliveryEvent(db, {
        thread_id: result.thread_id,
        next_step: result.next_step,
        action_category: result.action_category,
        delivery_score: threadRow?.delivery_score ?? 0,
      });
      deliveryEventsLogged++;
    }
    console.log(`  Delivery events logged: ${deliveryEventsLogged}`);
    console.log(`  Duration: ${Date.now() - t4}ms\n`);
  } else if (!detectOnly && !classifyOnly && !skipInfer) {
    console.log('── Stage 4: Skipped (no threads passed gate) ──\n');
  }

  // ── Summary ──────────────────────────────────────────────────────────────
  printStats(db);

  // Write progress file (Anthropic harness pattern)
  writeProgressFile(db, startTime);

  console.log(`\nTotal pipeline time: ${Date.now() - startTime}ms`);

  db.close();
}

function printStats(db: any): void {
  const stats = getL4Stats(db);
  console.log('── L4 Stats ──────────────────────────────────');
  console.log(`  Total threads: ${stats.totalThreads}`);
  console.log(`  By state: ${JSON.stringify(stats.byState)}`);
  console.log(`  Stalled: ${stats.stalledCount}`);
  console.log(`  With next steps: ${stats.withNextSteps}`);
  console.log(`  Avg sources/thread: ${stats.avgSourcesPerThread.toFixed(1)}`);
}

// ── Progress file (Anthropic harness pattern) ───────────────────────────────

function writeProgressFile(db: any, startTime: number): void {
  const stats = getL4Stats(db);
  const deliveryCount = (db.prepare('SELECT COUNT(*) as c FROM delivery_events').get() as any)?.c ?? 0;

  const progress = {
    last_run_at: new Date().toISOString(),
    duration_ms: Date.now() - startTime,
    threads_total: stats.totalThreads,
    threads_by_state: stats.byState,
    stalled_count: stats.stalledCount,
    with_next_steps: stats.withNextSteps,
    avg_sources_per_thread: Number(stats.avgSourcesPerThread.toFixed(1)),
    total_delivery_events: deliveryCount,
  };

  const progressPath = path.join(__dirname, '../../l4-progress.json');
  try {
    fs.writeFileSync(progressPath, JSON.stringify(progress, null, 2) + '\n');
  } catch {
    // Non-critical — don't fail the pipeline
  }
}

main().catch(err => {
  console.error('L4 pipeline failed:', err);
  process.exit(1);
});
