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
//   research | reading | personal | mikai | business | general
// (mikai is MIKAI's own template — Personal Growth + wisdom page type;
//  added Session-7, 2026-08-20)
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

// Port of nashsu's Rust seeding in src-tauri/src/commands/project.rs L196-235.
// Desktop app writes these three files on project creation; the Rust path is
// unreachable in headless mode, so mirror them here verbatim.
const OBSIDIAN_APP_JSON = `{
  "attachmentFolderPath": "raw/assets",
  "userIgnoreFilters": [
    ".cache",
    ".llm-wiki",
    ".superpowers"
  ],
  "useMarkdownLinks": false,
  "newLinkFormat": "shortest",
  "showUnsupportedFiles": false
}`

const OBSIDIAN_APPEARANCE_JSON = `{
  "baseFontSize": 16,
  "theme": "obsidian"
}`

const OBSIDIAN_CORE_PLUGINS_JSON = `{
  "file-explorer": true,
  "global-search": true,
  "graph": true,
  "backlink": true,
  "tag-pane": true,
  "page-preview": true,
  "outgoing-link": true,
  "starred": true
}`

// MIKAI deviation (2026-08-25, Session-8): seed graph filter that
// excludes log.md and index.md from Obsidian's default graph view.
// Both files exist as navigational aggregates linking to nearly every
// wiki page — without this filter they become the graph's mega-hubs
// and drown out the actual thematic clustering the user wants to see.
const OBSIDIAN_GRAPH_JSON = `{
  "collapse-filter": false,
  "search": "-path:index.md -path:log.md",
  "showTags": false,
  "showAttachments": false,
  "hideUnresolved": false,
  "showOrphans": true,
  "collapse-color-groups": false,
  "colorGroups": [
    {"query": "path:wisdom/", "color": {"a": 1, "rgb": 16749614}},
    {"query": "path:concepts/", "color": {"a": 1, "rgb": 5431518}},
    {"query": "path:entities/", "color": {"a": 1, "rgb": 14701138}},
    {"query": "path:sources/", "color": {"a": 1, "rgb": 8421504}},
    {"query": "path:queries/", "color": {"a": 1, "rgb": 15773696}},
    {"query": "path:journal/", "color": {"a": 1, "rgb": 4494319}}
  ],
  "collapse-display": true,
  "showArrow": false,
  "textFadeMultiplier": 0,
  "nodeSizeMultiplier": 1,
  "lineSizeMultiplier": 1,
  "collapse-forces": true,
  "centerStrength": 0.518713248970312,
  "repelStrength": 10,
  "linkStrength": 1,
  "linkDistance": 250,
  "scale": 1,
  "close": true
}`

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

  // Seed .obsidian/ config for Obsidian compatibility (mirrors Rust
  // src-tauri/src/commands/project.rs L196-235 which is unreachable
  // in headless mode).
  const obsidianDir = path.join(projectPath, ".obsidian")
  await fs.mkdir(obsidianDir, { recursive: true })
  await fs.writeFile(path.join(obsidianDir, "app.json"), OBSIDIAN_APP_JSON, "utf-8")
  await fs.writeFile(path.join(obsidianDir, "appearance.json"), OBSIDIAN_APPEARANCE_JSON, "utf-8")
  await fs.writeFile(path.join(obsidianDir, "core-plugins.json"), OBSIDIAN_CORE_PLUGINS_JSON, "utf-8")
  await fs.writeFile(path.join(obsidianDir, "graph.json"), OBSIDIAN_GRAPH_JSON, "utf-8")
  console.log(`[init] seeded .obsidian/ (app.json + appearance.json + core-plugins.json + graph.json with log/index filter + type-color groups)`)

  console.log("")
  console.log(`[init] project ready at ${projectPath}`)
  console.log(`[init] next: bridge sources into raw/sources/, then run ingest.ts`)
}

main().catch((err) => {
  console.error("[init] FATAL:", err instanceof Error ? err.message : err)
  process.exit(1)
})
