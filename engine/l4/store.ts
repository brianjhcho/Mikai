/**
 * engine/l4/store.ts
 *
 * L4 CRUD operations for threads, members, transitions, and thread edges.
 * Follows the same patterns as lib/store-sqlite.ts.
 */

import type Database from 'better-sqlite3';
import { randomUUID } from 'crypto';
import type {
  Thread, ThreadInsert, ThreadMember, ThreadMemberInsert,
  ThreadTransition, ThreadEdge, ThreadEdgeType, ThreadState,
  DeliveryEvent, DeliveryEventInsert, UserResponse,
  VALID_TRANSITIONS,
} from './types.js';

// ── Threads ──────────────────────────────────────────────────────────────────

export function insertThread(db: Database.Database, row: ThreadInsert): { id: string } {
  const id = randomUUID();
  db.prepare(`
    INSERT INTO threads (id, label, summary, state, state_changed_at, first_seen_at, last_activity_at, source_count, source_types, confidence)
    VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)
  `).run(
    id, row.label, row.summary ?? null, row.state ?? 'exploring',
    row.first_seen_at, row.last_activity_at,
    row.source_count ?? 0, JSON.stringify(row.source_types ?? []),
    row.confidence ?? 0.5,
  );
  return { id };
}

export function updateThread(db: Database.Database, id: string, values: Partial<Thread>): void {
  const sets: string[] = [];
  const params: any[] = [];
  for (const [key, val] of Object.entries(values)) {
    if (key === 'id' || key === 'created_at') continue;
    sets.push(`${key} = ?`);
    params.push(val);
  }
  if (sets.length === 0) return;
  params.push(id);
  db.prepare(`UPDATE threads SET ${sets.join(', ')} WHERE id = ?`).run(...params);
}

export function getThread(db: Database.Database, id: string): Thread | null {
  return (db.prepare('SELECT * FROM threads WHERE id = ?').get(id) as Thread) ?? null;
}

export function getActiveThreads(db: Database.Database, limit: number = 20): Thread[] {
  return db.prepare(`
    SELECT * FROM threads
    WHERE resolved_at IS NULL AND state != 'completed'
    ORDER BY last_activity_at DESC
    LIMIT ?
  `).all(limit) as Thread[];
}

export function getThreadsByState(db: Database.Database, state: ThreadState, limit: number = 20): Thread[] {
  return db.prepare(`
    SELECT * FROM threads WHERE state = ? ORDER BY last_activity_at DESC LIMIT ?
  `).all(state, limit) as Thread[];
}

export function getStalledThreads(db: Database.Database, threshold: number = 0.5, limit: number = 10): Thread[] {
  return db.prepare(`
    SELECT * FROM threads
    WHERE stall_probability > ? AND resolved_at IS NULL
    ORDER BY stall_probability DESC
    LIMIT ?
  `).all(threshold, limit) as Thread[];
}

export function getThreadsWithNextSteps(db: Database.Database, limit: number = 10): Thread[] {
  return db.prepare(`
    SELECT * FROM threads
    WHERE next_step IS NOT NULL AND resolved_at IS NULL AND state != 'completed'
    ORDER BY last_activity_at DESC
    LIMIT ?
  `).all(limit) as Thread[];
}

// ── Thread Members ───────────────────────────────────────────────────────────

export function insertThreadMembers(db: Database.Database, rows: ThreadMemberInsert[]): void {
  const stmt = db.prepare(`
    INSERT INTO thread_members (id, thread_id, source_id, node_id, segment_id, contribution_type)
    VALUES (?, ?, ?, ?, ?, ?)
  `);

  const tx = db.transaction(() => {
    for (const row of rows) {
      stmt.run(
        randomUUID(), row.thread_id,
        row.source_id ?? null, row.node_id ?? null, row.segment_id ?? null,
        row.contribution_type,
      );
    }
  });
  tx();
}

export function getThreadMembers(db: Database.Database, threadId: string): ThreadMember[] {
  return db.prepare('SELECT * FROM thread_members WHERE thread_id = ?').all(threadId) as ThreadMember[];
}

export function getThreadsForSegment(db: Database.Database, segmentId: string): Thread[] {
  return db.prepare(`
    SELECT t.* FROM threads t
    INNER JOIN thread_members tm ON tm.thread_id = t.id
    WHERE tm.segment_id = ?
  `).all(segmentId) as Thread[];
}

export function getThreadsForNode(db: Database.Database, nodeId: string): Thread[] {
  return db.prepare(`
    SELECT t.* FROM threads t
    INNER JOIN thread_members tm ON tm.thread_id = t.id
    WHERE tm.node_id = ?
  `).all(nodeId) as Thread[];
}

// ── State Transitions ────────────────────────────────────────────────────────

export function recordTransition(
  db: Database.Database,
  threadId: string,
  fromState: ThreadState | null,
  toState: ThreadState,
  reason?: string,
  evidenceNodeId?: string,
): { id: string } {
  const id = randomUUID();
  db.prepare(`
    INSERT INTO thread_transitions (id, thread_id, from_state, to_state, reason, evidence_node_id)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(id, threadId, fromState, toState, reason ?? null, evidenceNodeId ?? null);

  // Update thread state
  db.prepare(`
    UPDATE threads SET state = ?, state_changed_at = datetime('now') WHERE id = ?
  `).run(toState, threadId);

  // If completed, set resolved_at
  if (toState === 'completed') {
    db.prepare(`UPDATE threads SET resolved_at = datetime('now') WHERE id = ?`).run(threadId);
  }

  return { id };
}

export function getTransitionHistory(db: Database.Database, threadId: string): ThreadTransition[] {
  return db.prepare(`
    SELECT * FROM thread_transitions WHERE thread_id = ? ORDER BY created_at ASC
  `).all(threadId) as ThreadTransition[];
}

// ── Thread Edges ─────────────────────────────────────────────────────────────

export function insertThreadEdge(
  db: Database.Database,
  fromThread: string,
  toThread: string,
  relationship: ThreadEdgeType,
  note?: string,
): { id: string } | null {
  try {
    const id = randomUUID();
    db.prepare(`
      INSERT INTO thread_edges (id, from_thread, to_thread, relationship, note)
      VALUES (?, ?, ?, ?, ?)
    `).run(id, fromThread, toThread, relationship, note ?? null);
    return { id };
  } catch {
    return null;
  }
}

export function getThreadEdges(db: Database.Database, threadId: string): ThreadEdge[] {
  return db.prepare(`
    SELECT * FROM thread_edges WHERE from_thread = ? OR to_thread = ?
  `).all(threadId, threadId) as ThreadEdge[];
}

// ── Delivery Events (PPP training signal) ────────────────────────────────

export function insertDeliveryEvent(db: Database.Database, row: DeliveryEventInsert): { id: string } {
  const id = randomUUID();
  db.prepare(`
    INSERT INTO delivery_events (id, thread_id, next_step, action_category, delivery_score)
    VALUES (?, ?, ?, ?, ?)
  `).run(id, row.thread_id, row.next_step, row.action_category ?? null, row.delivery_score ?? 0);

  // Update thread surfacing metadata
  db.prepare(`
    UPDATE threads SET last_surfaced_at = datetime('now') WHERE id = ?
  `).run(row.thread_id);

  return { id };
}

export function recordDeliveryResponse(
  db: Database.Database,
  eventId: string,
  response: UserResponse,
): void {
  db.prepare(`
    UPDATE delivery_events SET user_response = ?, response_at = datetime('now') WHERE id = ?
  `).run(response, eventId);

  // Update thread counts based on response
  const event = db.prepare('SELECT thread_id FROM delivery_events WHERE id = ?').get(eventId) as { thread_id: string } | undefined;
  if (event) {
    if (response === 'acted') {
      db.prepare('UPDATE threads SET acted_count = acted_count + 1 WHERE id = ?').run(event.thread_id);
    } else if (response === 'dismissed') {
      db.prepare('UPDATE threads SET dismissed_count = dismissed_count + 1 WHERE id = ?').run(event.thread_id);
    }
  }
}

export function getDeliveryEvents(db: Database.Database, threadId: string, limit: number = 20): DeliveryEvent[] {
  return db.prepare(`
    SELECT * FROM delivery_events WHERE thread_id = ? ORDER BY delivered_at DESC LIMIT ?
  `).all(threadId, limit) as DeliveryEvent[];
}

export function getPPPMetrics(db: Database.Database): {
  totalDeliveries: number;
  actedCount: number;
  dismissedCount: number;
  ignoredCount: number;
  productivityScore: number;
  personalizationScore: number;
} {
  const total = (db.prepare('SELECT COUNT(*) as c FROM delivery_events').get() as any).c;
  const acted = (db.prepare("SELECT COUNT(*) as c FROM delivery_events WHERE user_response = 'acted'").get() as any).c;
  const dismissed = (db.prepare("SELECT COUNT(*) as c FROM delivery_events WHERE user_response = 'dismissed'").get() as any).c;
  const ignored = (db.prepare("SELECT COUNT(*) as c FROM delivery_events WHERE user_response = 'ignored'").get() as any).c;

  return {
    totalDeliveries: total,
    actedCount: acted,
    dismissedCount: dismissed,
    ignoredCount: ignored,
    productivityScore: total > 0 ? acted / total : 0,
    personalizationScore: total > 0 ? 1 - (dismissed / total) : 1,
  };
}

// ── Stats ────────────────────────────────────────────────────────────────────

export function getL4Stats(db: Database.Database): {
  totalThreads: number;
  byState: Record<string, number>;
  stalledCount: number;
  withNextSteps: number;
  avgSourcesPerThread: number;
} {
  const totalThreads = (db.prepare('SELECT COUNT(*) as c FROM threads').get() as any).c;
  const stalledCount = (db.prepare('SELECT COUNT(*) as c FROM threads WHERE stall_probability > 0.5 AND resolved_at IS NULL').get() as any).c;
  const withNextSteps = (db.prepare('SELECT COUNT(*) as c FROM threads WHERE next_step IS NOT NULL AND resolved_at IS NULL').get() as any).c;
  const avgResult = db.prepare('SELECT AVG(source_count) as avg FROM threads').get() as any;

  const stateRows = db.prepare('SELECT state, COUNT(*) as c FROM threads GROUP BY state').all() as { state: string; c: number }[];
  const byState: Record<string, number> = {};
  for (const row of stateRows) byState[row.state] = row.c;

  return {
    totalThreads,
    byState,
    stalledCount,
    withNextSteps,
    avgSourcesPerThread: avgResult.avg ?? 0,
  };
}
