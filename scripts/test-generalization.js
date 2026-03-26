#!/usr/bin/env node
/**
 * O-025 Generalization Test: Does the extraction prompt work on non-Brian content?
 *
 * Picks 10 sources that are NOT Brian's personal reflections (Perplexity Q&A threads,
 * Gmail behavioral traces processed through Track A for testing) and runs extractGraph()
 * on each. Evaluates whether tension/question nodes appear or only concepts.
 *
 * Pass criteria: >= 6 out of 10 sources produce at least 1 tension or question node.
 * If all produce only concepts, the prompt has drifted to summarization on non-reflective content.
 *
 * Usage: npx tsx scripts/test-generalization.js
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createClient } from '@supabase/supabase-js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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

// Dynamic import after env loaded
const { extractGraph } = await import('../lib/ingest-pipeline.ts');

async function main() {
  console.log('O-025 Generalization Test');
  console.log('========================\n');

  // Fetch 10 Perplexity sources (Q&A format, not Brian's reflective style)
  const { data: sources, error } = await supabase
    .from('sources')
    .select('id, label, raw_content, source')
    .eq('source', 'perplexity')
    .gt('chunk_count', 0)
    .not('raw_content', 'is', null)
    .limit(10);

  if (error) { console.error('Query failed:', error.message); process.exit(1); }
  if (!sources || sources.length === 0) { console.error('No Perplexity sources found.'); process.exit(1); }

  console.log(`Testing ${sources.length} Perplexity sources (Q&A format, non-reflective)\n`);

  let passed = 0;
  let failed = 0;
  const results = [];

  for (const source of sources) {
    const content = source.raw_content;
    if (!content || content.trim().length < 200) {
      console.log(`SKIP "${source.label?.slice(0, 50)}" — too short`);
      continue;
    }

    process.stdout.write(`"${source.label?.slice(0, 60)}"... `);

    try {
      const graph = await extractGraph(content, source.label || 'Untitled');

      const types = {};
      for (const node of graph.nodes) {
        types[node.type] = (types[node.type] || 0) + 1;
      }

      const hasTensionOrQuestion = (types['tension'] || 0) + (types['question'] || 0) > 0;
      const totalNodes = graph.nodes.length;
      const typeStr = Object.entries(types).map(([t, c]) => `${t}:${c}`).join(', ');

      if (hasTensionOrQuestion) {
        console.log(`PASS — ${totalNodes} nodes (${typeStr})`);
        passed++;
      } else {
        console.log(`FAIL — ${totalNodes} nodes (${typeStr}) — no tension/question nodes`);
        failed++;
      }

      results.push({
        label: source.label,
        source: source.source,
        nodeCount: totalNodes,
        types,
        hasTensionOrQuestion,
        edgeCount: graph.edges.length,
      });
    } catch (err) {
      console.log(`ERROR — ${err.message}`);
      failed++;
    }
  }

  console.log('\n========================');
  console.log(`Results: ${passed} PASS / ${failed} FAIL out of ${passed + failed} tested`);
  console.log(`Pass rate: ${Math.round(passed / (passed + failed) * 100)}%`);
  console.log(`Gate: >= 60% must produce tension/question nodes`);
  console.log(`Verdict: ${passed / (passed + failed) >= 0.6 ? 'PASS' : 'FAIL — prompt needs style-adaptive variant'}`);

  // Save results
  const resultsPath = path.join(__dirname, '../engine/eval/results', `generalization-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.json`);
  fs.writeFileSync(resultsPath, JSON.stringify({ date: new Date().toISOString(), passed, failed, passRate: passed / (passed + failed), results }, null, 2));
  console.log(`\nResults saved to: ${resultsPath}`);
}

main().catch(err => { console.error('Fatal:', err.message); process.exit(1); });
