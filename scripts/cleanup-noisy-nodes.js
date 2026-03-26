#!/usr/bin/env node
/**
 * One-time cleanup: delete noisy Track B nodes from Supabase.
 * These were created before the boilerplate filter was added/enhanced.
 *
 * Usage: node scripts/cleanup-noisy-nodes.js [--dry-run]
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createClient } from '@supabase/supabase-js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DRY_RUN = process.argv.includes('--dry-run');

// Load env
const envPath = path.join(__dirname, '../.env.local');
for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
  const t = line.trim();
  if (!t || t.startsWith('#')) continue;
  const eq = t.indexOf('=');
  if (eq < 0) continue;
  if (!process.env[t.slice(0, eq).trim()]) process.env[t.slice(0, eq).trim()] = t.slice(eq + 1).trim();
}

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);

// Same patterns as build-graph.js BOILERPLATE_PATTERNS
const NOISE = [
  /msg rates?.*apply/i, /std msg/i, /unsubscribe/i, /view in (browser|email)/i,
  /for your records/i, /privacy policy/i, /terms of (service|use)/i, /click here/i,
  /buy \d.*get \d/i, /taxes? (apply|&)/i, /fees?.*apply/i, /auto.?renew/i,
  /download (our|the) app/i, /upon.*conclusion.*trial/i, /please pay by/i,
  /reschedule or cancel/i, /cancel.*for a full refund/i, /cancellation is complete/i,
  /if you change your mind.*renew/i, /renew.*pro now/i, /order minim/i,
  /you.?ll hear their stories/i, /urgent update.*client info/i, /one year ago.*we wrote/i,
  /part \d+ of the schedule/i, /bill into parliament/i, /legislation which is not/i,
  /login links? pointing/i, /free plan/i,
];

function isNoise(text) {
  if (NOISE.some(p => p.test(text))) return true;
  const stripped = text.replace(/https?:\/\/\S+/g, '').trim();
  if (stripped.length < 20) return true;
  return false;
}

async function main() {
  console.log('Fetching Track B nodes with baseline stall probability...');
  const { data: nodes, error } = await supabase
    .from('nodes')
    .select('id, label, content')
    .eq('track', 'B')
    .eq('stall_probability', 0.6);

  if (error) { console.error('Query failed:', error.message); process.exit(1); }

  const noisy = nodes.filter(n => isNoise(n.content));
  console.log(`Track B nodes: ${nodes.length} total, ${noisy.length} noise detected`);

  if (noisy.length === 0) { console.log('No noise to clean. Done.'); return; }

  console.log('\nSample noise:');
  for (const n of noisy.slice(0, 10)) console.log(`  - "${n.label}"`);

  if (DRY_RUN) {
    console.log(`\n[dry-run] Would delete ${noisy.length} nodes. Run without --dry-run to execute.`);
    return;
  }

  const ids = noisy.map(n => n.id);
  let deleted = 0;
  for (let i = 0; i < ids.length; i += 100) {
    const batch = ids.slice(i, i + 100);
    const { error: e } = await supabase.from('nodes').delete().in('id', batch);
    if (e) console.error(`Delete batch failed: ${e.message}`);
    else deleted += batch.length;
  }

  console.log(`\nDeleted ${deleted} noisy Track B nodes.`);
}

main().catch(err => { console.error('Fatal:', err.message); process.exit(1); });
