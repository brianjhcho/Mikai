// feedback.ts — explicit user replies to surfaced items (iMessage via Hermes, etc.).
// Writes to an additive notification_feedback table; the legacy notification_events
// table's CHECK constraint only admits SENT/TAPPED/DISMISSED_INFERRED, so it is left untouched.

import path from "node:path"

export const FEEDBACK_LABELS = ["ACTED", "DISMISSED", "SNOOZED", "NOT_RELEVANT"] as const
export type FeedbackLabel = typeof FEEDBACK_LABELS[number]

export interface FeedbackInput {
  notifId?: string
  threadSlug?: string
  label: string
  note?: string
  source?: string
}

export interface FeedbackRecord {
  id: number
  notif_id: string | null
  thread_slug: string | null
  label: FeedbackLabel
  note: string | null
  source: string
  event_ts: string
  matched_notification: boolean
}

export function notificationDbFromEnv(): string {
  const p = process.env.MIKAI_NOTIFICATION_DB ?? path.join(process.env.HOME || "", ".mikai", "notification_log.db")
  return p.startsWith("~") ? path.join(process.env.HOME || "", p.slice(1)) : p
}

const SCHEMA = `CREATE TABLE IF NOT EXISTS notification_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notif_id TEXT,
  thread_slug TEXT,
  label TEXT NOT NULL CHECK (label IN ('ACTED','DISMISSED','SNOOZED','NOT_RELEVANT')),
  note TEXT,
  source TEXT NOT NULL,
  event_ts TEXT NOT NULL,
  CHECK (notif_id IS NOT NULL OR thread_slug IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_notification_feedback_notif ON notification_feedback(notif_id);
CREATE INDEX IF NOT EXISTS idx_notification_feedback_thread ON notification_feedback(thread_slug);`

export async function recordFeedback(dbPath: string, input: FeedbackInput): Promise<FeedbackRecord> {
  const label = input.label.trim().toUpperCase().replace(/[\s-]+/g, "_")
  if (!(FEEDBACK_LABELS as readonly string[]).includes(label)) {
    throw new Error(`label must be one of ${FEEDBACK_LABELS.join(", ")}`)
  }
  const notifId = input.notifId?.trim() || null
  const threadSlug = input.threadSlug?.trim() || null
  if (!notifId && !threadSlug) throw new Error("notif_id or thread_slug is required")

  const { DatabaseSync } = (await import("node:sqlite" as string)) as {
    DatabaseSync: new (p: string) => {
      exec(sql: string): void
      prepare(sql: string): {
        run(...p: unknown[]): { lastInsertRowid: number | bigint }
        get(...p: unknown[]): unknown
      }
      close(): void
    }
  }
  const db = new DatabaseSync(dbPath)
  try {
    db.exec(SCHEMA)
    let matched = false
    if (notifId) {
      const hasLog = db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='notification_log'").get()
      if (hasLog) matched = !!db.prepare("SELECT 1 FROM notification_log WHERE notif_id = ?").get(notifId)
    }
    const eventTs = new Date().toISOString()
    const source = input.source?.trim() || "mcp"
    const note = input.note?.trim() || null
    const res = db
      .prepare("INSERT INTO notification_feedback (notif_id, thread_slug, label, note, source, event_ts) VALUES (?, ?, ?, ?, ?, ?)")
      .run(notifId, threadSlug, label, note, source, eventTs)
    return {
      id: Number(res.lastInsertRowid),
      notif_id: notifId,
      thread_slug: threadSlug,
      label: label as FeedbackLabel,
      note,
      source,
      event_ts: eventTs,
      matched_notification: matched,
    }
  } finally {
    db.close()
  }
}
