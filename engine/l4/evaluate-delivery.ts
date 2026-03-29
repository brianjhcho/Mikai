/**
 * engine/l4/evaluate-delivery.ts
 *
 * Sumimasen Gate — decides which threads are worth surfacing.
 *
 * Sits between classify (Stage 2) and infer (Stage 3) in the L4 pipeline.
 * Only threads that pass the gate get Haiku inference, saving cost and
 * reducing noise.
 *
 * V1: Rule-based proxy using temporal signals and cooldowns.
 * V2+: Adaptive threshold trained from dismiss/act feedback (PPP paper).
 *
 * Research basis:
 *   - ProMemAssist (UIST 2025): working memory model → timing heuristics
 *   - Inner Thoughts (CHI 2025): evaluation as stage 4 of proactive loop
 *   - PPP (CMU 2025): joint optimization target for delivery quality
 */

import type Database from 'better-sqlite3';
import type { Thread } from './types.js';
import { getActiveThreads, getStalledThreads } from './store.js';

// ── Configuration ────────────────────────────────────────────────────────────

const MAX_DELIVERABLE_PER_CYCLE = 5;     // cap items per pipeline run
const COOLDOWN_HOURS = 48;                // don't re-surface within 48h
const STALL_MIN_DAYS = 7;                // only surface stalls older than 7d
const STALL_MAX_DAYS = 30;               // don't surface ancient stalls
const ACTIVITY_RECENCY_DAYS = 14;        // active threads must have recent activity
const HIGH_LOAD_SOURCE_TYPES = 3;        // 3+ source types active in 1h = high load

// ── Types ────────────────────────────────────────────────────────────────────

export interface EvaluationResult {
  deliverableThreadIds: string[];
  evaluated: number;
  filtered: number;
  reasons: Map<string, string>;           // threadId → why it was filtered
}

interface ScoredThread {
  thread: Thread;
  score: number;
  reason: string;
}

// ── Scoring ──────────────────────────────────────────────────────────────────

function computeDeliveryScore(thread: Thread, now: number): ScoredThread | null {
  const lastActivity = new Date(thread.last_activity_at).getTime();
  const daysSinceActivity = (now - lastActivity) / (1000 * 60 * 60 * 24);

  // ── Filter: cooldown ──────────────────────────────────────────────────
  if (thread.last_surfaced_at) {
    const lastSurfaced = new Date(thread.last_surfaced_at).getTime();
    const hoursSinceSurfaced = (now - lastSurfaced) / (1000 * 60 * 60);
    if (hoursSinceSurfaced < COOLDOWN_HOURS) {
      return null; // too soon
    }
  }

  // ── Filter: completed/resolved threads ────────────────────────────────
  if (thread.state === 'completed' || thread.resolved_at) {
    return null;
  }

  let score = 0;
  let reason = '';

  // ── Stalled threads: high priority if in the right window ─────────────
  if (thread.state === 'stalled' || thread.stall_probability > 0.5) {
    if (daysSinceActivity < STALL_MIN_DAYS) {
      return null; // too fresh to call stalled
    }
    if (daysSinceActivity > STALL_MAX_DAYS) {
      return null; // too old, probably abandoned
    }
    // Sweet spot: 7-30 days stalled
    score = 0.8 - (daysSinceActivity - STALL_MIN_DAYS) * 0.02; // decays gently
    reason = `stalled ${Math.round(daysSinceActivity)}d — unblock opportunity`;
  }

  // ── State-changed threads: worth surfacing if recently transitioned ───
  else if (thread.state_changed_at) {
    const stateChangedAt = new Date(thread.state_changed_at).getTime();
    const hoursSinceChange = (now - stateChangedAt) / (1000 * 60 * 60);
    if (hoursSinceChange < 24) {
      score = 0.7;
      reason = `state changed to ${thread.state} within 24h`;
    }
  }

  // ── Active threads with recent activity ───────────────────────────────
  if (score === 0 && daysSinceActivity <= ACTIVITY_RECENCY_DAYS) {
    // Cross-source threads are more valuable to surface
    const sourceTypes: string[] = JSON.parse(thread.source_types || '[]');
    const crossSourceBonus = Math.min(sourceTypes.length * 0.1, 0.3);

    score = 0.4 + crossSourceBonus - (daysSinceActivity * 0.02);
    reason = `active (${sourceTypes.length} sources, ${Math.round(daysSinceActivity)}d ago)`;
  }

  // ── Confidence weighting ──────────────────────────────────────────────
  score *= thread.confidence;

  if (score <= 0) return null;

  return { thread, score: Math.min(score, 1.0), reason };
}

// ── Main evaluation ──────────────────────────────────────────────────────────

export async function evaluateForDelivery(db: Database.Database): Promise<EvaluationResult> {
  const now = Date.now();
  const reasons = new Map<string, string>();

  // Gather candidates: stalled + active threads
  const stalled = getStalledThreads(db, 0.3, 20);
  const active = getActiveThreads(db, 50);

  // Deduplicate
  const seen = new Set<string>();
  const candidates: Thread[] = [];
  for (const t of [...stalled, ...active]) {
    if (seen.has(t.id)) continue;
    seen.add(t.id);
    candidates.push(t);
  }

  // Score all candidates
  const scored: ScoredThread[] = [];
  for (const thread of candidates) {
    const result = computeDeliveryScore(thread, now);
    if (result) {
      scored.push(result);
    } else {
      reasons.set(thread.id, 'filtered by gate');
    }
  }

  // Sort by score descending, take top N
  scored.sort((a, b) => b.score - a.score);
  const deliverable = scored.slice(0, MAX_DELIVERABLE_PER_CYCLE);

  // Update delivery_score on threads that pass the gate
  const updateStmt = db.prepare('UPDATE threads SET delivery_score = ? WHERE id = ?');
  for (const { thread, score } of deliverable) {
    updateStmt.run(score, thread.id);
  }

  return {
    deliverableThreadIds: deliverable.map(s => s.thread.id),
    evaluated: candidates.length,
    filtered: candidates.length - deliverable.length,
    reasons,
  };
}
