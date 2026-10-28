// threads.ts — read-only access to MIKAI's L4 task-state files (~/.mikai/brain/threads/*.md).

import fs from "node:fs/promises"
import path from "node:path"
import { parseFrontmatter, stringList } from "./vault.js"

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/
const CLOSED_STATES = new Set(["completed", "done", "closed", "abandoned"])
const DAY_MS = 86_400_000

export interface ThreadSummary {
  slug: string
  title: string
  state: string | null
  state_since: string | null
  last_activity: string | null
  next_step: string | null
  entities: string[]
  department: string | null
  days_quiet: number | null
}

export interface ThreadContent extends ThreadSummary {
  body: string
}

export function brainRootFromEnv(): string {
  const root = process.env.MIKAI_BRAIN_ROOT ?? path.join(process.env.HOME || "", ".mikai", "brain")
  return root.startsWith("~") ? path.join(process.env.HOME || "", root.slice(1)) : root
}

function str(v: string | string[] | undefined): string | null {
  if (v === undefined) return null
  const s = Array.isArray(v) ? v.join(", ") : v
  return s.trim() === "" ? null : s
}

function daysSince(date: string | null, now: Date): number | null {
  if (!date) return null
  const t = Date.parse(date.length === 10 ? `${date}T00:00:00Z` : date)
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.floor((now.getTime() - t) / DAY_MS))
}

function toThread(slug: string, text: string, now: Date): ThreadContent {
  const { fields, end } = parseFrontmatter(text)
  const lastActivity = str(fields.last_activity)
  const stateSince = str(fields.state_since)
  return {
    slug: str(fields.slug) ?? slug,
    title: str(fields.title) ?? slug,
    state: str(fields.state),
    state_since: stateSince,
    last_activity: lastActivity,
    next_step: str(fields.next_step),
    entities: stringList(fields.entities),
    department: str(fields.department),
    days_quiet: daysSince(lastActivity ?? stateSince, now),
    body: text.slice(end).trim(),
  }
}

function summary({ body: _body, ...rest }: ThreadContent): ThreadSummary {
  return rest
}

async function readAll(root: string, now: Date): Promise<ThreadContent[]> {
  const dir = path.join(root, "threads")
  let names: string[]
  try {
    names = await fs.readdir(dir)
  } catch {
    return []
  }
  const out: ThreadContent[] = []
  for (const name of names.sort()) {
    if (!name.endsWith(".md")) continue
    const text = await fs.readFile(path.join(dir, name), "utf-8")
    out.push(toThread(name.slice(0, -3), text, now))
  }
  return out
}

export async function listThreads(
  root: string,
  options: { state?: string; now?: Date } = {},
): Promise<ThreadSummary[]> {
  const all = await readAll(root, options.now ?? new Date())
  return all.filter(t => !options.state || t.state === options.state).map(summary)
}

export async function getThread(root: string, slug: string, now: Date = new Date()): Promise<ThreadContent | null> {
  if (!SLUG_RE.test(slug)) return null
  try {
    const text = await fs.readFile(path.join(root, "threads", `${slug}.md`), "utf-8")
    return toThread(slug, text, now)
  } catch {
    return null
  }
}

export const THREAD_STATES = ["exploring", "evaluating", "decided", "acting", "stalled", "completed"] as const

export interface ThreadUpsertInput {
  slug?: string
  title?: string
  state?: string
  next_step?: string
  department?: string
  note?: string
  source?: string
}

export interface ThreadUpsertResult {
  slug: string
  created: boolean
  backup: string | null
  thread: ThreadSummary
}

function slugify(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60).replace(/-+$/, "")
}

function setField(front: string, key: string, value: string): string {
  const line = `${key}: ${JSON.stringify(value)}`
  const re = new RegExp(`^${key}:.*$`, "m")
  return re.test(front) ? front.replace(re, line) : `${front}\n${line}`
}

// The one write path into L4 thread files. Never touches the wiki. Every
// modification of an existing thread first copies it to threads/.history/.
export async function upsertThread(
  root: string,
  input: ThreadUpsertInput,
  now: Date = new Date(),
): Promise<ThreadUpsertResult> {
  const slug = input.slug?.trim() || (input.title ? slugify(input.title) : "")
  if (!SLUG_RE.test(slug)) throw new Error("a valid slug or title is required (lowercase letters, digits, hyphens)")
  const state = input.state?.trim().toLowerCase()
  if (state && !(THREAD_STATES as readonly string[]).includes(state)) {
    throw new Error(`state must be one of ${THREAD_STATES.join(", ")}`)
  }
  // Local calendar date: thread dates are read by a human in their own timezone.
  const today = new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
  const dir = path.join(root, "threads")
  const file = path.join(dir, `${slug}.md`)
  await fs.mkdir(dir, { recursive: true })

  let existing: string | null = null
  try {
    existing = await fs.readFile(file, "utf-8")
  } catch {
    existing = null
  }
  const logLine = input.note?.trim() ? `- ${today} (${input.source?.trim() || "mcp"}): ${input.note.trim()}` : null

  if (existing === null) {
    if (!input.title?.trim()) throw new Error("title is required to create a new thread")
    const fields: Array<[string, string]> = [
      ["slug", slug],
      ["title", input.title.trim()],
      ["state", state ?? "exploring"],
      ["state_since", today],
      ["last_activity", today],
      ["next_step", input.next_step?.trim() ?? ""],
      ["department", input.department?.trim() ?? ""],
      ["source", input.source?.trim() || "mcp"],
    ]
    const front = fields.filter(([, v]) => v !== "").map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join("\n")
    const body = `## Context\n\nCreated from a conversation on ${today}.\n\n## Log\n\n${logLine ?? `- ${today}: thread created`}\n`
    await fs.writeFile(file, `---\n${front}\n---\n\n${body}`, "utf-8")
    return { slug, created: true, backup: null, thread: summary(toThread(slug, await fs.readFile(file, "utf-8"), now)) }
  }

  const historyDir = path.join(dir, ".history")
  await fs.mkdir(historyDir, { recursive: true })
  const backup = path.join(historyDir, `${slug}-${now.toISOString().replace(/[:.]/g, "-")}.md`)
  await fs.writeFile(backup, existing, "utf-8")

  const m = existing.match(/^---\n([\s\S]*?)\n---\n?/)
  if (!m) throw new Error(`thread ${slug} has no frontmatter; not modifying it`)
  let front = m[1]
  let body = existing.slice(m[0].length)
  const current = toThread(slug, existing, now)
  if (input.title?.trim()) front = setField(front, "title", input.title.trim())
  if (state && state !== current.state) {
    front = setField(front, "state", state)
    front = setField(front, "state_since", today)
  }
  if (input.next_step?.trim()) front = setField(front, "next_step", input.next_step.trim())
  if (input.department?.trim()) front = setField(front, "department", input.department.trim())
  front = setField(front, "last_activity", today)
  if (logLine) {
    body = /^## Log\s*$/m.test(body) ? body.replace(/^## Log\s*$/m, `## Log\n\n${logLine}`) : `${body.trimEnd()}\n\n## Log\n\n${logLine}\n`
  }
  await fs.writeFile(file, `---\n${front}\n---\n${body}`, "utf-8")
  return { slug, created: false, backup, thread: summary(toThread(slug, await fs.readFile(file, "utf-8"), now)) }
}

export async function stalledThreads(
  root: string,
  options: { days?: number; now?: Date } = {},
): Promise<ThreadSummary[]> {
  const days = options.days ?? 14
  const all = await readAll(root, options.now ?? new Date())
  return all
    .filter(t => !CLOSED_STATES.has(t.state ?? ""))
    .filter(t => t.state === "stalled" || (t.days_quiet !== null && t.days_quiet >= days))
    .sort((a, b) => (b.days_quiet ?? -1) - (a.days_quiet ?? -1))
    .map(summary)
}
