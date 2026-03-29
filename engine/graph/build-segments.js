#!/usr/bin/env node
/**
 * engine/graph/build-segments.js
 *
 * Track C: Reads stored sources and produces topic segments with condensed prose.
 * Uses source-type-aware structural splitting (ZERO LLM calls) + Voyage AI embeddings.
 *
 * Unlike build-graph (which atomizes content into nodes/edges), build-segments
 * preserves semantic coherence by condensing topic-level passages. This matches
 * the manual workflow: paste relevant notes into Claude, get synthesis.
 *
 * Source-aware segmentation (via smart-split.js):
 *   claude-thread → split at [User] boundaries, each turn = one segment
 *   perplexity    → same as claude-thread
 *   apple-notes   → journal-style line merging into coherent blocks
 *   manual        → heading-based or generic paragraph merging
 *   all others    → generic double-newline paragraph merging
 *
 * Usage (from MIKAI root):
 *   npm run build-segments
 *   npm run build-segments -- --rebuild        Re-segment all sources
 *   npm run build-segments -- --source-id <uuid>
 *   npm run build-segments -- --batch-size 20
 *   npm run build-segments -- --dry-run        Print what would run, no API calls
 *   npm run build-segments -- --preview        Split + print segments, no DB writes
 *   npm run build-segments -- --sources apple-notes,perplexity,manual,claude-thread,gmail,imessage
 *
 * Default sources: apple-notes, perplexity, manual, claude-thread, gmail, imessage
 */

import fs   from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── CLI options ────────────────────────────────────────────────────────────────

const args   = process.argv.slice(2);
const flag   = (name) => args.includes(name);
const option = (name, def) => { const i = args.indexOf(name); return i !== -1 && args[i + 1] ? args[i + 1] : def; };

const REBUILD     = flag('--rebuild');
const DRY_RUN     = flag('--dry-run');
const PREVIEW     = flag('--preview');
const SOURCE_ID   = option('--source-id', null);
const BATCH_SIZE  = parseInt(option('--batch-size', '10'), 10);
const CONCURRENCY = parseInt(option('--concurrency', '5'), 10);

// --sources apple-notes,perplexity,manual,claude-thread,gmail,imessage
// Comma-separated list of source origins to process. All source types included by default.
// Per-source minimum word thresholds applied (see SEGMENTATION_FRAMEWORK.md).
const SOURCES_RAW     = option('--sources', 'apple-notes,perplexity,manual,claude-thread,gmail,imessage');
const ALLOWED_SOURCES = new Set(SOURCES_RAW.split(',').map((s) => s.trim()));

// ── Env loader ────────────────────────────────────────────────────────────────

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
  } catch { /* .env.local not found — env assumed already set */ }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  loadEnv();

  const { smartSplit }       = await import('./smart-split.js');
  const { embedDocuments }   = await import('../../lib/embeddings.ts');
  const { createClient }     = await import('@supabase/supabase-js');

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    console.error('SUPABASE_URL / SUPABASE_SERVICE_KEY not set in .env.local');
    process.exit(1);
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  // ── Find sources already segmented ─────────────────────────────────────────

  let segmentedIds = new Set();

  if (!REBUILD) {
    const { data: existing, error: existingError } = await supabase
      .from('segments')
      .select('source_id');

    if (existingError) {
      console.error('Failed to query existing segments:', existingError.message);
      process.exit(1);
    }

    segmentedIds = new Set((existing ?? []).map((r) => r.source_id));
  }

  // ── Query source metadata only (no raw_content — fetch on demand) ──────────

  let query = supabase
    .from('sources')
    .select('id, label, source, type, chunk_count')
    .not('raw_content', 'is', null)
    .gt('chunk_count', 0)
    .in('source', [...ALLOWED_SOURCES]);

  if (SOURCE_ID) {
    query = query.eq('id', SOURCE_ID);
  } else {
    query = query.limit(BATCH_SIZE);
  }

  const { data: allSources, error: queryError } = await query;

  if (queryError) {
    console.error('Supabase query failed:', queryError.message);
    process.exit(1);
  }

  // Filter out already-segmented sources (unless --rebuild)
  const sources = (allSources ?? []).filter((s) => REBUILD || !segmentedIds.has(s.id));

  if (sources.length === 0) {
    console.log('No sources to segment. All sources have segments. Use --rebuild to re-segment.');
    return;
  }

  console.log(`${sources.length} source(s) to segment${REBUILD ? ' (--rebuild mode)' : ''}`);

  // ── Dry run ─────────────────────────────────────────────────────────────────

  if (DRY_RUN) {
    console.log('\n[dry-run — no API calls, no writes]');
    for (const s of sources) {
      const words = s.raw_content?.split(/\s+/).filter(Boolean).length ?? 0;
      console.log(`  would segment: "${s.label}" (source: ${s.source}, ${words} words)`);
    }
    return;
  }

  // ── Process sources ─────────────────────────────────────────────────────────

  let totalSegments = 0;
  let failed = 0;

  // Process a single source end-to-end (fetches raw_content on demand)
  async function processSource(source) {
    const label = `"${source.label}" (${source.source})`;

    // Fetch raw_content for this source only
    const { data: contentRow, error: contentError } = await supabase
      .from('sources')
      .select('raw_content')
      .eq('id', source.id)
      .single();

    if (contentError || !contentRow?.raw_content) {
      console.log(`  ${label} ... skipped (no content)`);
      return 0;
    }

    const rawContent = contentRow.raw_content;

    // Skip sources below the minimum word threshold
    const wc = rawContent.split(/\s+/).filter(Boolean).length ?? 0;
    // Source-type-aware minimum thresholds (from SEGMENTATION_FRAMEWORK.md)
    const minWords = {
      'perplexity': 30,
      'claude-thread': 15,
      'manual': 20,
      'gmail': 15,
      'apple-notes': 10,
      'imessage': 20,
    };
    const threshold = minWords[source.source] ?? 50;
    if (wc < threshold) {
      console.log(`  ${label} ... skipped (${wc} words < ${threshold} min for ${source.source || 'unknown'})`);
      return 0;
    }

    const startMs = Date.now();

    try {
      // Split is instant — zero LLM cost
      const segments = smartSplit(rawContent, source.source);

      if (segments.length === 0) {
        console.log(`  ${label} ... 0 segments`);
        return 0;
      }

      if (PREVIEW) {
        console.log(`  ${label} ... ${segments.length} segment(s):`);
        for (const seg of segments) {
          console.log(`\n  [${seg.topic_label}]`);
          console.log(`  ${seg.condensed_content.slice(0, 200)}${seg.condensed_content.length > 200 ? '...' : ''}`);
        }
        return 0;
      }

      // Embed all segment texts via Voyage AI
      const embeddings = await embedDocuments(segments.map((s) => s.condensed_content));

      // Delete old segments if rebuilding this source
      if (REBUILD && segmentedIds.has(source.id)) {
        await supabase.from('segments').delete().eq('source_id', source.id);
      }

      const rows = segments.map((seg, i) => ({
        source_id:           source.id,
        topic_label:         seg.topic_label.trim(),
        processed_content:   seg.condensed_content.trim(),
        processed_embedding: embeddings[i],
      }));

      const { error: insertError } = await supabase.from('segments').insert(rows);
      if (insertError) throw new Error(`Insert failed: ${insertError.message}`);

      const durationMs = Date.now() - startMs;

      // Log extraction metrics — fire-and-forget
      supabase.from('extraction_logs').insert({
        source_id:     source.id,
        operation:     'segmentation',
        model:         'none',
        input_tokens:  0,
        output_tokens: 0,
        duration_ms:   durationMs,
      }).then(() => {}).catch(() => {});

      console.log(`  ${label} ... ${segments.length} segment(s) written`);
      return segments.length;

    } catch (err) {
      console.log(`  ${label} ... FAILED — ${err.message}`);
      failed++;
      return 0;
    }
  }

  // Process sources in concurrent batches (concurrency applies to embed+write step)
  console.log(`Processing ${sources.length} sources (concurrency: ${CONCURRENCY})...\n`);

  for (let i = 0; i < sources.length; i += CONCURRENCY) {
    const batch = sources.slice(i, i + CONCURRENCY);
    const results = await Promise.all(batch.map(processSource));
    totalSegments += results.reduce((a, b) => a + b, 0);

    const done = Math.min(i + CONCURRENCY, sources.length);
    if (done % 25 < CONCURRENCY || done === sources.length) {
      console.log(`  [${done}/${sources.length} sources, ${totalSegments} segments so far]\n`);
    }
  }

  if (!PREVIEW) {
    console.log(`\nDone. ${totalSegments} segments written across ${sources.length - failed} sources. ${failed} failed.`);
  }
}

main().catch((err) => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
