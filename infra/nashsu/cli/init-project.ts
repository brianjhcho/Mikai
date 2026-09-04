// infra/nashsu/cli/init-project.ts
//
// Bootstrap a fresh nashsu project directory from a template.
// Writes purpose.md + schema.md, creates the standard raw/ + wiki/
// subdirectories, and any template-specific extra dirs.
//
// Usage (from ~/.mikai/vendor/nashsu-llm-wiki after setup.sh):
//   npx tsx src/mikai-cli/init-project.ts \
//     --project ~/.mikai/wiki-golden \
//     --template personal
//
// Templates available (from src/lib/templates.ts):
//   research | reading | personal | business | general
//
// Deviation: this file did not exist in nashsu; MIKAI-authored.
// Installed into vendor at src/mikai-cli/init-project.ts by setup.sh.

import fs from "node:fs/promises"
import path from "node:path"
import { getTemplate } from "@/lib/templates"

interface Args {
  project: string
  template: string
  force: boolean
}

function parseArgs(argv: string[]): Args {
  const out: Args = { project: "", template: "personal", force: false }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === "--project") out.project = argv[++i]
    else if (a === "--template") out.template = argv[++i]
    else if (a === "--force") out.force = true
    else throw new Error(`unknown flag: ${a}`)
  }
  if (!out.project) throw new Error("--project PATH required")
  return out
}

const BASE_DIRS = [
  "raw/sources",
  "raw/assets",
  "wiki/entities",
  "wiki/concepts",
  "wiki/sources",
  "wiki/queries",
  "wiki/synthesis",
  "wiki/comparisons",
  "wiki/media",
]

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2))
  const projectPath = path.resolve(args.project)

  // Check if project already initialized
  const purposeExists = await fs
    .access(path.join(projectPath, "purpose.md"))
    .then(() => true)
    .catch(() => false)
  if (purposeExists && !args.force) {
    throw new Error(`project already initialized at ${projectPath} (use --force to overwrite)`)
  }

  const template = getTemplate(args.template)
  console.log(`[init] template = ${template.name} (${template.id}) ${template.icon}`)

  // Create dirs
  const allDirs = [...BASE_DIRS, ...(template.extraDirs ?? [])]
  for (const d of allDirs) {
    await fs.mkdir(path.join(projectPath, d), { recursive: true })
  }
  console.log(`[init] created ${allDirs.length} directories`)

  // Write purpose.md + schema.md
  await fs.writeFile(path.join(projectPath, "purpose.md"), template.purpose, "utf-8")
  await fs.writeFile(path.join(projectPath, "schema.md"), template.schema, "utf-8")
  console.log(`[init] wrote purpose.md (${template.purpose.length} chars)`)
  console.log(`[init] wrote schema.md  (${template.schema.length} chars)`)

  console.log("")
  console.log(`[init] project ready at ${projectPath}`)
  console.log(`[init] next: bridge sources into raw/sources/, then run ingest.ts`)
}

main().catch((err) => {
  console.error("[init] FATAL:", err instanceof Error ? err.message : err)
  process.exit(1)
})
