// Task-state tools: thread listing/stall detection over temp brain dirs, and feedback
// recording into a temp SQLite DB (never ~/.mikai/notification_log.db).

import { test } from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"

import { listThreads, getThread, stalledThreads } from "../dist/src/threads.js"
import { recordFeedback } from "../dist/src/feedback.js"

const NOW = new Date("2026-10-13T12:00:00Z")

function thread({ slug, state, stateSince, lastActivity, nextStep }) {
  const lines = ["---", `slug: ${slug}`, `title: ${slug} title`, `state: ${state}`]
  if (stateSince) lines.push(`state_since: ${stateSince}`)
  if (lastActivity) lines.push(`last_activity: ${lastActivity}`)
  if (nextStep) lines.push(`next_step: "${nextStep}"`)
  lines.push("entities: [germaine]", "department: love", "---", "", `## Context`, "", `Body of ${slug}.`)
  return lines.join("\n")
}

async function makeBrain(t, threads) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "mikai-brain-test-"))
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  await fs.mkdir(path.join(root, "threads"))
  for (const th of threads) {
    await fs.writeFile(path.join(root, "threads", `${th.slug}.md`), thread(th))
  }
  return root
}

const FIXTURE = [
  { slug: "fresh", state: "acting", stateSince: "2026-10-01", lastActivity: "2026-10-12", nextStep: "keep going" },
  { slug: "quiet", state: "exploring", stateSince: "2026-06-30", lastActivity: "2026-08-04", nextStep: "shortlist venues" },
  { slug: "flagged", state: "stalled", stateSince: "2026-10-10", nextStep: "unblock" },
  { slug: "finished", state: "completed", stateSince: "2026-05-01", lastActivity: "2026-05-01" },
  { slug: "no-activity", state: "evaluating", stateSince: "2026-09-01" },
]

test("listThreads parses frontmatter, computes days_quiet, filters by state", async (t) => {
  const root = await makeBrain(t, FIXTURE)
  const all = await listThreads(root, { now: NOW })
  assert.equal(all.length, 5)
  const quiet = all.find(x => x.slug === "quiet")
  assert.equal(quiet.state, "exploring")
  assert.equal(quiet.next_step, "shortlist venues")
  assert.deepEqual(quiet.entities, ["germaine"])
  assert.equal(quiet.days_quiet, 70)
  assert.equal(all.find(x => x.slug === "no-activity").days_quiet, 42, "falls back to state_since")
  assert.ok(!("body" in quiet), "list omits body")

  const acting = await listThreads(root, { state: "acting", now: NOW })
  assert.deepEqual(acting.map(x => x.slug), ["fresh"])
})

test("getThread returns body and rejects path traversal", async (t) => {
  const root = await makeBrain(t, FIXTURE)
  const th = await getThread(root, "quiet", NOW)
  assert.match(th.body, /Body of quiet/)
  assert.equal(await getThread(root, "../../etc/passwd", NOW), null)
  assert.equal(await getThread(root, "missing", NOW), null)
})

test("stalledThreads: quiet past threshold or state=stalled, excludes completed, sorted", async (t) => {
  const root = await makeBrain(t, FIXTURE)
  const stalled = await stalledThreads(root, { now: NOW })
  assert.deepEqual(stalled.map(x => x.slug), ["quiet", "no-activity", "flagged"])
  const strict = await stalledThreads(root, { days: 60, now: NOW })
  assert.deepEqual(strict.map(x => x.slug), ["quiet", "flagged"])
})

test("listThreads on a missing brain dir returns empty", async () => {
  assert.deepEqual(await listThreads(path.join(os.tmpdir(), "does-not-exist-mikai")), [])
})

test("recordFeedback writes to notification_feedback in a temp DB", async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "mikai-fb-test-"))
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  const dbPath = path.join(dir, "notification_log.db")
  const seed = new DatabaseSync(dbPath)
  seed.exec("CREATE TABLE notification_log (id INTEGER PRIMARY KEY, notif_id TEXT)")
  seed.prepare("INSERT INTO notification_log (notif_id) VALUES (?)").run("abc123def456")
  seed.close()

  const r1 = await recordFeedback(dbPath, { notifId: "abc123def456", label: "acted", source: "hermes-imessage" })
  assert.equal(r1.label, "ACTED")
  assert.equal(r1.matched_notification, true)

  const r2 = await recordFeedback(dbPath, { threadSlug: "quiet", label: "not relevant", note: "wrong time" })
  assert.equal(r2.label, "NOT_RELEVANT")
  assert.equal(r2.matched_notification, false)
  assert.equal(r2.source, "mcp")

  const db = new DatabaseSync(dbPath)
  const rows = db.prepare("SELECT notif_id, thread_slug, label, note FROM notification_feedback ORDER BY id").all()
  db.close()
  assert.equal(rows.length, 2)
  assert.equal(rows[1].note, "wrong time")
})

test("recordFeedback rejects bad labels and missing targets", async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "mikai-fb-test-"))
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  const dbPath = path.join(dir, "fb.db")
  await assert.rejects(recordFeedback(dbPath, { threadSlug: "x", label: "maybe" }), /label must be one of/)
  await assert.rejects(recordFeedback(dbPath, { label: "ACTED" }), /notif_id or thread_slug/)
})
