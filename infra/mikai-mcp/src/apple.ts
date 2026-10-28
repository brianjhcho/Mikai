// apple.ts — READ-ONLY access to the user's Apple Calendar, Messages and Contacts
// databases on this Mac. Never writes, never sends. Reading these files needs
// macOS Full Disk Access for the process that runs this server.

import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const COCOA_EPOCH = 978307200
const DAY_S = 86_400

type Row = Record<string, unknown>
type Db = {
  prepare(sql: string): { all(...p: unknown[]): unknown[]; get(...p: unknown[]): unknown }
  close(): void
}

export function calendarDbFromEnv(): string {
  return process.env.MIKAI_CALENDAR_DB
    ?? path.join(os.homedir(), "Library", "Group Containers", "group.com.apple.calendar", "Calendar.sqlitedb")
}

export function messagesDbFromEnv(): string {
  return process.env.MIKAI_MESSAGES_DB ?? path.join(os.homedir(), "Library", "Messages", "chat.db")
}

export function addressBookDbsFromEnv(): string[] {
  if (process.env.MIKAI_ADDRESSBOOK_DBS !== undefined) {
    return process.env.MIKAI_ADDRESSBOOK_DBS.split(":").filter(Boolean)
  }
  const sources = path.join(os.homedir(), "Library", "Application Support", "AddressBook", "Sources")
  try {
    return fs.readdirSync(sources)
      .map(d => path.join(sources, d, "AddressBook-v22.abcddb"))
      .filter(p => fs.existsSync(p))
  } catch {
    return []
  }
}

export class AppleDataAccessError extends Error {}

async function openRo(dbPath: string): Promise<Db> {
  const { DatabaseSync } = (await import("node:sqlite" as string)) as {
    DatabaseSync: new (p: string, o: { readOnly: boolean }) => Db
  }
  try {
    const db = new DatabaseSync(dbPath, { readOnly: true })
    db.prepare("SELECT 1 FROM sqlite_master LIMIT 1").get()
    return db
  } catch (e) {
    throw new AppleDataAccessError(
      `cannot read ${dbPath} (${(e as Error).message}). If this file exists, macOS is blocking access: ` +
      `grant Full Disk Access to ${process.execPath} (System Settings → Privacy & Security → Full Disk Access).`,
    )
  }
}

function pad(n: number): string {
  return String(n).padStart(2, "0")
}

function localStamp(unixSeconds: number): string {
  const d = new Date(unixSeconds * 1000)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function localMidnight(date: string): number {
  const [y, m, d] = date.split("-").map(Number)
  const t = new Date(y, m - 1, d).getTime() / 1000
  if (!Number.isFinite(t)) throw new Error(`invalid date '${date}', expected YYYY-MM-DD`)
  return t
}

// ── Calendar ───────────────────────────────────────────────────────────

export interface CalendarEvent {
  title: string
  start: string
  end: string | null
  all_day: boolean
  calendar: string | null
  location: string | null
  has_attendees: boolean
}

export async function calendarEvents(
  dbPath: string,
  options: { start?: string; end?: string; limit?: number; now?: Date } = {},
): Promise<CalendarEvent[]> {
  const now = options.now ?? new Date()
  const startUnix = options.start
    ? localMidnight(options.start)
    : new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000
  const endUnix = options.end ? localMidnight(options.end) + DAY_S : startUnix + 7 * DAY_S
  const limit = options.limit ?? 100
  const db = await openRo(dbPath)
  try {
    // OccurrenceCache expands recurring events; occurrence_start_date is usually
    // NULL and occurrence_date carries the start.
    const rows = db.prepare(`
      SELECT ci.ROWID AS id, ci.summary AS title,
             COALESCE(oc.occurrence_start_date, oc.occurrence_date) AS s,
             oc.occurrence_end_date AS e, ci.all_day AS all_day,
             cal.title AS calendar, l.title AS location, l.address AS address,
             ci.has_attendees AS has_attendees
      FROM OccurrenceCache oc
      JOIN CalendarItem ci ON ci.ROWID = oc.event_id
      LEFT JOIN Calendar cal ON cal.ROWID = ci.calendar_id
      LEFT JOIN Location l ON l.ROWID = ci.location_id
      WHERE COALESCE(oc.occurrence_start_date, oc.occurrence_date) >= ?
        AND COALESCE(oc.occurrence_start_date, oc.occurrence_date) < ?
        AND ci.summary IS NOT NULL
        AND COALESCE(ci.hidden, 0) = 0
        AND COALESCE(ci.junk_status, 0) = 0
      ORDER BY s ASC
      LIMIT ?`).all(startUnix - COCOA_EPOCH, endUnix - COCOA_EPOCH, limit * 2) as Row[]
    const seen = new Set<string>()
    const out: CalendarEvent[] = []
    for (const r of rows) {
      const key = `${r.id}:${r.s}`
      if (seen.has(key)) continue
      seen.add(key)
      const loc = [r.location, r.address].filter(v => typeof v === "string" && v.trim()).join(", ")
      out.push({
        title: String(r.title),
        start: localStamp(Number(r.s) + COCOA_EPOCH),
        end: r.e == null ? null : localStamp(Number(r.e) + COCOA_EPOCH),
        all_day: !!r.all_day,
        calendar: (r.calendar as string) ?? null,
        location: loc || null,
        has_attendees: !!r.has_attendees,
      })
      if (out.length >= limit) break
    }
    return out
  } finally {
    db.close()
  }
}

// ── Contacts ───────────────────────────────────────────────────────────

function phoneKey(s: string): string | null {
  const digits = s.replace(/\D/g, "")
  return digits.length >= 7 ? digits.slice(-10) : null
}

export async function contactNames(abDbs: string[]): Promise<Map<string, string>> {
  const names = new Map<string, string>()
  for (const p of abDbs) {
    let db: Db
    try {
      db = await openRo(p)
    } catch {
      continue
    }
    try {
      const people = new Map<number, string>()
      for (const r of db.prepare("SELECT Z_PK AS pk, ZFIRSTNAME AS f, ZLASTNAME AS l, ZORGANIZATION AS o FROM ZABCDRECORD").all() as Row[]) {
        const name = [r.f, r.l].filter(Boolean).join(" ") || (r.o as string) || ""
        if (name) people.set(Number(r.pk), name)
      }
      for (const r of db.prepare("SELECT ZOWNER AS owner, ZFULLNUMBER AS n FROM ZABCDPHONENUMBER").all() as Row[]) {
        const key = typeof r.n === "string" ? phoneKey(r.n) : null
        const name = people.get(Number(r.owner))
        if (key && name && !names.has(key)) names.set(key, name)
      }
      try {
        for (const r of db.prepare("SELECT ZOWNER AS owner, ZADDRESS AS a FROM ZABCDEMAILADDRESS").all() as Row[]) {
          const name = people.get(Number(r.owner))
          if (typeof r.a === "string" && name) names.set(r.a.toLowerCase(), name)
        }
      } catch {
        // older AddressBook schemas may lack the email table
      }
    } finally {
      db.close()
    }
  }
  return names
}

function resolveName(handle: string | null, names: Map<string, string>): string | null {
  if (!handle) return null
  if (handle.includes("@")) return names.get(handle.toLowerCase()) ?? null
  const key = phoneKey(handle)
  return key ? names.get(key) ?? null : null
}

// MIKAI's own iMessage line (Hermes/Photon) must not show up as a dropped
// conversation. Excluded by default from Hermes's auth file, plus
// MIKAI_MESSAGES_EXCLUDE (comma-separated handles).
export function excludedHandlesFromEnv(): string[] {
  const out = (process.env.MIKAI_MESSAGES_EXCLUDE ?? "").split(",").map(s => s.trim()).filter(Boolean)
  const authPath = path.join(process.env.HERMES_HOME ?? path.join(os.homedir(), ".hermes"), "auth.json")
  try {
    const auth = JSON.parse(fs.readFileSync(authPath, "utf-8")) as { credential_pool?: { photon_user?: Array<{ assigned_phone_number?: string }> } }
    for (const u of auth.credential_pool?.photon_user ?? []) {
      if (u.assigned_phone_number) out.push(u.assigned_phone_number)
    }
  } catch {
    // no Hermes install or unreadable auth file: nothing extra to exclude
  }
  return out
}

function handleKey(h: string): string {
  return h.includes("@") ? h.toLowerCase() : phoneKey(h) ?? h
}

// ── Messages ───────────────────────────────────────────────────────────

// Newer macOS stores many message bodies only in attributedBody (an NSArchiver
// typedstream). The plain string follows the "NSString" class marker.
export function decodeAttributedBody(buf: Uint8Array | null | undefined): string | null {
  if (!buf || buf.length === 0) return null
  const data = Buffer.from(buf)
  const idx = data.indexOf("NSString")
  if (idx < 0) return null
  let i = idx + "NSString".length + 5
  if (i >= data.length) return null
  let len = data[i]
  i += 1
  if (len === 0x81) {
    len = data.readUInt16LE(i)
    i += 2
  } else if (len === 0x82) {
    len = data.readUIntLE(i, 3)
    i += 3
  }
  if (i + len > data.length) return null
  const text = data.subarray(i, i + len).toString("utf-8").trim()
  return text || null
}

// chat.db stores nanoseconds since 2001 on modern macOS (too large for a JS
// number), seconds on old ones; normalise to seconds inside SQLite.
const MESSAGE_SECONDS = "(CASE WHEN m.date > 1000000000000 THEN m.date / 1000000000.0 ELSE m.date * 1.0 END)"

export interface Conversation {
  conversation: string
  contact_name: string | null
  is_group: boolean
  last_message: string
  last_from: "me" | "them"
  last_at: string
  unanswered: boolean
  unread_from_them: number
  messages_in_window: number
}

const TRUNCATE = 200

export async function recentMessages(
  dbPath: string,
  options: { hours?: number; limit?: number; now?: Date; addressBookDbs?: string[]; exclude?: string[] } = {},
): Promise<Conversation[]> {
  const now = options.now ?? new Date()
  const hours = options.hours ?? 48
  const limit = options.limit ?? 30
  const cutoffCocoa = now.getTime() / 1000 - hours * 3600 - COCOA_EPOCH
  const names = await contactNames(options.addressBookDbs ?? addressBookDbsFromEnv())
  const excluded = new Set((options.exclude ?? excludedHandlesFromEnv()).map(handleKey))
  const db = await openRo(dbPath)
  try {
    const rows = db.prepare(`
      SELECT m.ROWID AS id, ${MESSAGE_SECONDS} AS date_s, m.is_from_me AS from_me, m.text AS text,
             m.attributedBody AS body, m.is_read AS is_read, h.id AS handle,
             c.ROWID AS chat_rowid, c.chat_identifier AS chat_identifier,
             c.display_name AS display_name, c.style AS style
      FROM message m
      LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
      LEFT JOIN chat c ON c.ROWID = cmj.chat_id
      LEFT JOIN handle h ON h.ROWID = m.handle_id
      WHERE ${MESSAGE_SECONDS} > ? AND m.date > 0
        AND COALESCE(m.associated_message_type, 0) = 0
        AND COALESCE(m.is_system_message, 0) = 0
        AND COALESCE(m.item_type, 0) = 0
      ORDER BY m.date DESC
      LIMIT 2000`).all(cutoffCocoa) as Row[]

    const convos = new Map<string, Conversation>()
    for (const r of rows) {
      const ident0 = (r.chat_identifier as string) ?? (r.handle as string) ?? ""
      if (ident0 && excluded.has(handleKey(ident0))) continue
      const key = r.chat_rowid != null ? `chat:${r.chat_rowid}` : `handle:${r.handle ?? "unknown"}`
      let c = convos.get(key)
      if (!c) {
        const isGroup = Number(r.style) === 43
        const ident = (r.chat_identifier as string) ?? (r.handle as string) ?? "unknown"
        const text = (r.text as string) || decodeAttributedBody(r.body as Uint8Array) || "[no text: attachment or unsupported message]"
        c = {
          conversation: (r.display_name as string) || ident,
          contact_name: isGroup ? null : resolveName(ident, names) ?? resolveName((r.handle as string) ?? null, names),
          is_group: isGroup,
          last_message: text.length > TRUNCATE ? `${text.slice(0, TRUNCATE)}…` : text,
          last_from: r.from_me ? "me" : "them",
          last_at: localStamp(Number(r.date_s) + COCOA_EPOCH),
          unanswered: !r.from_me,
          unread_from_them: 0,
          messages_in_window: 0,
        }
        convos.set(key, c)
      }
      c.messages_in_window += 1
      if (!r.from_me && !r.is_read) c.unread_from_them += 1
    }
    return [...convos.values()].slice(0, limit)
  } finally {
    db.close()
  }
}

// Logged at server start so the gateway's macOS permission state is visible in
// ~/.hermes/logs/mcp-stderr.log without sending anything.
export async function probeAppleAccess(): Promise<Record<string, string>> {
  const out: Record<string, string> = {}
  for (const [name, p] of [["calendar", calendarDbFromEnv()], ["messages", messagesDbFromEnv()]] as const) {
    try {
      const db = await openRo(p)
      try {
        db.prepare("SELECT 1 FROM sqlite_master LIMIT 1").get()
        out[name] = "ok"
      } finally {
        db.close()
      }
    } catch (e) {
      out[name] = `denied: ${(e as Error).message}`
    }
  }
  return out
}
