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
