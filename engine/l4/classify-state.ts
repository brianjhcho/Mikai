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
import { getDomainConfig, getValidTransitions, isTerminalState } from './domain-config.js';
import type { DomainConfig } from './domain-config.js';

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

  // Research-only threads: content comes from AI responses, not user actions.
  // Action keywords in Perplexity/Claude responses ("building", "working on")
  // describe topics being discussed, not actions the user is taking.
  const RESEARCH_ONLY_SOURCES = new Set(['perplexity', 'claude-thread']);
  const isResearchOnly = sourceTypes.length > 0 && sourceTypes.every(s => RESEARCH_ONLY_SOURCES.has(s));

  // Graph enrichment signals from L3 edges within this thread
  const edgeTypesWithin: string[] = JSON.parse(thread.edge_types_within || '[]');
  const graphClassSignals = extractGraphClassificationSignals(edgeTypesWithin);

  // ── Temporal signals from edge valid_at / invalid_at (Phase 3) ──────────
  let edgeAgeDays = Infinity;
  let invalidatedEdgeCount = 0;
  let validEdgeCount = 0;

  if (nodeIds.length >= 2) {
    try {
      const placeholders = nodeIds.map(() => '?').join(',');
      const temporal = db.prepare(`
        SELECT
          MAX(valid_at) as newest,
          SUM(CASE WHEN invalid_at IS NOT NULL THEN 1 ELSE 0 END) as invalidated,
          SUM(CASE WHEN invalid_at IS NULL THEN 1 ELSE 0 END) as valid
        FROM edges
        WHERE from_node IN (${placeholders}) AND to_node IN (${placeholders})
      `).get(...nodeIds, ...nodeIds) as any;

      if (temporal?.newest) {
        edgeAgeDays = (now - new Date(temporal.newest).getTime()) / (1000 * 60 * 60 * 24);
      }
      invalidatedEdgeCount = temporal?.invalidated ?? 0;
      validEdgeCount = temporal?.valid ?? 0;
    } catch { /* temporal columns may not exist */ }
  }

  const hasEvolved = invalidatedEdgeCount > 0;

  return {
    source_type_count: sourceTypes.length,
    is_research_only: isResearchOnly,
    has_comparison_language: matchesAny(allContent, COMPARISON_PATTERNS),
    has_decision_language: matchesAny(allContent, DECISION_PATTERNS),
    // Discount action evidence for research-only threads: AI responses contain
    // action words ("building", "working on") that describe topics, not user behavior.
    has_action_evidence: isResearchOnly ? false : matchesAny(allContent, ACTION_PATTERNS),
    days_since_last_activity: daysSinceLastActivity,
    activity_frequency: activityFrequency,
    has_resolution_signal: matchesAny(allContent, RESOLUTION_PATTERNS),
    stall_probability: stallProbability,
    node_types_involved: [...new Set(nodeTypes)],
    graph_edge_types: edgeTypesWithin,
    ...graphClassSignals,
    // Temporal signals
    edge_age_days: edgeAgeDays,
    invalidated_edge_count: invalidatedEdgeCount,
    valid_edge_count: validEdgeCount,
    has_evolved: hasEvolved,
  };
}

// ── State classification rules ───────────────────────────────────────────────

function classifyFromSignals(signals: ClassificationSignals, currentState: ThreadState, config?: DomainConfig): ThreadState {
  const cfg = config ?? getDomainConfig();
  // ── Layer 1: Terminal signals (strongest) ─────────────────────────────────
  // Resolution language = completed regardless of other signals
  if (signals.has_resolution_signal) {
    return 'completed';
  }

  // ── Layer 2: Temporal signals (Graphiti Phase 3) ──────────────────────────
  // Temporal signals override content patterns. What you wrote doesn't reflect
  // where you are now — WHEN new content last appeared does.

  // Old thread with no recent edges: cap at exploring or stalled.
  // Content may say "I'm building X" but if the newest edge is 30+ days old,
  // you're not actively building it.
  const isTemporallyDormant = signals.edge_age_days > cfg.temporal.dormantDays && signals.days_since_last_activity > cfg.temporal.staleDays * 2;
  const isTemporallyStale = signals.days_since_last_activity > cfg.temporal.staleDays;

  // Thread has evolved (invalidated edges = thinking changed over time)
  // Evolved threads with recent activity → evaluating (reconsidering)
  if (signals.has_evolved && signals.days_since_last_activity < cfg.temporal.actionRecencyDays) {
    return 'evaluating';
  }

  // Dormant threads: no new thinking in 30+ days → stalled (resurfacing candidate)
  // These aren't dead — they're candidates for "does this still matter to you?"
  if (isTemporallyDormant && currentState !== 'completed') {
    return 'stalled';
  }

  // ── Layer 3: Stall detection ──────────────────────────────────────────────
  if (signals.stall_probability >= 0.5 && currentState !== 'exploring') {
    return 'stalled';
  }
  if (signals.has_dependency_chain && !signals.has_action_evidence && signals.days_since_last_activity > 5) {
    return 'stalled';
  }

  // ── Layer 4: Content signals (weakest — only trusted for RECENT threads) ─
  // Content patterns are only reliable when the thread has recent activity.
  // "I'm building X" written yesterday = probably acting.
  // "I'm building X" written 3 months ago = probably stalled or completed.

  // Action evidence only counts if thread is recent (< 7 days)
  if (signals.has_action_evidence && !isTemporallyStale) {
    return 'acting';
  }

  // Decision language — require recency
  if (signals.has_decision_language && !signals.has_action_evidence) {
    if (signals.is_research_only) return 'evaluating';
    return isTemporallyStale ? 'exploring' : 'decided';
  }

  if (signals.has_decision_language && signals.has_action_evidence && !isTemporallyStale) {
    return 'acting';
  }

  // ── Layer 5: Graph structure signals ──────────────────────────────────────
  if (signals.has_contradiction_edges) {
    return 'evaluating';
  }

  if (signals.has_comparison_language && signals.source_type_count >= 2) {
    return 'evaluating';
  }

  if (signals.has_comparison_language) {
    return 'evaluating';
  }

  // ── Layer 6: Default ──────────────────────────────────────────────────────
  // Young threads with few signals → exploring
  if (signals.days_since_last_activity < cfg.temporal.staleDays) {
    return currentState === 'stalled' ? 'exploring' : currentState;
  }

  // Stale threads with no strong signals → exploring (not acting)
  if (isTemporallyStale) {
    return 'exploring';
  }

  return currentState;
}

// ── Main classification ──────────────────────────────────────────────────────

export interface ClassifyResult {
  threadsClassified: number;
  stateChanges: number;
  byState: Record<string, number>;
}

export async function classifyThreadStates(db: Database.Database, domainId?: string): Promise<ClassifyResult> {
  const config = getDomainConfig(domainId);
  const threads = getActiveThreads(db, 10000); // All active threads
  let stateChanges = 0;
  const byState: Record<string, number> = {};

  for (const thread of threads) {
    const signals = extractSignals(db, thread);
    const newState = classifyFromSignals(signals, thread.state as ThreadState, config);

    // Count by state
    byState[newState] = (byState[newState] ?? 0) + 1;

    // Update stall probability on thread regardless
    updateThread(db, thread.id, {
      stall_probability: signals.stall_probability,
    } as any);

    // Only record transition if state actually changed
    if (newState !== thread.state) {
      // Validate transition against domain config
      const validTargets = getValidTransitions(config, thread.state);
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
