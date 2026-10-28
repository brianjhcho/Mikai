#!/usr/bin/osascript -l JavaScript
// Read-only Apple Notes export → markdown source pages for MIKAI's wiki.
// Usage: osascript -l JavaScript export-apple-notes.js <out_dir> [limit]
// Writes <out_dir>/<yyyy-mm-dd>-<slug>-<id6>.md; skips locked notes and files
// that already exist (re-runs only add new notes). Never modifies Notes.

ObjC.import("Foundation")

function slugify(s) {
  return (s || "untitled").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "untitled"
}

function yamlString(s) {
  return JSON.stringify(String(s || ""))
}

function isoDate(d) {
  try {
    const p = (n) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
  } catch (e) { return "1970-01-01" }
}

function shortHash(s) {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return ("000000" + h.toString(16)).slice(-6)
}

function exists(path) {
  return $.NSFileManager.defaultManager.fileExistsAtPath(path)
}

function writeFile(path, text) {
  const ok = $(text).writeToFileAtomicallyEncodingError(path, true, $.NSUTF8StringEncoding, null)
  if (!ok) throw new Error("could not write " + path)
}

function run(argv) {
  const outDir = argv[0]
  const limit = argv.length > 1 ? parseInt(argv[1], 10) : 0
  if (!outDir) return "usage: export-apple-notes.js <out_dir> [limit]"
  $.NSFileManager.defaultManager.createDirectoryAtPathWithIntermediateDirectoriesAttributesError(outDir, true, $(), null)

  const Notes = Application("Notes")
  const notes = Notes.notes()
  let written = 0, skipped = 0, locked = 0
  for (let i = 0; i < notes.length; i++) {
    if (limit && written >= limit) break
    const n = notes[i]
    let title, modified, body, id
    try {
      if (n.passwordProtected()) { locked++; continue }
      title = n.name().replace(/^#+\s*/, "").trim() || "untitled"
      modified = n.modificationDate()
      body = n.plaintext()
      id = n.id()
    } catch (e) {
      locked++
      continue
    }
    const date = isoDate(modified)
    const file = `${outDir}/${date}-${slugify(title)}-${shortHash(id)}.md`
    if (exists(file)) { skipped++; continue }
    const page = [
      "---",
      "type: source-summary",
      `title: ${yamlString(title)}`,
      `date: ${date}`,
      `sources: [${yamlString("apple-notes::" + title)}]`,
      "tags: [source, apple-notes]",
      "---",
      "",
      `# ${title}`,
      "",
      body,
      "",
    ].join("\n")
    writeFile(file, page)
    written++
  }
  return `apple-notes export: ${written} written, ${skipped} already present, ${locked} locked/unreadable skipped`
}
