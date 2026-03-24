#!/usr/bin/env node
/**
 * sources/apple-notes/sync.js
 *
 * Reads Apple Notes HTML export files and POSTs to /api/ingest/batch.
 *
 * Usage (from MIKAI root):
 *   node sources/apple-notes/sync.js [options]
 *
 * Options:
 *   --dir           Path to folder with .html files (default: ./sources/apple-notes/export)
 *   --host          API host (default: http://localhost:3000)
 *   --batch-size    Notes per batch request (default: 10, max: 20)
 *   --timeout       Per-batch timeout in ms (default: 120000)
 *   --force         Re-ingest all files, ignoring .synced.json and Supabase state
 *   --dry-run       Print what would be ingested, don't POST
 *   --retry-failed  Re-run the pipeline on sources where chunk_count=0 (pipeline crash recovery).
 *                   Reads raw_content from Supabase — no Apple Notes export needed.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { cleanContent } from '../../engine/ingestion/preprocess.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Config ────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const flag   = (name) => args.includes(name);
const option = (name, def) => { const i = args.indexOf(name); return i !== -1 && args[i + 1] ? args[i + 1] : def; };

const EXPORT_DIR  = option('--dir',        path.join(__dirname, 'export'));
const API_HOST    = option('--host',       'http://localhost:3000');
const BATCH_SIZE  = Math.min(parseInt(option('--batch-size', '10'), 10), 20);
const TIMEOUT_MS  = parseInt(option('--timeout', '300000'), 10);
const BATCH_URL   = `${API_HOST}/api/ingest/batch`;
const STATE_FILE  = path.join(__dirname, '.synced.json');
const FORCE        = flag('--force');
const DRY_RUN      = flag('--dry-run');
const RETRY_FAILED = flag('--retry-failed');

// ── State tracking ────────────────────────────────────────────────────────────

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); }
  catch { return {}; }
}

function saveState(state) {
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

// ── Env file reader ───────────────────────────────────────────────────────────

function readEnvFile(filePath) {
  const env = {};
  try {
    for (const line of fs.readFileSync(filePath, 'utf8').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx < 0) continue;
      env[trimmed.slice(0, eqIdx).trim()] = trimmed.slice(eqIdx + 1).trim();
    }
  } catch { /* file not found — env stays empty */ }
  return env;
}

// ── Deduplication: fetch already-ingested labels from Supabase ────────────────
//
// Queries sources WHERE chunk_count > 0 (fully ingested, not orphaned partials).
// Returns a Set<string> of labels. Files whose extracted title is in this Set
// are skipped without POSTing — prevents duplicate source records on re-runs.
//
// Credentials are read from .env.local at the project root.

async function fetchExistingLabels() {
  const envPath = path.join(__dirname, '../../.env.local');
  const env = readEnvFile(envPath);
  const supabaseUrl = env['SUPABASE_URL'];
  const supabaseKey = env['SUPABASE_SERVICE_KEY'];

  if (!supabaseUrl || !supabaseKey) {
    console.warn('  warn: SUPABASE_URL / SUPABASE_SERVICE_KEY not in .env.local — dedup skipped');
    return new Set();
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);

  try {
    // Only fetch labels where chunk_count > 0.
    // chunk_count = 0 means the pipeline crashed after creating the source record (orphan).
    // Those orphaned records are not considered "ingested" — they will be retried.
    const res = await fetch(
      `${supabaseUrl}/rest/v1/sources?chunk_count=gt.0&select=label`,
      {
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
        },
        signal: controller.signal,
      }
    );
    clearTimeout(timer);

    if (!res.ok) {
      console.warn(`  warn: Supabase dedup query failed (HTTP ${res.status}) — dedup skipped`);
      return new Set();
    }

    const rows = await res.json();
    return new Set(rows.map((r) => r.label));
  } catch (err) {
    clearTimeout(timer);
    console.warn(`  warn: Supabase dedup check failed (${err.message}) — dedup skipped`);
    return new Set();
  }
}

// ── Retry: fetch failed source records from Supabase ─────────────────────────
//
// Returns sources where chunk_count = 0 AND raw_content is not empty.
// These are orphaned records from prior pipeline crashes — the raw content is
// already stored in Supabase, so we can re-run the pipeline without re-reading
// from Apple Notes export files.

async function fetchFailedSources() {
  const envPath = path.join(__dirname, '../../.env.local');
  const env = readEnvFile(envPath);
  const supabaseUrl = env['SUPABASE_URL'];
  const supabaseKey = env['SUPABASE_SERVICE_KEY'];

  if (!supabaseUrl || !supabaseKey) {
    console.error('SUPABASE_URL / SUPABASE_SERVICE_KEY not in .env.local');
    process.exit(1);
  }

  const res = await fetch(
    `${supabaseUrl}/rest/v1/sources?chunk_count=eq.0&raw_content=not.is.null&select=id,label,raw_content,type,source`,
    {
      headers: {
        apikey: supabaseKey,
        Authorization: `Bearer ${supabaseKey}`,
      },
    }
  );

  if (!res.ok) {
    console.error(`Supabase query failed: HTTP ${res.status}`);
    process.exit(1);
  }

  const rows = await res.json();
  // Filter out empty content just in case
  return rows.filter((r) => r.raw_content && r.raw_content.trim().length >= 50);
}

// ── HTML parsing ──────────────────────────────────────────────────────────────

function extractTitle(html) {
  const m = html.match(/<title[^>]*>([^<]+)<\/title>/i) || html.match(/<h1[^>]*>([^<]+)<\/h1>/i);
  return m ? m[1].replace(/&amp;/g, '&').trim() : null;
}

function inferType(text) {
  const lower = text.toLowerCase();
  if (lower.includes('http') || lower.includes('www.')) return 'web_clip';
  if (lower.includes('[') && lower.includes(']')) return 'note';
  if (lower.split('\n').length < 5) return 'note';
  return 'document';
}

// ── Batch ingestion: try direct Supabase write first, fall back to HTTP POST ──
//
// Direct path: imports ingest-direct.ts and writes to Supabase without
// requiring the Next.js dev server to be running.
// Fallback path: HTTP POST to localhost:3000/api/ingest/batch (original behavior).

async function postBatch(notes) {
  // ── Try direct ingest ────────────────────────────────────────────────────
  try {
    const { ingestNotes } = await import('../../engine/ingestion/ingest-direct.ts');
    const results = await ingestNotes(notes);
    console.log('  [via direct ingest]');
    return { results };
  } catch (directErr) {
    console.warn(`  warn: direct ingest failed (${directErr.message}) — falling back to HTTP`);
  }

  // ── Fall back to HTTP POST ───────────────────────────────────────────────
  console.log('  [via HTTP POST to localhost:3000]');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(BATCH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error ?? `HTTP ${res.status}`);
    }

    return res.json(); // { results: [...] }
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      throw new Error(`Batch timed out after ${TIMEOUT_MS / 1000}s`);
    }
    throw err;
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {

  // ── --retry-failed mode: reprocess orphaned source records ─────────────────
  //
  // Fetches sources with chunk_count = 0 from Supabase and re-runs the pipeline
  // on their stored raw_content. Passes the existing source_id to the batch API
  // so it updates the existing row instead of creating a duplicate.

  if (RETRY_FAILED) {
    process.stdout.write('Fetching failed source records from Supabase... ');
    const failed = await fetchFailedSources();
    console.log(`${failed.length} found`);

    if (failed.length === 0) {
      console.log('Nothing to retry.');
      return;
    }

    const batches = [];
    for (let i = 0; i < failed.length; i += BATCH_SIZE) {
      batches.push(failed.slice(i, i + BATCH_SIZE));
    }

    console.log(`${failed.length} failed records → ${batches.length} batch(es) of ${BATCH_SIZE}`);

    if (DRY_RUN) {
      console.log('\n[dry-run — no data will be written]');
      for (const r of failed) {
        const words = r.raw_content.split(/\s+/).filter(Boolean).length;
        console.log(`  would retry: "${r.label}" (id: ${r.id}, ${words} words)`);
      }
      return;
    }

    let synced = 0, retryFailed = 0;

    for (let b = 0; b < batches.length; b++) {
      const batch = batches[b];
      console.log(`\nBatch ${b + 1}/${batches.length} (${batch.length} notes)`);

      const notes = batch.map((r) => ({
        content: r.raw_content,
        label: r.label,
        type: r.type || 'note',
        source: r.source || 'apple-notes',
        source_id: r.id,
      }));

      try {
        const { results } = await postBatch(notes);

        for (let i = 0; i < results.length; i++) {
          const r = results[i];
          const record = batch[i];

          if (r.error) {
            console.log(`  ✗ ${record.label} — ${r.error}`);
            retryFailed++;
          } else {
            console.log(`  ✓ ${record.label}  (chunks: ${r.chunks})`);
            synced++;
          }
        }
      } catch (err) {
        console.log(`  BATCH FAILED — ${err.message}`);
        retryFailed += batch.length;
      }
    }

    console.log(`\nDone. ${synced} recovered, ${retryFailed} still failed.`);
    return;
  }

  if (!fs.existsSync(EXPORT_DIR)) {
    console.error(`Export directory not found: ${EXPORT_DIR}`);
    process.exit(1);
  }

  const htmlFiles = fs.readdirSync(EXPORT_DIR)
    .filter(f => f.endsWith('.html') || f.endsWith('.htm'))
    .map(f => path.join(EXPORT_DIR, f));

  if (htmlFiles.length === 0) {
    console.log(`No .html files found in ${EXPORT_DIR}`);
    process.exit(0);
  }

  // ── Deduplication pass ─────────────────────────────────────────────────────

  process.stdout.write(`Checking Supabase for already-ingested labels... `);
  const existingLabels = FORCE ? new Set() : await fetchExistingLabels();
  console.log(`${existingLabels.size} found`);

  const state = FORCE ? {} : loadState();

  // ── Build pending list ─────────────────────────────────────────────────────
  //
  // A file is SKIPPED if any of these are true:
  //   1. It appears in .synced.json (confirmed successful on a prior run)
  //   2. Its extracted title exists in Supabase with chunk_count > 0
  //      (successful in a prior run but .synced.json was lost/wiped)
  //
  // A file is PENDING if it has never been successfully ingested.
  // Orphaned source records (chunk_count = 0) do NOT block re-ingestion.

  const pending = [];
  let skippedState = 0, skippedSupabase = 0;

  for (const filePath of htmlFiles) {
    if (state[filePath]) { skippedState++; continue; }

    const html = fs.readFileSync(filePath, 'utf8');
    const label = extractTitle(html) || path.basename(filePath, path.extname(filePath));

    if (!FORCE && existingLabels.has(label)) {
      // Write to .synced.json so future runs don't re-query Supabase for this file
      state[filePath] = { synced_at: new Date().toISOString(), label, via: 'supabase-dedup' };
      skippedSupabase++;
      continue;
    }

    const content = cleanContent(html, 'apple-notes');
    if (content.length < 50) continue; // too short to ingest

    pending.push({ filePath, label, content, type: inferType(content) });
  }

  if (!FORCE && skippedSupabase > 0) saveState(state); // persist dedup marks

  const batches = [];
  for (let i = 0; i < pending.length; i += BATCH_SIZE) {
    batches.push(pending.slice(i, i + BATCH_SIZE));
  }

  console.log(
    `${htmlFiles.length} files total | ` +
    `${skippedState} in .synced.json | ` +
    `${skippedSupabase} dedup'd from Supabase | ` +
    `${pending.length} pending → ${batches.length} batch(es) of ${BATCH_SIZE}`
  );

  if (DRY_RUN) {
    console.log('\n[dry-run — no data will be written]');
    for (const item of pending) {
      const words = item.content.split(/\s+/).filter(Boolean).length;
      console.log(`  would ingest: "${item.label}" (${item.type}, ${words} words)`);
    }
    return;
  }

  if (pending.length === 0) {
    console.log('Nothing to ingest.');
    return;
  }

  // ── Process batches ────────────────────────────────────────────────────────

  let synced = 0, failed = 0;

  for (let b = 0; b < batches.length; b++) {
    const batch = batches[b];
    const batchLabel = `Batch ${b + 1}/${batches.length} (${batch.length} notes)`;
    console.log(`\n${batchLabel}`);

    const notes = batch.map(({ content, label, type }) => ({
      content, label, type, source: 'apple-notes',
    }));

    try {
      const { results } = await postBatch(notes);

      for (let i = 0; i < results.length; i++) {
        const r = results[i];
        const { filePath, label } = batch[i];

        if (r.error) {
          console.log(`  ✗ ${label} — ${r.error}`);
          failed++;
        } else {
          console.log(`  ✓ ${label}  (chunks: ${r.chunks})`);
          state[filePath] = { synced_at: new Date().toISOString(), source_id: r.source_id, label };
          saveState(state);
          synced++;
        }
      }
    } catch (err) {
      console.log(`  BATCH FAILED — ${err.message}`);
      failed += batch.length;
    }
  }

  console.log(`\nDone. ${synced} ingested, ${failed} failed, ${skippedState + skippedSupabase} already ingested.`);
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
