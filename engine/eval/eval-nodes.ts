/**
 * engine/eval/eval-nodes.ts
 *
 * Interactive evaluation script for MIKAI extraction quality.
 * Fetches ~10 nodes from Supabase, prompts Brian to rate each on:
 *   - Accuracy (1–5): Does this node accurately represent what I actually wrote/think?
 *   - Non-obviousness (1–5): Is this something a keyword search wouldn't have surfaced?
 *
 * Writes results to engine/eval/results/eval-{ISO-timestamp}.json
 *
 * Run: npm run eval
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

interface EvalNode {
  id: string;
  label: string;
  content: string;
  node_type: string;
  source_id: string | null;
  source_label: string | null;
  edges: EvalEdge[];
}

interface EvalEdge {
  from_node: string;
  to_node: string;
  relationship: string;
  note: string | null;
  connected_label: string;
  direction: 'outgoing' | 'incoming';
}

interface NodeRating {
  node: EvalNode;
  accuracy: number;
  nonObviousness: number;
  note: string;
  pass: boolean;
}

interface EvalResult {
  timestamp: string;
  node_count: number;
  nodes: NodeRating[];
  summary: {
    avgAccuracy: number;
    avgNonObviousness: number;
    passCount: number;
    failCount: number;
    verdict: 'PASS' | 'NEEDS WORK';
  };
}

// ── Fetch nodes ────────────────────────────────────────────────────────────────

async function fetchNodes(): Promise<EvalNode[]> {
  // Fetch ~10 nodes with a mix of types
  const targetTypes = ['concept', 'tension', 'question', 'decision'];
  const nodesPerType = [3, 3, 2, 2]; // ~10 total

  const allNodes: EvalNode[] = [];

  for (let i = 0; i < targetTypes.length; i++) {
    const type = targetTypes[i];
    const limit = nodesPerType[i];

    const { data, error } = await supabase
      .from('nodes')
      .select('id, label, content, node_type, source_id')
      .eq('node_type', type)
      .limit(limit);

    if (error) {
      console.warn(`Warning: failed to fetch ${type} nodes:`, error.message);
      continue;
    }

    for (const row of data ?? []) {
      allNodes.push({
        id: row.id,
        label: row.label,
        content: row.content,
        node_type: row.node_type,
        source_id: row.source_id ?? null,
        source_label: null,
        edges: [],
      });
    }
  }

  if (allNodes.length === 0) {
    console.error('No nodes found. Has the graph been built yet? Run: npm run build-graph');
    process.exit(1);
  }

  // ── Fetch source labels ──────────────────────────────────────────────────────
  const sourceIds = [...new Set(allNodes.map((n) => n.source_id).filter(Boolean))] as string[];

  if (sourceIds.length > 0) {
    const { data: sources, error: srcError } = await supabase
      .from('sources')
      .select('id, label')
      .in('id', sourceIds);

    if (!srcError && sources) {
      const srcMap = new Map(sources.map((s) => [s.id, s.label]));
      for (const node of allNodes) {
        if (node.source_id) {
          node.source_label = srcMap.get(node.source_id) ?? null;
        }
      }
    }
  }

  // ── Fetch edges for each node ────────────────────────────────────────────────
  const nodeIds = allNodes.map((n) => n.id);

  const { data: edges, error: edgeError } = await supabase
    .from('edges')
    .select('from_node, to_node, relationship, note')
    .or(`from_node.in.(${nodeIds.join(',')}),to_node.in.(${nodeIds.join(',')})`);

  if (!edgeError && edges) {
    // Collect all connected node IDs not already in our set
    const nodeIdSet = new Set(nodeIds);
    const connectedIds = new Set<string>();
    for (const edge of edges) {
      if (!nodeIdSet.has(edge.from_node)) connectedIds.add(edge.from_node);
      if (!nodeIdSet.has(edge.to_node)) connectedIds.add(edge.to_node);
    }

    // Fetch labels for connected nodes
    const connectedLabelMap = new Map<string, string>();
    if (connectedIds.size > 0) {
      const { data: connectedNodes } = await supabase
        .from('nodes')
        .select('id, label')
        .in('id', [...connectedIds]);

      for (const n of connectedNodes ?? []) {
        connectedLabelMap.set(n.id, n.label);
      }
    }

    // Also add our own nodes to the label map
    for (const n of allNodes) {
      connectedLabelMap.set(n.id, n.label);
    }

    // Attach edges to each node
    const nodeMap = new Map(allNodes.map((n) => [n.id, n]));
    for (const edge of edges) {
      if (nodeMap.has(edge.from_node)) {
        const node = nodeMap.get(edge.from_node)!;
        node.edges.push({
          from_node: edge.from_node,
          to_node: edge.to_node,
          relationship: edge.relationship,
          note: edge.note ?? null,
          connected_label: connectedLabelMap.get(edge.to_node) ?? edge.to_node,
          direction: 'outgoing',
        });
      }
      if (nodeMap.has(edge.to_node)) {
        const node = nodeMap.get(edge.to_node)!;
        node.edges.push({
          from_node: edge.from_node,
          to_node: edge.to_node,
          relationship: edge.relationship,
          note: edge.note ?? null,
          connected_label: connectedLabelMap.get(edge.from_node) ?? edge.from_node,
          direction: 'incoming',
        });
      }
    }
  }

  return allNodes;
}

// ── Display node ───────────────────────────────────────────────────────────────

function displayNode(node: EvalNode, index: number, total: number): void {
  console.log('\n' + '═'.repeat(60));
  console.log(`NODE ${index} of ${total}`);
  console.log('═'.repeat(60));
  console.log(`Type:    ${node.node_type.toUpperCase()}`);
  console.log(`Label:   ${node.label}`);
  console.log(`Source:  ${node.source_label ?? node.source_id ?? '(unknown)'}`);
  console.log('');
  console.log('Content:');
  console.log(node.content);

  if (node.edges.length > 0) {
    console.log('');
    console.log(`Edges (${node.edges.length}):`);
    for (const edge of node.edges) {
      const arrow = edge.direction === 'outgoing' ? '→' : '←';
      const noteStr = edge.note ? ` [${edge.note}]` : '';
      console.log(`  ${arrow} ${edge.relationship}: "${edge.connected_label}"${noteStr}`);
    }
  } else {
    console.log('');
    console.log('Edges: (none)');
  }
}

// ── Readline helpers ───────────────────────────────────────────────────────────

function prompt(rl: readline.Interface, question: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(question, (answer) => resolve(answer.trim()));
  });
}

async function promptRating(rl: readline.Interface, question: string): Promise<number> {
  while (true) {
    const answer = await prompt(rl, question);
    const n = parseInt(answer, 10);
    if (n >= 1 && n <= 5) return n;
    console.log('  Please enter a number between 1 and 5.');
  }
}

// ── Main ───────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log('\nMIKAI Extraction Quality Evaluation');
  console.log('====================================');
  console.log('Fetching nodes from Supabase...');

  const nodes = await fetchNodes();

  console.log(`\nLoaded ${nodes.length} nodes. Starting evaluation.\n`);
  console.log('For each node you will be asked:');
  console.log('  1. Accuracy (1-5): Does this node accurately represent what I actually wrote/think?');
  console.log('  2. Non-obviousness (1-5): Is this something a keyword search wouldn\'t have surfaced?');
  console.log('\nPress Enter to begin...');

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  await prompt(rl, '');

  const ratings: NodeRating[] = [];

  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    displayNode(node, i + 1, nodes.length);

    console.log('');
    const accuracy = await promptRating(
      rl,
      'Accuracy (1=wrong, 5=spot-on) — Does this accurately represent what you actually wrote/think? '
    );
    const nonObviousness = await promptRating(
      rl,
      'Non-obviousness (1=obvious, 5=surprising) — Is this something a keyword search wouldn\'t have surfaced? '
    );
    const noteInput = await prompt(rl, 'Note (optional, press Enter to skip): ');

    const pass = accuracy >= 3 && nonObviousness >= 3;
    ratings.push({
      node,
      accuracy,
      nonObviousness,
      note: noteInput,
      pass,
    });

    console.log(`  → ${pass ? 'PASS' : 'FAIL'} (accuracy: ${accuracy}, non-obviousness: ${nonObviousness})`);
  }

  rl.close();

  // ── Compute summary ──────────────────────────────────────────────────────────

  const avgAccuracy =
    ratings.reduce((sum, r) => sum + r.accuracy, 0) / ratings.length;
  const avgNonObviousness =
    ratings.reduce((sum, r) => sum + r.nonObviousness, 0) / ratings.length;
  const passCount = ratings.filter((r) => r.pass).length;
  const failCount = ratings.length - passCount;
  const verdict: 'PASS' | 'NEEDS WORK' =
    avgAccuracy >= 3.5 && avgNonObviousness >= 3.0 ? 'PASS' : 'NEEDS WORK';

  const timestamp = new Date().toISOString();

  const result: EvalResult = {
    timestamp,
    node_count: nodes.length,
    nodes: ratings,
    summary: {
      avgAccuracy: Math.round(avgAccuracy * 100) / 100,
      avgNonObviousness: Math.round(avgNonObviousness * 100) / 100,
      passCount,
      failCount,
      verdict,
    },
  };

  // ── Write results file ───────────────────────────────────────────────────────

  const safeTimestamp = timestamp.replace(/[:.]/g, '-');
  const resultsDir = path.join(__dirname, 'results');
  const outPath = path.join(resultsDir, `eval-${safeTimestamp}.json`);

  fs.mkdirSync(resultsDir, { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf-8');

  // ── Print summary ────────────────────────────────────────────────────────────

  console.log('\n' + '═'.repeat(60));
  console.log('EVALUATION COMPLETE');
  console.log('═'.repeat(60));
  console.log(`Nodes rated:         ${nodes.length}`);
  console.log(`Avg accuracy:        ${result.summary.avgAccuracy} / 5`);
  console.log(`Avg non-obviousness: ${result.summary.avgNonObviousness} / 5`);
  console.log(`Pass:                ${passCount}`);
  console.log(`Fail:                ${failCount}`);
  console.log('');
  console.log(`VERDICT: ${verdict}`);
  if (verdict === 'PASS') {
    console.log('  Extraction quality meets the threshold. Phase 2 unblocked.');
  } else {
    console.log('  Extraction quality below threshold. Review prompt or graph build.');
    console.log('  Threshold: avgAccuracy >= 3.5 AND avgNonObviousness >= 3.0');
  }
  console.log('');
  console.log(`Results written to: ${outPath}`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
