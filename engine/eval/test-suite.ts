/**
 * engine/eval/test-suite.ts
 *
 * Unified MIKAI test suite. Consolidates all eval protocols into one automated runner.
 *
 * Categories:
 *   1. Pipeline Health   — DB counts, freshness, MCP connectivity (no LLM)
 *   2. Segmentation Quality — 3-pass LLM-as-Judge via Haiku (~$0.02/run)
 *   3. Retrieval Quality — queries against /api/chat/synthesize
 *   4. Cost Tracking     — extraction_logs token sums for last 24h
 *   5. Brief Routing     — generates manual test template
 *
 * Usage:
 *   npm run test             # --all
 *   npm run test:quick       # --quick (pipeline + cost only)
 *   npm run test:segments    # --segments
 *   npm run test:retrieval   # --retrieval
 *   npm run test:cost        # --cost
 *
 *   tsx engine/eval/test-suite.ts --all
 *   tsx engine/eval/test-suite.ts --pipeline --cost
 *   tsx engine/eval/test-suite.ts --brief
 */

import * as fs from 'fs';
import * as path from 'path';
import { createClient } from '@supabase/supabase-js';
import Anthropic from '@anthropic-ai/sdk';

// ── Env loader (same pattern as other eval scripts) ─────────────────────────

const envPath = path.resolve(process.cwd(), '.env.local');
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, 'utf-8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx < 0) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim();
    if (!process.env[key]) process.env[key] = val;
  }
}

// ── CLI flags ───────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const flag = (name: string) => args.includes(name);

const RUN_ALL       = flag('--all') || args.length === 0;
const RUN_PIPELINE  = RUN_ALL || flag('--pipeline') || flag('--quick');
const RUN_SEGMENTS  = RUN_ALL || flag('--segments');
const RUN_RETRIEVAL = RUN_ALL || flag('--retrieval');
const RUN_COST      = RUN_ALL || flag('--cost') || flag('--quick');
const RUN_BRIEF     = RUN_ALL || flag('--brief');

// ── Supabase ────────────────────────────────────────────────────────────────

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env.local');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

// ── Anthropic (lazy — only created if needed) ───────────────────────────────

let _anthropic: Anthropic | null = null;
function getAnthropic(): Anthropic {
  if (!_anthropic) {
    if (!process.env.ANTHROPIC_API_KEY) {
      throw new Error('Missing ANTHROPIC_API_KEY in .env.local');
    }
    _anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  }
  return _anthropic;
}

const EVAL_MODEL = 'claude-haiku-4-5-20251001';

// ── Types ───────────────────────────────────────────────────────────────────

type TestStatus = 'pass' | 'fail' | 'warn' | 'skip' | 'manual';

interface TestResult {
  name: string;
  status: TestStatus;
  details: string;
  data?: Record<string, unknown>;
}

interface CategoryResult {
  category: string;
  status: TestStatus;
  tests: TestResult[];
}

// ── Predefined retrieval test queries ───────────────────────────────────────

const RETRIEVAL_QUERIES = [
  'What are my key tensions about building MIKAI?',
  'What opportunities am I exploring in Kenya?',
  'What do I think about passive capture as a moat?',
  'What is my personality type and how does it affect my work?',
  'What products or businesses have I been researching?',
];

// ── Brief routing test queries (from eval-brief-routing.md) ─────────────────

const BRIEF_ROUTING_TESTS = [
  { id: 'A1', query: 'What time is it in Vancouver right now?', expected: '0 MIKAI calls', category: 'A' },
  { id: 'A2', query: 'Help me write a Python function to sort a list', expected: '0 MIKAI calls', category: 'A' },
  { id: 'B1', query: 'What do I think about the coffee industry?', expected: '0-1 calls (brief)', category: 'B' },
  { id: 'B2', query: 'How many sources are in my knowledge base?', expected: '0-1 calls (get_brief)', category: 'B' },
  { id: 'B3', query: 'Am I stalling on anything?', expected: '0-1 calls (get_brief)', category: 'B' },
  { id: 'C1', query: "What specifically do I think about Kenya's coffee market?", expected: '1 depth call (search_knowledge)', category: 'C' },
  { id: 'C2', query: 'What contradicts my passive capture thesis?', expected: '1 depth call (search_graph)', category: 'C' },
  { id: 'C3', query: 'Give me the full details on my trust cliff tension', expected: '1 depth call (search_knowledge)', category: 'C' },
  { id: 'C4', query: 'What was I thinking about last week?', expected: '1 depth call (search_knowledge)', category: 'C' },
  { id: 'C5', query: 'Show me all my stalled items with details', expected: '1 depth call (get_stalled)', category: 'C' },
];

// ═══════════════════════════════════════════════════════════════════════════════
// CATEGORY 1: PIPELINE HEALTH
// ═══════════════════════════════════════════════════════════════════════════════

async function runPipelineHealth(): Promise<CategoryResult> {
  const tests: TestResult[] = [];

  // --- pipeline.sources ---
  try {
    const { data, error } = await supabase
      .from('sources')
      .select('source', { count: 'exact' });

    if (error) throw new Error(error.message);

    const rows = data ?? [];
    const total = rows.length;
    const byType: Record<string, number> = {};
    for (const row of rows) {
      const t = (row as { source: string }).source || 'unknown';
      byType[t] = (byType[t] || 0) + 1;
    }

    const breakdown = Object.entries(byType)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}: ${v.toLocaleString()}`)
      .join(', ');

    tests.push({
      name: 'pipeline.sources',
      status: total > 0 ? 'pass' : 'fail',
      details: `${total.toLocaleString()} sources (${breakdown})`,
      data: { total, byType },
    });
  } catch (err) {
    tests.push({ name: 'pipeline.sources', status: 'fail', details: `Error: ${(err as Error).message}` });
  }

  // --- pipeline.segments ---
  try {
    const { count, error } = await supabase
      .from('segments')
      .select('id', { count: 'exact', head: true });

    if (error) throw new Error(error.message);

    const segCount = count ?? 0;
    tests.push({
      name: 'pipeline.segments',
      status: segCount > 0 ? 'pass' : 'fail',
      details: `${segCount.toLocaleString()} segments`,
      data: { count: segCount },
    });
  } catch (err) {
    tests.push({ name: 'pipeline.segments', status: 'fail', details: `Error: ${(err as Error).message}` });
  }

  // --- pipeline.nodes ---
  try {
    const { data, error } = await supabase
      .from('nodes')
      .select('node_type');

    if (error) throw new Error(error.message);

    const rows = data ?? [];
    const total = rows.length;
    const byType: Record<string, number> = {};
    for (const row of rows) {
      const t = (row as { node_type: string }).node_type || 'unknown';
      byType[t] = (byType[t] || 0) + 1;
    }

    const breakdown = Object.entries(byType)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}: ${v.toLocaleString()}`)
      .join(', ');

    tests.push({
      name: 'pipeline.nodes',
      status: total > 0 ? 'pass' : 'fail',
      details: `${total.toLocaleString()} nodes (${breakdown})`,
      data: { total, byType },
    });
  } catch (err) {
    tests.push({ name: 'pipeline.nodes', status: 'fail', details: `Error: ${(err as Error).message}` });
  }

  // --- pipeline.freshness ---
  try {
    const { data, error } = await supabase
      .from('sources')
      .select('created_at')
      .order('created_at', { ascending: false })
      .limit(1);

    if (error) throw new Error(error.message);

    if (!data || data.length === 0) {
      tests.push({ name: 'pipeline.freshness', status: 'fail', details: 'No sources found' });
    } else {
      const latest = new Date(data[0].created_at);
      const ageMs = Date.now() - latest.getTime();
      const ageMin = Math.floor(ageMs / 60000);
      const ageHours = Math.floor(ageMin / 60);
      const fresh = ageMin < 60;
      const ageStr = ageHours > 0 ? `${ageHours}h ${ageMin % 60}m ago` : `${ageMin} min ago`;

      tests.push({
        name: 'pipeline.freshness',
        status: fresh ? 'pass' : 'warn',
        details: `Last sync: ${ageStr}${fresh ? '' : ' (> 1 hour)'}`,
        data: { lastSyncMinAgo: ageMin },
      });
    }
  } catch (err) {
    tests.push({ name: 'pipeline.freshness', status: 'fail', details: `Error: ${(err as Error).message}` });
  }

  // --- pipeline.mcp ---
  try {
    const res = await fetch('http://localhost:3000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: [{ role: 'user', content: 'ping' }] }),
      signal: AbortSignal.timeout(5000),
    }).catch(() => null);

    if (res && res.status < 500) {
      tests.push({ name: 'pipeline.mcp', status: 'pass', details: 'Dev server reachable' });
    } else {
      tests.push({ name: 'pipeline.mcp', status: 'warn', details: 'Dev server not reachable (not required for DB tests)' });
    }
  } catch {
    tests.push({ name: 'pipeline.mcp', status: 'warn', details: 'Dev server not reachable (not required for DB tests)' });
  }

  const overallStatus = tests.some(t => t.status === 'fail') ? 'fail' :
                         tests.some(t => t.status === 'warn') ? 'warn' : 'pass';

  return { category: 'PIPELINE HEALTH', status: overallStatus, tests };
}

// ═══════════════════════════════════════════════════════════════════════════════
// CATEGORY 2: SEGMENTATION QUALITY
// ═══════════════════════════════════════════════════════════════════════════════

async function runSegmentationQuality(): Promise<CategoryResult> {
  const tests: TestResult[] = [];
  const anthropic = getAnthropic();

  try {
    // Fetch sources that have segments, pick 5 randomly
    const { data: sourcesWithSegs, error: srcErr } = await supabase
      .from('sources')
      .select('id, label, raw_content, source')
      .not('raw_content', 'is', null)
      .limit(50);

    if (srcErr) throw new Error(srcErr.message);
    if (!sourcesWithSegs || sourcesWithSegs.length === 0) {
      return { category: 'SEGMENTATION QUALITY', status: 'skip', tests: [{ name: 'segments', status: 'skip', details: 'No sources found' }] };
    }

    const sourceIds = sourcesWithSegs.map(s => s.id);
    const { data: allSegments, error: segErr } = await supabase
      .from('segments')
      .select('id, source_id, topic_label, processed_content')
      .in('source_id', sourceIds);

    if (segErr) throw new Error(segErr.message);

    const segsBySource = new Map<string, Array<{ id: string; source_id: string; topic_label: string; processed_content: string }>>();
    for (const seg of allSegments ?? []) {
      const arr = segsBySource.get(seg.source_id) ?? [];
      arr.push(seg);
      segsBySource.set(seg.source_id, arr);
    }

    const withSegs = sourcesWithSegs.filter(s => (segsBySource.get(s.id)?.length ?? 0) > 0);
    if (withSegs.length === 0) {
      return { category: 'SEGMENTATION QUALITY', status: 'skip', tests: [{ name: 'segments', status: 'skip', details: 'No sources with segments' }] };
    }

    // Pick 5 random
    const shuffled = withSegs.sort(() => Math.random() - 0.5).slice(0, 5);

    let totalCoverage = 0;
    let totalFidelity = 0;
    let totalVoice = 0;
    let evalCount = 0;

    for (const source of shuffled) {
      const segments = segsBySource.get(source.id) ?? [];
      const rawContent = source.raw_content as string;

      // Pass 1: Topic Inventory
      const truncated = rawContent.slice(0, 8000);
      const p1 = await anthropic.messages.create({
        model: EVAL_MODEL,
        max_tokens: 1024,
        system: 'You are an evaluation assistant. List every distinct topic or idea in a personal note. Return ONLY a JSON array of short labels (2-5 words each). No explanation, no markdown, just the JSON array.',
        messages: [{ role: 'user', content: `List every distinct topic or idea:\n\n${truncated}` }],
      });
      const p1Text = p1.content[0]?.type === 'text' ? p1.content[0].text : '[]';
      let topics: string[] = [];
      try { topics = JSON.parse(p1Text.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '').trim()); } catch { topics = []; }
      if (!Array.isArray(topics)) topics = [];

      // Pass 2: Coverage
      const segText = segments.map((s, i) => `[${i + 1}] ${s.topic_label}: ${s.processed_content.slice(0, 300)}`).join('\n\n');
      const invText = topics.map((t, i) => `${i + 1}. ${t}`).join('\n');
      const p2 = await anthropic.messages.create({
        model: EVAL_MODEL,
        max_tokens: 1024,
        system: 'Compare a topic inventory against extracted segments. Return ONLY valid JSON: {"captured": [...], "missing": [...], "coverage_pct": 75}',
        messages: [{ role: 'user', content: `TOPICS:\n${invText}\n\nSEGMENTS:\n${segText}\n\nReturn JSON only.` }],
      });
      const p2Text = p2.content[0]?.type === 'text' ? p2.content[0].text : '{}';
      let coverage = { coverage_pct: 0 };
      try { coverage = JSON.parse(p2Text.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '').trim()); } catch { /* */ }

      // Pass 3: Fidelity + Voice
      const segList = segments.map((s, i) => `[${i + 1}] "${s.topic_label}": "${s.processed_content.slice(0, 400)}"`).join('\n\n');
      const p3 = await anthropic.messages.create({
        model: EVAL_MODEL,
        max_tokens: 2048,
        system: 'Rate each segment on fidelity (1-5) and voice (1-5). Return ONLY a JSON array: [{"index":1,"fidelity":4,"voice":3}, ...]',
        messages: [{ role: 'user', content: `SOURCE:\n${rawContent.slice(0, 3000)}\n\nSEGMENTS:\n${segList}\n\nReturn JSON array only.` }],
      });
      const p3Text = p3.content[0]?.type === 'text' ? p3.content[0].text : '[]';
      let scores: Array<{ fidelity: number; voice: number }> = [];
      try { scores = JSON.parse(p3Text.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '').trim()); } catch { scores = []; }
      if (!Array.isArray(scores)) scores = [];

      const covPct = typeof (coverage as { coverage_pct?: number }).coverage_pct === 'number' ? (coverage as { coverage_pct: number }).coverage_pct : 0;
      const avgF = scores.length > 0 ? scores.reduce((s, x) => s + (x.fidelity || 0), 0) / scores.length : 0;
      const avgV = scores.length > 0 ? scores.reduce((s, x) => s + (x.voice || 0), 0) / scores.length : 0;

      totalCoverage += covPct;
      totalFidelity += avgF;
      totalVoice += avgV;
      evalCount++;
    }

    const avgCoverage = evalCount > 0 ? Math.round(totalCoverage / evalCount) : 0;
    const avgFidelity = evalCount > 0 ? Math.round((totalFidelity / evalCount) * 10) / 10 : 0;
    const avgVoice = evalCount > 0 ? Math.round((totalVoice / evalCount) * 10) / 10 : 0;
    const pass = avgCoverage >= 70;

    tests.push({
      name: 'segmentation.coverage',
      status: pass ? 'pass' : 'fail',
      details: `Avg coverage: ${avgCoverage}% (threshold: 70%)`,
      data: { avgCoverage },
    });
    tests.push({
      name: 'segmentation.fidelity',
      status: avgFidelity >= 3.0 ? 'pass' : 'warn',
      details: `Avg fidelity: ${avgFidelity}/5`,
      data: { avgFidelity },
    });
    tests.push({
      name: 'segmentation.voice',
      status: avgVoice >= 3.0 ? 'pass' : 'warn',
      details: `Avg voice: ${avgVoice}/5`,
      data: { avgVoice },
    });
    tests.push({
      name: 'segmentation.sources_tested',
      status: 'pass',
      details: `${evalCount} sources evaluated (Haiku judge, ~$0.02 cost)`,
      data: { evalCount },
    });

    const overallStatus = tests.some(t => t.status === 'fail') ? 'fail' :
                           tests.some(t => t.status === 'warn') ? 'warn' : 'pass';

    return { category: 'SEGMENTATION QUALITY', status: overallStatus, tests };

  } catch (err) {
    return {
      category: 'SEGMENTATION QUALITY',
      status: 'fail',
      tests: [{ name: 'segmentation', status: 'fail', details: `Error: ${(err as Error).message}` }],
    };
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CATEGORY 3: RETRIEVAL QUALITY
// ═══════════════════════════════════════════════════════════════════════════════

async function runRetrievalQuality(): Promise<CategoryResult> {
  const tests: TestResult[] = [];

  // Try HTTP to the dev server first
  let serverAvailable = false;
  try {
    const ping = await fetch('http://localhost:3000/api/chat/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'test' }),
      signal: AbortSignal.timeout(5000),
    }).catch(() => null);
    serverAvailable = ping !== null && ping.status < 500;
  } catch { /* */ }

  if (!serverAvailable) {
    return {
      category: 'RETRIEVAL QUALITY',
      status: 'skip',
      tests: [{
        name: 'retrieval',
        status: 'skip',
        details: 'Dev server not running at localhost:3000. Start with `npm run dev` to run retrieval tests.',
      }],
    };
  }

  // --- retrieval.relevance ---
  try {
    let totalSimilarity = 0;
    let queryCount = 0;
    const queryDetails: string[] = [];

    for (const query of RETRIEVAL_QUERIES) {
      const res = await fetch('http://localhost:3000/api/chat/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, match_count: 5 }),
        signal: AbortSignal.timeout(30000),
      });

      if (!res.ok) {
        queryDetails.push(`"${query.slice(0, 40)}..." => HTTP ${res.status}`);
        continue;
      }

      const json = await res.json() as { segments?: Array<{ similarity: number }>; answer?: string };
      const segs = json.segments ?? [];
      const avgSim = segs.length > 0
        ? segs.reduce((s: number, x: { similarity: number }) => s + x.similarity, 0) / segs.length
        : 0;

      totalSimilarity += avgSim;
      queryCount++;
      queryDetails.push(`"${query.slice(0, 40)}..." => avg sim ${avgSim.toFixed(2)} (${segs.length} segs)`);
    }

    const avgSimilarity = queryCount > 0 ? Math.round((totalSimilarity / queryCount) * 100) / 100 : 0;
    tests.push({
      name: 'retrieval.relevance',
      status: avgSimilarity >= 0.3 ? 'pass' : 'fail',
      details: `Avg similarity: ${avgSimilarity} across ${queryCount} queries (threshold: 0.3)`,
      data: { avgSimilarity, queryCount, queryDetails },
    });
  } catch (err) {
    tests.push({ name: 'retrieval.relevance', status: 'fail', details: `Error: ${(err as Error).message}` });
  }

  // --- retrieval.grounding ---
  try {
    let groundedCount = 0;
    let totalQueries = 0;

    for (const query of RETRIEVAL_QUERIES) {
      const res = await fetch('http://localhost:3000/api/chat/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
        signal: AbortSignal.timeout(30000),
      });

      if (!res.ok) continue;

      const json = await res.json() as { answer?: string };
      const answer = json.answer ?? '';
      totalQueries++;

      // Check for source citations in the answer
      if (answer.includes('[Source:') || answer.includes('Source:') || answer.includes('"') && answer.includes('notes')) {
        groundedCount++;
      }
    }

    tests.push({
      name: 'retrieval.grounding',
      status: groundedCount >= Math.ceil(totalQueries * 0.6) ? 'pass' : 'warn',
      details: `${groundedCount}/${totalQueries} queries cited sources`,
      data: { groundedCount, totalQueries },
    });
  } catch (err) {
    tests.push({ name: 'retrieval.grounding', status: 'fail', details: `Error: ${(err as Error).message}` });
  }

  // --- retrieval.mode_comparison ---
  try {
    const testQuery = RETRIEVAL_QUERIES[0]; // "What are my key tensions about building MIKAI?"

    // Mode D (segments / synthesize)
    const modeD = await fetch('http://localhost:3000/api/chat/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: testQuery }),
      signal: AbortSignal.timeout(30000),
    });

    // Mode B (graph / chat)
    const modeB = await fetch('http://localhost:3000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: [{ role: 'user', content: testQuery }] }),
      signal: AbortSignal.timeout(30000),
    });

    const modeDOk = modeD.ok;
    const modeBOk = modeB.ok;

    if (modeDOk && modeBOk) {
      tests.push({
        name: 'retrieval.mode_comparison',
        status: 'pass',
        details: 'Both Mode B (graph) and Mode D (segments) returned responses',
      });
    } else {
      const parts: string[] = [];
      if (!modeDOk) parts.push(`Mode D: HTTP ${modeD.status}`);
      if (!modeBOk) parts.push(`Mode B: HTTP ${modeB.status}`);
      tests.push({
        name: 'retrieval.mode_comparison',
        status: 'warn',
        details: `Partial: ${parts.join(', ')}`,
      });
    }
  } catch (err) {
    tests.push({ name: 'retrieval.mode_comparison', status: 'warn', details: `Error: ${(err as Error).message}` });
  }

  const overallStatus = tests.some(t => t.status === 'fail') ? 'fail' :
                         tests.some(t => t.status === 'warn') ? 'warn' : 'pass';

  return { category: 'RETRIEVAL QUALITY', status: overallStatus, tests };
}

// ═══════════════════════════════════════════════════════════════════════════════
// CATEGORY 4: COST TRACKING
// ═══════════════════════════════════════════════════════════════════════════════

async function runCostTracking(): Promise<CategoryResult> {
  const tests: TestResult[] = [];

  try {
    const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

    const { data: logs, error } = await supabase
      .from('extraction_logs')
      .select('operation, model, input_tokens, output_tokens, source_id')
      .gte('created_at', since);

    if (error) throw new Error(error.message);

    const entries = logs ?? [];

    if (entries.length === 0) {
      tests.push({
        name: 'cost.summary',
        status: 'pass',
        details: 'No extraction logs in the last 24h (no cost incurred)',
        data: { totalCost: 0 },
      });
      return { category: 'COST (last 24h)', status: 'pass', tests };
    }

    // Aggregate by operation
    const byOp: Record<string, { input: number; output: number; count: number }> = {};
    for (const e of entries) {
      const op = (e as { operation: string }).operation || 'unknown';
      if (!byOp[op]) byOp[op] = { input: 0, output: 0, count: 0 };
      byOp[op].input += (e as { input_tokens?: number }).input_tokens || 0;
      byOp[op].output += (e as { output_tokens?: number }).output_tokens || 0;
      byOp[op].count++;
    }

    // Estimate cost (rough pricing per 1M tokens)
    // Haiku: $0.25/1M input, $1.25/1M output
    // Sonnet: $3/1M input, $15/1M output
    const pricingInput: Record<string, number> = {
      'claude-haiku-4-5-20251001': 0.25 / 1_000_000,
      'claude-sonnet-4-6': 3 / 1_000_000,
    };
    const pricingOutput: Record<string, number> = {
      'claude-haiku-4-5-20251001': 1.25 / 1_000_000,
      'claude-sonnet-4-6': 15 / 1_000_000,
    };
    const defaultInputPrice = 3 / 1_000_000; // assume Sonnet if unknown
    const defaultOutputPrice = 15 / 1_000_000;

    let totalCost = 0;
    const costDetails: string[] = [];

    for (const [op, agg] of Object.entries(byOp)) {
      // Find models used for this operation to estimate pricing
      const opLogs = entries.filter(e => (e as { operation: string }).operation === op);
      let opCost = 0;
      for (const log of opLogs) {
        const model = (log as { model: string }).model || '';
        const inTok = (log as { input_tokens?: number }).input_tokens || 0;
        const outTok = (log as { output_tokens?: number }).output_tokens || 0;
        const inPrice = pricingInput[model] ?? defaultInputPrice;
        const outPrice = pricingOutput[model] ?? defaultOutputPrice;
        opCost += inTok * inPrice + outTok * outPrice;
      }

      totalCost += opCost;
      costDetails.push(`${op}: $${opCost.toFixed(4)} (${agg.count} calls, ${agg.input.toLocaleString()} in / ${agg.output.toLocaleString()} out)`);
    }

    // Cost per source
    const uniqueSources = new Set(entries.map(e => (e as { source_id?: string }).source_id).filter(Boolean));
    const costPerSource = uniqueSources.size > 0 ? totalCost / uniqueSources.size : 0;
    const costPerSourceOk = costPerSource <= 0.005;

    tests.push({
      name: 'cost.total',
      status: 'pass',
      details: `Total: $${totalCost.toFixed(4)} across ${entries.length} operations`,
      data: { totalCost, operationCount: entries.length },
    });

    for (const detail of costDetails) {
      tests.push({
        name: `cost.${detail.split(':')[0].trim()}`,
        status: 'pass',
        details: detail,
      });
    }

    tests.push({
      name: 'cost.per_source',
      status: costPerSourceOk ? 'pass' : 'warn',
      details: `$${costPerSource.toFixed(4)}/source (${uniqueSources.size} sources, threshold: $0.005)`,
      data: { costPerSource, sourceCount: uniqueSources.size },
    });

    const overallStatus = tests.some(t => t.status === 'fail') ? 'fail' :
                           tests.some(t => t.status === 'warn') ? 'warn' : 'pass';

    return { category: 'COST (last 24h)', status: overallStatus, tests };

  } catch (err) {
    return {
      category: 'COST (last 24h)',
      status: 'fail',
      tests: [{ name: 'cost', status: 'fail', details: `Error: ${(err as Error).message}` }],
    };
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CATEGORY 5: BRIEF ROUTING (manual template generation)
// ═══════════════════════════════════════════════════════════════════════════════

function runBriefRouting(): CategoryResult {
  const resultsDir = path.join(__dirname, 'results');
  fs.mkdirSync(resultsDir, { recursive: true });

  const templatePath = path.join(resultsDir, 'brief-routing-template.md');

  const now = new Date().toISOString().split('T')[0];
  const lines: string[] = [
    `# MIKAI Brief Routing Test Results`,
    ``,
    `Date: ${now}`,
    `Tester: ___`,
    `Score: ___/10`,
    ``,
    `## Instructions`,
    `1. Restart Claude Desktop (loads updated MCP server with get_brief)`,
    `2. Open MCP log: \`tail -f ~/Library/Logs/Claude/mcp-server-mikai.log\``,
    `3. Run each query below in Claude Desktop`,
    `4. Count tool calls in the MCP log and fill in the Result column`,
    `5. Pass threshold: 8/10 correct routing`,
    ``,
    `## Results`,
    ``,
    `| # | Category | Query | Expected | Tool Calls | Result |`,
    `|---|----------|-------|----------|------------|--------|`,
  ];

  for (const t of BRIEF_ROUTING_TESTS) {
    lines.push(`| ${t.id} | ${t.category} | ${t.query} | ${t.expected} | ___ | PASS / FAIL |`);
  }

  lines.push('');
  lines.push('## Scoring');
  lines.push('- Category A: 0 MIKAI calls = PASS, any calls = FAIL');
  lines.push('- Category B: 0-1 calls (get_brief only) = PASS, depth calls = FAIL');
  lines.push('- Category C: exactly 1 depth call = PASS, 0 calls = FAIL');
  lines.push('');
  lines.push('## Notes');
  lines.push('___');

  fs.writeFileSync(templatePath, lines.join('\n'), 'utf-8');

  return {
    category: 'BRIEF ROUTING',
    status: 'manual',
    tests: [{
      name: 'brief.template',
      status: 'manual',
      details: `Template generated at engine/eval/results/brief-routing-template.md`,
    }],
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// REPORT RENDERING
// ═══════════════════════════════════════════════════════════════════════════════

function statusLabel(s: TestStatus): string {
  switch (s) {
    case 'pass': return 'PASS';
    case 'fail': return 'FAIL';
    case 'warn': return 'WARN';
    case 'skip': return 'SKIP';
    case 'manual': return 'MANUAL';
  }
}

function statusIcon(s: TestStatus): string {
  switch (s) {
    case 'pass': return 'v';
    case 'fail': return 'X';
    case 'warn': return '!';
    case 'skip': return '-';
    case 'manual': return '?';
  }
}

function printReport(categories: CategoryResult[]): void {
  const now = new Date().toISOString().split('T')[0];
  const W = 55;

  console.log('');
  console.log(`MIKAI Test Suite -- ${now}`);
  console.log('='.repeat(W));

  let catIdx = 0;
  for (const cat of categories) {
    catIdx++;
    const label = `${catIdx}. ${cat.category}`;
    const tag = `[${statusLabel(cat.status)}]`;
    const pad = Math.max(1, W - label.length - tag.length);
    console.log('');
    console.log(`${label}${' '.repeat(pad)}${tag}`);

    for (const t of cat.tests) {
      console.log(`   ${statusIcon(t.status)} ${t.details}`);
    }
  }

  console.log('');
  console.log('='.repeat(W));

  const automated = categories.filter(c => c.status !== 'manual' && c.status !== 'skip');
  const passCount = automated.filter(c => c.status === 'pass').length;
  const warnCount = automated.filter(c => c.status === 'warn').length;
  const failCount = automated.filter(c => c.status === 'fail').length;
  const manualCount = categories.filter(c => c.status === 'manual').length;
  const skipCount = categories.filter(c => c.status === 'skip').length;

  const parts: string[] = [];
  if (passCount > 0) parts.push(`${passCount} PASS`);
  if (warnCount > 0) parts.push(`${warnCount} WARN`);
  if (failCount > 0) parts.push(`${failCount} FAIL`);
  if (skipCount > 0) parts.push(`${skipCount} skipped`);
  if (manualCount > 0) parts.push(`${manualCount} manual pending`);

  console.log(`OVERALL: ${parts.join(', ')}`);
  console.log('');
}

function saveReport(categories: CategoryResult[]): string {
  const timestamp = new Date().toISOString();
  const safeTimestamp = timestamp.replace(/[:.]/g, '-');
  const resultsDir = path.join(__dirname, 'results');
  fs.mkdirSync(resultsDir, { recursive: true });

  const report = {
    timestamp,
    categories: categories.map(cat => ({
      category: cat.category,
      status: cat.status,
      tests: cat.tests.map(t => ({
        name: t.name,
        status: t.status,
        details: t.details,
        data: t.data,
      })),
    })),
  };

  const outPath = path.join(resultsDir, `test-suite-${safeTimestamp}.json`);
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2), 'utf-8');
  return outPath;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════

async function main(): Promise<void> {
  const categories: CategoryResult[] = [];

  if (RUN_PIPELINE) {
    process.stdout.write('Running pipeline health checks... ');
    const result = await runPipelineHealth();
    console.log(statusLabel(result.status));
    categories.push(result);
  }

  if (RUN_SEGMENTS) {
    process.stdout.write('Running segmentation quality eval (Haiku judge, ~$0.02)... ');
    const result = await runSegmentationQuality();
    console.log(statusLabel(result.status));
    categories.push(result);
  }

  if (RUN_RETRIEVAL) {
    process.stdout.write('Running retrieval quality tests... ');
    const result = await runRetrievalQuality();
    console.log(statusLabel(result.status));
    categories.push(result);
  }

  if (RUN_COST) {
    process.stdout.write('Running cost tracking... ');
    const result = await runCostTracking();
    console.log(statusLabel(result.status));
    categories.push(result);
  }

  if (RUN_BRIEF) {
    const result = runBriefRouting();
    categories.push(result);
  }

  // Print full report
  printReport(categories);

  // Save JSON report
  const outPath = saveReport(categories);
  console.log(`Full report saved to: ${outPath}`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
