import { test } from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"

import { upsertThread, getThread } from "../dist/src/threads.js"
import { recentSurfaced, latestUnanswered } from "../dist/src/outbox.js"
import { recordFeedback } from "../dist/src/feedback.js"

async function tmp() {
  return fs.mkdtemp(path.join(os.tmpdir(), "mikai-upsert-"))
}

test("upsertThread creates a new thread from a title", async (t) => {
  const root = await tmp()
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  const now = new Date("2026-10-24T12:00:00Z")
  const r = await upsertThread(root, { title: "Movie tickets next week", next_step: "Pick a showtime", note: "asked over iMessage", source: "hermes-imessage" }, now)
  assert.equal(r.created, true)
  assert.equal(r.slug, "movie-tickets-next-week")
  assert.equal(r.thread.state, "exploring")
  assert.equal(r.thread.next_step, "Pick a showtime")
  const full = await getThread(root, r.slug, now)
  assert.match(full.body, /2026-10-24 \(hermes-imessage\): asked over iMessage/)
})

test("upsertThread updates state, backs up the old file, keeps other fields", async (t) => {
  const root = await tmp()
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  await fs.mkdir(path.join(root, "threads"))
  const original = `---\nslug: monstera-moss-pole\ntitle: Monstera pole\nstate: evaluating\nstate_since: 2026-07-20\nlast_activity: 2026-08-05\nentities: [monstera]\n---\n\n## Context\n\nAerial roots.\n\n## Log\n\n- 2026-08-05: still deciding\n`
  await fs.writeFile(path.join(root, "threads", "monstera-moss-pole.md"), original)
  const now = new Date("2026-10-24T12:00:00Z")
  const r = await upsertThread(root, { slug: "monstera-moss-pole", state: "decided", next_step: "Buy a coco pole", note: "chose coco" }, now)
  assert.equal(r.created, false)
  assert.equal(await fs.readFile(r.backup, "utf-8"), original)
  assert.equal(r.thread.state, "decided")
  assert.equal(r.thread.state_since, "2026-10-24")
  assert.equal(r.thread.last_activity, "2026-10-24")
  assert.deepEqual(r.thread.entities, ["monstera"])
  const full = await getThread(root, "monstera-moss-pole", now)
  assert.match(full.body, /chose coco[\s\S]*still deciding/)
})

test("upsertThread rejects unknown states and new threads without a title", async (t) => {
  const root = await tmp()
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  await assert.rejects(upsertThread(root, { title: "X", state: "maybe" }), /state must be one of/)
  await assert.rejects(upsertThread(root, { slug: "brand-new" }), /title is required/)
})

test("recentSurfaced and latestUnanswered read the outbox and skip answered items", async (t) => {
  const dir = await tmp()
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  const dbPath = path.join(dir, "log.db")
  const db = new DatabaseSync(dbPath)
  db.exec("CREATE TABLE imessage_outbox (ref TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL, sent_at TEXT NOT NULL)")
  db.prepare("INSERT INTO imessage_outbox VALUES (?, ?, ?, ?)").run("old", "Old item", "surface", "2026-10-24T08:00:00+00:00")
  db.prepare("INSERT INTO imessage_outbox VALUES (?, ?, ?, ?)").run("new", "New item", "surface", "2026-10-24T11:00:00+00:00")
  db.prepare("INSERT INTO imessage_outbox VALUES (?, ?, ?, ?)").run("stale", "Too old", "surface", "2026-10-20T11:00:00+00:00")
  db.close()
  const now = new Date("2026-10-24T12:00:00Z")

  const items = await recentSurfaced(dbPath, 48, now)
  assert.deepEqual(items.map(i => i.ref), ["new", "old"])
  assert.equal((await latestUnanswered(dbPath, 48, now)).ref, "new")

  await recordFeedback(dbPath, { notifId: "new", label: "ACTED" })
  assert.equal((await latestUnanswered(dbPath, 48, now)).ref, "old")
})

test("recentSurfaced returns nothing when no outbox exists", async (t) => {
  const dir = await tmp()
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  assert.deepEqual(await recentSurfaced(path.join(dir, "empty.db")), [])
})
