#!/usr/bin/env node
/**
 * engine/inference/run-rule-engine.js
 *
 * Bulk-scores all nodes using the rule engine and writes stall_probability
 * back to the nodes table in Supabase.
 *
 * Run after build-graph to populate stall_probability for Track A nodes.
 * Track B nodes already have stall_probability set at insertion time, but
 * this script will re-score them too for consistency.
 *
 * Usage:
 *   npm run run-rule-engine
 *   npm run run-rule-engine -- --dry-run     # print scores, no writes
 *   npm run run-rule-engine -- --track A     # only Track A nodes
 *   npm run run-rule-engine -- --track B     # only Track B nodes
 *   npm run run-rule-engine -- --min-score 0.3  # only update if score >= N
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── CLI options ───────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const flag   = (name) => args.includes(name);
const option = (name, def) => { const i = args.indexOf(name); return i !== -1 && args[i + 1] ? args[i + 1] : def; };

const DRY_RUN   = flag('--dry-run');
const TRACK     = option('--track', null);   // 'A' | 'B' | null (all)
const MIN_SCORE = parseFloat(option('--min-score', '0'));

// ── Env loader ────────────────────────────────────────────────────────────────
// Must run before any dynamic imports that read process.env at module init time.

function loadEnv() {
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
  } catch { /* .env.local not found — env assumed to already be set */ }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  loadEnv();

  // Dynamic imports after env is loaded so API keys are available at module init
  const { scoreNode } = await import('../../engine/inference/rule-engine.ts');
  const { createClient } = await import('@supabase/supabase-js');

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    console.error('SUPABASE_URL / SUPABASE_SERVICE_KEY not set in .env.local');
    process.exit(1);
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  // ── Query nodes ──────────────────────────────────────────────────────────────

  let query = supabase
    .from('nodes')
    .select(
      'id, label, content, node_type, occurrence_count, query_hit_count, ' +
      'confidence_weight, has_action_verb, stall_probability, resolved_at, ' +
      'created_at, track'
    );

  // Filter by track if specified. Nodes with null track are treated as Track A.
  if (TRACK === 'A') {
    query = query.or('track.eq.A,track.is.null');
  } else if (TRACK === 'B') {
    query = query.eq('track', 'B');
  }

  const { data: nodes, error: queryError } = await query;

  if (queryError) {
    console.error('Supabase query failed:', queryError.message);
    process.exit(1);
  }

  if (!nodes || nodes.length === 0) {
    console.log('No nodes found.');
    return;
  }

  console.log(`Fetched ${nodes.length} nodes`);
  console.log('Scoring...');

  if (DRY_RUN) {
    // ── Dry-run: score in JS, print, no writes ────────────────────────────────
    const scored = [];
    for (const node of nodes) {
      const days = (Date.now() - new Date(node.created_at).getTime()) / (1000 * 60 * 60 * 24);
      const nodeWithFeatures = {
        ...node,
        occurrence_count:     node.occurrence_count  ?? 1,
        query_hit_count:      node.query_hit_count   ?? 0,
        confidence_weight:    node.confidence_weight ?? 0.5,
        has_action_verb:      node.has_action_verb   ?? false,
        days_since_first_seen: days,
        resolved_at:          node.resolved_at       ?? null,
      };
      let score = scoreNode(nodeWithFeatures);
      if (node.track === 'B') score = Math.max(score, node.has_action_verb ? 0.6 : 0.0);
      scored.push({ id: node.id, label: node.label, node_type: node.node_type, score });
    }
    const highConfidence = scored.filter(n => n.score >= 0.8).length;
    const aboveHalf      = scored.filter(n => n.score >= 0.5).length;
    console.log(`  ${highConfidence} nodes scored >= 0.8 (high-confidence stall)`);
    console.log(`  ${aboveHalf} nodes scored >= 0.5`);
    console.log('\n[dry-run — no writes]');
    const top = scored.filter(n => n.score > 0).sort((a, b) => b.score - a.score).slice(0, 10);
    if (top.length > 0) {
      console.log('\nDone. Top stalled nodes:');
      for (const n of top) console.log(`  ${n.score.toFixed(2)} | "${n.label}" (${n.node_type})`);
    }
    return;
  }

  // ── Fast path: single Postgres RPC updates all nodes in one round trip ───────
  // score_all_nodes() runs compute_stall_probability() server-side — no per-row
  // fetch/update loop. Falls back to JS path only when --track filter is active,
  // since score_all_nodes() scores all tracks.

  if (!TRACK) {
    const { data: updatedCount, error: rpcError } = await supabase.rpc('score_all_nodes');
    if (rpcError) {
      console.error('score_all_nodes() RPC failed:', rpcError.message);
      console.log('Falling back to JS scoring path...');
    } else {
      console.log(`  ${updatedCount} nodes updated (via Postgres function)`);

      // Fetch top stalled nodes for display
      const { data: top } = await supabase
        .from('nodes')
        .select('label, node_type, stall_probability')
        .gt('stall_probability', 0)
        .order('stall_probability', { ascending: false })
        .limit(10);

      if (top && top.length > 0) {
        console.log('\nDone. Top stalled nodes:');
        for (const n of top) {
          console.log(`  ${(n.stall_probability ?? 0).toFixed(2)} | "${n.label}" (${n.node_type})`);
        }
      } else {
        console.log('\nDone. No nodes scored above 0.');
      }
      return;
    }
  }

  // ── JS fallback path (--track filter or RPC failure) ─────────────────────────
  const scored = [];
  for (const node of nodes) {
    const days = (Date.now() - new Date(node.created_at).getTime()) / (1000 * 60 * 60 * 24);
    const nodeWithFeatures = {
      ...node,
      occurrence_count:     node.occurrence_count  ?? 1,
      query_hit_count:      node.query_hit_count   ?? 0,
      confidence_weight:    node.confidence_weight ?? 0.5,
      has_action_verb:      node.has_action_verb   ?? false,
      days_since_first_seen: days,
      resolved_at:          node.resolved_at       ?? null,
    };
    let score = scoreNode(nodeWithFeatures);
    if (node.track === 'B') score = Math.max(score, node.has_action_verb ? 0.6 : 0.0);
    scored.push({ id: node.id, label: node.label, node_type: node.node_type, score });
  }

  const highConfidence = scored.filter(n => n.score >= 0.8).length;
  const aboveHalf      = scored.filter(n => n.score >= 0.5).length;
  const toUpdate       = scored.filter(n => n.score >= MIN_SCORE);

  console.log(`  ${highConfidence} nodes scored >= 0.8 (high-confidence stall)`);
  console.log(`  ${aboveHalf} nodes scored >= 0.5`);

  const CONCURRENCY = 20;
  let updated = 0;
  let idx = 0;

  async function updateWorker() {
    while (idx < toUpdate.length) {
      const node = toUpdate[idx++];
      const { error } = await supabase.from('nodes').update({ stall_probability: node.score }).eq('id', node.id);
      if (error) console.log(`  update failed for "${node.label}": ${error.message}`);
      else updated++;
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, updateWorker));
  console.log(`  ${updated} nodes updated`);

  const top = scored.filter(n => n.score > 0).sort((a, b) => b.score - a.score).slice(0, 10);
  if (top.length > 0) {
    console.log('\nDone. Top stalled nodes:');
    for (const n of top) console.log(`  ${n.score.toFixed(2)} | "${n.label}" (${n.node_type})`);
  } else {
    console.log('\nDone. No nodes scored above 0.');
  }
}

main().catch((err) => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
