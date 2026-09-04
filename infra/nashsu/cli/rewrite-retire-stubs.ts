// infra/nashsu/cli/rewrite-retire-stubs.ts
//
// One-shot: find every page with `retired_to: <new-slug>` frontmatter,
// build a redirect map, and rewrite every inbound [[old-slug]] and
// [[dir/old-slug]] wikilink across the vault to point at the new slug.
// Also updates `related:` frontmatter arrays via nashsu's semantics.
//
// Retire stubs stay in place (they're the redirect layer, Wikipedia-style).
// This script only fixes the broken inbound links Fable's audit surfaced.
//
// Usage:
//   npx tsx --tsconfig src/mikai-cli/tsconfig.json src/mikai-cli/rewrite-retire-stubs.ts \
//     --project /Users/briancho/.mikai/wiki-mikai-parallel-test \
//     [--dry-run]
//
// Idempotent: rerunning after all rewrites are applied is a no-op.

import fs from "node:fs/promises"
import path from "node:path"
import { rewriteCrossReferences } from "@/lib/dedup"

interface Args {
  project: string
  dryRun: boolean
}

function parseArgs(argv: string[]): Args {
  const out: Args = { project: "", dryRun: false }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === "--project") out.project = argv[++i]
    else if (a === "--dry-run") out.dryRun = true
    else throw new Error(`unknown flag: ${a}`)
  }
  if (!out.project) throw new Error("--project PATH required")
  return out
}

// Knowledge-page dirs where retire stubs live and where inbound links resolve.
const DIRS = ["concepts", "entities", "wisdom", "goals", "habits", "reflections", "queries", "synthesis"]

async function findRetireStubs(
  projectPath: string,
): Promise<Array<{ dir: string; oldSlug: string; newSlug: string; stubPath: string }>> {
  const stubs: Array<{ dir: string; oldSlug: string; newSlug: string; stubPath: string }> = []
  for (const dir of DIRS) {
    const full = path.join(projectPath, "wiki", dir)
    let entries: string[]
    try {
      entries = await fs.readdir(full)
    } catch {
      continue
    }
    for (const name of entries) {
      if (!name.endsWith(".md")) continue
      const stubPath = path.join(full, name)
      const buf = await fs.readFile(stubPath, "utf-8")
      // Match `retired_to: value` (with optional quotes) in the first
      // ~500 bytes of frontmatter.
      const m = buf.slice(0, 500).match(/^retired_to:\s*["']?([^"'\n]+?)["']?\s*$/m)
      if (!m) continue
      stubs.push({
        dir,
        oldSlug: name.replace(/\.md$/, ""),
        newSlug: m[1].trim(),
        stubPath,
      })
    }
  }
  return stubs
}

// Build the redirect map. rewriteCrossReferences matches literal
// [[oldSlug]] strings, so we register BOTH the bare form and the
// dir-prefixed form (nashsu-generated content uses both, we saw
// both in the vault).
function buildRedirects(
  stubs: Array<{ dir: string; oldSlug: string; newSlug: string }>,
): Map<string, string> {
  const m = new Map<string, string>()
  for (const s of stubs) {
    m.set(s.oldSlug, s.newSlug)
    m.set(`${s.dir}/${s.oldSlug}`, `${s.dir}/${s.newSlug}`)
  }
  return m
}

// Walk every knowledge page and index.md; skip retire stubs themselves
// (they're the source of truth for the redirect target).
async function* walkPages(
  projectPath: string,
  stubPaths: Set<string>,
): AsyncGenerator<string> {
  const wiki = path.join(projectPath, "wiki")
  for (const dir of [...DIRS, "sources"]) {
    const full = path.join(wiki, dir)
    let entries: string[]
    try {
      entries = await fs.readdir(full)
    } catch {
      continue
    }
    for (const name of entries) {
      if (!name.endsWith(".md")) continue
      const p = path.join(full, name)
      if (stubPaths.has(p)) continue
      yield p
    }
  }
  // Also rewrite log.md and index.md if present.
  for (const name of ["log.md", "index.md", "overview.md"]) {
    const p = path.join(wiki, name)
    try {
      await fs.access(p)
      yield p
    } catch {
      // absent, skip
    }
  }
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2))
  const projectPath = path.resolve(args.project)
  const stubs = await findRetireStubs(projectPath)
  console.log(`[rewrite-stubs] found ${stubs.length} retire stubs`)
  for (const s of stubs) {
    console.log(`  ${s.dir}/${s.oldSlug} → ${s.newSlug}`)
  }
  if (stubs.length === 0) return
  const redirects = buildRedirects(stubs)
  const stubPathsSet = new Set(stubs.map((s) => s.stubPath))

  let scanned = 0
  let changed = 0
  const changedPaths: string[] = []
  for await (const p of walkPages(projectPath, stubPathsSet)) {
    scanned++
    const before = await fs.readFile(p, "utf-8")
    const after = rewriteCrossReferences(before, redirects)
    if (after !== before) {
      changed++
      changedPaths.push(path.relative(projectPath, p))
      if (!args.dryRun) {
        await fs.writeFile(p, after, "utf-8")
      }
    }
  }
  const verb = args.dryRun ? "would rewrite" : "rewrote"
  console.log(`[rewrite-stubs] scanned ${scanned} pages, ${verb} ${changed}`)
  for (const rel of changedPaths.slice(0, 30)) {
    console.log(`  - ${rel}`)
  }
  if (changedPaths.length > 30) {
    console.log(`  ... +${changedPaths.length - 30} more`)
  }
}

main().catch((err) => {
  console.error(`[rewrite-stubs] error: ${err instanceof Error ? err.message : String(err)}`)
  process.exit(1)
})
