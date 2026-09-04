// DEVIATION from upstream nashsu/llm_wiki (MIKAI-specific).
//
// Original: src/lib/claude-cli-transport.ts — spawns `claude -p` via Rust
// IPC (Tauri invoke("claude_cli_spawn"), events emitted as claude-cli:{id}).
// This replacement: same exported interface, but spawns directly through
// Node's child_process. Removes the Rust dependency so nashsu's ingest
// runs headless from Node without a Tauri host.
//
// The exports (createClaudeCodeStreamParser, streamClaudeCodeCli,
// buildExitError) match the original signatures exactly. llm-client.ts's
// dynamic import at line 41 works unchanged after this file is copied
// into ~/.mikai/vendor/nashsu-llm-wiki/src/lib/claude-cli-transport.ts.
//
// Installation: run `infra/nashsu/setup.sh` — it copies this file into
// the vendor dir. See infra/nashsu/patches/README.md for reproducibility.
//
// Working directory: uses process.cwd() rather than
// useWikiStore.getState().project?.path (which requires Zustand + React
// context). CLI wrapper must chdir to the project root before invoking
// autoIngest.
//
// Auth: strips ANTHROPIC_API_KEY from child env so `claude -p` falls
// through to Max subscription auth (per MIKAI memory
// [[anthropic-subscription-auth-policy]] — API keys reserved for future).

import { spawn } from "node:child_process"
import type { LlmConfig } from "@/stores/wiki-store"
import type { ChatMessage, RequestOverrides } from "./llm-providers"
import type { StreamCallbacks } from "./llm-client"

// ── Content-block helpers (mirror Rust claude_content_* helpers) ─────

type ImageBlock = { type: "image"; mediaType: string; dataBase64: string }
type TextBlock = { type: "text"; text: string }
type ContentBlock = TextBlock | ImageBlock

function contentTextOnly(content: string | ContentBlock[]): string {
  if (typeof content === "string") return content
  return content
    .filter((b): b is TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("")
}

function contentBlocks(content: string | ContentBlock[]): unknown[] {
  if (typeof content === "string") return [{ type: "text", text: content }]
  return content.map((b) => {
    if (b.type === "text") return { type: "text", text: b.text }
    if (b.type === "image") {
      return {
        type: "image",
        source: { type: "base64", media_type: b.mediaType, data: b.dataBase64 },
      }
    }
    return b
  })
}

function mergeSystemIntoFirstUser(blocks: unknown[], preamble: string): unknown[] {
  return [{ type: "text", text: preamble }, ...blocks]
}

// ── Stream parser — pure JS, copied verbatim from upstream ───────────

export function createClaudeCodeStreamParser() {
  let sawDelta = false
  let emittedFromAssistant = ""

  return function parseLine(rawLine: string): string | null {
    const line = rawLine.trim()
    if (!line) return null

    let evt: unknown
    try {
      evt = JSON.parse(line)
    } catch {
      return null
    }
    if (!evt || typeof evt !== "object") return null
    const obj = evt as Record<string, unknown>
    const type = obj.type

    // Real streaming deltas via --verbose passthrough
    if (type === "stream_event") {
      const event = obj.event as Record<string, unknown> | undefined
      if (event?.type === "content_block_delta") {
        const delta = event.delta as Record<string, unknown> | undefined
        if (delta?.type === "text_delta" && typeof delta.text === "string") {
          sawDelta = true
          return delta.text
        }
      }
      return null
    }

    // Full assistant message — emit only the delta beyond what deltas showed
    if (type === "assistant") {
      if (sawDelta) return null
      const message = obj.message as Record<string, unknown> | undefined
      const content = message?.content as Array<Record<string, unknown>> | undefined
      if (!content) return null
      const fullText = content
        .filter((c) => c.type === "text")
        .map((c) => String(c.text ?? ""))
        .join("")
      if (fullText.length <= emittedFromAssistant.length) return null
      const chunk = fullText.slice(emittedFromAssistant.length)
      emittedFromAssistant = fullText
      return chunk
    }

    return null
  }
}

// ── Error formatting ─────────────────────────────────────────────────

export function buildExitError(code: number, stderr: string, unparsedStdout: string): string {
  const parts: string[] = [`claude -p exited with code ${code}`]
  if (stderr) parts.push(`stderr:\n${stderr}`)
  if (unparsedStdout) parts.push(`unparsed stdout:\n${unparsedStdout}`)
  return parts.join("\n\n")
}

// ── CLI argument construction (matches build_claude_cli_args in Rust) ─

function buildArgs(model: string, isolateLocalConfig: boolean): string[] {
  const args = [
    "-p",
    "--output-format",
    "stream-json",
    "--input-format",
    "stream-json",
    "--verbose",
  ]
  if (isolateLocalConfig) {
    args.push("--setting-sources", "project")
  }
  if (model) {
    args.push("--model", model)
  }
  return args
}

// ── Main entry point — matches upstream signature exactly ────────────

export async function streamClaudeCodeCli(
  config: LlmConfig,
  messages: ChatMessage[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  overrides?: RequestOverrides,
): Promise<void> {
  const { onToken, onDone, onError } = callbacks

  // Sampling knobs aren't wired through the CLI. Warn once if the caller
  // supplied any — silently ignored otherwise.
  if (overrides) {
    for (const key of ["temperature", "top_p", "top_k", "max_tokens", "stop"] as const) {
      if ((overrides as Record<string, unknown>)[key] !== undefined) {
        // eslint-disable-next-line no-console
        console.warn(`[claude-code:node] ignoring unsupported override "${key}"`)
      }
    }
  }

  // Fold system messages into a preamble on the first user turn (CLI
  // has no --system-prompt equivalent across all versions).
  const systemPreamble = messages
    .filter((m) => m.role === "system")
    .map((m) => contentTextOnly(m.content as string | ContentBlock[]))
    .join("\n\n")

  const conversation = messages.filter((m) => m.role === "user" || m.role === "assistant")
  if (conversation.length === 0) {
    onError(new Error("No user/assistant messages to send to claude CLI"))
    return
  }

  let firstUserSeen = false
  const turns = conversation.map((m) => {
    let blocks = contentBlocks(m.content as string | ContentBlock[])
    if (!firstUserSeen && m.role === "user" && systemPreamble.length > 0) {
      blocks = mergeSystemIntoFirstUser(blocks, systemPreamble)
      firstUserSeen = true
    }
    return { role: m.role, content: blocks }
  })

  const args = buildArgs(config.model ?? "", config.localCliIsolation === true)

  // Strip ANTHROPIC_API_KEY to force subscription auth (MIKAI policy).
  const env: NodeJS.ProcessEnv = { ...process.env }
  delete env.ANTHROPIC_API_KEY

  let child: ReturnType<typeof spawn>
  try {
    child = spawn("claude", args, {
      cwd: process.cwd(),
      env,
      stdio: ["pipe", "pipe", "pipe"],
    })
  } catch (err) {
    onError(err as Error)
    return
  }

  const parse = createClaudeCodeStreamParser()
  let finished = false
  let emittedToken = false

  // Diagnostic capture for the silent-failure case (exit 0, no tokens).
  const UNPARSED_CAP = 4096
  const unparsedLines: string[] = []
  let unparsedSize = 0
  const captureUnparsed = (line: string): void => {
    if (unparsedSize >= UNPARSED_CAP) return
    const trimmed = line.trim()
    if (trimmed.length === 0) return
    unparsedLines.push(line)
    unparsedSize += line.length + 1
  }

  // Stderr capture (drained continuously to prevent buffer deadlock).
  let stderrBuf = ""
  child.stderr!.setEncoding("utf8")
  child.stderr!.on("data", (chunk: string) => {
    stderrBuf += chunk
  })

  // Stdout parsing (line-buffered).
  let stdoutBuf = ""
  child.stdout!.setEncoding("utf8")
  child.stdout!.on("data", (chunk: string) => {
    stdoutBuf += chunk
    let idx: number
    while ((idx = stdoutBuf.indexOf("\n")) !== -1) {
      const line = stdoutBuf.slice(0, idx)
      stdoutBuf = stdoutBuf.slice(idx + 1)
      const token = parse(line)
      if (token !== null) {
        emittedToken = true
        onToken(token)
      } else {
        captureUnparsed(line)
      }
    }
  })

  const finishWith = (cb: () => void): void => {
    if (finished) return
    finished = true
    cb()
  }

  const abortHandler = (): void => {
    try {
      child.kill("SIGTERM")
    } catch {
      /* best-effort */
    }
    finishWith(onDone)
  }
  if (signal?.aborted) {
    abortHandler()
    return
  }
  signal?.addEventListener("abort", abortHandler)

  const completion = new Promise<void>((resolve) => {
    child.on("close", (code) => {
      // Drain any final buffered line without trailing newline.
      if (stdoutBuf.length > 0) {
        const token = parse(stdoutBuf)
        if (token !== null) {
          emittedToken = true
          onToken(token)
        } else {
          captureUnparsed(stdoutBuf)
        }
        stdoutBuf = ""
      }

      if (code !== null && code !== 0) {
        finishWith(() =>
          onError(new Error(buildExitError(code, stderrBuf.trim(), unparsedLines.join("\n")))),
        )
      } else if (!emittedToken) {
        const details = stderrBuf.trim() || unparsedLines.join("\n").trim()
        finishWith(() =>
          onError(
            new Error(
              details
                ? `Claude Code CLI completed but returned no content:\n${details}`
                : "Claude Code CLI completed but returned no content.",
            ),
          ),
        )
      } else {
        finishWith(onDone)
      }
      resolve()
    })

    child.on("error", (err) => {
      finishWith(() => onError(err))
      resolve()
    })
  })

  // Write JSON turns to stdin (one event per line), then close stdin so
  // the CLI starts processing.
  try {
    for (const turn of turns) {
      const event = {
        type: turn.role,
        message: { role: turn.role, content: turn.content },
      }
      child.stdin!.write(JSON.stringify(event) + "\n")
    }
    child.stdin!.end()
  } catch (err) {
    finishWith(() => onError(err as Error))
    return
  }

  await completion
}
