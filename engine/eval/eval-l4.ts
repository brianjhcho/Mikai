#!/usr/bin/env tsx
/**
 * engine/eval/eval-l4.ts
 *
 * L4 evaluation suite — modeled on MEMTRACK (NeurIPS 2025, arXiv:2510.01353).
 *
 * MEMTRACK's key insight: memory infrastructure alone doesn't solve cross-platform
 * state tracking. GPT-5 + Mem0/Zep ≈ no significant improvement over GPT-5 alone.
 * This eval tests whether MIKAI's L4 layer (the reasoning layer) actually adds value
 * on top of L3 memory.
 *
 * Three metrics (adapted from MEMTRACK):
 *   1. Detection accuracy — do detected threads match real topics? (precision/recall)
 *   2. State accuracy     — does the classified state match ground truth?
 *   3. Next-step relevance — is the suggested action useful? (1-5 human rating)
 *
 * Usage:
 *   npx tsx engine/eval/eval-l4.ts                 # full eval (detection + state)
 *   npx tsx engine/eval/eval-l4.ts --detection     # detection only
 *   npx tsx engine/eval/eval-l4.ts --state         # state accuracy only
 *   npx tsx engine/eval/eval-l4.ts --export        # export threads for labeling
 *   npx tsx engine/eval/eval-l4.ts --report        # show last eval results
 *
 * Ground truth: engine/eval/l4-ground-truth.json (manually labeled by user)
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { openDatabase, initDatabase } from '../../lib/store-sqlite.js';
import { initL4Schema } from '../l4/schema.js';
import { getActiveThreads, getThreadMembers, getStalledThreads } from '../l4/store.js';
import type { Thread, ThreadState } from '../l4/types.js';

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
  } catch { /* .env.local not found */ }
}

loadEnv();

// ── Database ─────────────────────────────────────────────────────────────────

function getDbPath(): string {
  const configPath = path.join(process.env.HOME ?? '', '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.db_path) return config.db_path;
  } catch { /* Use default */ }
  return path.join(process.env.HOME ?? '', '.mikai', 'mikai.db');
}

// ── Types ────────────────────────────────────────────────────────────────────

interface GroundTruthEntry {
  /** A human-readable label for the expected thread (e.g., "Kenya real estate research") */
  expected_label: string;
  /** Which source types should be grouped in this thread */
  expected_source_types: string[];
  /** What state is this thread really in */
  expected_state: ThreadState;
  /** What kind of action is appropriate (OmniActions category) */
  expected_action_category: string;
  /** Keywords that should appear in thread member content */
  keywords: string[];
  /** Optional notes about why this is the expected state */
  notes?: string;
}

interface GroundTruthFile {
  version: string;
  labeled_at: string;
  labeled_by: string;
  entries: GroundTruthEntry[];
}

interface ThreadMatchResult {
  ground_truth: GroundTruthEntry;
  matched_thread: Thread | null;
  detection_correct: boolean;
  state_correct: boolean;
  source_type_overlap: number;   // 0-1, Jaccard similarity
  match_confidence: number;       // how confident the match is
}

interface EvalReport {
  run_at: string;
  ground_truth_count: number;
  threads_in_db: number;

  // Detection metrics
  detection_precision: number;     // correct matches / total matches attempted
  detection_recall: number;        // correct matches / total ground truth entries
  detection_f1: number;

  // State metrics
  state_accuracy: number;          // correct state / total matched threads
  state_confusion: Record<string, Record<string, number>>;  // confusion matrix

  // Per-entry details
  details: ThreadMatchResult[];
}

// ── Ground truth file management ─────────────────────────────────────────────

const GROUND_TRUTH_PATH = path.join(__dirname, 'l4-ground-truth.json');
const EVAL_RESULTS_PATH = path.join(__dirname, 'results', 'l4-eval-latest.json');

function loadGroundTruth(): GroundTruthFile | null {
  try {
    return JSON.parse(fs.readFileSync(GROUND_TRUTH_PATH, 'utf8'));
  } catch {
    return null;
  }
}

function saveEvalReport(report: EvalReport): void {
  const resultsDir = path.join(__dirname, 'results');
  if (!fs.existsSync(resultsDir)) fs.mkdirSync(resultsDir, { recursive: true });

  fs.writeFileSync(EVAL_RESULTS_PATH, JSON.stringify(report, null, 2) + '\n');

  // Also save timestamped copy
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  fs.writeFileSync(
    path.join(resultsDir, `l4-eval-${timestamp}.json`),
    JSON.stringify(report, null, 2) + '\n',
  );
}

// ── Export threads for labeling ──────────────────────────────────────────────

function exportForLabeling(db: any): void {
  const active = getActiveThreads(db, 100);
  const stalled = getStalledThreads(db, 0.3, 50);

  const seen = new Set<string>();
  const allThreads: Thread[] = [];
  for (const t of [...stalled, ...active]) {
    if (seen.has(t.id)) continue;
    seen.add(t.id);
    allThreads.push(t);
  }

  console.log(`\nFound ${allThreads.length} threads to label.\n`);

  // Build export with context
  const exportEntries = allThreads.map(t => {
    const members = getThreadMembers(db, t.id);
    const segmentIds = members.filter(m => m.segment_id).map(m => m.segment_id!);

    // Get sample content
    let sampleContent: string[] = [];
    if (segmentIds.length > 0) {
      const placeholders = segmentIds.slice(0, 5).map(() => '?').join(',');
      const segments = db.prepare(`
        SELECT topic_label, substr(processed_content, 1, 200) as preview
        FROM segments WHERE id IN (${placeholders})
        ORDER BY created_at DESC
      `).all(...segmentIds.slice(0, 5)) as { topic_label: string; preview: string }[];
      sampleContent = segments.map((s: any) => `[${s.topic_label}] ${s.preview}`);
    }

    const sourceTypes: string[] = JSON.parse(t.source_types || '[]');

    return {
      thread_id: t.id,
      label: t.label,
      current_state: t.state,
      source_types: sourceTypes,
      source_count: t.source_count,
      member_count: members.length,
      first_seen: t.first_seen_at,
      last_activity: t.last_activity_at,
      confidence: t.confidence,
      stall_probability: t.stall_probability,
      sample_content: sampleContent,
      // Fields for you to fill in:
      _your_label: '',           // what would YOU call this thread?
      _your_state: '',           // exploring/evaluating/decided/acting/stalled/completed
      _your_action: '',          // search/create/share/schedule/navigate/configure
      _is_real_thread: null,     // true/false — is this a real coherent topic?
      _notes: '',
    };
  });

  const exportPath = path.join(__dirname, 'l4-threads-to-label.json');
  fs.writeFileSync(exportPath, JSON.stringify(exportEntries, null, 2) + '\n');
  console.log(`Exported to: ${exportPath}`);
  console.log(`\nInstructions:`);
  console.log(`  1. Open ${exportPath}`);
  console.log(`  2. For each thread, fill in _your_label, _your_state, _your_action, _is_real_thread`);
  console.log(`  3. Delete threads that are noise (not real topics)`);
  console.log(`  4. Save, then run: npx tsx engine/eval/eval-l4.ts --import`);
}

// ── Import labeled data into ground truth ────────────────────────────────────

function importLabeled(): void {
  const labeledPath = path.join(__dirname, 'l4-threads-to-label.json');
  if (!fs.existsSync(labeledPath)) {
    console.error('No labeled file found. Run --export first.');
    process.exit(1);
  }

  const labeled = JSON.parse(fs.readFileSync(labeledPath, 'utf8'));
  const entries: GroundTruthEntry[] = [];

  for (const item of labeled) {
    if (!item._is_real_thread) continue;
    if (!item._your_state) continue;

    entries.push({
      expected_label: item._your_label || item.label,
      expected_source_types: item.source_types,
      expected_state: item._your_state as ThreadState,
      expected_action_category: item._your_action || 'search',
      keywords: extractKeywords(item._your_label || item.label),
      notes: item._notes || undefined,
    });
  }

  const groundTruth: GroundTruthFile = {
    version: '1.0',
    labeled_at: new Date().toISOString(),
    labeled_by: 'brian',
    entries,
  };

  fs.writeFileSync(GROUND_TRUTH_PATH, JSON.stringify(groundTruth, null, 2) + '\n');
  console.log(`Imported ${entries.length} ground truth entries to ${GROUND_TRUTH_PATH}`);
}

function extractKeywords(label: string): string[] {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')
    .split(/\s+/)
    .filter(w => w.length > 3);
}

// ── Thread matching ──────────────────────────────────────────────────────────

function matchThreadToGroundTruth(
  thread: Thread,
  members: any[],
  db: any,
  entry: GroundTruthEntry,
): number {
  let score = 0;

  // Label similarity: check keyword overlap
  const threadLabel = thread.label.toLowerCase();
  const keywordHits = entry.keywords.filter(kw => threadLabel.includes(kw));
  score += (keywordHits.length / Math.max(entry.keywords.length, 1)) * 0.5;

  // Source type overlap (Jaccard)
  const threadSourceTypes: string[] = JSON.parse(thread.source_types || '[]');
  const intersection = entry.expected_source_types.filter(t => threadSourceTypes.includes(t));
  const union = new Set([...entry.expected_source_types, ...threadSourceTypes]);
  const jaccard = union.size > 0 ? intersection.length / union.size : 0;
  score += jaccard * 0.3;

  // Content keyword check: do thread member segments contain the keywords?
  const segmentIds = members.filter(m => m.segment_id).map(m => m.segment_id!);
  if (segmentIds.length > 0) {
    const placeholders = segmentIds.slice(0, 10).map(() => '?').join(',');
    const segments = db.prepare(`
      SELECT processed_content FROM segments WHERE id IN (${placeholders})
    `).all(...segmentIds.slice(0, 10)) as { processed_content: string }[];

    const allContent = segments.map(s => s.processed_content).join(' ').toLowerCase();
    const contentHits = entry.keywords.filter(kw => allContent.includes(kw));
    score += (contentHits.length / Math.max(entry.keywords.length, 1)) * 0.2;
  }

  return score;
}

// ── Eval runner ──────────────────────────────────────────────────────────────

function runEval(db: any, runDetection: boolean, runState: boolean): EvalReport {
  const groundTruth = loadGroundTruth();
  if (!groundTruth || groundTruth.entries.length === 0) {
    console.error('No ground truth found. Run --export, label the threads, then --import.');
    process.exit(1);
  }

  const allThreads = [...getStalledThreads(db, 0, 200), ...getActiveThreads(db, 200)];
  const seen = new Set<string>();
  const threads: Thread[] = [];
  for (const t of allThreads) {
    if (seen.has(t.id)) continue;
    seen.add(t.id);
    threads.push(t);
  }

  console.log(`\nGround truth entries: ${groundTruth.entries.length}`);
  console.log(`Threads in database: ${threads.length}\n`);

  const details: ThreadMatchResult[] = [];
  const stateConfusion: Record<string, Record<string, number>> = {};
  let detectionCorrect = 0;
  let stateCorrect = 0;
  let stateTotal = 0;

  for (const entry of groundTruth.entries) {
    // Find best matching thread
    let bestThread: Thread | null = null;
    let bestScore = 0;

    for (const thread of threads) {
      const members = getThreadMembers(db, thread.id);
      const score = matchThreadToGroundTruth(thread, members, db, entry);
      if (score > bestScore) {
        bestScore = score;
        bestThread = thread;
      }
    }

    // Threshold: match must score > 0.3 to count as a detection
    const MATCH_THRESHOLD = 0.3;
    const isDetected = bestThread !== null && bestScore > MATCH_THRESHOLD;

    if (isDetected) detectionCorrect++;

    // State accuracy (only for detected threads)
    let isStateCorrect = false;
    if (isDetected && bestThread) {
      isStateCorrect = bestThread.state === entry.expected_state;
      if (isStateCorrect) stateCorrect++;
      stateTotal++;

      // Confusion matrix
      const actual = bestThread.state;
      const expected = entry.expected_state;
      if (!stateConfusion[expected]) stateConfusion[expected] = {};
      stateConfusion[expected][actual] = (stateConfusion[expected][actual] ?? 0) + 1;
    }

    // Source type overlap
    const threadSourceTypes: string[] = bestThread ? JSON.parse(bestThread.source_types || '[]') : [];
    const intersection = entry.expected_source_types.filter(t => threadSourceTypes.includes(t));
    const union = new Set([...entry.expected_source_types, ...threadSourceTypes]);
    const sourceTypeOverlap = union.size > 0 ? intersection.length / union.size : 0;

    details.push({
      ground_truth: entry,
      matched_thread: isDetected ? bestThread : null,
      detection_correct: isDetected,
      state_correct: isStateCorrect,
      source_type_overlap: sourceTypeOverlap,
      match_confidence: bestScore,
    });
  }

  // Compute metrics
  const precision = details.length > 0 ? detectionCorrect / details.length : 0;
  const recall = groundTruth.entries.length > 0 ? detectionCorrect / groundTruth.entries.length : 0;
  const f1 = (precision + recall) > 0 ? 2 * (precision * recall) / (precision + recall) : 0;
  const stateAccuracy = stateTotal > 0 ? stateCorrect / stateTotal : 0;

  const report: EvalReport = {
    run_at: new Date().toISOString(),
    ground_truth_count: groundTruth.entries.length,
    threads_in_db: threads.length,
    detection_precision: Number(precision.toFixed(3)),
    detection_recall: Number(recall.toFixed(3)),
    detection_f1: Number(f1.toFixed(3)),
    state_accuracy: Number(stateAccuracy.toFixed(3)),
    state_confusion: stateConfusion,
    details,
  };

  return report;
}

// ── Display ──────────────────────────────────────────────────────────────────

function displayReport(report: EvalReport): void {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  MIKAI L4 Eval — MEMTRACK-inspired          ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  console.log(`  Run at:            ${report.run_at}`);
  console.log(`  Ground truth:      ${report.ground_truth_count} entries`);
  console.log(`  Threads in DB:     ${report.threads_in_db}`);
  console.log('');

  console.log('── Detection ──────────────────────────────────');
  console.log(`  Precision: ${(report.detection_precision * 100).toFixed(1)}%`);
  console.log(`  Recall:    ${(report.detection_recall * 100).toFixed(1)}%`);
  console.log(`  F1:        ${(report.detection_f1 * 100).toFixed(1)}%`);
  console.log('');

  console.log('── State Classification ────────────────────────');
  console.log(`  Accuracy:  ${(report.state_accuracy * 100).toFixed(1)}%`);
  if (Object.keys(report.state_confusion).length > 0) {
    console.log('  Confusion matrix (expected → actual):');
    for (const [expected, actuals] of Object.entries(report.state_confusion)) {
      for (const [actual, count] of Object.entries(actuals)) {
        const marker = expected === actual ? '✓' : '✗';
        console.log(`    ${marker} ${expected} → ${actual}: ${count}`);
      }
    }
  }
  console.log('');

  console.log('── Per-Entry Details ──────────────────────────');
  for (const d of report.details) {
    const det = d.detection_correct ? '✓' : '✗';
    const st = d.state_correct ? '✓' : '—';
    const matched = d.matched_thread
      ? `→ "${d.matched_thread.label}" (${d.matched_thread.state}, conf=${d.match_confidence.toFixed(2)})`
      : '→ NO MATCH';
    console.log(`  ${det}${st} "${d.ground_truth.expected_label}" [expect: ${d.ground_truth.expected_state}] ${matched}`);
  }

  console.log('');
  console.log('── Targets ────────────────────────────────────');
  console.log(`  Detection F1 target:    >70%  ${report.detection_f1 >= 0.7 ? '✓ PASS' : '✗ FAIL'}`);
  console.log(`  State accuracy target:  >50%  ${report.state_accuracy >= 0.5 ? '✓ PASS' : '✗ FAIL'}`);
}

// ── CLI ──────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const doExport = args.includes('--export');
const doImport = args.includes('--import');
const doReport = args.includes('--report');
const doDetection = args.includes('--detection') || (!doExport && !doImport && !doReport);
const doState = args.includes('--state') || (!doExport && !doImport && !doReport);

async function main(): Promise<void> {
  const dbPath = getDbPath();
  const db = openDatabase(dbPath);
  initDatabase(db);
  initL4Schema(db);

  if (doExport) {
    exportForLabeling(db);
    db.close();
    return;
  }

  if (doImport) {
    importLabeled();
    db.close();
    return;
  }

  if (doReport) {
    if (!fs.existsSync(EVAL_RESULTS_PATH)) {
      console.error('No eval results found. Run the eval first.');
      process.exit(1);
    }
    const report = JSON.parse(fs.readFileSync(EVAL_RESULTS_PATH, 'utf8'));
    displayReport(report);
    db.close();
    return;
  }

  // Run eval
  const report = runEval(db, doDetection, doState);
  saveEvalReport(report);
  displayReport(report);

  db.close();
}

main().catch(err => {
  console.error('L4 eval failed:', err);
  process.exit(1);
});
