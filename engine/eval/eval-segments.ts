/**
 * engine/eval/eval-segments.ts
 *
 * LLM-as-Judge evaluation of segment extraction quality.
 * Runs three evaluation passes using claude-haiku-4-5-20251001 (cheap evaluation):
 *
 *   Pass 1 — Topic Inventory: lists every distinct topic/idea in the raw content
 *   Pass 2 — Coverage Score: which topics are captured/missing in segments
 *   Pass 3 — Fidelity + Voice: per-segment quality scores
 *
 * Writes results to engine/eval/results/eval-segments-{timestamp}.json
 *
 * Usage:
 *   npm run eval:segments
 *   npm run eval:segments -- --source-id <uuid>
 *   npm run eval:segments -- --batch-size 5
 *   npm run eval:segments -- --dry-run
 */

import * as fs from 'fs';
import * as path from 'path';
import { createClient } from '@supabase/supabase-js';
import Anthropic from '@anthropic-ai/sdk';

// ── Env loader ────────────────────────────────────────────────────────────────

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

// ── CLI options ───────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const flag = (name: string) => args.includes(name);
const option = (name: string, def: string) => {
  const i = args.indexOf(name);
  return i !== -1 && args[i + 1] ? args[i + 1] : def;
};

const DRY_RUN   = flag('--dry-run');
const SOURCE_ID = option('--source-id', '');
const BATCH_SIZE = parseInt(option('--batch-size', '10'), 10);

const COVERAGE_THRESHOLD = 0.70; // 70%
const EVAL_MODEL = 'claude-haiku-4-5-20251001';

// ── Supabase ──────────────────────────────────────────────────────────────────

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables.');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

// ── Types ─────────────────────────────────────────────────────────────────────

interface SourceRow {
  id: string;
  label: string;
  raw_content: string;
  source: string;
}

interface SegmentRow {
  id: string;
  source_id: string;
  topic_label: string;
  processed_content: string;
}

interface CoverageResult {
  captured: string[];
  missing: string[];
  coverage_pct: number;
}

interface SegmentScore {
  segment_id: string;
  topic_label: string;
  fidelity: number;
  voice: number;
}

interface SourceEvalResult {
  source_id: string;
  source_label: string;
  source_type: string;
  topic_inventory: string[];
  coverage: CoverageResult;
  segment_scores: SegmentScore[];
  avg_fidelity: number;
  avg_voice: number;
  verdict: 'PASS' | 'FAIL';
}

interface EvalResult {
  timestamp: string;
  model: string;
  source_count: number;
  sources: SourceEvalResult[];
  summary: {
    avg_coverage_pct: number;
    avg_fidelity: number;
    avg_voice: number;
    pass_count: number;
    fail_count: number;
    verdict: 'PASS' | 'FAIL';
  };
}

// ── Anthropic client ──────────────────────────────────────────────────────────

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// ── Pass 1: Topic Inventory ───────────────────────────────────────────────────

async function runTopicInventory(rawContent: string): Promise<string[]> {
  const truncated = rawContent.slice(0, 8000);

  const message = await anthropic.messages.create({
    model: EVAL_MODEL,
    max_tokens: 1024,
    system: `You are an evaluation assistant. Your job is to identify every distinct topic or idea in a personal note. Return ONLY a JSON array of short labels (2-5 words each). No explanation, no markdown, just the JSON array.

Example output: ["career pivot decision", "relationship with time", "AI product strategy", "fitness routine change"]`,
    messages: [
      {
        role: 'user',
        content: `List every distinct topic or idea in this text as a JSON array of short labels:\n\n${truncated}`,
      },
    ],
  });

  const rawText = message.content[0]?.type === 'text' ? message.content[0].text : '[]';
  const jsonText = rawText.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '').trim();

  try {
    const parsed = JSON.parse(jsonText);
    if (Array.isArray(parsed)) return parsed.filter((t) => typeof t === 'string');
  } catch {
    // Try to extract array from text
    const match = jsonText.match(/\[[\s\S]*\]/);
    if (match) {
      try {
        const parsed = JSON.parse(match[0]);
        if (Array.isArray(parsed)) return parsed.filter((t) => typeof t === 'string');
      } catch { /* fall through */ }
    }
  }

  return [];
}

// ── Pass 2: Coverage Score ────────────────────────────────────────────────────

async function runCoverageScore(
  topicInventory: string[],
  segments: SegmentRow[],
): Promise<CoverageResult> {
  if (topicInventory.length === 0) {
    return { captured: [], missing: [], coverage_pct: 0 };
  }

  const segmentText = segments
    .map((s, i) => `[${i + 1}] ${s.topic_label}: ${s.processed_content.slice(0, 300)}`)
    .join('\n\n');

  const inventoryText = topicInventory.map((t, i) => `${i + 1}. ${t}`).join('\n');

  const message = await anthropic.messages.create({
    model: EVAL_MODEL,
    max_tokens: 1024,
    system: `You are an evaluation assistant comparing a topic inventory against extracted segments. Return ONLY valid JSON in exactly this format:
{"captured": ["topic label", ...], "missing": ["topic label", ...], "coverage_pct": 75}

coverage_pct is an integer 0-100. No explanation, no markdown.`,
    messages: [
      {
        role: 'user',
        content: `TOPIC INVENTORY:\n${inventoryText}\n\nEXTRACTED SEGMENTS:\n${segmentText}\n\nWhich topics from the inventory are captured in the segments? Which are missing? Return JSON only.`,
      },
    ],
  });

  const rawText = message.content[0]?.type === 'text' ? message.content[0].text : '{}';
  const jsonText = rawText.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '').trim();

  try {
    const parsed = JSON.parse(jsonText);
    if (parsed && typeof parsed === 'object') {
      return {
        captured: Array.isArray(parsed.captured) ? parsed.captured : [],
        missing: Array.isArray(parsed.missing) ? parsed.missing : [],
        coverage_pct: typeof parsed.coverage_pct === 'number' ? parsed.coverage_pct : 0,
      };
    }
  } catch { /* fall through */ }

  return { captured: [], missing: topicInventory, coverage_pct: 0 };
}

// ── Pass 3: Fidelity + Voice ──────────────────────────────────────────────────

async function runFidelityVoice(
  segments: SegmentRow[],
  rawContent: string,
): Promise<SegmentScore[]> {
  if (segments.length === 0) return [];

  const contextSnippet = rawContent.slice(0, 3000);

  const segmentList = segments
    .map((s, i) => `[${i + 1}] topic_label: "${s.topic_label}"\ncontent: "${s.processed_content.slice(0, 400)}"`)
    .join('\n\n');

  const message = await anthropic.messages.create({
    model: EVAL_MODEL,
    max_tokens: 2048,
    system: `You are evaluating extracted knowledge segments against the original source text.

Rate each segment on two dimensions (1-5 scale):
- fidelity: Does it accurately represent what's in the source? (1=fabricated, 5=spot-on)
- voice: Is it written in first person, preserving specific tensions and nuance, not a generic summary? (1=generic summary, 5=authentic first-person voice)

Return ONLY a JSON array in exactly this format:
[{"index": 1, "fidelity": 4, "voice": 3}, ...]

No explanation, no markdown.`,
    messages: [
      {
        role: 'user',
        content: `SOURCE TEXT (excerpt):\n${contextSnippet}\n\nSEGMENTS TO EVALUATE:\n${segmentList}\n\nReturn JSON array of scores only.`,
      },
    ],
  });

  const rawText = message.content[0]?.type === 'text' ? message.content[0].text : '[]';
  const jsonText = rawText.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '').trim();

  let scores: Array<{ index: number; fidelity: number; voice: number }> = [];
  try {
    const parsed = JSON.parse(jsonText);
    if (Array.isArray(parsed)) scores = parsed;
  } catch {
    const match = jsonText.match(/\[[\s\S]*\]/);
    if (match) {
      try {
        const parsed = JSON.parse(match[0]);
        if (Array.isArray(parsed)) scores = parsed;
      } catch { /* fall through */ }
    }
  }

  return segments.map((seg, i) => {
    const score = scores.find((s) => s.index === i + 1);
    return {
      segment_id: seg.id,
      topic_label: seg.topic_label,
      fidelity: score?.fidelity ?? 0,
      voice: score?.voice ?? 0,
    };
  });
}

// ── Evaluate one source ───────────────────────────────────────────────────────

async function evaluateSource(
  source: SourceRow,
  segments: SegmentRow[],
): Promise<SourceEvalResult> {
  process.stdout.write(`  "${source.label}" (${source.source}, ${segments.length} segments) ... `);

  // Pass 1
  const topicInventory = await runTopicInventory(source.raw_content);

  // Pass 2
  const coverage = await runCoverageScore(topicInventory, segments);

  // Pass 3
  const segmentScores = await runFidelityVoice(segments, source.raw_content);

  const avgFidelity =
    segmentScores.length > 0
      ? segmentScores.reduce((sum, s) => sum + s.fidelity, 0) / segmentScores.length
      : 0;
  const avgVoice =
    segmentScores.length > 0
      ? segmentScores.reduce((sum, s) => sum + s.voice, 0) / segmentScores.length
      : 0;

  const coveragePass = coverage.coverage_pct / 100 >= COVERAGE_THRESHOLD;
  const verdict: 'PASS' | 'FAIL' = coveragePass ? 'PASS' : 'FAIL';

  console.log(`${verdict}`);

  return {
    source_id: source.id,
    source_label: source.label,
    source_type: source.source,
    topic_inventory: topicInventory,
    coverage,
    segment_scores: segmentScores,
    avg_fidelity: Math.round(avgFidelity * 100) / 100,
    avg_voice: Math.round(avgVoice * 100) / 100,
    verdict,
  };
}

// ── Print summary table ───────────────────────────────────────────────────────

function printSummaryTable(results: SourceEvalResult[]): void {
  console.log('\n' + '═'.repeat(60));
  console.log('EVALUATION RESULTS');
  console.log('═'.repeat(60));

  for (const r of results) {
    const coverageFlag =
      r.coverage.coverage_pct / 100 >= COVERAGE_THRESHOLD
        ? ''
        : ` <- FAIL (threshold: ${Math.round(COVERAGE_THRESHOLD * 100)}%)`;

    console.log(`\nSource: "${r.source_label}" (${r.source_type})`);
    console.log(`Topics found:     ${r.topic_inventory.length}`);
    console.log(`Topics captured:  ${r.coverage.captured.length}`);
    console.log(`Coverage:         ${r.coverage.coverage_pct}%${coverageFlag}`);
    console.log(`Avg fidelity:     ${r.avg_fidelity}/5`);
    console.log(`Avg voice:        ${r.avg_voice}/5`);

    if (r.coverage.missing.length > 0) {
      console.log(`Missing topics:   ${r.coverage.missing.slice(0, 3).join(', ')}${r.coverage.missing.length > 3 ? ` (+${r.coverage.missing.length - 3} more)` : ''}`);
    }
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log('\nMIKAI Segment Extraction Evaluation');
  console.log('=====================================');
  console.log(`Model: ${EVAL_MODEL}`);
  console.log(`Coverage threshold: ${Math.round(COVERAGE_THRESHOLD * 100)}%`);

  // ── Query sources ──────────────────────────────────────────────────────────

  let sourceQuery = supabase
    .from('sources')
    .select('id, label, raw_content, source')
    .not('raw_content', 'is', null);

  if (SOURCE_ID) {
    sourceQuery = sourceQuery.eq('id', SOURCE_ID);
  } else {
    sourceQuery = sourceQuery.limit(BATCH_SIZE);
  }

  const { data: allSources, error: sourceError } = await sourceQuery;

  if (sourceError) {
    console.error('Supabase sources query failed:', sourceError.message);
    process.exit(1);
  }

  const sources = (allSources ?? []) as SourceRow[];

  if (sources.length === 0) {
    console.log('No sources found.');
    return;
  }

  // ── Filter to sources that have segments ──────────────────────────────────

  const sourceIds = sources.map((s) => s.id);
  const { data: allSegments, error: segError } = await supabase
    .from('segments')
    .select('id, source_id, topic_label, processed_content')
    .in('source_id', sourceIds);

  if (segError) {
    console.error('Supabase segments query failed:', segError.message);
    process.exit(1);
  }

  const segmentsBySource = new Map<string, SegmentRow[]>();
  for (const seg of allSegments ?? []) {
    const arr = segmentsBySource.get(seg.source_id) ?? [];
    arr.push(seg as SegmentRow);
    segmentsBySource.set(seg.source_id, arr);
  }

  const sourcesWithSegments = sources.filter((s) => (segmentsBySource.get(s.id) ?? []).length > 0);

  if (sourcesWithSegments.length === 0) {
    console.log('No sources with segments found. Run: npm run build-segments');
    return;
  }

  console.log(`\n${sourcesWithSegments.length} source(s) to evaluate`);

  if (DRY_RUN) {
    console.log('\n[dry-run — no API calls]');
    for (const s of sourcesWithSegments) {
      const segCount = segmentsBySource.get(s.id)?.length ?? 0;
      console.log(`  would evaluate: "${s.label}" (${s.source}, ${segCount} segments)`);
    }
    return;
  }

  // ── Evaluate each source ───────────────────────────────────────────────────

  console.log('');
  const evalResults: SourceEvalResult[] = [];

  for (const source of sourcesWithSegments) {
    const segments = segmentsBySource.get(source.id) ?? [];
    try {
      const result = await evaluateSource(source, segments);
      evalResults.push(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.log(`FAILED — ${message}`);
    }
  }

  if (evalResults.length === 0) {
    console.log('All evaluations failed.');
    return;
  }

  // ── Compute aggregate summary ──────────────────────────────────────────────

  const avgCoverage =
    evalResults.reduce((sum, r) => sum + r.coverage.coverage_pct, 0) / evalResults.length;
  const avgFidelity =
    evalResults.reduce((sum, r) => sum + r.avg_fidelity, 0) / evalResults.length;
  const avgVoice =
    evalResults.reduce((sum, r) => sum + r.avg_voice, 0) / evalResults.length;
  const passCount = evalResults.filter((r) => r.verdict === 'PASS').length;
  const failCount = evalResults.length - passCount;
  const overallVerdict: 'PASS' | 'FAIL' =
    avgCoverage / 100 >= COVERAGE_THRESHOLD ? 'PASS' : 'FAIL';

  const timestamp = new Date().toISOString();

  const result: EvalResult = {
    timestamp,
    model: EVAL_MODEL,
    source_count: evalResults.length,
    sources: evalResults,
    summary: {
      avg_coverage_pct: Math.round(avgCoverage * 100) / 100,
      avg_fidelity: Math.round(avgFidelity * 100) / 100,
      avg_voice: Math.round(avgVoice * 100) / 100,
      pass_count: passCount,
      fail_count: failCount,
      verdict: overallVerdict,
    },
  };

  // ── Write results file ─────────────────────────────────────────────────────

  const safeTimestamp = timestamp.replace(/[:.]/g, '-');
  const resultsDir = path.join(__dirname, 'results');
  const outPath = path.join(resultsDir, `eval-segments-${safeTimestamp}.json`);

  fs.mkdirSync(resultsDir, { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf-8');

  // ── Print summary table ────────────────────────────────────────────────────

  printSummaryTable(evalResults);

  console.log('\n' + '═'.repeat(60));
  console.log('OVERALL SUMMARY');
  console.log('═'.repeat(60));
  console.log(`Sources evaluated: ${evalResults.length}`);
  console.log(`Avg coverage:      ${result.summary.avg_coverage_pct}%`);
  console.log(`Avg fidelity:      ${result.summary.avg_fidelity}/5`);
  console.log(`Avg voice:         ${result.summary.avg_voice}/5`);
  console.log(`Pass:              ${passCount}`);
  console.log(`Fail:              ${failCount}`);
  console.log('');
  console.log(`VERDICT: ${overallVerdict}`);
  if (overallVerdict === 'PASS') {
    console.log('  Coverage meets threshold. Segment quality validated.');
  } else {
    console.log(`  Coverage below ${Math.round(COVERAGE_THRESHOLD * 100)}% threshold. Review segmentation prompt or increase segment cap.`);
  }
  console.log('');
  console.log(`Results written to: ${outPath}`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
