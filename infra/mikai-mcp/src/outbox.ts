// outbox.ts — what MIKAI has texted the user (imessage_outbox, written by the Surface
// Engine's imessage_dispatch.py) and whether each item has a recorded reply yet.

export interface SurfacedItem {
  ref: string
  text: string
  kind: string
  sent_at: string
  answered: boolean
}

type Db = {
  exec(sql: string): void
  prepare(sql: string): { all(...p: unknown[]): unknown[]; get(...p: unknown[]): unknown }
  close(): void
}

async function openDb(dbPath: string): Promise<Db> {
  const { DatabaseSync } = (await import("node:sqlite" as string)) as { DatabaseSync: new (p: string) => Db }
  return new DatabaseSync(dbPath)
}

function hasTable(db: Db, name: string): boolean {
  return !!db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(name)
}

export async function recentSurfaced(dbPath: string, hours = 48, now: Date = new Date()): Promise<SurfacedItem[]> {
  const db = await openDb(dbPath)
  try {
    if (!hasTable(db, "imessage_outbox")) return []
    const since = new Date(now.getTime() - hours * 3_600_000).toISOString()
    const answered = hasTable(db, "notification_feedback")
      ? "EXISTS (SELECT 1 FROM notification_feedback f WHERE f.notif_id = o.ref)"
      : "0"
    const rows = db
      .prepare(`SELECT ref, text, kind, sent_at, ${answered} AS answered FROM imessage_outbox o WHERE sent_at >= ? ORDER BY sent_at DESC`)
      .all(since) as Array<Omit<SurfacedItem, "answered"> & { answered: number }>
    return rows.map(r => ({ ...r, answered: !!r.answered }))
  } finally {
    db.close()
  }
}

export async function latestUnanswered(dbPath: string, hours = 48, now: Date = new Date()): Promise<SurfacedItem | null> {
  const items = await recentSurfaced(dbPath, hours, now)
  return items.find(i => !i.answered) ?? null
}
