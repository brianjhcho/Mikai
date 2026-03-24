#!/usr/bin/env node
/**
 * sources/gmail/sync.js
 *
 * Reads Gmail messages via Google API and POSTs to /api/ingest/batch.
 *
 * Usage (from MIKAI root):
 *   node sources/gmail/sync.js [options]
 *
 * Options:
 *   --days N        Fetch emails from last N days (default: 90)
 *   --label L       INBOX, SENT, or both (default: both)
 *   --host          API host (default: http://localhost:3000)
 *   --force         Re-ingest all emails, ignoring .synced.json and Supabase state
 *   --dry-run       Print what would be ingested, don't POST
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { google } from 'googleapis';
import { cleanContent } from '../../engine/ingestion/preprocess.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Config ────────────────────────────────────────────────────────────────────

const args   = process.argv.slice(2);
const flag   = (name) => args.includes(name);
const option = (name, def) => { const i = args.indexOf(name); return i !== -1 && args[i + 1] ? args[i + 1] : def; };

const API_HOST   = option('--host',  'http://localhost:3000');
const DAYS       = parseInt(option('--days', '90'), 10);
const LABEL_ARG  = option('--label', 'both');  // INBOX | SENT | both
const BATCH_SIZE = 10;
const TIMEOUT_MS = 300_000;
const BATCH_URL  = `${API_HOST}/api/ingest/batch`;
const STATE_FILE = path.join(__dirname, '.synced.json');
const FORCE      = flag('--force');
const DRY_RUN    = flag('--dry-run');

// Action-verb subject/body filter — only ingest emails likely to contain intent
const ACTION_VERBS = [
  'book', 'schedule', 'buy', 'purchase', 'order', 'reserve', 'plan',
  'research', 'decide', 'follow up', 'follow-up', 'check', 'review',
  'send', 'call', 'meet', 'fix', 'resolve', 'complete', 'finish',
  'apply', 'register', 'confirm', 'cancel', 'update', 'remind',
  'draft', 'write', 'prepare', 'organize', 'arrange', 'contact',
];
const ACTION_VERB_RE = new RegExp(`\\b(${ACTION_VERBS.join('|')})\\b`, 'i');

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
// Returns a Set<string> of labels.

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

// ── Email body extraction ─────────────────────────────────────────────────────

function decodeBase64Url(encoded) {
  // Gmail uses base64url encoding (- and _ instead of + and /)
  const base64 = encoded.replace(/-/g, '+').replace(/_/g, '/');
  return Buffer.from(base64, 'base64').toString('utf8');
}

function extractBodyFromParts(parts, preferredMime = 'text/plain') {
  if (!parts || parts.length === 0) return '';

  // Try preferred MIME type first
  for (const part of parts) {
    if (part.mimeType === preferredMime && part.body?.data) {
      return decodeBase64Url(part.body.data);
    }
    // Recurse into nested parts (multipart/alternative, multipart/mixed)
    if (part.parts) {
      const nested = extractBodyFromParts(part.parts, preferredMime);
      if (nested) return nested;
    }
  }

  // Fall back to text/html if text/plain not found
  if (preferredMime === 'text/plain') {
    return extractBodyFromParts(parts, 'text/html');
  }

  return '';
}

function extractBody(payload) {
  // Simple single-part message
  if (payload.body?.data) {
    return decodeBase64Url(payload.body.data);
  }
  // Multipart message
  if (payload.parts) {
    return extractBodyFromParts(payload.parts);
  }
  return '';
}

function stripQuotedReplies(text) {
  // Remove lines starting with >
  const lines = text.split('\n');
  const filtered = [];
  let inQuoteBlock = false;

  for (const line of lines) {
    // "On Mon, Jan 1 2024 ... wrote:" pattern — start of quoted reply block
    if (/^On .{10,100} wrote:/.test(line)) {
      inQuoteBlock = true;
      continue;
    }
    if (line.startsWith('>')) {
      inQuoteBlock = true;
      continue;
    }
    // Blank line after a quote block resets — but only if the block truly ended
    if (inQuoteBlock && line.trim() === '') continue;
    if (inQuoteBlock && !line.startsWith('>')) {
      inQuoteBlock = false;
    }
    filtered.push(line);
  }

  return filtered.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

function stripEmailHeaders(text) {
  // Strip forwarded message headers ("From:", "To:", "Date:", "Subject:" blocks at top)
  return text
    .replace(/^-{3,}.*?Forwarded message.*?-{3,}$/gim, '')
    .replace(/^(From|To|Cc|Bcc|Date|Subject|Sent|Reply-To):\s*.+$/gim, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function cleanEmailBody(rawBody, mimeType) {
  let text = rawBody;

  // Strip HTML if the body is HTML
  if (mimeType === 'text/html' || /<[a-z][\s\S]*>/i.test(text)) {
    text = cleanContent(text, 'browser');
  }

  text = stripQuotedReplies(text);
  text = stripEmailHeaders(text);

  return text.replace(/\n{3,}/g, '\n\n').trim();
}

function hasActionVerb(subject, body) {
  return ACTION_VERB_RE.test(subject) || ACTION_VERB_RE.test(body.slice(0, 500));
}

// ── Gmail API helpers ─────────────────────────────────────────────────────────

function buildAfterDateString(daysAgo) {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  const yyyy = d.getFullYear();
  const mm   = String(d.getMonth() + 1).padStart(2, '0');
  const dd   = String(d.getDate()).padStart(2, '0');
  return `${yyyy}/${mm}/${dd}`;
}

async function listMessageIds(gmail, labelId, afterDate) {
  const ids = [];
  let pageToken;

  do {
    // Pre-filter server-side using Gmail search OR syntax {word1 word2 ...}
    // This reduces individual message fetches from O(all messages) to O(matching messages).
    // Multi-word phrases (follow up) are excluded — single words catch the majority.
    const verbQuery = ACTION_VERBS.filter(v => !v.includes(' ')).join(' ');
    const res = await gmail.users.messages.list({
      userId: 'me',
      labelIds: [labelId],
      q: `after:${afterDate} {${verbQuery}}`,
      maxResults: 500,
      ...(pageToken ? { pageToken } : {}),
    });

    const messages = res.data.messages ?? [];
    for (const m of messages) ids.push(m.id);
    pageToken = res.data.nextPageToken;
  } while (pageToken);

  return ids;
}

async function fetchMessage(gmail, id) {
  const msg = await gmail.users.messages.get({
    userId: 'me',
    id,
    format: 'full',
  });
  return msg.data;
}

// ── Concurrent message fetcher ────────────────────────────────────────────────

const CONCURRENCY = 10;

async function fetchAllMessages(gmail, ids, onFetched) {
  let i = 0;
  let completed = 0;
  const total = ids.length;

  async function worker() {
    while (i < ids.length) {
      const id = ids[i++];
      try {
        const msg = await fetchMessage(gmail, id);
        completed++;
        if (completed % 100 === 0) {
          process.stdout.write(`  ${completed}/${total}...\r`);
        }
        await onFetched(msg);
      } catch (err) {
        // skip failed message fetch
      }
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  process.stdout.write('\n');
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  // ── Load credentials ───────────────────────────────────────────────────────

  const envPath = path.join(__dirname, '../../.env.local');
  const env = readEnvFile(envPath);

  const CLIENT_ID     = env['GMAIL_CLIENT_ID'];
  const CLIENT_SECRET = env['GMAIL_CLIENT_SECRET'];
  const REFRESH_TOKEN = env['GMAIL_REFRESH_TOKEN'];

  if (!CLIENT_ID || !CLIENT_SECRET || !REFRESH_TOKEN) {
    console.error(
      'Missing Gmail credentials in .env.local.\n' +
      'Required: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN\n' +
      'See sources/gmail/SETUP.md for how to obtain these.'
    );
    process.exit(1);
  }

  // ── Set up Gmail client ────────────────────────────────────────────────────

  const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET);
  oauth2Client.setCredentials({ refresh_token: REFRESH_TOKEN });

  // Verify token works before scanning thousands of messages
  try {
    await oauth2Client.getAccessToken();
  } catch (err) {
    console.error(
      `OAuth2 token refresh failed: ${err.message}\n` +
      'Your refresh token may be expired or revoked.\n' +
      'Follow sources/gmail/SETUP.md to generate a new refresh token.'
    );
    process.exit(1);
  }

  const gmail = google.gmail({ version: 'v1', auth: oauth2Client });

  // ── Determine which labels to scan ────────────────────────────────────────

  const labelsToScan = [];
  if (LABEL_ARG === 'both' || LABEL_ARG === 'SENT')  labelsToScan.push('SENT');
  if (LABEL_ARG === 'both' || LABEL_ARG === 'INBOX') labelsToScan.push('INBOX');

  if (labelsToScan.length === 0) {
    console.error(`Unknown --label value: ${LABEL_ARG}. Use INBOX, SENT, or both.`);
    process.exit(1);
  }

  const afterDate = buildAfterDateString(DAYS);
  console.log(`Scanning ${labelsToScan.join(' + ')} from last ${DAYS} days (after ${afterDate})`);

  // ── Load state and Supabase dedup ─────────────────────────────────────────

  process.stdout.write('Checking Supabase for already-ingested labels... ');
  const existingLabels = FORCE ? new Set() : await fetchExistingLabels();
  console.log(`${existingLabels.size} found`);

  const state = FORCE ? {} : loadState();
  // state is a plain object keyed by message ID

  // ── Collect message IDs ────────────────────────────────────────────────────

  let allIds = [];
  for (const labelId of labelsToScan) {
    process.stdout.write(`  Listing ${labelId} messages... `);
    const ids = await listMessageIds(gmail, labelId, afterDate);
    console.log(`${ids.length} found`);
    allIds = allIds.concat(ids);
  }

  // Deduplicate IDs (a message can appear in both INBOX and SENT if self-sent)
  allIds = [...new Set(allIds)];

  // ── Fetch and filter messages ──────────────────────────────────────────────

  console.log(`\nFetching ${allIds.length} messages (filtering by action verbs)...`);

  const pending = [];
  let skippedState = 0, skippedSupabase = 0, skippedNoAction = 0;

  // Pre-filter IDs already in state file before fetching
  const idsToFetch = [];
  for (const id of allIds) {
    if (state[id]) { skippedState++; } else { idsToFetch.push(id); }
  }

  await fetchAllMessages(gmail, idsToFetch, async (msgData) => {
    const headers  = msgData.payload?.headers ?? [];
    const subject  = headers.find(h => h.name === 'Subject')?.value ?? '(no subject)';
    const dateHdr  = headers.find(h => h.name === 'Date')?.value ?? '';

    const rawBody  = extractBody(msgData.payload ?? {});
    const mimeType = msgData.payload?.mimeType ?? '';
    const body     = cleanEmailBody(rawBody, mimeType);

    if (body.length < 50) { skippedNoAction++; return; }

    // Newsletter/marketing filter — List-Unsubscribe header is legally required
    // on all bulk/newsletter emails (CAN-SPAM, GDPR). Precedence: bulk covers
    // promotional and transactional mailers that omit List-Unsubscribe (receipts,
    // promo codes, game notifications). Skip both: they produce noise nodes.
    const hasListUnsubscribe = headers.some(h => h.name === 'List-Unsubscribe');
    const hasPrecedenceBulk  = headers.some(
      h => h.name.toLowerCase() === 'precedence' && h.value.toLowerCase().includes('bulk')
    );
    if (hasListUnsubscribe || hasPrecedenceBulk) { skippedNoAction++; return; }

    // Action-verb filter
    if (!hasActionVerb(subject, body)) { skippedNoAction++; return; }

    const label = `Gmail: ${subject}`.slice(0, 100);

    // Supabase dedup
    if (!FORCE && existingLabels.has(label)) {
      state[msgData.id] = { synced_at: new Date().toISOString(), label, via: 'supabase-dedup' };
      skippedSupabase++;
      return;
    }

    const content = cleanContent(body, 'gmail');

    pending.push({ id: msgData.id, label, content, date: dateHdr });
  });

  if (!FORCE && skippedSupabase > 0) saveState(state);

  const batches = [];
  for (let i = 0; i < pending.length; i += BATCH_SIZE) {
    batches.push(pending.slice(i, i + BATCH_SIZE));
  }

  console.log(
    `${allIds.length} messages total | ` +
    `${skippedState} in .synced.json | ` +
    `${skippedSupabase} dedup'd from Supabase | ` +
    `${skippedNoAction} skipped (no action verb / too short) | ` +
    `${pending.length} pending → ${batches.length} batch(es) of ${BATCH_SIZE}`
  );

  if (DRY_RUN) {
    console.log('\n[dry-run — no data will be written]');
    for (const item of pending) {
      const words = item.content.split(/\s+/).filter(Boolean).length;
      console.log(`  would ingest: "${item.label}" (email, ${words} words)`);
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
    console.log(`\nBatch ${b + 1}/${batches.length} (${batch.length} emails)`);

    const notes = batch.map(({ content, label }) => ({
      content, label, type: 'email', source: 'gmail',
    }));

    try {
      const { results } = await postBatch(notes);

      for (let i = 0; i < results.length; i++) {
        const r      = results[i];
        const { id, label } = batch[i];

        if (r.error) {
          console.log(`  x ${label} — ${r.error}`);
          failed++;
        } else {
          console.log(`  + ${label}  (chunks: ${r.chunks})`);
          state[id] = { synced_at: new Date().toISOString(), source_id: r.source_id, label };
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
