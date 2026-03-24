#!/usr/bin/env node
/**
 * sources/local-files/sync.js
 *
 * Unified connector for local file sources: markdown documents, Claude
 * conversation JSON exports, and Perplexity thread exports (HTML or markdown).
 *
 * Drop files into the appropriate subdirectory and run this script.
 *
 * Directory layout:
 *   sources/local-files/export/
 *     markdown/        ← .md files (project docs, notes)
 *     claude-exports/  ← .json files (Claude conversation exports)
 *     perplexity/      ← .html or .md files (Perplexity thread exports)
 *
 * Usage (from MIKAI root):
 *   npm run sync:local
 *   npm run sync:local -- --dry-run
 *   npm run sync:local -- --force
 *   npm run sync:local -- --retry-failed
 *
 * Options:
 *   --batch-size    Notes per batch (default: 10, max: 20)
 *   --force         Re-ingest all files, ignoring state and Supabase dedup
 *   --dry-run       Print what would be ingested, don't write
 *   --retry-failed  Re-run pipeline on sources where chunk_count=0
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

const EXPORT_DIR   = path.join(__dirname, 'export');
const BATCH_SIZE   = Math.min(parseInt(option('--batch-size', '10'), 10), 20);
const STATE_FILE   = path.join(__dirname, '.synced.json');
const FORCE        = flag('--force');
const DRY_RUN      = flag('--dry-run');
const RETRY_FAILED = flag('--retry-failed');

// ── Subdirectory → handler config ─────────────────────────────────────────────

const HANDLERS = [
  {
    subdir:    'markdown',
    exts:      ['.md', '.txt'],
    source:    'manual',
    type:      'document',
    cleanType: 'markdown',
  },
  {
    subdir:    'claude-exports',
    exts:      ['.json'],
    source:    'claude-thread',
    type:      'llm_thread',
    cleanType: 'claude-export',
  },
  {
    subdir:    'perplexity',
    exts:      ['.json'],
    source:    'perplexity',
    type:      'llm_thread',
    cleanType: 'claude-export',
  },
  {
    subdir:    'perplexity',
    exts:      ['.html', '.htm'],
    source:    'perplexity',
    type:      'document',
    cleanType: 'browser',
  },
  {
    subdir:    'perplexity',
    exts:      ['.md'],
    source:    'perplexity',
    type:      'document',
    cleanType: 'markdown',
  },
];

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
  } catch { /* file not found */ }
  return env;
}

// ── Supabase helpers ──────────────────────────────────────────────────────────

function getSupabaseCreds() {
  const envPath = path.join(__dirname, '../../.env.local');
  const env = readEnvFile(envPath);
  return {
    supabaseUrl: env['SUPABASE_URL'],
    supabaseKey: env['SUPABASE_SERVICE_KEY'],
  };
}

async function fetchExistingLabels() {
  const { supabaseUrl, supabaseKey } = getSupabaseCreds();
  if (!supabaseUrl || !supabaseKey) {
    console.warn('  warn: SUPABASE_URL / SUPABASE_SERVICE_KEY not found — dedup skipped');
    return new Set();
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);

  try {
    const res = await fetch(
      `${supabaseUrl}/rest/v1/sources?chunk_count=gt.0&select=label`,
      {
        headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}` },
        signal: controller.signal,
      }
    );
    clearTimeout(timer);
    if (!res.ok) { console.warn(`  warn: dedup query failed (HTTP ${res.status})`); return new Set(); }
    const rows = await res.json();
    return new Set(rows.map((r) => r.label));
  } catch (err) {
    clearTimeout(timer);
    console.warn(`  warn: dedup check failed (${err.message})`);
    return new Set();
  }
}

async function fetchFailedSources() {
  const { supabaseUrl, supabaseKey } = getSupabaseCreds();
  if (!supabaseUrl || !supabaseKey) {
    console.error('SUPABASE_URL / SUPABASE_SERVICE_KEY not set in .env.local');
    process.exit(1);
  }

  const res = await fetch(
    `${supabaseUrl}/rest/v1/sources?chunk_count=eq.0&raw_content=not.is.null&select=id,label,raw_content,type,source`,
    { headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}` } }
  );
  if (!res.ok) { console.error(`Supabase query failed: HTTP ${res.status}`); process.exit(1); }
  const rows = await res.json();
  return rows.filter((r) => r.raw_content && r.raw_content.trim().length >= 50);
}

// ── Title extraction ──────────────────────────────────────────────────────────

function extractTitleFromMarkdown(content) {
  const match = content.match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : null;
}

function extractTitleFromJson(raw) {
  try {
    const parsed = JSON.parse(raw);
    return parsed.title ?? parsed.name ?? parsed.subject ?? null;
  } catch {
    return null;
  }
}

function extractTitleFromHtml(raw) {
  const m = raw.match(/<title[^>]*>([^<]+)<\/title>/i)
         || raw.match(/<h1[^>]*>([^<]+)<\/h1>/i);
  return m ? m[1].replace(/&amp;/g, '&').trim() : null;
}

function extractTitle(raw, ext) {
  if (ext === '.md' || ext === '.txt') return extractTitleFromMarkdown(raw);
  if (ext === '.json') return extractTitleFromJson(raw);
  if (ext === '.html' || ext === '.htm') return extractTitleFromHtml(raw);
  return null;
}

// ── Batch ingestion: direct Supabase write (no web server needed) ─────────────

async function postBatch(notes) {
  const { ingestNotes } = await import('../../engine/ingestion/ingest-direct.ts');
  const results = await ingestNotes(notes);
  return { results };
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {

  // ── --retry-failed mode ─────────────────────────────────────────────────────
  if (RETRY_FAILED) {
    process.stdout.write('Fetching failed source records from Supabase... ');
    const failed = await fetchFailedSources();
    console.log(`${failed.length} found`);
    if (failed.length === 0) { console.log('Nothing to retry.'); return; }

    const batches = [];
    for (let i = 0; i < failed.length; i += BATCH_SIZE) batches.push(failed.slice(i, i + BATCH_SIZE));
    console.log(`${failed.length} failed records → ${batches.length} batch(es)`);

    if (DRY_RUN) {
      console.log('\n[dry-run]');
      for (const r of failed) console.log(`  would retry: "${r.label}" (${r.id})`);
      return;
    }

    let synced = 0, retryFailed = 0;
    for (let b = 0; b < batches.length; b++) {
      const batch = batches[b];
      console.log(`\nBatch ${b + 1}/${batches.length} (${batch.length} notes)`);
      const notes = batch.map((r) => ({ content: r.raw_content, label: r.label, type: r.type || 'document', source: r.source || 'manual', source_id: r.id }));
      try {
        const { results } = await postBatch(notes);
        for (let i = 0; i < results.length; i++) {
          const r = results[i];
          if (r.error) { console.log(`  ✗ ${batch[i].label} — ${r.error}`); retryFailed++; }
          else { console.log(`  ✓ ${batch[i].label}  (chunks: ${r.chunks})`); synced++; }
        }
      } catch (err) {
        console.log(`  BATCH FAILED — ${err.message}`);
        retryFailed += batch.length;
      }
    }
    console.log(`\nDone. ${synced} recovered, ${retryFailed} still failed.`);
    return;
  }

  // ── Normal sync mode ────────────────────────────────────────────────────────

  process.stdout.write(`Checking Supabase for already-ingested labels... `);
  const existingLabels = FORCE ? new Set() : await fetchExistingLabels();
  console.log(`${existingLabels.size} found`);

  const state = FORCE ? {} : loadState();
  const pending = [];
  let skippedState = 0, skippedSupabase = 0, tooShort = 0;

  for (const handler of HANDLERS) {
    const dir = path.join(EXPORT_DIR, handler.subdir);
    if (!fs.existsSync(dir)) continue;

    const files = fs.readdirSync(dir)
      .filter((f) => handler.exts.includes(path.extname(f).toLowerCase()))
      .map((f) => path.join(dir, f));

    for (const filePath of files) {
      if (state[filePath]) { skippedState++; continue; }

      const raw = fs.readFileSync(filePath, 'utf8');
      const ext = path.extname(filePath).toLowerCase();
      const basename = path.basename(filePath, ext);

      const titleRaw = extractTitle(raw, ext) || basename.replace(/[-_]/g, ' ');
      const label = titleRaw.trim() || 'Untitled';

      if (!FORCE && existingLabels.has(label)) {
        state[filePath] = { synced_at: new Date().toISOString(), label, via: 'supabase-dedup' };
        skippedSupabase++;
        continue;
      }

      const content = cleanContent(raw, handler.cleanType);
      if (content.length < 50) { tooShort++; continue; }

      pending.push({ filePath, label, content, type: handler.type, source: handler.source });
    }
  }

  if (!FORCE && skippedSupabase > 0) saveState(state);

  const batches = [];
  for (let i = 0; i < pending.length; i += BATCH_SIZE) batches.push(pending.slice(i, i + BATCH_SIZE));

  console.log(
    `${pending.length + skippedState + skippedSupabase + tooShort} files scanned | ` +
    `${skippedState} in .synced.json | ` +
    `${skippedSupabase} dedup'd from Supabase | ` +
    `${tooShort} too short | ` +
    `${pending.length} pending → ${batches.length} batch(es) of ${BATCH_SIZE}`
  );

  if (DRY_RUN) {
    console.log('\n[dry-run — no data will be written]');
    for (const item of pending) {
      const words = item.content.split(/\s+/).filter(Boolean).length;
      console.log(`  would ingest: "${item.label}" (${item.source}/${item.type}, ${words} words)`);
    }
    return;
  }

  if (pending.length === 0) { console.log('Nothing to ingest.'); return; }

  let synced = 0, failed = 0;

  for (let b = 0; b < batches.length; b++) {
    const batch = batches[b];
    console.log(`\nBatch ${b + 1}/${batches.length} (${batch.length} notes)`);

    const notes = batch.map(({ content, label, type, source }) => ({ content, label, type, source }));

    try {
      const { results } = await postBatch(notes);
      for (let i = 0; i < results.length; i++) {
        const r = results[i];
        const { filePath, label } = batch[i];
        if (r.error) { console.log(`  ✗ ${label} — ${r.error}`); failed++; }
        else {
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

main().catch((err) => { console.error('Fatal:', err.message); process.exit(1); });
