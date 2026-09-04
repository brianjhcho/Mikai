// DEVIATION from upstream nashsu (MIKAI-specific).
//
// Stubs @tauri-apps/api/core (invoke) for headless Node execution.
// Selected via tsconfig-node.json path alias.
//
// The real @tauri-apps/api/core delegates to
//   window.__TAURI_INTERNALS__.invoke(cmd, args, options)
// which crashes with `window is not defined` in Node.
//
// The MIKAI CLI seeds Zustand stores to disable multimodal + embedding
// + mineru + auto-watch BEFORE calling autoIngest, which prunes every
// code path that would invoke a Tauri command. This stub therefore
// throws with a descriptive error for any command that ever reaches it
// — the throw catches regressions early instead of silently corrupting
// output.
//
// Whitelisted commands (return safe no-op values instead of throwing):
//   - none currently; extend if a benign command surfaces from ingest.

const UNREACHABLE_CMDS = new Set([
  // Embedding / vector store (embedding.ts) — pruned by embeddingConfig.enabled=false
  "embedding_fetch",
  "embedding_fetch_batch",
  "vector_upsert_chunks",
  "vector_search_chunks",
  "vector_delete_page",
  "vector_count_chunks",
  "vector_clear_chunks",
  "vector_optimize_chunks",
  "vector_legacy_row_count",
  "vector_drop_legacy",
  // Image extraction (extract-source-images.ts) — pruned by multimodalConfig.enabled=false
  "extract_source_images",
  // Claude CLI (claude-cli-transport.ts) — replaced by transport/claude-cli-transport.ts
  "claude_cli_spawn",
  "claude_cli_kill",
  "claude_cli_detect",
])

export async function invoke<T = unknown>(
  cmd: string,
  _args?: Record<string, unknown>,
  _options?: unknown,
): Promise<T> {
  if (UNREACHABLE_CMDS.has(cmd)) {
    throw new Error(
      `[mikai:tauri-shim] command "${cmd}" was invoked but should have been ` +
        `pruned by store seeding or replaced by the Node transport. ` +
        `Something in the ingest path is calling it under conditions the ` +
        `MIKAI CLI didn't anticipate — file a bug with the calling stack.`,
    )
  }
  throw new Error(
    `[mikai:tauri-shim] unhandled Tauri invoke("${cmd}"). ` +
      `Add a stub in infra/nashsu/shims/tauri-core.ts if this command is safe ` +
      `to no-op in headless mode.`,
  )
}

// Also provide the `Channel` and any type-level exports the ingest tree
// might import from @tauri-apps/api/core. If it type-imports these,
// declaring them as unknowns keeps tsc happy.
export type InvokeArgs = Record<string, unknown>
export type InvokeOptions = { headers?: Record<string, string> }
export class Channel<T = unknown> {
  onmessage: ((message: T) => void) | null = null
}
