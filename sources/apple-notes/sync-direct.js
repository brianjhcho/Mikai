#!/usr/bin/env node
/**
 * sources/apple-notes/sync-direct.js
 *
 * Reads Apple Notes directly via osascript/AppleScript — no HTML export required.
 *
 * Usage (from MIKAI root):
 *   npm run sync:notes
 *   tsx sources/apple-notes/sync-direct.js [options]
 *
 * Options:
 *   --force      Re-ingest all notes, ignoring .synced-direct.json state
 *   --dry-run    Print what would be ingested, don't write anything
 *   --batch-size Number of notes per ingest batch (default: 50, max: 50)
 *   --limit      Max notes to read from Notes app (default: unlimited)
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { cleanContent } from '../../engine/ingestion/preprocess.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Config ────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const flag   = (name) => args.includes(name);
const option = (name, def) => { const i = args.indexOf(name); return i !== -1 && args[i + 1] ? args[i + 1] : def; };

const FORCE      = flag('--force');
const DRY_RUN    = flag('--dry-run');
const BATCH_SIZE = Math.min(parseInt(option('--batch-size', '50'), 10), 50);
const LIMIT      = option('--limit', null) ? parseInt(option('--limit', null), 10) : null;
const MAX_BODY_BYTES = 50 * 1024; // 50KB truncation limit
const MIN_CONTENT_LENGTH = 50;

const STATE_FILE = path.join(__dirname, '.synced-direct.json');

// ── State tracking ────────────────────────────────────────────────────────────

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); }
  catch { return {}; }
}

function saveState(state) {
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

// ── AppleScript helpers ───────────────────────────────────────────────────────

/**
 * Run an AppleScript snippet via osascript.
 * Returns stdout as a trimmed string, or throws on failure.
 */
function runAppleScript(script) {
  try {
    return execSync(`osascript -e ${JSON.stringify(script)}`, {
      encoding: 'utf8',
      timeout: 60_000,
      // suppress stderr bleed into our output
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  } catch (err) {
    const stderr = err.stderr?.toString() ?? '';
    if (stderr.includes('Not authorized') || stderr.includes('permission')) {
      throw new Error(
        'Permission denied: Apple Notes access requires "Full Disk Access" or ' +
        '"Automation" permission in System Preferences → Security & Privacy. ' +
        `Original error: ${stderr.trim()}`
      );
    }
    if (stderr.includes('Application isn\'t running') || stderr.includes('-1728')) {
      throw new Error('Notes app is not running. Open Notes.app and try again.');
    }
    throw new Error(`AppleScript error: ${stderr.trim() || err.message}`);
  }
}

/**
 * Get total note count from Notes app.
 */
function getNoteCount() {
  const result = runAppleScript('tell application "Notes" to count of notes');
  return parseInt(result, 10);
}

/**
 * Fetch a batch of notes by 1-based index range.
 * Returns an array of { name, body, modDate, folder } objects.
 *
 * AppleScript indexing is 1-based and inclusive on both ends.
 * We fetch name, body, modification date, and folder name in one call
 * to minimize round-trips.
 */
function fetchNotesBatch(startIdx, endIdx) {
  // AppleScript: get properties of notes startIdx through endIdx
  // We fetch each property as a list to avoid the overhead of record serialization.
  const script = `
    tell application "Notes"
      set noteRange to notes ${startIdx} through ${endIdx}
      set nameList to name of noteRange
      set bodyList to body of noteRange
      set dateList to modification date of noteRange
      set folderList to {}
      repeat with n in noteRange
        try
          set folderList to folderList & {name of container of n}
        on error
          set folderList to folderList & {""}
        end try
      end repeat
      return {nameList, bodyList, dateList, folderList}
    end tell
  `.trim();

  const raw = runAppleScript(script);

  // AppleScript returns a comma-separated list representation.
  // We parse it by splitting on the known record boundary.
  // The result is: {{name1, name2, ...}, {body1, body2, ...}, {date1, date2, ...}, {folder1, ...}}
  // This is tricky to parse reliably for large bodies, so we use a safer per-note approach
  // for the body (which may contain commas), but batch names/dates/folders.
  // Actually: we use a dedicated per-property extraction approach below.

  return parseAppleScriptBatchResult(raw, endIdx - startIdx + 1);
}

/**
 * Fetch notes one at a time when the batch approach fails (fallback).
 * Used when note bodies contain characters that confuse the batch parser.
 */
function fetchNoteSingle(idx) {
  // Fetch name, body, modification date, folder separately
  const name = runAppleScript(`tell application "Notes" to get name of note ${idx}`);
  const body = runAppleScript(`tell application "Notes" to get body of note ${idx}`);
  const modDateRaw = runAppleScript(`tell application "Notes" to get modification date of note ${idx}`);
  let folder = '';
  try {
    folder = runAppleScript(
      `tell application "Notes" to get name of container of note ${idx}`
    );
  } catch { /* folder unavailable */ }

  return { name, body, modDate: modDateRaw, folder };
}

/**
 * Parse the AppleScript batch result.
 *
 * AppleScript returns multi-list results as:
 *   {{item1, item2, ...}, {item1, item2, ...}, ...}
 *
 * Because note bodies can contain arbitrary text including braces and commas,
 * reliable parsing of the raw string is fragile. Instead we use a simpler
 * strategy: fetch just name + modDate + folder in the batch (safe fields),
 * and fetch body separately only for notes that need processing.
 */
function parseAppleScriptBatchResult(raw, expectedCount) {
  // This function is intentionally left as a stub — the actual implementation
  // uses the safer fetchNotesMeta / fetchNoteBody split below.
  // Kept for reference; not called directly.
  return [];
}

/**
 * Fetch metadata (name, modDate, folder) for a range of notes.
 * Bodies are NOT fetched here — only fetched when a note needs processing.
 * This is the safe batch approach: name/date/folder are short strings.
 */
function fetchNotesMeta(startIdx, endIdx) {
  const count = endIdx - startIdx + 1;

  // Fetch all three properties as separate lists in one AppleScript call.
  // This is safe because names, dates, and folder names don't contain braces.
  const script = `
    tell application "Notes"
      set noteRange to notes ${startIdx} through ${endIdx}
      set nameList to name of noteRange
      set dateList to modification date of noteRange
      set folderList to {}
      repeat with n in noteRange
        try
          set folderList to folderList & {name of container of n}
        on error
          set folderList to folderList & {""}
        end try
      end repeat
      -- Return as pipe-delimited records, one per line, tab-separated fields
      set output to ""
      repeat with i from 1 to count of nameList
        set noteName to item i of nameList
        set noteDate to item i of dateList as string
        set noteFolder to item i of folderList
        set output to output & noteName & "\t" & noteDate & "\t" & noteFolder & "\n"
      end repeat
      return output
    end tell
  `.trim();

  try {
    const raw = runAppleScript(script);
    const lines = raw.split('\n').filter(l => l.trim().length > 0);
    return lines.slice(0, count).map((line, i) => {
      const parts = line.split('\t');
      return {
        index: startIdx + i,
        name: parts[0] ?? `Note ${startIdx + i}`,
        modDate: parts[1] ?? '',
        folder: parts[2] ?? '',
      };
    });
  } catch (err) {
    // If batch meta fetch fails, fall back to individual fetches
    console.warn(`  warn: batch meta fetch failed for [${startIdx}–${endIdx}]: ${err.message}`);
    const results = [];
    for (let i = startIdx; i <= endIdx; i++) {
      try {
        const name = runAppleScript(`tell application "Notes" to get name of note ${i}`);
        const modDate = runAppleScript(`tell application "Notes" to get modification date of note ${i} as string`);
        let folder = '';
        try { folder = runAppleScript(`tell application "Notes" to get name of container of note ${i}`); } catch { /* ok */ }
        results.push({ index: i, name, modDate, folder });
      } catch (singleErr) {
        console.warn(`  warn: could not fetch meta for note ${i}: ${singleErr.message}`);
      }
    }
    return results;
  }
}

/**
 * Fetch the body of a single note by 1-based index.
 * Truncates to MAX_BODY_BYTES bytes.
 */
function fetchNoteBody(idx) {
  const body = runAppleScript(`tell application "Notes" to get body of note ${idx}`);
  // Truncate at byte boundary (approximate using char count)
  if (body.length > MAX_BODY_BYTES) {
    return body.slice(0, MAX_BODY_BYTES);
  }
  return body;
}

// ── Type inference (mirrors sync.js) ─────────────────────────────────────────

function inferType(text) {
  const lower = text.toLowerCase();
  if (lower.includes('http') || lower.includes('www.')) return 'web_clip';
  if (lower.includes('[') && lower.includes(']')) return 'note';
  if (lower.split('\n').length < 5) return 'note';
  return 'document';
}

// ── State key: name + folder as stable dedup key ──────────────────────────────

function stateKey(name, folder) {
  return `${folder ? folder + '/' : ''}${name}`;
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  // ── Step 1: Verify Notes access ───────────────────────────────────────────
  process.stdout.write('Checking Apple Notes access... ');
  let totalNotes;
  try {
    totalNotes = getNoteCount();
    console.log(`${totalNotes} notes found`);
  } catch (err) {
    console.error(`\nFailed: ${err.message}`);
    process.exit(1);
  }

  if (totalNotes === 0) {
    console.log('No notes in Apple Notes. Nothing to sync.');
    return;
  }

  // ── Step 2: Load state and determine which notes need processing ───────────
  const state = FORCE ? {} : loadState();
  const limit = LIMIT ?? totalNotes;
  const maxIndex = Math.min(totalNotes, limit);

  console.log(`Processing notes 1–${maxIndex} (batch size: ${BATCH_SIZE})...`);

  // ── Step 3: Scan all note metadata in batches ─────────────────────────────
  const allMeta = [];
  for (let start = 1; start <= maxIndex; start += BATCH_SIZE) {
    const end = Math.min(start + BATCH_SIZE - 1, maxIndex);
    process.stdout.write(`  Fetching metadata [${start}–${end}]... `);
    const batch = fetchNotesMeta(start, end);
    allMeta.push(...batch);
    console.log(`${batch.length} ok`);
  }

  // ── Step 4: Determine pending notes ───────────────────────────────────────
  //
  // A note is pending if:
  //   1. Its state key is not in .synced-direct.json, OR
  //   2. Its modification date is newer than the last sync timestamp
  //
  const pending = [];
  let skipped = 0;

  for (const meta of allMeta) {
    const key = stateKey(meta.name, meta.folder);
    const existing = state[key];

    if (existing) {
      // Check if note has been modified since last sync
      const lastSynced = new Date(existing.synced_at);
      const modDate = meta.modDate ? new Date(meta.modDate) : null;

      if (modDate && modDate <= lastSynced) {
        skipped++;
        continue;
      }
      // Modified since last sync — re-ingest
    }

    pending.push(meta);
  }

  const found = allMeta.length;
  console.log(`\n${found} notes total | ${skipped} already synced | ${pending.length} to process`);

  if (DRY_RUN) {
    console.log('\n[dry-run — no data will be written]');
    let tooShort = 0;
    for (const meta of pending) {
      const key = stateKey(meta.name, meta.folder);
      console.log(`  would process: "${meta.name}" (folder: ${meta.folder || 'All Notes'}, modified: ${meta.modDate})`);
    }
    console.log(`\nSummary: ${found} notes found, ${pending.length} new/updated, ${skipped} skipped (already synced)`);
    return;
  }

  if (pending.length === 0) {
    console.log('Nothing to ingest. All notes are up to date.');
    return;
  }

  // ── Step 5: Fetch bodies and ingest in batches ────────────────────────────

  const { ingestNotes } = await import('../../engine/ingestion/ingest-direct.ts');

  let totalNew = 0;
  let totalTooShort = 0;
  let totalFailed = 0;

  // Process pending notes in ingest batches
  for (let b = 0; b < pending.length; b += BATCH_SIZE) {
    const batchMeta = pending.slice(b, b + BATCH_SIZE);
    const batchNum = Math.floor(b / BATCH_SIZE) + 1;
    const totalBatches = Math.ceil(pending.length / BATCH_SIZE);

    console.log(`\nBatch ${batchNum}/${totalBatches} (${batchMeta.length} notes)`);

    const notesToIngest = [];
    const metaForBatch = [];

    for (const meta of batchMeta) {
      // Fetch body for this note
      let body;
      try {
        process.stdout.write(`  Fetching body: "${meta.name}"... `);
        body = fetchNoteBody(meta.index);
        console.log(`${body.length} chars`);
      } catch (err) {
        console.log(`FAILED (${err.message})`);
        totalFailed++;
        continue;
      }

      // Clean the HTML body using the apple-notes cleaner
      const content = cleanContent(body, 'apple-notes');

      // Skip notes that are too short after cleaning
      if (content.length < MIN_CONTENT_LENGTH) {
        console.log(`  skip (too short after clean): "${meta.name}" (${content.length} chars)`);
        totalTooShort++;
        continue;
      }

      notesToIngest.push({
        content,
        label: meta.name || 'Untitled',
        type: inferType(content),
        source: 'apple-notes',
      });
      metaForBatch.push(meta);
    }

    if (notesToIngest.length === 0) {
      console.log('  (all notes in batch were too short or failed)');
      continue;
    }

    // Ingest the batch via direct ingest
    let results;
    try {
      results = await ingestNotes(notesToIngest);
    } catch (err) {
      console.log(`  BATCH FAILED — ${err.message}`);
      totalFailed += notesToIngest.length;
      continue;
    }

    // Process results and update state
    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      const meta = metaForBatch[i];
      const key = stateKey(meta.name, meta.folder);

      if (result.error) {
        console.log(`  x "${result.label}" — ${result.error}`);
        totalFailed++;
      } else {
        console.log(`  + "${result.label}" (chunks: ${result.chunks}, id: ${result.source_id})`);
        state[key] = {
          synced_at: new Date().toISOString(),
          source_id: result.source_id,
          label: result.label,
          folder: meta.folder,
          mod_date: meta.modDate,
        };
        saveState(state);
        totalNew++;
      }
    }
  }

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log(
    `\nDone. ${found} notes found, ${totalNew} new/updated ingested, ` +
    `${skipped} skipped (already synced), ${totalTooShort} too short, ${totalFailed} failed.`
  );
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
