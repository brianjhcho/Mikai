#!/usr/bin/env node
/**
 * Cleans up junk rows in the `sources` table:
 *   - [DEBUG] prefixed records from debug-single.js runs
 *   - Known test/verification records created during pipeline testing
 *
 * Real notes with chunk_count = 0 (pipeline failures) are LEFT INTACT
 * so they can be recovered with: node sources/apple-notes/sync.js --retry-failed
 *
 * Usage (from MIKAI root):
 *   npm run cleanup             # delete for real
 *   npm run cleanup -- --dry-run  # preview only
 */

import { createClient } from '@supabase/supabase-js';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Labels that are definitively test/debug records, not real notes
const TEST_LABELS = new Set([
  'test',
  'Pipeline Verification Test',
  'Pipeline Verify v2',
  'Post-restart Test',
]);

// Load .env.local (Next.js doesn't inject env for standalone node scripts)
function loadEnv() {
  const envPath = resolve(__dirname, '../.env.local');
  const raw = readFileSync(envPath, 'utf8');
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    const val = trimmed.slice(eq + 1).trim();
    if (key) process.env[key] = val;
  }
}

loadEnv();

const { SUPABASE_URL, SUPABASE_SERVICE_KEY } = process.env;
if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
  console.error('Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env.local');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
const dryRun = process.argv.includes('--dry-run');

async function main() {
  // [DEBUG] prefixed rows
  const { data: debugRows, error: e1 } = await supabase
    .from('sources')
    .select('id, label, created_at')
    .like('label', '[DEBUG]%');
  if (e1) { console.error('Error fetching debug rows:', e1.message); process.exit(1); }

  // Known test labels (exact match, any chunk_count)
  const { data: allSources, error: e2 } = await supabase
    .from('sources')
    .select('id, label, created_at')
    .in('label', [...TEST_LABELS]);
  if (e2) { console.error('Error fetching test rows:', e2.message); process.exit(1); }

  console.log(`\n[DEBUG] records: ${debugRows.length}`);
  debugRows.forEach(r => console.log(`  ${r.id}  ${r.label}`));

  console.log(`\nTest records: ${allSources.length}`);
  allSources.forEach(r => console.log(`  ${r.id}  ${r.label}`));

  const allIds = [...new Set([...debugRows, ...allSources].map(r => r.id))];

  if (allIds.length === 0) {
    console.log('\nNothing to delete. All clean!');
    return;
  }

  console.log(`\nTotal rows to delete: ${allIds.length}`);
  console.log('(Real notes with chunk_count=0 are preserved — use sync.js --retry-failed to recover them)');

  if (dryRun) {
    console.log('--dry-run: skipping deletion.');
    return;
  }

  const { error: delErr, count } = await supabase
    .from('sources')
    .delete({ count: 'exact' })
    .in('id', allIds);

  if (delErr) { console.error('Delete error:', delErr.message); process.exit(1); }

  console.log(`Deleted ${count} source rows (nodes + edges cascaded).`);
}

main().catch(err => { console.error(err); process.exit(1); });
