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
