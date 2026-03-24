/**
 * engine/eval/eval-stall.ts
 *
 * Stall detection quality evaluation — validates whether getTopStalledNodes()
 * returns items Brian would actually act on if surfaced via WhatsApp.
 *
 * Phase 3 gate prerequisite: ≥60% of top nodes must score yes/yes.
 * Results feed into the decision: proceed to Phase 3 vs. fix O-024 first.
 *
 * Run: npm run eval:stall
 */

import * as readline from 'readline';
import * as fs from 'fs';
import * as path from 'path';
import { createClient } from '@supabase/supabase-js';

// Load .env.local manually (no dotenv dependency)
const envPath = path.resolve(process.cwd(), '.env.local');
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, 'utf-8').split('\n')) {
    const match = line.match(/^([^#=]+)=(.*)$/);
    if (match) process.env[match[1].trim()] = match[2].trim();
  }
}

// ── Supabase ───────────────────────────────────────────────────────────────────

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables.');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

// ── Types ──────────────────────────────────────────────────────────────────────

interface StallNode {
  id: string;
  label: string;
  content: string;
  node_type: string;
  stall_probability: number;
  track: string | null;
  occurrence_count: number;
  created_at: string;
  days_since_first_seen: number; // computed from created_at
  has_action_verb: boolean;
  source_label: string | null;
}

interface NodeRating {
  node: StallNode;
  genuinelyStalled: boolean;
  wouldAct: boolean;
  note: string;
  hit: boolean; // yes/yes
}

interface EvalResult {
  timestamp: string;
  node_count: number;
  nodes: NodeRating[];
  summary: {
    actionableHitRate: number;
    genuinelyStalledRate: number;
    wouldActRate: number;
    trackBreakdown: {
      A: { total: number; hits: number };
      B: { total: number; hits: number };
    };
    verdict: 'PASS' | 'FIX_NOISE' | 'RECALIBRATE';
  };
}

// ── Fetch nodes ────────────────────────────────────────────────────────────────

async function fetchTopStalledNodes(limit = 15): Promise<StallNode[]> {
  const { data: nodes, error } = await supabase
    .from('nodes')
    .select(
      'id, label, content, node_type, stall_probability, track, occurrence_count, created_at, has_action_verb, source_id'
    )
    .gt('stall_probability', 0.5)
    .order('stall_probability', { ascending: false })
    .limit(limit);

  if (error || !nodes) {
    console.error('Supabase query failed:', error?.message);
    process.exit(1);
  }

  if (nodes.length === 0) {
    console.error('No nodes with stall_probability > 0.5. Run: npm run run-rule-engine');
    process.exit(1);
  }

  // Fetch source labels
  const sourceIds = Array.from(new Set(nodes.map((n) => n.source_id).filter(Boolean))) as string[];
  const sourceMap = new Map<string, string>();

  if (sourceIds.length > 0) {
    const { data: sources } = await supabase
      .from('sources')
      .select('id, label')
      .in('id', sourceIds);

    for (const s of sources ?? []) {
      sourceMap.set(s.id, s.label);
    }
  }

  return nodes.map((n) => {
    const days = n.created_at
      ? Math.floor((Date.now() - new Date(n.created_at).getTime()) / (1000 * 60 * 60 * 24))
      : 0;
    return {
      id: n.id,
      label: n.label,
      content: n.content,
      node_type: n.node_type,
      stall_probability: n.stall_probability ?? 0,
      track: n.track ?? null,
      created_at: n.created_at ?? '',
      occurrence_count: n.occurrence_count ?? 1,
      days_since_first_seen: days,
      has_action_verb: n.has_action_verb ?? false,
      source_label: n.source_id ? (sourceMap.get(n.source_id) ?? null) : null,
    };
  });
}

// ── Display node ───────────────────────────────────────────────────────────────

function displayNode(node: StallNode, index: number, total: number): void {
  console.log('\n' + '═'.repeat(60));
  console.log(`NODE ${index} of ${total}`);
  console.log('═'.repeat(60));
  console.log(`Stall score:  ${node.stall_probability.toFixed(2)}  |  Track: ${node.track ?? '?'}  |  Type: ${node.node_type}`);
  console.log(`Source:       ${node.source_label ?? '(unknown)'}`);
  console.log(`Occurrences:  ${node.occurrence_count}  |  Days old: ${node.days_since_first_seen}  |  Action verb: ${node.has_action_verb ? 'yes' : 'no'}`);
  console.log(`Label:        ${node.label}`);
  console.log('');
  console.log('Content:');
  console.log(node.content.length > 300 ? node.content.slice(0, 300) + '...' : node.content);
}

// ── Readline helpers ───────────────────────────────────────────────────────────

function prompt(rl: readline.Interface, question: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(question, (answer) => resolve(answer.trim().toLowerCase()));
  });
}

async function promptYN(rl: readline.Interface, question: string): Promise<boolean> {
  while (true) {
    const answer = await prompt(rl, question);
    if (answer === 'y' || answer === 'yes') return true;
    if (answer === 'n' || answer === 'no') return false;
    console.log('  Please enter y or n.');
  }
}

// ── Main ───────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log('\nMIKAI Stall Detection Evaluation');
  console.log('==================================');
  console.log('Fetching top stalled nodes from Supabase...');

  const nodes = await fetchTopStalledNodes(15);

  console.log(`\nLoaded ${nodes.length} nodes (top by stall_probability). Starting evaluation.\n`);
  console.log('For each node you will be asked:');
  console.log('  1. Is this genuinely stalled? (y/n) — MIKAI correctly identified it as unresolved?');
  console.log('  2. Would you act if WhatsApp surfaced this? (y/n) — useful nudge?');
  console.log('\nGate: ≥60% yes/yes = Phase 3 ready. Press Enter to begin...');

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  await new Promise<void>((resolve) => rl.question('', () => resolve()));

  const ratings: NodeRating[] = [];

  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    displayNode(node, i + 1, nodes.length);

    console.log('');
    const genuinelyStalled = await promptYN(rl, 'Genuinely stalled? (y/n) ');
    const wouldAct = await promptYN(rl, 'Would you act if WhatsApp surfaced this? (y/n) ');
    const noteInput = await new Promise<string>((resolve) =>
      rl.question('Note (optional, press Enter to skip): ', (a) => resolve(a.trim()))
    );

    const hit = genuinelyStalled && wouldAct;
    ratings.push({ node, genuinelyStalled, wouldAct, note: noteInput, hit });
    console.log(`  → ${hit ? 'HIT ✓' : 'MISS ✗'} (stalled: ${genuinelyStalled ? 'y' : 'n'}, would act: ${wouldAct ? 'y' : 'n'})`);
  }

  rl.close();

  // ── Compute summary ──────────────────────────────────────────────────────────

  const hits = ratings.filter((r) => r.hit).length;
  const actionableHitRate = Math.round((hits / ratings.length) * 100) / 100;
  const genuinelyStalledRate =
    Math.round((ratings.filter((r) => r.genuinelyStalled).length / ratings.length) * 100) / 100;
  const wouldActRate =
    Math.round((ratings.filter((r) => r.wouldAct).length / ratings.length) * 100) / 100;

  const trackA = ratings.filter((r) => r.node.track === 'A');
  const trackB = ratings.filter((r) => r.node.track === 'B');

  const verdict: 'PASS' | 'FIX_NOISE' | 'RECALIBRATE' =
    actionableHitRate >= 0.6
      ? 'PASS'
      : trackB.length > 0 && trackB.filter((r) => r.hit).length / trackB.length < 0.4
      ? 'FIX_NOISE'
      : 'RECALIBRATE';

  const timestamp = new Date().toISOString();

  const result: EvalResult = {
    timestamp,
    node_count: ratings.length,
    nodes: ratings,
    summary: {
      actionableHitRate,
      genuinelyStalledRate,
      wouldActRate,
      trackBreakdown: {
        A: { total: trackA.length, hits: trackA.filter((r) => r.hit).length },
        B: { total: trackB.length, hits: trackB.filter((r) => r.hit).length },
      },
      verdict,
    },
  };

  // ── Write results file ───────────────────────────────────────────────────────

  const safeTimestamp = timestamp.replace(/[:.]/g, '-');
  const resultsDir = path.join(__dirname, 'results');
  const outPath = path.join(resultsDir, `eval-stall-${safeTimestamp}.json`);

  fs.mkdirSync(resultsDir, { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf-8');

  // ── Print summary ────────────────────────────────────────────────────────────

  console.log('\n' + '═'.repeat(60));
  console.log('STALL DETECTION EVALUATION COMPLETE');
  console.log('═'.repeat(60));
  console.log(`Nodes rated:           ${ratings.length}`);
  console.log(`Actionable hit rate:   ${(actionableHitRate * 100).toFixed(0)}%  (yes/yes)`);
  console.log(`Genuinely stalled:     ${(genuinelyStalledRate * 100).toFixed(0)}%`);
  console.log(`Would act:             ${(wouldActRate * 100).toFixed(0)}%`);
  console.log('');
  console.log(`Track A: ${trackA.length} nodes, ${trackA.filter((r) => r.hit).length} hits`);
  console.log(`Track B: ${trackB.length} nodes, ${trackB.filter((r) => r.hit).length} hits`);
  console.log('');
  console.log(`VERDICT: ${verdict}`);
  if (verdict === 'PASS') {
    console.log('  ≥60% actionable. Phase 3 (WhatsApp) can begin.');
  } else if (verdict === 'FIX_NOISE') {
    console.log('  Track B noise is degrading results. Fix O-024 before Phase 3.');
    console.log('  See: engine/graph/build-graph.js Track B line filter');
  } else {
    console.log('  Hit rate too low and not obviously a Track B noise problem.');
    console.log('  Review rule engine weights in engine/inference/rule-engine.ts.');
  }
  console.log('');
  console.log(`Results written to: ${outPath}`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
