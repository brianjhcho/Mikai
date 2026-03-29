/**
 * engine/l4/classify-state.ts
 *
 * Rule-based thread state classification. Zero LLM.
 *
 * Analyzes temporal patterns, content signals, and activity frequency
 * to classify each thread into one of six states:
 *   exploring → evaluating → decided → acting → stalled → completed
 *
 * Runs after detect-threads, before infer-next-step.
 */

import type Database from 'better-sqlite3';
import {
  getActiveThreads, getThreadMembers, recordTransition, updateThread,
} from './store.js';
import type { Thread, ThreadState, ClassificationSignals } from './types.js';
import { VALID_TRANSITIONS } from './types.js';
import { extractGraphClassificationSignals } from './graph-enrichment.js';

// ── Signal extraction ────────────────────────────────────────────────────────

// Content patterns (case-insensitive)
const COMPARISON_PATTERNS = [
  /\bvs\.?\b/i, /\bcompare\b/i, /\bversus\b/i, /\bor should\b/i,
  /\bpros? and cons?\b/i, /\balternative/i, /\btrade-?off/i,
  /\bwhich (one|is better)\b/i, /\bon one hand\b/i, /\bbetween\b.*\band\b/i,
];

const DECISION_PATTERNS = [
  /\bdecided\b/i, /\bgoing (with|to)\b/i, /\bchose\b/i, /\bpicked\b/i,
  /\bcommitting to\b/i, /\bfinal answer\b/i, /\blet'?s go with\b/i,
  /\bI('?m| am) going\b/i, /\bwe('?re| are) going\b/i, /\bthe plan is\b/i,
  /\bi('?ll| will)\b/i,
];

const ACTION_PATTERNS = [
  /\bdone\b/i, /\bcompleted\b/i, /\bfinished\b/i, /\bshipped\b/i,
  /\bdeployed\b/i, /\bmerged\b/i, /\bsubmitted\b/i, /\bsent\b/i,
  /\bstarted\b/i, /\bworking on\b/i, /\bin progress\b/i, /\bdrafting\b/i,
  /\bbuilding\b/i, /\bwriting\b/i, /\bimplementing\b/i,
];

const RESOLUTION_PATTERNS = [
  /\bresolved\b/i, /\bclosed\b/i, /\bno longer\b/i, /\bnever ?mind\b/i,
  /\bchanged my mind\b/i, /\bdoesn'?t matter\b/i, /\bmoot\b/i,
  /\bcancelled?\b/i, /\babandoned\b/i,
];

function matchesAny(text: string, patterns: RegExp[]): boolean {
  return patterns.some(p => p.test(text));
}

// ── Signal computation ───────────────────────────────────────────────────────

function extractSignals(db: Database.Database, thread: Thread): ClassificationSignals {
  const members = getThreadMembers(db, thread.id);

  // Gather all content for pattern matching
  const segmentIds = members.filter(m => m.segment_id).map(m => m.segment_id!);
  const nodeIds = members.filter(m => m.node_id).map(m => m.node_id!);

  let allContent = '';
  const nodeTypes: string[] = [];

  if (segmentIds.length > 0) {
    const placeholders = segmentIds.map(() => '?').join(',');
    const segments = db.prepare(
      `SELECT processed_content FROM segments WHERE id IN (${placeholders})`
    ).all(...segmentIds) as { processed_content: string }[];
    allContent += segments.map(s => s.processed_content).join('\n');
  }

  if (nodeIds.length > 0) {
    const placeholders = nodeIds.map(() => '?').join(',');
    const nodes = db.prepare(
      `SELECT content, node_type, has_action_verb FROM nodes WHERE id IN (${placeholders})`
    ).all(...nodeIds) as { content: string; node_type: string; has_action_verb: number }[];
    allContent += '\n' + nodes.map(n => n.content).join('\n');
    nodeTypes.push(...nodes.map(n => n.node_type));
  }

  // Temporal signals
  const now = Date.now();
  const lastActivity = new Date(thread.last_activity_at).getTime();
  const firstSeen = new Date(thread.first_seen_at).getTime();
  const daysSinceLastActivity = (now - lastActivity) / (1000 * 60 * 60 * 24);
  const threadAgeDays = (now - firstSeen) / (1000 * 60 * 60 * 24);

  // Activity frequency: source_count / age in weeks (clamped)
  const ageWeeks = Math.max(threadAgeDays / 7, 0.5);
  const activityFrequency = thread.source_count / ageWeeks;

  // Compute stall probability from temporal signals
  let stallProbability = 0;
  if (daysSinceLastActivity > 10) stallProbability = 0.8;
  else if (daysSinceLastActivity > 5) stallProbability = 0.5;
  else if (daysSinceLastActivity > 2) stallProbability = 0.2;

  // Source type count
  const sourceTypes: string[] = JSON.parse(thread.source_types || '[]');

  // Graph enrichment signals from L3 edges within this thread
  const edgeTypesWithin: string[] = JSON.parse(thread.edge_types_within || '[]');
  const graphClassSignals = extractGraphClassificationSignals(edgeTypesWithin);

  return {
    source_type_count: sourceTypes.length,
    has_comparison_language: matchesAny(allContent, COMPARISON_PATTERNS),
    has_decision_language: matchesAny(allContent, DECISION_PATTERNS),
    has_action_evidence: matchesAny(allContent, ACTION_PATTERNS),
    days_since_last_activity: daysSinceLastActivity,
    activity_frequency: activityFrequency,
    has_resolution_signal: matchesAny(allContent, RESOLUTION_PATTERNS),
    stall_probability: stallProbability,
    node_types_involved: [...new Set(nodeTypes)],
    graph_edge_types: edgeTypesWithin,
    ...graphClassSignals,
  };
}

// ── State classification rules ───────────────────────────────────────────────

function classifyFromSignals(signals: ClassificationSignals, currentState: ThreadState): ThreadState {
  // Terminal: resolution signals → completed
  if (signals.has_resolution_signal) {
    return 'completed';
  }

  // Stall detection: no activity for 7+ days, was previously active
  // Graph signal: unresolved dependency chain strengthens stall signal
  if (signals.stall_probability >= 0.5 && currentState !== 'exploring') {
    return 'stalled';
  }
  if (signals.has_dependency_chain && !signals.has_action_evidence && signals.days_since_last_activity > 5) {
    return 'stalled';
  }

  // Action evidence → acting (content signal is primary; recency is secondary)
  if (signals.has_action_evidence && signals.days_since_last_activity < 14) {
    return 'acting';
  }

  // Decision language + no strong action evidence → decided
  if (signals.has_decision_language && !signals.has_action_evidence) {
    return 'decided';
  }

  // Decision language + action evidence → acting (decided and moved on)
  if (signals.has_decision_language && signals.has_action_evidence) {
    return 'acting';
  }

  // Graph signal: contradiction/tension edges → evaluating (even without comparison language)
  if (signals.has_contradiction_edges) {
    return 'evaluating';
  }

  // Comparison language + multiple source types → evaluating
  if (signals.has_comparison_language && signals.source_type_count >= 2) {
    return 'evaluating';
  }

  // Comparison language alone → evaluating
  if (signals.has_comparison_language) {
    return 'evaluating';
  }

  // Default: if young thread with few signals → exploring
  if (signals.days_since_last_activity < 7) {
    return currentState === 'stalled' ? 'exploring' : currentState;
  }

  return currentState;
}

// ── Main classification ──────────────────────────────────────────────────────

export interface ClassifyResult {
  threadsClassified: number;
  stateChanges: number;
  byState: Record<string, number>;
}

export async function classifyThreadStates(db: Database.Database): Promise<ClassifyResult> {
  const threads = getActiveThreads(db, 10000); // All active threads
  let stateChanges = 0;
  const byState: Record<string, number> = {};

  for (const thread of threads) {
    const signals = extractSignals(db, thread);
    const newState = classifyFromSignals(signals, thread.state as ThreadState);

    // Count by state
    byState[newState] = (byState[newState] ?? 0) + 1;

    // Update stall probability on thread regardless
    updateThread(db, thread.id, {
      stall_probability: signals.stall_probability,
    } as any);

    // Only record transition if state actually changed
    if (newState !== thread.state) {
      // Validate transition
      const validTargets = VALID_TRANSITIONS[thread.state as ThreadState] ?? [];
      if (!validTargets.includes(newState)) continue;

      const reason = buildTransitionReason(signals, thread.state as ThreadState, newState);
      recordTransition(db, thread.id, thread.state as ThreadState, newState, reason);
      stateChanges++;
    }
  }

  return {
    threadsClassified: threads.length,
    stateChanges,
    byState,
  };
}

function buildTransitionReason(
  signals: ClassificationSignals,
  from: ThreadState,
  to: ThreadState,
): string {
  if (to === 'completed') return 'Resolution signal detected in thread content';
  if (to === 'stalled') return `No activity for ${Math.round(signals.days_since_last_activity)} days (was ${from})`;
  if (to === 'acting') return 'Action language detected with recent activity';
  if (to === 'decided') return 'Decision language detected without follow-through action';
  if (to === 'evaluating') return `Comparison language detected across ${signals.source_type_count} source types`;
  if (to === 'exploring') return 'Thread re-activated after stall';
  return `State changed from ${from} to ${to}`;
}
