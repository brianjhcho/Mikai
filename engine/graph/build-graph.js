#!/usr/bin/env node
/**
 * engine/graph/build-graph.js
 *
 * Reads stored sources from Supabase and runs the reasoning extraction prompt
 * to construct nodes and edges. Runs independently of ingestion and can be
 * re-run without re-ingesting.
 *
 * Ingestion (sync.js → /api/ingest/batch) stores raw content and chunk counts.
 * This script does everything that requires LLM calls: graph extraction (Claude)
 * and embedding (Voyage AI).
 *
 * Usage (from MIKAI root):
 *   npm run build-graph
 *   npm run build-graph -- --rebuild
 *   npm run build-graph -- --source-id <uuid>
 *   npm run build-graph -- --dry-run
 *
 * Options:
 *   --rebuild     Also process sources that already have node_count > 0
 *   --source-id   Process a single source by ID
 *   --batch-size  Number of sources to process per run (default: 10)
 *   --dry-run     Print what would be processed — no writes, no API calls
 *   --preview     Run Claude extraction and print raw JSON — no embeddings, no DB writes
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import crypto from 'crypto';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── CLI options ───────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const flag   = (name) => args.includes(name);
const option = (name, def) => { const i = args.indexOf(name); return i !== -1 && args[i + 1] ? args[i + 1] : def; };

const REBUILD    = flag('--rebuild');
const DRY_RUN    = flag('--dry-run');
const PREVIEW    = flag('--preview');
const SOURCE_ID  = option('--source-id', null);
const BATCH_SIZE = parseInt(option('--batch-size', '10'), 10);

// ── Track B — behavioral trace sources (rule engine only, no LLM) ─────────────
//
// Sources in this set are processed by the Track B rule engine path:
//   - No Claude extraction (no LLM call)
//   - No Voyage AI embeddings
//   - Direct node creation from action-verb line detection
//   - stall_probability set immediately via inline rule
//
// Track A (default): authored content → Claude extractGraph() → embeddings
// Track B:           behavioral traces → line scan → rule-engine node creation
//
// NOTE: The `track` column ('A' | 'B') must exist on the nodes table.
// If it does not yet exist, Track B node inserts will error per-node (logged
// as warnings) but the script will not abort. Add the column via Supabase
// dashboard: ALTER TABLE nodes ADD COLUMN track text;

const TRACK_B_SOURCES = new Set(['imessage', 'gmail']);

const ACTION_VERBS = /\b(buy|book|schedule|call|send|order|sign up|register|apply|pay|upgrade|cancel|renew|install|download|join|visit|meet|plan|confirm|reserve)\b/i;

// Track B boilerplate filter — lines matching these patterns are structural noise
// (SMS legal disclaimers, email CTA boilerplate, URL-only fragments) and should
// never become nodes regardless of action-verb presence.
const BOILERPLATE_PATTERNS = [
  /msg rates?.*apply/i,          // "Msg rates may apply" (was: /msg rates? apply/i)
  /std msg/i,
  /unsubscribe/i,
  /view in (browser|email)/i,
  /you will be redirect/i,
  /for your records/i,
  /privacy policy/i,
  /terms of (service|use)/i,
  /click here/i,
  /buy \d.*get \d/i,             // "Buy 1, Get 1 Free"
  /\$[\d,.]+\s*\/(month|year)/i, // "$99/month", "$96/year"
  /taxes? (apply|&)/i,           // "fees & taxes apply"
  /fees?.*apply/i,               // "other fees apply"
  /auto.?renew/i,                // subscription billing boilerplate
  /download (our|the) app/i,     // CTA boilerplate
  /upon.*conclusion.*trial/i,    // subscription fine print
  /please pay by/i,              // payment reminders with no context
];

function isBoilerplateLine(line) {
  if (BOILERPLATE_PATTERNS.some(p => p.test(line))) return true;
  // Filter lines where a URL consumes most of the content
  const stripped = line.replace(/https?:\/\/\S+/g, '').trim();
  if (stripped.length < 15) return true;
  return false;
}

const SOURCE_WEIGHTS = {
  'apple-notes': 1.0,
  'llm_thread':  0.9,
  'document':    0.7,
  'imessage':    0.8,
  'gmail':       0.85,
};

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
  const { extractGraph } = await import('../../lib/ingest-pipeline.ts');
  const { embedDocuments } = await import('../../lib/embeddings.ts');
  const { createClient } = await import('@supabase/supabase-js');

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    console.error('SUPABASE_URL / SUPABASE_SERVICE_KEY not set in .env.local');
    process.exit(1);
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  // ── Query sources to process ────────────────────────────────────────────────

  let query = supabase
    .from('sources')
    .select('id, label, raw_content, type, source, node_count, content_hash')
    .not('raw_content', 'is', null);

  // When targeting a specific source by ID, skip the chunk_count guard —
  // the caller knows what they want. For bulk runs, only process sources
  // that completed ingestion (chunk_count > 0).
  if (!SOURCE_ID) {
    query = query.gt('chunk_count', 0);
  }

  if (!REBUILD) {
    query = query.eq('node_count', 0); // skip sources that already have a graph
  }

  if (SOURCE_ID) {
    query = query.eq('id', SOURCE_ID);
  } else {
    query = query.limit(BATCH_SIZE);
  }

  const { data: sources, error: queryError } = await query;

  if (queryError) {
    console.error('Supabase query failed:', queryError.message);
    process.exit(1);
  }

  if (!sources || sources.length === 0) {
    console.log('No sources to process. All sources have node_count > 0. Use --rebuild to re-extract.');
    return;
  }

  console.log(`${sources.length} source(s) to process${REBUILD ? ' (--rebuild mode)' : ''}`);

  if (DRY_RUN) {
    console.log('\n[dry-run — no API calls, no writes]');
    for (const s of sources) {
      const words = s.raw_content?.split(/\s+/).filter(Boolean).length ?? 0;
      if (TRACK_B_SOURCES.has(s.source)) {
        console.log(`  would process [Track B]: "${s.label}" (id: ${s.id}, ${words} words, current node_count: ${s.node_count ?? 0})`);
      } else {
        console.log(`  would process [Track A]: "${s.label}" (id: ${s.id}, ${words} words, current node_count: ${s.node_count ?? 0})`);
      }
    }
    return;
  }

  if (PREVIEW) {
    console.log('\n[preview — Claude extraction only, no embeddings, no DB writes]\n');
    for (const source of sources) {
      console.log(`Source: "${source.label}" (${source.id})`);
      const graph = await extractGraph(source.raw_content, source.label);
      console.log(JSON.stringify(graph, null, 2));
    }
    return;
  }

  // ── Process each source ─────────────────────────────────────────────────────

  const counts = { processed: 0, failed: 0, skipped: 0 };

  // Split by track — Track B is fast (no API calls), Track A needs concurrency
  const trackBSources = sources.filter(s => TRACK_B_SOURCES.has(s.source));
  const trackASources = sources.filter(s => !TRACK_B_SOURCES.has(s.source));

  // ── Helper: compute content hash ──────────────────────────────────────────
  function contentHash(text) {
    return crypto.createHash('sha256').update(text).digest('hex');
  }

  // ── Track B: sequential (regex only, no API calls) ────────────────────────
  for (const source of trackBSources) {
    process.stdout.write(`\n"${source.label}"\n`);

    const content = source.raw_content;
    if (!content || content.trim().length < 50) { console.log('  skip — content too short'); continue; }

    // Content hash check — skip unchanged sources on rebuild
    const hash = contentHash(content);
    if (REBUILD && source.content_hash && source.content_hash === hash) {
      console.log('  skip — content unchanged');
      counts.skipped++;
      continue;
    }

    // Delete existing nodes when rebuilding
    if (REBUILD && source.node_count > 0) {
      const { error: deleteError } = await supabase.from('nodes').delete().eq('source_id', source.id);
      if (deleteError) { console.log(`  delete existing nodes FAILED — ${deleteError.message}`); counts.failed++; continue; }
    }

    process.stdout.write('  [Track B] scanning for action-verb lines... ');
    const lines = content.split(/[\n.!?]+/).map(l => l.trim()).filter(l => l.length > 10);
    const actionLines = lines.filter(l => !isBoilerplateLine(l) && ACTION_VERBS.test(l));

    if (actionLines.length === 0) {
      console.log('0 action lines — marking as processed (node_count = -1)');
      await supabase.from('sources').update({ node_count: -1, content_hash: hash }).eq('id', source.id);
      counts.skipped++;
      continue;
    }

    console.log(`${actionLines.length} action lines found`);

    const confidence_weight = SOURCE_WEIGHTS[source.source] ?? 0.5;

    // Batch insert all nodes in one round trip
    const nodesToInsert = actionLines.map(line => ({
      source_id:        source.id,
      content:          line,
      label:            line.slice(0, 60),
      node_type:        'concept',
      has_action_verb:  true,
      confidence_weight,
      stall_probability: 0.6,
      track:            'B',
    }));

    const { data: insertedNodes, error: insertError } = await supabase
      .from('nodes')
      .insert(nodesToInsert)
      .select('id');

    if (insertError) {
      console.log(`  batch insert FAILED — ${insertError.message}`);
      counts.failed++;
      continue;
    }

    const nodeCount = insertedNodes?.length ?? 0;
    await supabase.from('sources').update({ node_count: nodeCount, edge_count: 0, content_hash: hash }).eq('id', source.id);
    console.log(`  ✓ [Track B] ${nodeCount} nodes written`);
    counts.processed++;
  }

  // ── Track A: parallel workers (Claude + Voyage AI) ────────────────────────
  const TRACK_A_CONCURRENCY = 4;
  let trackAIdx = 0;

  async function processTrackA() {
    while (trackAIdx < trackASources.length) {
      const source = trackASources[trackAIdx++];
      process.stdout.write(`\n"${source.label}"\n`);

      const content = source.raw_content;
      if (!content || content.trim().length < 50) { console.log('  skip — content too short'); continue; }

      // Content hash check — skip unchanged sources on rebuild
      const hash = contentHash(content);
      if (REBUILD && source.content_hash && source.content_hash === hash) {
        console.log('  skip — content unchanged');
        counts.skipped++;
        continue;
      }

      // Step 1: Extract graph (Claude)
      process.stdout.write('  extracting graph... ');
      const graphStartMs = Date.now();
      const graph = await extractGraph(content, source.label);
      const graphDurationMs = Date.now() - graphStartMs;

      // Log extraction metrics — fire-and-forget, never blocks the pipeline
      supabase.from('extraction_logs').insert({
        source_id:   source.id,
        operation:   'graph_extraction',
        model:       'claude-haiku-4-5-20251001',
        duration_ms: graphDurationMs,
        error:       graph.nodes.length === 0 ? 'no nodes extracted' : null,
      }).then(() => {}).catch(() => {});

      if (graph.nodes.length === 0) {
        console.log('0 nodes extracted — skipping');
        counts.failed++;
        continue;
      }

      console.log(`${graph.nodes.length} nodes, ${graph.edges.length} edges`);

      // Step 2: Embed node content (Voyage AI)
      process.stdout.write('  embedding nodes... ');
      let embeddings;
      try {
        embeddings = await embedDocuments(graph.nodes.map(n => n.content));
        console.log('done');
      } catch (err) {
        console.log(`FAILED — ${err.message}`);
        counts.failed++;
        continue;
      }

      // Step 3: Delete existing nodes if rebuilding
      if (REBUILD && source.node_count > 0) {
        const { error: deleteError } = await supabase.from('nodes').delete().eq('source_id', source.id);
        if (deleteError) {
          console.log(`  delete existing nodes FAILED — ${deleteError.message}`);
          counts.failed++;
          continue;
        }
      }

      // Step 4: Batch insert all nodes in one round trip
      const confidence_weight = SOURCE_WEIGHTS[source.type] ?? 0.5;
      const nodesToInsert = graph.nodes.map((node, j) => ({
        source_id:        source.id,
        content:          node.content,
        label:            node.label,
        node_type:        node.type,
        embedding:        embeddings[j],
        has_action_verb:  ACTION_VERBS.test(node.content),
        confidence_weight,
      }));

      const { data: insertedNodes, error: insertError } = await supabase
        .from('nodes')
        .insert(nodesToInsert)
        .select('id, label');

      if (insertError) {
        console.log(`  batch insert FAILED — ${insertError.message}`);
        counts.failed++;
        continue;
      }

      // Build nodeIdMap from returned rows (preserves insertion order)
      const nodeIdMap = new Map(insertedNodes.map(n => [n.label, n.id]));

      // Step 5: Insert edges (small N per source, stays sequential)
      let edgesCreated = 0;
      for (const edge of graph.edges) {
        const fromId = nodeIdMap.get(edge.from_label);
        const toId   = nodeIdMap.get(edge.to_label);
        if (!fromId || !toId) continue;

        const { error } = await supabase.from('edges').insert({
          from_node:    fromId,
          to_node:      toId,
          relationship: edge.relationship,
          note:         edge.note ?? null,
        });

        if (!error) edgesCreated++;
      }

      // Step 6: Update source counters + content hash
      await supabase
        .from('sources')
        .update({ node_count: nodeIdMap.size, edge_count: edgesCreated, content_hash: hash })
        .eq('id', source.id);

      console.log(`  ✓ ${nodeIdMap.size} nodes, ${edgesCreated} edges written`);
      counts.processed++;
    }
  }

  await Promise.all(Array.from({ length: TRACK_A_CONCURRENCY }, processTrackA));

  console.log(`\nDone. ${counts.processed} processed, ${counts.failed} failed, ${counts.skipped} skipped (no action verbs or unchanged).`);
}

main().catch((err) => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
