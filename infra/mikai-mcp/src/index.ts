#!/usr/bin/env node
// mikai-wiki-mcp v1 — headless MCP server for MIKAI's file-based wiki.
// No Desktop app dependency; reads the vault directly from disk.
// Set MIKAI_WIKI_ROOT to the vault root (e.g. ~/.mikai/wiki-mikai-parallel-test).

import { Server } from "@modelcontextprotocol/sdk/server/index.js"
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js"
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js"
import { Vault } from "./vault.js"
import { semanticSearch } from "./search.js"
import { chat } from "./chat.js"
import { brainRootFromEnv, getThread, listThreads, stalledThreads } from "./threads.js"
import { FEEDBACK_LABELS, notificationDbFromEnv, recordFeedback } from "./feedback.js"

const VERSION = "1.0.0"
let vault: Vault
try {
  vault = Vault.fromEnv()
} catch (e) {
  console.error(`[mikai-wiki-mcp] init error: ${(e as Error).message}`)
  process.exit(1)
}

const server = new Server(
  { name: "mikai-wiki", version: VERSION },
  { capabilities: { tools: {} } },
)

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "mikai_wiki_status",
      description: "Return vault root, page counts by kind, and version.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
    },
    {
      name: "mikai_wiki_search",
      description: "Semantic search over vault pages using embedding kNN (Ollama nomic-embed-text). Falls back to lexical if Ollama unreachable. Returns top-K pages with cosine + snippet.",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Natural-language search query." },
          limit: { type: "number", description: "Max results (default 10)." },
          kinds: { type: "array", items: { type: "string" }, description: "Restrict to these page kinds: concepts, entities, wisdom, sources. Default: concepts+entities+wisdom." },
        },
        required: ["query"],
        additionalProperties: false,
      },
    },
    {
      name: "mikai_wiki_read_file",
      description: "Read a specific page's frontmatter + body. Follows retire redirects by default.",
      inputSchema: {
        type: "object",
        properties: {
          kind: { type: "string", enum: ["concepts", "entities", "wisdom", "sources"], description: "Page kind." },
          slug: { type: "string", description: "Page slug (basename without .md)." },
          follow_redirects: { type: "boolean", description: "If true (default), follow retire_to redirects to the canonical page." },
        },
        required: ["kind", "slug"],
        additionalProperties: false,
      },
    },
    {
      name: "mikai_wiki_list",
      description: "List pages by kind (excludes retired stubs by default).",
      inputSchema: {
        type: "object",
        properties: {
          kind: { type: "string", enum: ["concepts", "entities", "wisdom", "sources"] },
          limit: { type: "number", description: "Max pages to return (default 500)." },
          include_retired: { type: "boolean", description: "Include retired-stub pages (default false)." },
        },
        required: ["kind"],
        additionalProperties: false,
      },
    },
    {
      name: "mikai_wiki_graph",
      description: "Return inbound + outbound wikilinks for a given page. Inbound crawls all vault kinds; outbound is the page's own body wikilinks.",
      inputSchema: {
        type: "object",
        properties: {
          kind: { type: "string", enum: ["concepts", "entities", "wisdom", "sources"] },
          slug: { type: "string" },
          max_inbound: { type: "number", description: "Cap inbound edges (default 50)." },
        },
        required: ["kind", "slug"],
        additionalProperties: false,
      },
    },
    {
      name: "mikai_wiki_chat",
      description: "RAG chat: retrieve top-K semantically similar pages, then answer via `claude -p` using ONLY the retrieved excerpts. Subscription-safe. Returns answer text + source list.",
      inputSchema: {
        type: "object",
        properties: {
          question: { type: "string" },
          top_k: { type: "number", description: "How many pages to retrieve (default 8)." },
          kinds: { type: "array", items: { type: "string" } },
        },
        required: ["question"],
        additionalProperties: false,
      },
    },
    {
      name: "mikai_threads_list",
      description: "List the user's tracked threads (task-state) with state, last activity, next step and days quiet. Optionally filter by state (exploring, evaluating, decided, acting, stalled, completed).",
      inputSchema: {
        type: "object",
        properties: {
          state: { type: "string", description: "Only return threads in this state." },
        },
        additionalProperties: false,
      },
    },
    {
      name: "mikai_thread_get",
      description: "Read one tracked thread by slug: its task-state fields plus the full body (context, history, notes).",
      inputSchema: {
        type: "object",
        properties: { slug: { type: "string", description: "Thread slug (filename without .md)." } },
        required: ["slug"],
        additionalProperties: false,
      },
    },
    {
      name: "mikai_get_stalled_threads",
      description: "Threads that have gone quiet: not completed and no activity for at least `days` days (default 14), plus any explicitly in state 'stalled'. Sorted by days quiet, most stalled first; includes each thread's next step.",
      inputSchema: {
        type: "object",
        properties: { days: { type: "number", description: "Quiet-days threshold (default 14)." } },
        additionalProperties: false,
      },
    },
    {
      name: "mikai_record_feedback",
      description: "Record the user's reply to something MIKAI surfaced (e.g. an iMessage reply: done, dismiss, snooze, not relevant). Writes one row to the local notification feedback log; never edits threads or the vault. Provide notif_id when replying to a specific notification, otherwise thread_slug.",
      inputSchema: {
        type: "object",
        properties: {
          notif_id: { type: "string", description: "The surfaced notification's id, if known." },
          thread_slug: { type: "string", description: "The thread the reply is about, if no notif_id." },
          label: { type: "string", enum: [...FEEDBACK_LABELS], description: "ACTED = did it / done; DISMISSED = not now, no; SNOOZED = remind later; NOT_RELEVANT = wrong or unwanted surface." },
          note: { type: "string", description: "Optional free-text from the user's reply." },
          source: { type: "string", description: "Where the reply came from, e.g. 'hermes-imessage' (default 'mcp')." },
        },
        required: ["label"],
        additionalProperties: false,
      },
    },
  ],
}))

function textResult(obj: unknown): { content: Array<{ type: "text"; text: string }> } {
  return { content: [{ type: "text", text: JSON.stringify(obj, null, 2) }] }
}

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const name = request.params.name
  const args = (request.params.arguments ?? {}) as Record<string, unknown>

  try {
    switch (name) {
      case "mikai_wiki_status": {
        const [c, e, w, s] = await Promise.all([
          vault.listPages("concepts"),
          vault.listPages("entities"),
          vault.listPages("wisdom"),
          vault.listPages("sources"),
        ])
        return textResult({
          version: VERSION,
          vault_root: vault.vaultRoot,
          counts: {
            concepts: c.length,
            entities: e.length,
            wisdom: w.length,
            sources: s.length,
          },
        })
      }
      case "mikai_wiki_search": {
        const results = await semanticSearch(vault, String(args.query ?? ""), {
          limit: typeof args.limit === "number" ? args.limit : undefined,
          kinds: Array.isArray(args.kinds) ? args.kinds as string[] : undefined,
        })
        return textResult({ results })
      }
      case "mikai_wiki_read_file": {
        const page = await vault.readPage(
          String(args.kind ?? ""),
          String(args.slug ?? ""),
          args.follow_redirects !== false,
        )
        if (!page) throw new McpError(ErrorCode.InvalidRequest, `Page not found: ${args.kind}/${args.slug}`)
        return textResult(page)
      }
      case "mikai_wiki_list": {
        const pages = await vault.listPages(String(args.kind ?? ""), {
          limit: typeof args.limit === "number" ? args.limit : 500,
          includeRetired: args.include_retired === true,
        })
        return textResult({ count: pages.length, pages })
      }
      case "mikai_wiki_graph": {
        const result = await vault.graph(
          String(args.kind ?? ""),
          String(args.slug ?? ""),
          typeof args.max_inbound === "number" ? args.max_inbound : 50,
        )
        if (!result) throw new McpError(ErrorCode.InvalidRequest, `Page not found: ${args.kind}/${args.slug}`)
        return textResult(result)
      }
      case "mikai_wiki_chat": {
        const result = await chat(vault, String(args.question ?? ""), {
          topK: typeof args.top_k === "number" ? args.top_k : undefined,
          kinds: Array.isArray(args.kinds) ? args.kinds as string[] : undefined,
        })
        return textResult(result)
      }
      case "mikai_threads_list": {
        const threads = await listThreads(brainRootFromEnv(), {
          state: typeof args.state === "string" && args.state ? args.state : undefined,
        })
        return textResult({ count: threads.length, threads })
      }
      case "mikai_thread_get": {
        const thread = await getThread(brainRootFromEnv(), String(args.slug ?? ""))
        if (!thread) throw new McpError(ErrorCode.InvalidRequest, `Thread not found: ${args.slug}`)
        return textResult(thread)
      }
      case "mikai_get_stalled_threads": {
        const days = typeof args.days === "number" ? args.days : 14
        const threads = await stalledThreads(brainRootFromEnv(), { days })
        return textResult({ days_threshold: days, count: threads.length, threads })
      }
      case "mikai_record_feedback": {
        let record
        try {
          record = await recordFeedback(notificationDbFromEnv(), {
            notifId: typeof args.notif_id === "string" ? args.notif_id : undefined,
            threadSlug: typeof args.thread_slug === "string" ? args.thread_slug : undefined,
            label: String(args.label ?? ""),
            note: typeof args.note === "string" ? args.note : undefined,
            source: typeof args.source === "string" ? args.source : undefined,
          })
        } catch (e) {
          throw new McpError(ErrorCode.InvalidParams, (e as Error).message)
        }
        return textResult({ recorded: record })
      }
      default:
        throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`)
    }
  } catch (e) {
    if (e instanceof McpError) throw e
    throw new McpError(ErrorCode.InternalError, `${name} failed: ${(e as Error).message}`)
  }
})

const transport = new StdioServerTransport()
await server.connect(transport)
console.error(`[mikai-wiki-mcp] v${VERSION} listening on stdio; vault=${vault.vaultRoot}`)
