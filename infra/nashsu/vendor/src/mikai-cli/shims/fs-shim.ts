// DEVIATION from upstream nashsu (MIKAI-specific).
//
// Overrides @/commands/fs with a Node fs backend so nashsu's ingest
// path can run headless (no Tauri host). Selected via tsconfig-node.json
// path alias.
//
// Coverage strategy:
//   - Re-export nashsu's own `realFs` (from src/test-helpers/fs-temp.ts)
//     for the 8 fs functions their vitest suite already backs with Node.
//   - Fill 5 gap functions using node:fs/promises directly.
//
// Ingest-path callers covered (per Explore audit §2):
//   ingest.ts, ingest-queue.ts, ingest-cache.ts, source-lifecycle.ts,
//   project-identity.ts, extract-source-images.ts, image-caption-pipeline.ts,
//   mineru.ts, parsed-source-output.ts, project-file-tree-refresh.ts,
//   embedding.ts.
//
// Installation: setup.sh copies this file to
//   vendor/src/mikai-cli/shims/fs-shim.ts
// and tsconfig-node.json aliases `@/commands/fs` → `./shims/fs-shim.ts`
// at tsx runtime.

import fs from "node:fs/promises"
import path from "node:path"
import { realFs } from "@/test-helpers/fs-temp"

// ── Re-export the 8 covered functions from nashsu's realFs ────────────
export const readFile = realFs.readFile
export const writeFile = realFs.writeFile
export const listDirectory = realFs.listDirectory
export const copyFile = realFs.copyFile
export const preprocessFile = realFs.preprocessFile
export const deleteFile = realFs.deleteFile
export const fileExists = realFs.fileExists
export const findRelatedWikiPages = realFs.findRelatedWikiPages
export const createDirectory = realFs.createDirectory

// realFs stubs that throw — kept as-is (only reached from createProject
// / openProject paths, which the CLI's autoIngest-direct call doesn't
// trigger).
export const createProject = realFs.createProject
export const openProject = realFs.openProject
export const clipServerStatus = realFs.clipServerStatus

// ── 5 gap fillers using node:fs/promises directly ─────────────────────

export async function getFileModifiedTime(p: string): Promise<number> {
  const stat = await fs.stat(p)
  return stat.mtimeMs
}

export async function getFileSize(p: string): Promise<number> {
  const stat = await fs.stat(p)
  return stat.size
}

// Extension → mime map (small, covers what ingest inspects: images,
// PDFs, text). Extend if a future source type surfaces a gap.
const MIME_BY_EXT: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".pdf": "application/pdf",
  ".txt": "text/plain",
  ".md": "text/markdown",
  ".json": "application/json",
}

function mimeFor(p: string): string {
  const ext = path.extname(p).toLowerCase()
  return MIME_BY_EXT[ext] ?? "application/octet-stream"
}

export async function readFileAsBase64(
  p: string,
): Promise<{ base64: string; mimeType: string }> {
  const buf = await fs.readFile(p)
  return { base64: buf.toString("base64"), mimeType: mimeFor(p) }
}

export async function writeFileBase64(p: string, b64: string): Promise<void> {
  await fs.mkdir(path.dirname(p), { recursive: true })
  await fs.writeFile(p, Buffer.from(b64, "base64"))
}

export async function writeFileAtomic(
  p: string,
  contents: string,
): Promise<void> {
  await fs.mkdir(path.dirname(p), { recursive: true })
  const tmp = `${p}.tmp.${process.pid}.${Date.now()}`
  await fs.writeFile(tmp, contents, "utf-8")
  await fs.rename(tmp, p)
}

// ── Any other exports the ingest tree imports (defensive) ─────────────
// If future audits find more callers, add pass-through wrappers here.

// Explicit signature-preserving re-export shape so IDEs / tsc see the
// same top-level surface as @/commands/fs.
