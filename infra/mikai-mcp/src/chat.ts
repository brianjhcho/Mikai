// chat.ts — RAG chat: semantic top-K → claude -p answer.
// Subscription-safe (uses `claude -p`, same as MIKAI's ingest path).

import { spawn } from "node:child_process"
import fs from "node:fs/promises"
import { Vault } from "./vault.js"
import { semanticSearch, SearchResult } from "./search.js"

const DEFAULT_MODEL = process.env.MIKAI_CHAT_MODEL ?? "claude-sonnet-4-5"
const DEFAULT_TIMEOUT_MS = 240_000

export interface ChatResult {
  answer: string
  sources: Array<{ slug: string; kind: string; title: string; cosine: number }>
  model: string
  elapsed_ms: number
  error?: string
}

function callClaude(prompt: string, model: string, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn("claude", ["-p", "--model", model, "--output-format", "json"], {
      stdio: ["pipe", "pipe", "pipe"],
    })
    let stdout = ""
    let stderr = ""
    const timer = setTimeout(() => {
      proc.kill("SIGTERM")
      reject(new Error(`claude -p timeout after ${timeoutMs}ms`))
    }, timeoutMs)
    proc.stdout.on("data", (b: Buffer) => { stdout += b.toString() })
    proc.stderr.on("data", (b: Buffer) => { stderr += b.toString() })
    proc.on("close", (code) => {
      clearTimeout(timer)
      if (code !== 0) {
        reject(new Error(`claude -p exit ${code}: ${stderr.slice(0, 400)}`))
        return
      }
      try {
        const outer = JSON.parse(stdout)
        resolve(outer.result ?? "")
      } catch (e) {
        reject(new Error(`parse: ${(e as Error).message}`))
      }
    })
    proc.on("error", err => {
      clearTimeout(timer)
      reject(err)
    })
    proc.stdin.write(prompt)
    proc.stdin.end()
  })
}

export async function chat(
  vault: Vault,
  question: string,
  options: { topK?: number; kinds?: string[]; model?: string } = {},
): Promise<ChatResult> {
  const start = Date.now()
  const topK = options.topK ?? 8
  const model = options.model ?? DEFAULT_MODEL
  const results = await semanticSearch(vault, question, { limit: topK, kinds: options.kinds })

  if (results.length === 0) {
    return {
      answer: "No relevant pages found in the vault for this query.",
      sources: [],
      model,
      elapsed_ms: Date.now() - start,
    }
  }

  // Load full bodies for top-K
  const context: string[] = []
  for (const r of results) {
    const page = await vault.readPage(r.kind, r.slug, true)
    if (!page) continue
    const body = page.body.length > 2500 ? page.body.slice(0, 2500) + "\n[...truncated...]" : page.body
    context.push(`## ${r.kind}/${r.slug} — ${r.title} (cosine ${r.cosine})\n\n${body}`)
  }

  const prompt = [
    "You are answering a question using ONLY the wiki excerpts below. Cite specific pages via [[kind/slug]] wikilinks. If the excerpts don't contain the answer, say so — do not fabricate.",
    "",
    "## Wiki excerpts (top-" + results.length + " by semantic similarity)",
    "",
    context.join("\n\n---\n\n"),
    "",
    "## Question",
    question,
    "",
    "## Answer",
    "(1-4 paragraphs; cite pages inline via [[kind/slug]])",
  ].join("\n")

  try {
    const answer = await callClaude(prompt, model, DEFAULT_TIMEOUT_MS)
    return {
      answer: answer.trim(),
      sources: results.map(r => ({ slug: r.slug, kind: r.kind, title: r.title, cosine: r.cosine })),
      model,
      elapsed_ms: Date.now() - start,
    }
  } catch (e) {
    return {
      answer: "",
      sources: results.map(r => ({ slug: r.slug, kind: r.kind, title: r.title, cosine: r.cosine })),
      model,
      elapsed_ms: Date.now() - start,
      error: (e as Error).message,
    }
  }
}
