// infra/nashsu/cli/dedup.ts
//
// MIKAI's headless CLI wrapper for nashsu's native dedup pipeline. Runs
// from Node without any Tauri host, mirroring infra/nashsu/cli/ingest.ts:
// same tsx + Node-native claude-cli-transport + tsconfig path shims.
//
// Invocation (from ~/.mikai/vendor/nashsu-llm-wiki after setup.sh):
//   npx tsx src/mikai-cli/dedup.ts --project PATH [--apply]
//     [--threshold 0.68] [--top-k 8] [--max-pages 5000]
//     [--report /path/report.md] [--model claude-sonnet-4-5]
//
// Without --apply: report-only (writes candidate groups to --report).
// With --apply: also runs executeMerge on every detected group, using
// the desktop UI's own default canonical choice (group.slugs[0] — see
// maintenance-section.tsx) since DuplicateGroup carries no suggestion.
//
// --threshold/--top-k/--max-pages map to nashsu's embedding-prefilter
// constants (DEDUP_PREFILTER_THRESHOLD/TOP_K/MAX_PAGES in dedup-runner.ts),
// but that prefilter requires a real Tauri host: it reads embedding
// config via @tauri-apps/plugin-store and fetches embeddings through the
// Rust `embedding_fetch` command, neither of which the CLI's shims
// implement (confirmed empirically: loadEmbeddingConfig() throws "window
// is not defined" headlessly). runDuplicateDetection() is called first
// so this activates for free if MIKAI ever ships a Node embedding
// transport; until then it always falls back to nashsu's non-prefiltered
// full LLM scan, and these three flags are accepted but have no effect —
// a warning is printed if any are passed.
//
// Deviation from upstream nashsu: this file did not exist in
// nashsu/llm_wiki. Authored by MIKAI. Installed into the vendor tree
// at src/mikai-cli/dedup.ts by infra/nashsu/setup.sh.

import fs from "node:fs/promises"
import path from "node:path"
import {
  runDuplicateDetection,
  executeMerge,
  loadAllEntitySummaries,
  buildDedupLlmCall,
} from "@/lib/dedup-runner"
import { detectDuplicateGroups, type DuplicateGroup, type MergeResult } from "@/lib/dedup"
import { loadNotDuplicates } from "@/lib/dedup-storage"
import type { LlmConfig } from "@/stores/wiki-store"

// Mirrors dedup-runner.ts's internal (unexported) DEDUP_DETECTION_MAX_TOKENS —
// only needed here for the headless fallback path (see detectGroups below).
const DEDUP_DETECTION_MAX_TOKENS = 8_192

// ── CLI arg parsing (minimal, no dependency) ──────────────────────────

interface Args {
  project: string
  apply: boolean
  threshold?: number
  topK?: number
  maxPages?: number
  report: string
  model: string
}

function parseArgs(argv: string[]): Args {
  const out: Args = {
    project: "",
    apply: false,
    report: `/tmp/dedup-report-${Date.now()}.md`,
    model: "claude-sonnet-4-5", // MIKAI default; overridable via --model
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === "--project") {
      out.project = argv[++i]
    } else if (a === "--apply") {
      out.apply = true
    } else if (a === "--threshold") {
      out.threshold = parseFloat(argv[++i])
    } else if (a === "--top-k") {
      out.topK = parseInt(argv[++i], 10)
    } else if (a === "--max-pages") {
      out.maxPages = parseInt(argv[++i], 10)
    } else if (a === "--report") {
      out.report = argv[++i]
    } else if (a === "--model") {
      out.model = argv[++i]
    } else {
      throw new Error(`unknown flag: ${a}`)
    }
  }
  if (!out.project) throw new Error("--project PATH required")
  return out
}

// ── LlmConfig for claude-code provider (mirrors ingest.ts) ────────────

function makeLlmConfig(model: string): any {
  return {
    provider: "claude-code",
    apiKey: "",
    model,
    customEndpoint: "",
    apiMode: "chat_completions",
    azureApiVersion: "",
    ollamaUrl: "",
    maxContextSize: 200_000,
    requestTimeoutMinutes: 30,
    streamingEnabled: true,
    localCliIsolation: false,
    chatPresetId: "",
    ingestPresetId: "",
  }
}

// ── Detection with headless-safe fallback ──────────────────────────────

async function detectGroups(
  projectPath: string,
  llmConfig: LlmConfig,
): Promise<DuplicateGroup[]> {
  try {
    return await runDuplicateDetection(projectPath, llmConfig, {})
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(
      `[dedup-cli] embedding-prefiltered detection unavailable headlessly (${msg}); ` +
        `falling back to nashsu's full LLM scan (no prefilter)`,
    )
    const summaries = await loadAllEntitySummaries(projectPath)
    if (summaries.length < 2) return []
    const notDuplicates = await loadNotDuplicates(projectPath)
    const llm = buildDedupLlmCall(llmConfig, DEDUP_DETECTION_MAX_TOKENS)
    return detectDuplicateGroups(summaries, llm, { notDuplicates })
  }
}

// ── Report ───────────────────────────────────────────────────────────

function renderReport(
  groups: DuplicateGroup[],
  applied: Map<number, { ok: true; result: MergeResult } | { ok: false; error: string }>,
): string {
  const lines: string[] = [
    "# Dedup report",
    "",
    `Generated ${new Date().toISOString()}`,
    `${groups.length} candidate duplicate group(s) found.`,
    "",
  ]
  groups.forEach((g, i) => {
    const canonicalSlug = g.slugs[0] // matches desktop default (maintenance-section.tsx)
    lines.push(`## Group ${i + 1}: ${g.slugs.join(", ")}`)
    lines.push("")
    lines.push(`- confidence: ${g.confidence}`)
    lines.push(`- suggested canonical: \`${canonicalSlug}\``)
    lines.push(`- reason: ${g.reason}`)
    const outcome = applied.get(i)
    if (outcome) {
      lines.push(
        outcome.ok
          ? `- merge: OK → ${outcome.result.canonicalPath} (deleted ${outcome.result.pagesToDelete.length} page(s))`
          : `- merge: FAILED — ${outcome.error}`,
      )
    }
    lines.push("")
  })
  return lines.join("\n")
}

// ── Main ─────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2))
  const projectPath = path.resolve(args.project)

  if (args.threshold !== undefined || args.topK !== undefined || args.maxPages !== undefined) {
    console.warn(
      "[dedup-cli] --threshold/--top-k/--max-pages have no effect headlessly: " +
        "nashsu's embedding prefilter requires a Tauri host (see file header comment)",
    )
  }

  process.chdir(projectPath)

  const llmConfig = makeLlmConfig(args.model)

  console.log(`[dedup-cli] project=${projectPath}`)
  console.log(`[dedup-cli] model=${args.model} apply=${args.apply}`)

  const groups = await detectGroups(projectPath, llmConfig)
  console.log(`[dedup-cli] detected ${groups.length} candidate duplicate group(s)`)

  const applied = new Map<number, { ok: true; result: MergeResult } | { ok: false; error: string }>()
  let failures = 0

  if (args.apply) {
    for (let i = 0; i < groups.length; i++) {
      const group = groups[i]
      const canonicalSlug = group.slugs[0]
      try {
        const result = await executeMerge(projectPath, group, canonicalSlug, llmConfig, {})
        applied.set(i, { ok: true, result })
        console.log(
          `[dedup-cli] OK  [${i + 1}/${groups.length}] ${group.slugs.join(",")} → ${canonicalSlug}`,
        )
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        applied.set(i, { ok: false, error: msg })
        failures++
        console.error(
          `[dedup-cli] ERR [${i + 1}/${groups.length}] ${group.slugs.join(",")}: ${msg}`,
        )
      }
    }
  }

  const reportPath = path.resolve(args.report)
  await fs.mkdir(path.dirname(reportPath), { recursive: true })
  await fs.writeFile(reportPath, renderReport(groups, applied), "utf-8")
  console.log(`[dedup-cli] report written to ${reportPath}`)

  console.log("")
  console.log(
    `[dedup-cli] complete: ${groups.length} group(s) found` +
      (args.apply ? `, ${applied.size - failures} merged, ${failures} failed` : " (report-only)"),
  )

  if (failures > 0) process.exit(1)
}

main().catch((err) => {
  console.error("[dedup-cli] FATAL:", err instanceof Error ? err.stack : err)
  process.exit(1)
})
