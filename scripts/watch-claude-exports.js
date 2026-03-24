#!/usr/bin/env node
/**
 * scripts/watch-claude-exports.js
 *
 * Watches sources/local-files/export/claude-exports/ for new .json or .zip files.
 * When a new Claude export is detected, automatically:
 *   0. If .zip → extract + split conversations.json into individual files
 *   1. npm run sync:local   (ingests new JSON into Supabase sources table)
 *   2. npm run build-segments -- --sources claude-thread  (segments + embeds)
 *
 * Usage:
 *   node scripts/watch-claude-exports.js
 *
 * Drop your Claude export (.json or .zip) into:
 *   sources/local-files/export/claude-exports/
 *
 * How to export from Claude:
 *   claude.ai → Settings → Export data → Download → drop file into the folder above
 */

import fs      from 'fs';
import path    from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __dirname  = path.dirname(fileURLToPath(import.meta.url));
const ROOT       = path.join(__dirname, '..');
const WATCH_DIR  = path.join(ROOT, 'sources/local-files/export/claude-exports');

console.log(`Watching for new Claude exports in:`);
console.log(`  ${WATCH_DIR}`);
console.log(`\nDrop .json or .zip files exported from claude.ai into that folder.`);
console.log(`Processing will start automatically.\n`);

// Track files we've already processed to avoid double-triggering
const processed = new Set(fs.readdirSync(WATCH_DIR).filter((f) => f.endsWith('.json') || f.endsWith('.zip')));
console.log(`${processed.size} existing file(s) already present — skipping those.\n`);

/**
 * Extract a Claude .zip export and split conversations.json into individual files.
 * Returns the number of conversation files created.
 */
function extractAndSplitZip(zipPath) {
  console.log(`  Extracting zip: ${path.basename(zipPath)}`);
  execSync(`unzip -o "${zipPath}" -d "${WATCH_DIR}"`, { stdio: 'pipe' });

  const convoPath = path.join(WATCH_DIR, 'conversations.json');
  if (!fs.existsSync(convoPath)) {
    console.log('  No conversations.json found in zip — skipping split');
    return 0;
  }

  const data = JSON.parse(fs.readFileSync(convoPath, 'utf8'));
  if (!Array.isArray(data)) {
    console.log('  conversations.json is not an array — skipping split');
    return 0;
  }

  let written = 0;
  for (const convo of data) {
    const uuid = convo.uuid || convo.id;
    if (!uuid) continue;

    const title = (convo.name || convo.title || uuid)
      .replace(/[^a-zA-Z0-9_\- ]/g, '')
      .replace(/\s+/g, '_')
      .slice(0, 80);

    const outPath = path.join(WATCH_DIR, `${uuid}_${title}.json`);
    if (fs.existsSync(outPath)) continue;

    // Write individual conversation with title + chat_messages
    const individual = {
      title: convo.name || convo.title || uuid,
      chat_messages: convo.chat_messages || convo.messages || [],
    };
    fs.writeFileSync(outPath, JSON.stringify(individual, null, 2));
    written++;
  }

  console.log(`  Split ${data.length} conversations → ${written} new files`);
  return written;
}

function runPipeline() {
  console.log(`\n[${new Date().toLocaleTimeString()}] New Claude export detected — running pipeline...\n`);
  try {
    console.log('→ Step 1: sync:local');
    execSync('npm run sync:local', { cwd: ROOT, stdio: 'inherit' });

    console.log('\n→ Step 2: build-segments (claude-thread only)');
    execSync('npm run build-segments -- --sources claude-thread', { cwd: ROOT, stdio: 'inherit' });

    console.log('\n✓ Done. New Claude threads are now searchable via /api/chat/synthesize\n');
  } catch (err) {
    console.error('\n✗ Pipeline failed:', err.message);
  }
}

let debounceTimer = null;

fs.watch(WATCH_DIR, (eventType, filename) => {
  if (!filename) return;
  if (processed.has(filename)) return;

  const ext = path.extname(filename).toLowerCase();

  if (ext === '.zip') {
    processed.add(filename);
    console.log(`  Detected zip: ${filename}`);
    try {
      extractAndSplitZip(path.join(WATCH_DIR, filename));
    } catch (err) {
      console.error(`  Zip extraction failed: ${err.message}`);
      return;
    }
    // After extracting, trigger pipeline
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runPipeline, 2000);
  } else if (ext === '.json') {
    processed.add(filename);
    console.log(`  Detected: ${filename}`);
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runPipeline, 2000);
  }
});
