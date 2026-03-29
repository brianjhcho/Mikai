/**
 * engine/l4/schema.ts
 *
 * L4 database schema — thread detection, state classification, next-step inference.
 * Extends the existing L3 tables (sources, nodes, edges, segments) with:
 *   - threads: cross-app topics being tracked
 *   - thread_members: links threads → L3 entities (sources, nodes, segments)
 *   - thread_transitions: state change history
 *   - thread_edges: L4 relationships between threads
 */

import type Database from 'better-sqlite3';

function addColumnSafe(db: Database.Database, table: string, column: string, type: string, defaultVal?: string): void {
  try {
    const def = defaultVal !== undefined ? ` DEFAULT ${defaultVal}` : '';
    db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${type}${def}`);
  } catch {
    // Column already exists — safe to ignore
  }
}

export function initL4Schema(db: Database.Database): void {
  db.exec(`
    -- ── Threads ──────────────────────────────────────────────────────────────
    -- A thread is a topic or concern tracked across multiple apps/sources.
    -- Core L4 entity. Everything else references this.

    CREATE TABLE IF NOT EXISTS threads (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      label TEXT NOT NULL,
      summary TEXT,
      state TEXT NOT NULL DEFAULT 'exploring',
      state_changed_at TEXT,
      first_seen_at TEXT NOT NULL,
      last_activity_at TEXT NOT NULL,
      source_count INTEGER DEFAULT 0,
      source_types TEXT DEFAULT '[]',
      next_step TEXT,
      next_step_generated_at TEXT,
      confidence REAL DEFAULT 0.5,
      stall_probability REAL DEFAULT 0.0,
      resolved_at TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    -- ── Thread Members ───────────────────────────────────────────────────────
    -- Links threads to their constituent L3 entities.
    -- A segment/node/source can belong to multiple threads.

    CREATE TABLE IF NOT EXISTS thread_members (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
      source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
      node_id TEXT REFERENCES nodes(id) ON DELETE SET NULL,
      segment_id TEXT REFERENCES segments(id) ON DELETE SET NULL,
      contribution_type TEXT NOT NULL DEFAULT 'evidence',
      created_at TEXT DEFAULT (datetime('now'))
    );

    -- ── Thread Transitions ───────────────────────────────────────────────────
    -- State change audit log. Every state transition is recorded.

    CREATE TABLE IF NOT EXISTS thread_transitions (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
      from_state TEXT,
      to_state TEXT NOT NULL,
      reason TEXT,
      evidence_node_id TEXT REFERENCES nodes(id) ON DELETE SET NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );

    -- ── Thread Edges ─────────────────────────────────────────────────────────
    -- L4 relationships between threads: led_to, blocked_by, resumed_from, resolved_by

    CREATE TABLE IF NOT EXISTS thread_edges (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      from_thread TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
      to_thread TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
      relationship TEXT NOT NULL,
      note TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    -- ── Delivery columns on threads (L4 research integration) ─────────────
    -- These are ALTER TABLE statements wrapped in a safe pattern.
    -- SQLite doesn't support IF NOT EXISTS on ALTER TABLE, so we handle
    -- missing columns via the error path in addColumnSafe() below.

    -- ── Delivery Events (PPP training signal collection) ────────────────

    CREATE TABLE IF NOT EXISTS delivery_events (
      id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
      thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
      next_step TEXT NOT NULL,
      action_category TEXT,
      delivery_score REAL DEFAULT 0.0,
      user_response TEXT CHECK(user_response IN ('acted', 'dismissed', 'ignored', 'deferred')),
      response_at TEXT,
      delivered_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_delivery_thread ON delivery_events(thread_id);
    CREATE INDEX IF NOT EXISTS idx_delivery_response ON delivery_events(user_response);

    -- ── Indexes ──────────────────────────────────────────────────────────────

    CREATE INDEX IF NOT EXISTS idx_threads_state ON threads(state);
    CREATE INDEX IF NOT EXISTS idx_threads_stall ON threads(stall_probability) WHERE stall_probability > 0.5;
    CREATE INDEX IF NOT EXISTS idx_threads_last_activity ON threads(last_activity_at);
    CREATE INDEX IF NOT EXISTS idx_thread_members_thread ON thread_members(thread_id);
    CREATE INDEX IF NOT EXISTS idx_thread_members_source ON thread_members(source_id);
    CREATE INDEX IF NOT EXISTS idx_thread_members_node ON thread_members(node_id);
    CREATE INDEX IF NOT EXISTS idx_thread_members_segment ON thread_members(segment_id);
    CREATE INDEX IF NOT EXISTS idx_thread_transitions_thread ON thread_transitions(thread_id);
    CREATE INDEX IF NOT EXISTS idx_thread_edges_from ON thread_edges(from_thread);
    CREATE INDEX IF NOT EXISTS idx_thread_edges_to ON thread_edges(to_thread);
  `);

  // ── Delivery columns on threads (safe migration) ────────────────────────
  addColumnSafe(db, 'threads', 'delivery_score', 'REAL', '0.0');
  addColumnSafe(db, 'threads', 'dismissed_count', 'INTEGER', '0');
  addColumnSafe(db, 'threads', 'acted_count', 'INTEGER', '0');
  addColumnSafe(db, 'threads', 'last_surfaced_at', 'TEXT');
  addColumnSafe(db, 'threads', 'edge_types_within', 'TEXT', "'[]'");
  addColumnSafe(db, 'threads', 'action_category', 'TEXT');
}
