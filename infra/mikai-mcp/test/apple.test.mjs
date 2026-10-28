import { test } from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"

import {
  AppleDataAccessError,
  calendarEvents,
  decodeAttributedBody,
  recentMessages,
} from "../dist/src/apple.js"

const COCOA = 978307200

async function tmpdir() {
  return fs.mkdtemp(path.join(os.tmpdir(), "mikai-apple-"))
}

// Local-time seconds since the Cocoa epoch for a given local date/time.
function cocoa(y, mo, d, h = 0, mi = 0) {
  return new Date(y, mo - 1, d, h, mi).getTime() / 1000 - COCOA
}

function makeCalendar(p) {
  const db = new DatabaseSync(p)
  db.exec(`
    CREATE TABLE Calendar (ROWID INTEGER PRIMARY KEY, title TEXT);
    CREATE TABLE Location (ROWID INTEGER PRIMARY KEY, title TEXT, address TEXT);
    CREATE TABLE CalendarItem (ROWID INTEGER PRIMARY KEY, summary TEXT, location_id INTEGER,
      start_date REAL, end_date REAL, all_day INTEGER, calendar_id INTEGER, hidden INTEGER,
      junk_status INTEGER, has_attendees INTEGER, entity_type INTEGER);
    CREATE TABLE OccurrenceCache (day REAL, event_id INTEGER, calendar_id INTEGER, store_id INTEGER,
      occurrence_date REAL, occurrence_start_date REAL, occurrence_end_date REAL);
  `)
  db.prepare("INSERT INTO Calendar VALUES (1, 'Personal')").run()
  db.prepare("INSERT INTO Location VALUES (1, 'Cineplex', '123 Main St')").run()
  const item = db.prepare("INSERT INTO CalendarItem VALUES (?, ?, ?, 0, 0, ?, 1, ?, 0, ?, 2)")
  item.run(1, "Movie night", 1, 0, 0, 1)
  item.run(2, "Weekly standup", null, 0, 0, 0)
  item.run(3, "Hidden thing", null, 0, 1, 0)
  const occ = db.prepare("INSERT INTO OccurrenceCache VALUES (0, ?, 1, 1, ?, NULL, ?)")
  occ.run(1, cocoa(2026, 10, 30, 19, 15), cocoa(2026, 10, 30, 21, 30))
  occ.run(2, cocoa(2026, 10, 28, 9), cocoa(2026, 10, 28, 9, 30))
  occ.run(2, cocoa(2026, 11, 4, 9), cocoa(2026, 11, 4, 9, 30))   // next week, outside default window
  occ.run(3, cocoa(2026, 10, 29, 12), cocoa(2026, 10, 29, 13))   // hidden
  db.close()
}

test("calendarEvents expands occurrences, joins calendar + location, skips hidden, respects window", async (t) => {
  const dir = await tmpdir()
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  const p = path.join(dir, "Calendar.sqlitedb")
  makeCalendar(p)
  const now = new Date(2026, 9, 27, 17, 0)
  const events = await calendarEvents(p, { now })
  assert.deepEqual(events.map(e => e.title), ["Weekly standup", "Movie night"])
  const movie = events[1]
  assert.equal(movie.start, "2026-10-30 19:15")
  assert.equal(movie.end, "2026-10-30 21:30")
  assert.equal(movie.calendar, "Personal")
  assert.equal(movie.location, "Cineplex, 123 Main St")
  assert.equal(movie.has_attendees, true)

  const nextWeek = await calendarEvents(p, { start: "2026-11-03", end: "2026-11-05", now })
  assert.deepEqual(nextWeek.map(e => e.start), ["2026-11-04 09:00"])
})

test("calendarEvents rejects a malformed date", async (t) => {
  const dir = await tmpdir()
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  const p = path.join(dir, "Calendar.sqlitedb")
  makeCalendar(p)
  await assert.rejects(calendarEvents(p, { start: "next tuesday" }), /invalid date/)
})

test("a missing database raises AppleDataAccessError naming the binary", async () => {
  await assert.rejects(
    calendarEvents("/nonexistent/dir/Calendar.sqlitedb"),
    e => e instanceof AppleDataAccessError && e.message.includes(process.execPath),
  )
})

function attributed(text) {
  const t = Buffer.from(text, "utf-8")
  const len = t.length < 0x80 ? Buffer.from([t.length]) : Buffer.concat([Buffer.from([0x81]), Buffer.from([t.length & 0xff, t.length >> 8])])
  return Buffer.concat([Buffer.from("streamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString", "latin1"), Buffer.from([0x01, 0x94, 0x84, 0x01, 0x2b]), len, t, Buffer.from([0x86, 0x84])])
}

test("decodeAttributedBody extracts short and long strings, and fails soft", () => {
  assert.equal(decodeAttributedBody(attributed("see you at 7")), "see you at 7")
  const long = "x".repeat(300)
  assert.equal(decodeAttributedBody(attributed(long)), long)
  assert.equal(decodeAttributedBody(Buffer.from("no marker here")), null)
  assert.equal(decodeAttributedBody(null), null)
})

function makeMessages(p) {
  const db = new DatabaseSync(p)
  db.exec(`
    CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT, service TEXT);
    CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT, display_name TEXT, style INTEGER, service_name TEXT);
    CREATE TABLE message (ROWID INTEGER PRIMARY KEY, date INTEGER, is_from_me INTEGER, text TEXT,
      attributedBody BLOB, handle_id INTEGER, is_read INTEGER, cache_roomnames TEXT, item_type INTEGER,
      associated_message_type INTEGER, is_system_message INTEGER, service TEXT);
    CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER, message_date INTEGER, index_state INTEGER);
  `)
  db.prepare("INSERT INTO handle VALUES (1, '+16045551234', 'iMessage')").run()
  db.prepare("INSERT INTO handle VALUES (2, '+14155550000', 'iMessage')").run()
  db.prepare("INSERT INTO chat VALUES (1, '+16045551234', NULL, 45, 'iMessage')").run()
  db.prepare("INSERT INTO chat VALUES (2, 'chat123', 'Climbing crew', 43, 'iMessage')").run()
  db.prepare("INSERT INTO chat VALUES (3, '+14155550000', NULL, 45, 'iMessage')").run()
  const msg = db.prepare("INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, 0, 'iMessage')")
  const join = db.prepare("INSERT INTO chat_message_join VALUES (?, ?, 0, 0)")
  // nanoseconds since 2001, the modern format; BigInt because it exceeds 2^53.
  const ns = (y, mo, d, h, mi = 0) => BigInt(Math.round(cocoa(y, mo, d, h, mi))) * 1000000000n
  msg.run(1, ns(2026, 10, 27, 10), 1, "want to get dinner fri?", null, 1, 1, 0); join.run(1, 1)
  msg.run(2, ns(2026, 10, 27, 11), 0, null, attributed("yes! where?"), 1, 0, 0); join.run(1, 2)
  msg.run(3, ns(2026, 10, 27, 11, 1), 0, "❤️", null, 1, 0, 2000); join.run(1, 3)        // tapback: ignored
  msg.run(4, ns(2026, 10, 27, 9), 0, "who's in saturday", null, 0, 1, 0); join.run(2, 4)
  msg.run(5, ns(2026, 10, 27, 9, 5), 1, "me", null, 0, 1, 0); join.run(2, 5)
  msg.run(6, ns(2026, 10, 27, 12), 0, "MIKAI says hi", null, 2, 0, 0); join.run(3, 6)     // MIKAI's own line
  msg.run(7, ns(2026, 10, 20, 9), 0, "old", null, 1, 1, 0); join.run(1, 7)               // outside window
  db.close()
}

function makeAddressBook(p) {
  const db = new DatabaseSync(p)
  db.exec(`
    CREATE TABLE ZABCDRECORD (Z_PK INTEGER PRIMARY KEY, ZFIRSTNAME TEXT, ZLASTNAME TEXT, ZORGANIZATION TEXT);
    CREATE TABLE ZABCDPHONENUMBER (ZOWNER INTEGER, ZFULLNUMBER TEXT);
    CREATE TABLE ZABCDEMAILADDRESS (ZOWNER INTEGER, ZADDRESS TEXT);
  `)
  db.prepare("INSERT INTO ZABCDRECORD VALUES (1, 'Alex', NULL, NULL)").run()
  db.prepare("INSERT INTO ZABCDPHONENUMBER VALUES (1, '(604) 555-1234')").run()
  db.close()
}

test("recentMessages groups by conversation, resolves names, flags unanswered, excludes MIKAI's line", async (t) => {
  const dir = await tmpdir()
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  const msgs = path.join(dir, "chat.db")
  const ab = path.join(dir, "AddressBook-v22.abcddb")
  makeMessages(msgs)
  makeAddressBook(ab)
  const now = new Date(2026, 9, 27, 17, 0)
  const convos = await recentMessages(msgs, { now, hours: 48, addressBookDbs: [ab], exclude: ["+1 (415) 555-0000"] })

  assert.equal(convos.length, 2)
  const [alex, group] = convos
  assert.equal(alex.contact_name, "Alex")
  assert.equal(alex.last_message, "yes! where?")
  assert.equal(alex.last_from, "them")
  assert.equal(alex.unanswered, true)
  assert.equal(alex.unread_from_them, 1)
  assert.equal(alex.messages_in_window, 2)
  assert.equal(alex.last_at, "2026-10-27 11:00")

  assert.equal(group.conversation, "Climbing crew")
  assert.equal(group.is_group, true)
  assert.equal(group.contact_name, null)
  assert.equal(group.last_from, "me")
  assert.equal(group.unanswered, false)
})

test("recentMessages truncates long text", async (t) => {
  const dir = await tmpdir()
  t.after(() => fs.rm(dir, { recursive: true, force: true }))
  const msgs = path.join(dir, "chat.db")
  makeMessages(msgs)
  const db = new DatabaseSync(msgs)
  db.prepare("UPDATE message SET text = ? WHERE ROWID = 4").run("a".repeat(500))
  db.prepare("DELETE FROM message WHERE ROWID = 5").run()
  db.close()
  const convos = await recentMessages(msgs, { now: new Date(2026, 9, 27, 17, 0), addressBookDbs: [], exclude: [] })
  const group = convos.find(c => c.conversation === "Climbing crew")
  assert.equal(group.last_message.length, 201)
})
