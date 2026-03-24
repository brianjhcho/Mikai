#!/usr/bin/env npx tsx
/**
 * engine/eval/eval-brief-routing.ts
 *
 * Automated brief routing test — simulates Claude Desktop's tool routing
 * decisions using the Anthropic API with the same tool definitions.
 *
 * Tests whether Claude correctly routes queries:
 *   Category A: 0 MIKAI tool calls (irrelevant queries)
 *   Category B: 0-1 calls (answerable from brief alone)
 *   Category C: 1+ depth calls (needs search_knowledge/search_graph)
 *
 * Usage: npm run test:brief
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import Anthropic from '@anthropic-ai/sdk';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load env
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
} catch {}

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// The custom instruction that mirrors Claude Desktop
const SYSTEM_PROMPT = `At the start of conversations about my work, projects, thinking, or decisions, call get_brief from MIKAI to load my knowledge base context. For simple factual questions unrelated to my personal work (weather, coding help, translations), don't call MIKAI tools. For depth on any topic from the brief, use search_knowledge or search_graph.

You have access to MIKAI tools for searching the user's personal knowledge base. Only use them when the query relates to the user's personal work, thinking, or projects.`;

// Simplified tool definitions matching the MCP server
const TOOLS: Anthropic.Tool[] = [
  {
    name: 'get_brief',
    description: 'Returns a compact knowledge base context brief (~400 tokens). Call this at conversation start to understand what\'s in the knowledge base before answering questions about the user\'s work, thinking, or projects.',
    input_schema: { type: 'object' as const, properties: {} },
  },
  {
    name: 'search_knowledge',
    description: 'Search MIKAI\'s knowledge base using semantic similarity. Returns relevant condensed passages with source provenance.',
    input_schema: { type: 'object' as const, properties: { query: { type: 'string' } }, required: ['query'] },
  },
  {
    name: 'search_graph',
    description: 'Search MIKAI\'s knowledge graph by semantic similarity, then expand via one-hop edge traversal.',
    input_schema: { type: 'object' as const, properties: { query: { type: 'string' } }, required: ['query'] },
  },
  {
    name: 'get_tensions',
    description: 'Retrieve the top tension nodes from the knowledge graph.',
    input_schema: { type: 'object' as const, properties: { limit: { type: 'integer' } } },
  },
  {
    name: 'get_stalled',
    description: 'Retrieve nodes with high stall probability — desires or projects that have gone quiet.',
    input_schema: { type: 'object' as const, properties: { threshold: { type: 'number' } } },
  },
  {
    name: 'get_status',
    description: 'Knowledge base health: source counts, segment counts, last sync time.',
    input_schema: { type: 'object' as const, properties: {} },
  },
  {
    name: 'mark_resolved',
    description: 'Mark a node as resolved. Use when user confirms they acted on something.',
    input_schema: { type: 'object' as const, properties: { node_id: { type: 'string' } }, required: ['node_id'] },
  },
  {
    name: 'add_note',
    description: 'Save a new note to the knowledge base from conversation.',
    input_schema: { type: 'object' as const, properties: { content: { type: 'string' }, label: { type: 'string' } }, required: ['content'] },
  },
];

// Test queries with expected routing
const TESTS = [
  // Category A: Should trigger 0 MIKAI calls
  { id: 'A1', query: 'What time is it in Vancouver right now?', category: 'A', maxCalls: 0 },
  { id: 'A2', query: 'Help me write a Python function to sort a list', category: 'A', maxCalls: 0 },

  // Category B: Should trigger 0-1 calls (get_brief only)
  { id: 'B1', query: 'What do I think about the coffee industry?', category: 'B', maxCalls: 1, allowedTools: ['get_brief', 'search_knowledge'] },
  { id: 'B2', query: 'How many sources are in my knowledge base?', category: 'B', maxCalls: 1, allowedTools: ['get_brief', 'get_status'] },
  { id: 'B3', query: 'Am I stalling on anything?', category: 'B', maxCalls: 1, allowedTools: ['get_brief', 'get_stalled'] },

  // Category C: Should trigger 1+ depth calls
  { id: 'C1', query: 'What specifically do I think about Kenya\'s coffee market?', category: 'C', minCalls: 1 },
  { id: 'C2', query: 'What contradicts my passive capture thesis?', category: 'C', minCalls: 1 },
  { id: 'C3', query: 'Give me the full details on my trust cliff tension', category: 'C', minCalls: 1 },
  { id: 'C4', query: 'What was I thinking about last week?', category: 'C', minCalls: 1 },
  { id: 'C5', query: 'Show me all my stalled items with details', category: 'C', minCalls: 1 },
];

async function testQuery(test: typeof TESTS[0]): Promise<{ id: string; pass: boolean; tools: string[]; reason: string }> {
  try {
    const response = await anthropic.messages.create({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 256,
      system: SYSTEM_PROMPT,
      tools: TOOLS,
      messages: [{ role: 'user', content: test.query }],
    });

    // Extract tool calls from response
    const toolCalls = response.content
      .filter((block): block is Anthropic.ToolUseBlock => block.type === 'tool_use')
      .map(block => block.name);

    const callCount = toolCalls.length;

    // Evaluate
    let pass = false;
    let reason = '';

    if (test.category === 'A') {
      pass = callCount === 0;
      reason = pass ? 'No MIKAI calls (correct)' : `Called ${toolCalls.join(', ')} (should be 0)`;
    } else if (test.category === 'B') {
      pass = callCount <= (test.maxCalls ?? 1);
      reason = pass
        ? callCount === 0 ? 'No calls needed (correct)' : `Called ${toolCalls.join(', ')} (acceptable)`
        : `Called ${toolCalls.join(', ')} (too many)`;
    } else if (test.category === 'C') {
      pass = callCount >= (test.minCalls ?? 1);
      reason = pass ? `Called ${toolCalls.join(', ')} (correct depth)` : 'No depth call (should have searched)';
    }

    return { id: test.id, pass, tools: toolCalls, reason };
  } catch (err: any) {
    return { id: test.id, pass: false, tools: [], reason: `Error: ${err.message}` };
  }
}

async function main() {
  console.log('MIKAI Brief Routing Test (Automated)');
  console.log('═'.repeat(60));
  console.log('Model: claude-haiku-4-5-20251001 (simulating Claude Desktop routing)\n');

  const results = [];

  // Run tests sequentially to avoid rate limits
  for (const test of TESTS) {
    process.stdout.write(`  ${test.id}: "${test.query.slice(0, 50)}..." `);
    const result = await testQuery(test);
    results.push(result);
    console.log(result.pass ? '✓ PASS' : '✗ FAIL', `— ${result.reason}`);
  }

  // Summary
  const passed = results.filter(r => r.pass).length;
  const total = results.length;

  console.log('\n' + '═'.repeat(60));
  console.log(`Score: ${passed}/${total}`);
  console.log(`Verdict: ${passed >= 8 ? 'PASS' : 'FAIL'} (threshold: 8/10)`);
  console.log('═'.repeat(60));

  // Category breakdown
  for (const cat of ['A', 'B', 'C']) {
    const catResults = results.filter(r => r.id.startsWith(cat));
    const catPassed = catResults.filter(r => r.pass).length;
    console.log(`  Category ${cat}: ${catPassed}/${catResults.length}`);
  }

  // Save results
  const resultsDir = path.join(__dirname, 'results');
  if (!fs.existsSync(resultsDir)) fs.mkdirSync(resultsDir, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const outPath = path.join(resultsDir, `eval-brief-routing-${timestamp}.json`);
  fs.writeFileSync(outPath, JSON.stringify({ timestamp: new Date().toISOString(), score: `${passed}/${total}`, verdict: passed >= 8 ? 'PASS' : 'FAIL', results }, null, 2));
  console.log(`\nResults: ${outPath}`);

  // Cost estimate
  const inputTokens = TESTS.length * 800; // ~800 tokens per call (system + tools + query)
  const outputTokens = TESTS.length * 50;
  const cost = (inputTokens * 1 / 1_000_000) + (outputTokens * 5 / 1_000_000);
  console.log(`Cost: ~$${cost.toFixed(4)} (${TESTS.length} Haiku calls)`);
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
