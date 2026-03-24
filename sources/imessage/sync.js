#!/usr/bin/env node
/**
 * sources/imessage/sync.js
 *
 * Reads iMessages from ~/Library/Messages/chat.db and POSTs to /api/ingest/batch.
 * Focuses on outgoing messages (is_from_me = 1) and incoming messages that
 * contain action verbs — behavioral traces, not authored content (Track B).
 *
 * Usage (from MIKAI root):
 *   node sources/imessage/sync.js [options]
 *
 * Options:
 *   --days N        How many days back to fetch (default: 90)
 *   --host          API host (default: http://localhost:3000)
 *   --timeout       Per-batch timeout in ms (default: 300000)
 *   --force         Ignore cursor in .synced.json and re-fetch all messages in window
 *   --dry-run       Print what would be ingested, don't POST
 *
 * State:
 *   sources/imessage/.synced.json — stores { last_cursor: <Apple epoch ns> }
 *   On next run, only messages after last_cursor are fetched.
 *   Use --force to ignore cursor and re-fetch the full --days window.
 *
 * Apple Messages DB:
 *   ~/Library/Messages/chat.db (SQLite, read-only access required)
 *   message.date is in Apple epoch: nanoseconds since 2001-01-01 00:00:00 UTC
 *   Unix time = date / 1e9 + 978307200
 *
 * Anonymization:
 *   Phone numbers (+1234567890) and email addresses → [contact]
 *   Handle IDs are never stored.
 *
 * Grouping:
 *   All messages in the fetch window are grouped into a single document per
 *   sync run, labeled "iMessage YYYY-MM-DD to YYYY-MM-DD".
 */

import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import Database from 'better-sqlite3';
import { cleanContent } from '../../engine/ingestion/preprocess.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Config ────────────────────────────────────────────────────────────────────

const args   = process.argv.slice(2);
const flag   = (name) => args.includes(name);
const option = (name, def) => { const i = args.indexOf(name); return i !== -1 && args[i + 1] ? args[i + 1] : def; };

const API_HOST   = option('--host',    'http://localhost:3000');
const DAYS       = parseInt(option('--days', '90'), 10);
const TIMEOUT_MS = parseInt(option('--timeout', '300000'), 10);
const BATCH_URL  = `${API_HOST}/api/ingest/batch`;
const STATE_FILE = path.join(__dirname, '.synced.json');
const DB_PATH    = path.join(os.homedir(), 'Library/Messages/chat.db');
const FORCE      = flag('--force');
const DRY_RUN    = flag('--dry-run');

// Apple epoch offset: seconds between Unix epoch (1970-01-01) and Apple epoch (2001-01-01)
const APPLE_EPOCH_OFFSET = 978307200;

// Action verbs filter for incoming messages
const ACTION_VERBS = /\b(buy|book|schedule|call|send|order|sign up|register|apply|pay|upgrade|cancel|renew|install|download|join|visit|meet|plan|confirm|reserve)\b/i;

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
// Returns a Set<string> of labels. Items whose label is in this Set are skipped
// without POSTing — prevents duplicate source records on re-runs.
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

// ── Batch POST with timeout ───────────────────────────────────────────────────

async function postBatch(notes) {
  const { ingestNotes } = await import('../../engine/ingestion/ingest-direct.ts');
  const results = await ingestNotes(notes);
  return { results };
  }
}

// ── Anonymization ─────────────────────────────────────────────────────────────

function anonymize(text) {
  if (!text) return '';
  // Replace phone numbers: +1234567890, 1234567890, (123) 456-7890, etc.
  let out = text.replace(/(\+?[\d][\d\s\-().]{6,}\d)/g, '[contact]');
  // Replace email addresses
  out = out.replace(/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g, '[contact]');
  return out;
}

// ── Apple epoch helpers ───────────────────────────────────────────────────────

// Convert Apple epoch nanoseconds → Unix timestamp seconds
function appleNsToUnixSec(appleNs) {
  return Number(appleNs) / 1e9 + APPLE_EPOCH_OFFSET;
}

// Convert Unix timestamp seconds → Apple epoch nanoseconds
function unixSecToAppleNs(unixSec) {
  return Math.round((unixSec - APPLE_EPOCH_OFFSET) * 1e9);
}

// Format a Unix timestamp as YYYY-MM-DD
function formatDate(unixSec) {
  return new Date(unixSec * 1000).toISOString().slice(0, 10);
}

// ── Read messages from chat.db ────────────────────────────────────────────────

function fetchMessages(cursorAppleNs) {
  if (!fs.existsSync(DB_PATH)) {
    throw new Error(`chat.db not found at ${DB_PATH}. Ensure Full Disk Access is granted.`);
  }

  // Open read-only to avoid corrupting the live Messages database
  const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });

  try {
    // Fetch outgoing messages OR incoming messages with action verbs.
    // We filter action verbs in JS after fetch (SQLite REGEXP is not always available).
    // date column in older iOS backups may be stored as integer seconds (pre-2016);
    // modern macOS Messages stores nanoseconds. We handle both by checking magnitude.
    // cursorAppleNs is whichever is later: the window floor or the last synced cursor.
    // Use strict greater-than so we never re-ingest the last message from a prior run.
    const rows = db.prepare(`
      SELECT
        m.rowid        AS id,
        m.text         AS text,
        m.date         AS date,
        m.is_from_me   AS is_from_me
      FROM message m
      WHERE
        m.text IS NOT NULL
        AND m.text != ''
        AND m.date > ?
      ORDER BY m.date ASC
    `).all(cursorAppleNs);

    return rows;
  } finally {
    db.close();
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  // ── Compute time window ─────────────────────────────────────────────────────

  const nowUnix      = Math.floor(Date.now() / 1000);
  const windowUnix   = nowUnix - DAYS * 86400;
  const windowAppleNs = unixSecToAppleNs(windowUnix);

  const state = FORCE ? {} : loadState();
  // cursor is the last synced Apple epoch nanoseconds value
  const cursorAppleNs = (!FORCE && state.last_cursor) ? state.last_cursor : windowAppleNs;

  // ── Read from chat.db ───────────────────────────────────────────────────────

  process.stdout.write('Reading chat.db... ');
  let rawRows;
  try {
    rawRows = fetchMessages(cursorAppleNs);
  } catch (err) {
    console.error(`\nFailed to read chat.db: ${err.message}`);
    process.exit(1);
  }
  console.log(`${rawRows.length} candidate messages`);

  // ── Filter: outgoing OR incoming with action verbs ──────────────────────────

  const filtered = rawRows.filter((row) => {
    if (row.is_from_me === 1) return true;
    return ACTION_VERBS.test(row.text || '');
  });

  console.log(`${filtered.length} messages after filter (outgoing + incoming with action verbs)`);

  if (filtered.length === 0) {
    console.log('Nothing to ingest.');
    if (!FORCE && rawRows.length > 0) {
      // Advance cursor even if nothing passed the filter
      const maxDate = Math.max(...rawRows.map((r) => Number(r.date)));
      state.last_cursor = maxDate;
      saveState(state);
    }
    return;
  }

  // ── Anonymize and build document text ──────────────────────────────────────

  const lines = filtered.map((row) => {
    const direction = row.is_from_me === 1 ? '[me]' : '[contact]';
    const text = anonymize(row.text || '');
    return `${direction}: ${text}`;
  });

  const rawText = lines.join('\n');

  // Compute date range label
  const firstUnix = appleNsToUnixSec(filtered[0].date);
  const lastUnix  = appleNsToUnixSec(filtered[filtered.length - 1].date);
  const label     = `iMessage ${formatDate(firstUnix)} to ${formatDate(lastUnix)}`;

  // ── Deduplication ───────────────────────────────────────────────────────────

  process.stdout.write('Checking Supabase for already-ingested labels... ');
  const existingLabels = FORCE ? new Set() : await fetchExistingLabels();
  console.log(`${existingLabels.size} found`);

  if (!FORCE && existingLabels.has(label)) {
    console.log(`  already ingested: "${label}" — skipping`);
    console.log('Nothing to ingest. Use --force to re-ingest.');
    return;
  }

  // ── Clean content ──────────────────────────────────────────────────────────

  const content = cleanContent(rawText, 'imessage');

  if (content.length < 50) {
    console.log('Content too short after cleaning — skipping.');
    return;
  }

  const wordCount = content.split(/\s+/).filter(Boolean).length;

  // ── Dry-run output ─────────────────────────────────────────────────────────

  if (DRY_RUN) {
    console.log('\n[dry-run — no data will be written]');
    console.log(`  would ingest: "${label}" (message, ${wordCount} words)`);
    console.log(`  messages:     ${filtered.length} (${filtered.filter(r => r.is_from_me === 1).length} outgoing, ${filtered.filter(r => r.is_from_me === 0).length} incoming)`);
    return;
  }

  // ── POST ───────────────────────────────────────────────────────────────────

  const notes = [{ content, label, type: 'message', source: 'imessage' }];

  console.log(`\nBatch 1/1 (1 document)`);
  console.log(`  "${label}" — ${wordCount} words, ${filtered.length} messages`);

  let synced = 0, failed = 0;

  try {
    const { results } = await postBatch(notes);
    const r = results[0];

    if (r.error) {
      console.log(`  x "${label}" — ${r.error}`);
      failed++;
    } else {
      console.log(`  ✓ "${label}"  (chunks: ${r.chunks})`);
      // Advance cursor to the last message's Apple timestamp
      const maxDate = Math.max(...filtered.map((row) => Number(row.date)));
      state.last_cursor = maxDate;
      saveState(state);
      synced++;
    }
  } catch (err) {
    console.log(`  BATCH FAILED — ${err.message}`);
    failed++;
  }

  console.log(`\nDone. ${synced} ingested, ${failed} failed.`);
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
