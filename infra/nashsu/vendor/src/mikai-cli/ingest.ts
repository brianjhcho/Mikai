// infra/nashsu/cli/ingest.ts
//
// MIKAI's headless CLI wrapper for nashsu's autoIngest. Runs from Node
// without any Tauri host. Uses the Node-native claude-cli-transport shim
// (installed by setup.sh) so claude -p is spawned directly.
//
// Invocation (from ~/.mikai/vendor/nashsu-llm-wiki after setup.sh):
//   npx tsx src/mikai-cli/ingest.ts --project PATH --workers N [SOURCE...]
//
// If no SOURCE positional args are given, ingests every file under
// PATH/raw/sources/**. Otherwise ingests only the listed sources
// (paths relative to PATH/raw/sources/).
//
// Deviation from upstream nashsu: this file did not exist in
// nashsu/llm_wiki. Authored by MIKAI. Installed into the vendor tree
// at src/mikai-cli/ingest.ts by infra/nashsu/setup.sh.

import fs from "node:fs/promises"
import path from "node:path"
import { spawn } from "node:child_process"
import { autoIngest } from "@/lib/ingest"

// ── Mechanism B: pre-extraction semantic top-K hook ───────────────────
// Before each autoIngest(), spawn pre_extract_topk.py to embed the
// source via Ollama and write the top-K semantically-similar existing
// concept/entity/wisdom slugs into a per-source markdown file. Nashsu's
// ingest.ts reads that file and prepends it to the extraction prompt's
// wiki-index block, so the LLM sees semantic neighbors upfront and
// reuses their slugs instead of coining synonyms (Heaps' law node side).

const PRE_TOPK_SCRIPT = "/Users/briancho/.superset/worktrees/MIKAI/pear-seashore/infra/nashsu/bridge/pre_extract_topk.py"

async function runPreExtractTopK(
  projectPath: string,
  sourceBasename: string,
  topK: number,
): Promise<{ ok: boolean; ms: number; error?: string }> {
  const start = Date.now()
  const sourcePath = path.join(projectPath, "raw", "sources", sourceBasename)
  const outMd = path.join(projectPath, "wiki", ".mikai-neighbors", sourceBasename)
  return new Promise((resolve) => {
    const proc = spawn(
      "python3",
      [
        PRE_TOPK_SCRIPT,
        "--source", sourcePath,
        "--project", projectPath,
        "--out-md", outMd,
        "--top-k", String(topK),
      ],
      { stdio: ["ignore", "pipe", "pipe"] },
    )
    let stderr = ""
    proc.stderr.on("data", (b: Buffer) => { stderr += b.toString() })
    proc.on("close", (code) => {
      resolve({
        ok: code === 0,
        ms: Date.now() - start,
        error: code === 0 ? undefined : (stderr.split("\n")[0] || `exit ${code}`),
      })
    })
    proc.on("error", (err) => {
      resolve({ ok: false, ms: Date.now() - start, error: err.message })
    })
  })
}
// Note: we call autoIngest directly (per-source) rather than going
// through the queue. The queue is designed for a long-running desktop
// app; for a one-shot CLI, direct calls with our own semaphore are
// simpler and expose per-source progress cleanly.

// ── CLI arg parsing (minimal, no dependency) ──────────────────────────

interface Args {
  project: string
  workers: number
  sources: string[]  // positional; empty = glob all
  model: string
  // Ablation flags (2026-09-03) — R8 needs to attribute effects across
  // the three R7 interventions independently. Each flag disables exactly
  // one intervention; combine as needed for factorial runs.
  noTopk: boolean            // skip runPreExtractTopK → no Mechanism B
  noIndex: boolean           // skip refreshCanonicalDirectory → LLM sees only rolling 200 entries
  noSlugDiscipline: boolean  // sets MIKAI_NO_SLUG_DISCIPLINE=1 → vendor prompt drops SLUG DISCIPLINE blocks
}

function parseArgs(argv: string[]): Args {
  const out: Args = {
    project: "",
    workers: 1,
    sources: [],
    model: "claude-sonnet-4-5",  // MIKAI default; overridable via --model
    noTopk: false,
    noIndex: false,
    noSlugDiscipline: false,
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === "--project") {
      out.project = argv[++i]
    } else if (a === "--workers") {
      out.workers = parseInt(argv[++i], 10) || 1
    } else if (a === "--model") {
      out.model = argv[++i]
    } else if (a === "--no-topk") {
      out.noTopk = true
    } else if (a === "--no-index") {
      out.noIndex = true
    } else if (a === "--no-slug-discipline") {
      out.noSlugDiscipline = true
    } else if (a.startsWith("--")) {
      throw new Error(`unknown flag: ${a}`)
    } else {
      out.sources.push(a)
    }
  }
  if (!out.project) throw new Error("--project PATH required")
  return out
}

// ── Canonical directory refresh ───────────────────────────────────────
//
// Nashsu's extraction prompt already reads wiki/index.md and instructs
// the LLM to check for existing content. But nashsu only maintains the
// rolling "## Recently Updated" section (bounded to 200 entries), so a
// vault with 700+ concepts leaves ~70% invisible to the LLM — which
// then coins duplicate slugs (`asymmetric-information` vs the existing
// `information-asymmetry`). Fixing that is the "link-at-birth" lever
// Fable's CTO analysis called load-bearing for Heaps' law.
//
// We fix it inside nashsu's own pattern: write comprehensive
// "## All Concepts" / "## All Entities" / "## All Wisdom" sections
// BEFORE "## Recently Updated" in index.md, so nashsu's per-source
// updater (which only touches Recently Updated, preserving prefix)
// leaves them intact. Refresh once at CLI startup — a source completing
// mid-run won't yet appear to concurrent workers, but that's acceptable
// for a workers=8 run against a bounded backlog.

interface DirectoryEntry {
  slug: string   // e.g. "concepts/intent-graph"
  title: string  // human-readable, from frontmatter
}

const CANONICAL_DIRS: Array<{ dir: string; heading: string }> = [
  { dir: "concepts", heading: "All Concepts" },
  { dir: "entities", heading: "All Entities" },
  { dir: "wisdom", heading: "All Wisdom" },
]

async function readFrontmatterTitle(filePath: string): Promise<string | null> {
  try {
    const buf = await fs.readFile(filePath, "utf-8")
    if (!buf.startsWith("---\n")) return null
    const end = buf.indexOf("\n---\n", 4)
    if (end < 0) return null
    const fm = buf.slice(4, end)
    // Skip retired pages — they're redirects, don't advertise them
    if (/^retired_to\s*:/m.test(fm)) return null
    const m = fm.match(/^title:\s*["']?(.+?)["']?\s*$/m)
    return m ? m[1].trim() : null
  } catch {
    return null
  }
}

async function collectDirectory(projectPath: string, dir: string): Promise<DirectoryEntry[]> {
  const full = path.join(projectPath, "wiki", dir)
  let entries: string[]
  try {
    entries = await fs.readdir(full)
  } catch {
    return []
  }
  const out: DirectoryEntry[] = []
  for (const name of entries) {
    if (!name.endsWith(".md")) continue
    const slug = name.replace(/\.md$/, "")
    const title = await readFrontmatterTitle(path.join(full, name)) ?? slug
    out.push({ slug: `${dir}/${slug}`, title })
  }
  out.sort((a, b) => a.slug.localeCompare(b.slug))
  return out
}

function stripCanonicalSections(index: string): string {
  // Remove any previously-written "## All *" sections we own; nashsu's
  // per-source writer only touches "## Recently Updated", so anything
  // between our headings and the next "## " boundary is ours to rewrite.
  const lines = index.split("\n")
  const out: string[] = []
  let skipping = false
  for (const line of lines) {
    if (/^##\s+All\s+/.test(line)) {
      skipping = true
      continue
    }
    if (skipping && /^##\s+/.test(line)) {
      skipping = false
    }
    if (!skipping) out.push(line)
  }
  return out.join("\n")
}

async function refreshCanonicalDirectory(projectPath: string): Promise<{
  sections: number
  totalEntries: number
}> {
  const indexPath = path.join(projectPath, "wiki", "index.md")
  let existing = ""
  try {
    existing = await fs.readFile(indexPath, "utf-8")
  } catch {
    existing = "# Wiki Index\n"
  }
  const stripped = stripCanonicalSections(existing)

  const sections: string[] = []
  let totalEntries = 0
  for (const { dir, heading } of CANONICAL_DIRS) {
    const rows = await collectDirectory(projectPath, dir)
    if (rows.length === 0) continue
    totalEntries += rows.length
    sections.push(`## ${heading}`)
    for (const r of rows) sections.push(`- [[${r.slug}]] — ${r.title}`)
    sections.push("")
  }
  if (sections.length === 0) return { sections: 0, totalEntries: 0 }

  // Insert canonical sections BEFORE "## Recently Updated" (or at end if
  // Recently Updated doesn't exist yet). Nashsu's updater treats anything
  // before Recently Updated as prefix and preserves it verbatim.
  const rxRecent = /^##\s+Recently Updated\s*$/m
  const marker = stripped.match(rxRecent)
  let next: string
  if (marker) {
    const before = stripped.slice(0, marker.index).trimEnd()
    const after = stripped.slice(marker.index)
    next = `${before}\n\n${sections.join("\n")}\n${after}`
  } else {
    next = `${stripped.trimEnd()}\n\n${sections.join("\n")}\n`
  }
  await fs.mkdir(path.dirname(indexPath), { recursive: true })
  await fs.writeFile(indexPath, next, "utf-8")
  return { sections: CANONICAL_DIRS.length, totalEntries }
}

// ── Source enumeration ────────────────────────────────────────────────

async function listSources(rawSourcesDir: string): Promise<string[]> {
  const out: string[] = []
  async function walk(dir: string, relPrefix: string): Promise<void> {
    const entries = await fs.readdir(dir, { withFileTypes: true })
    for (const e of entries) {
      const p = path.join(dir, e.name)
      const rel = relPrefix ? `${relPrefix}/${e.name}` : e.name
      if (e.isDirectory()) {
        await walk(p, rel)
      } else if (e.isFile() && e.name.endsWith(".md")) {
        out.push(rel)
      }
    }
  }
  await walk(rawSourcesDir, "")
  return out
}

// ── Concurrency semaphore ─────────────────────────────────────────────

function makeSemaphore(limit: number): (fn: () => Promise<void>) => Promise<void> {
  let active = 0
  const queue: Array<() => void> = []
  const acquire = (): Promise<void> =>
    new Promise((resolve) => {
      if (active < limit) {
        active++
        resolve()
      } else {
        queue.push(() => {
          active++
          resolve()
        })
      }
    })
  const release = (): void => {
    active--
    const next = queue.shift()
    if (next) next()
  }
  return async (fn) => {
    await acquire()
    try {
      await fn()
    } finally {
      release()
    }
  }
}

// ── LlmConfig for claude-code provider ────────────────────────────────

function makeLlmConfig(model: string): any {
  return {
    provider: "claude-code",
    apiKey: "",  // not used by claude-code provider
    model,
    customEndpoint: "",
    apiMode: "chat_completions",
    azureApiVersion: "",
    ollamaUrl: "",
    maxContextSize: 200_000,  // Sonnet capacity
    requestTimeoutMinutes: 30,
    streamingEnabled: true,
    localCliIsolation: false,
    // Fields the shim doesn't read but the type may require
    chatPresetId: "",
    ingestPresetId: "",
  }
}

// ── Main ──────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2))
  const projectPath = path.resolve(args.project)

  // Sanity-check the project layout
  const rawSourcesDir = path.join(projectPath, "raw", "sources")
  try {
    await fs.access(rawSourcesDir)
  } catch {
    throw new Error(`project missing raw/sources/ at ${rawSourcesDir}`)
  }

  // Enumerate sources
  const sources = args.sources.length > 0
    ? args.sources
    : await listSources(rawSourcesDir)
  if (sources.length === 0) {
    console.error("no sources to ingest")
    process.exit(0)
  }

  // chdir so the claude-code transport (which reads process.cwd()) uses
  // the project as its working directory.
  process.chdir(projectPath)

  const llmConfig = makeLlmConfig(args.model)
  const sem = makeSemaphore(args.workers)

  // Ablation: --no-slug-discipline propagates via env var so the vendor
  // buildAnalysisPrompt / buildGenerationPrompt can conditionally drop
  // the SLUG DISCIPLINE blocks. Vendor reads process.env.MIKAI_NO_SLUG_DISCIPLINE.
  if (args.noSlugDiscipline) {
    process.env.MIKAI_NO_SLUG_DISCIPLINE = "1"
  }

  const t0 = Date.now()
  let done = 0
  const failures: Array<{ source: string; error: string }> = []
  const results: Array<{ source: string; written: string[] }> = []

  const ablationNote = [
    args.noTopk ? "no-topk" : "",
    args.noIndex ? "no-index" : "",
    args.noSlugDiscipline ? "no-slug-discipline" : "",
  ].filter(Boolean).join(",") || "none"
  console.log(`[nashsu-cli] project=${projectPath}`)
  console.log(`[nashsu-cli] workers=${args.workers} model=${args.model} ablation=${ablationNote}`)
  console.log(`[nashsu-cli] sources=${sources.length}`)

  // Refresh canonical directory sections in wiki/index.md BEFORE the
  // source loop starts. Nashsu's extraction prompt already reads
  // index.md and asks the LLM to check for existing content; by making
  // the directory comprehensive we complete the link-at-birth loop.
  // --no-index skips this refresh so LLM sees only the rolling 200-entry
  // "Recently Updated" section. Existing All-X sections in index.md are
  // NOT stripped by this flag; strip them by hand before the run for a
  // clean ablation baseline.
  if (args.noIndex) {
    console.log(`[nashsu-cli] canonical directory refresh SKIPPED (--no-index)`)
  } else {
    const dirRefresh = await refreshCanonicalDirectory(projectPath)
    console.log(
      `[nashsu-cli] canonical directory refreshed: ${dirRefresh.sections} sections, ${dirRefresh.totalEntries} entries`,
    )
  }

  await Promise.all(
    sources.map((relSource) =>
      sem(async () => {
        const start = Date.now()
        try {
          // Mechanism B: pre-extraction semantic top-K. Populates
          // wiki/.mikai-neighbors/<source>.md; nashsu's ingest.ts reads
          // it and prepends to the extraction prompt. Graceful-degrade:
          // if this fails (Ollama down, cache empty, etc.), extraction
          // still runs with lexical-only slug guidance. --no-topk skips
          // it entirely (also skips neighbor-file write, so vendor's
          // readFile(neighborsPath).catch(() => "") returns empty).
          const topKResult = args.noTopk
            ? { ok: true as const, ms: 0, error: undefined as string | undefined }
            : await runPreExtractTopK(projectPath, relSource, 40)
          if (!args.noTopk && !topKResult.ok) {
            console.warn(
              `[nashsu-cli] pre-topk WARN ${relSource}: ${topKResult.error} (${topKResult.ms}ms)`,
            )
          }
          const written = await autoIngest(
            projectPath,
            path.join("raw", "sources", relSource),
            llmConfig,
          )
          // Per-page enrichWithWikilinks removed 2026-09-02 per Fable audit:
          // it fires one extra `claude -p` per written page doing what SLUG
          // DISCIPLINE in buildGenerationPrompt already asks for, and was the
          // dominant cost/fragility multiplier of the R7 stack. If page-level
          // link density needs a boost later, run a batched offline sweep
          // instead of per-ingest.
          const dt = ((Date.now() - start) / 1000).toFixed(1)
          done++
          results.push({ source: relSource, written })
          const topKNote = args.noTopk
            ? ` (topk: OFF)`
            : (topKResult.ok ? ` (topk: ${topKResult.ms}ms)` : ` (topk: FAIL)`)
          console.log(
            `[nashsu-cli] OK  [${done}/${sources.length}] ${relSource}  ${dt}s → ${written.length} files${topKNote}`,
          )
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          done++
          failures.push({ source: relSource, error: msg })
          console.error(
            `[nashsu-cli] ERR [${done}/${sources.length}] ${relSource}\n${msg}\n[nashsu-cli] --end err--`,
          )
        }
      }),
    ),
  )

  const totalDt = ((Date.now() - t0) / 1000).toFixed(1)
  console.log("")
  console.log(`[nashsu-cli] complete in ${totalDt}s`)
  console.log(`[nashsu-cli]   succeeded: ${results.length}/${sources.length}`)
  console.log(`[nashsu-cli]   failed:    ${failures.length}`)
  const totalWritten = results.reduce((n, r) => n + r.written.length, 0)
  console.log(`[nashsu-cli]   wiki files written: ${totalWritten}`)
  if (failures.length > 0) {
    console.log("")
    console.log("[nashsu-cli] failures:")
    for (const f of failures) {
      console.log(`  - ${f.source}:\n${f.error}\n`)
    }
  }
}

main().catch((err) => {
  console.error("[nashsu-cli] FATAL:", err instanceof Error ? err.stack : err)
  process.exit(1)
})
