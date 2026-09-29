# mikai-wiki-mcp v1

Headless MCP server for MIKAI's file-based wiki. Reads the vault directly from disk — **no nashsu Desktop app dependency.**

Sibling to nashsu's `llm-wiki-mcp-server`, but Desktop-independent. Tool schema is intentionally similar so clients that speak `llm-wiki` can speak `mikai-wiki` with only a name change.

## Tools exposed

| Tool | What it does |
|---|---|
| `mikai_wiki_status` | Vault root + page counts by kind + version |
| `mikai_wiki_search` | Semantic kNN via Ollama nomic-embed-text; lexical fallback if Ollama down |
| `mikai_wiki_read_file` | Read a specific page (frontmatter + body); follows retire redirects |
| `mikai_wiki_list` | List pages by kind |
| `mikai_wiki_graph` | Inbound + outbound wikilinks for a page |
| `mikai_wiki_chat` | RAG: retrieve top-K + `claude -p` answer with citations |

## Requirements

- Node.js 20+
- Ollama running locally (for `_search` and `_chat`) — falls back to lexical if unreachable
- `claude` CLI in PATH (for `_chat` only)

## Setup

```bash
cd infra/mikai-mcp
npm install
npm run build
```

That produces `dist/src/index.js`.

## Activate in Claude Code

Add to `~/.claude.json` (or wherever your Claude Code MCP config lives) alongside the existing `llm-wiki` entry:

```json
{
  "mcpServers": {
    "mikai-wiki-v1": {
      "command": "node",
      "args": [
        "/Users/briancho/.superset/worktrees/MIKAI/pear-seashore/infra/mikai-mcp/dist/src/index.js"
      ],
      "env": {
        "MIKAI_WIKI_ROOT": "/Users/briancho/.mikai/wiki-mikai-parallel-test",
        "OLLAMA_HOST": "http://localhost:11434",
        "MIKAI_CHAT_MODEL": "claude-sonnet-4-5"
      }
    }
  }
}
```

Restart Claude Code. The tools appear as `mcp__mikai-wiki-v1__*`.

## Point at a different vault

Change the `MIKAI_WIKI_ROOT` env var. To point at production (once verified safe):

```json
"MIKAI_WIKI_ROOT": "/Users/briancho/.mikai/wiki"
```

Or run multiple copies with different names for parallel comparison:

```json
"mikai-wiki-v1-parallel-test": { "env": { "MIKAI_WIKI_ROOT": "~/.mikai/wiki-mikai-parallel-test" } },
"mikai-wiki-v1-prod":          { "env": { "MIKAI_WIKI_ROOT": "~/.mikai/wiki" } }
```

## Sanity check without Claude Code

```bash
MIKAI_WIKI_ROOT=~/.mikai/wiki-mikai-parallel-test node dist/src/index.js
# Then in another terminal, pipe an MCP request via stdio (or use any MCP-inspector tool)
```

Or Node one-off script:

```javascript
import { Vault } from "./dist/src/vault.js"
process.env.MIKAI_WIKI_ROOT = "/Users/briancho/.mikai/wiki-mikai-parallel-test"
const v = Vault.fromEnv()
console.log(await v.listPages("concepts", { limit: 5 }))
```

## Versioning

`v1` is the first shippable read-side MCP for MIKAI. Future versions may:
- Add `_write_page` (page edits from MCP)
- Add `_reviews` (LLM-generated content review queue)
- Add streaming search
- Support pinned vaults, multi-vault projects

Keep `v1` on `mikai-wiki-v1` server name so clients don't break when `v2` ships as `mikai-wiki-v2`.

## Design principles

- **Headless first.** No Desktop dependency. Runs anywhere Node 20 does.
- **Cache-aligned.** Reuses `.embed-cache/` written by `bridge/dedup_embed.py` and `bridge/pre_extract_topk.py` — same sha256 keying, same raw-list format. No new indices to maintain.
- **Subscription-safe LLM.** `mikai_wiki_chat` uses `claude -p` subprocess (same convention as MIKAI's ingest path). No paid API keys.
- **Read-only.** v1 never writes to the vault. Changes to substrate happen through the ingest pipeline, not through the MCP.
- **Follow retire redirects.** Reading a retire stub transparently returns the canonical.

## Not in v1 (deferred)

- Write operations (page create/edit)
- Reviews / suggestion queue
- Multi-vault switching within a running server (restart with different env var instead)
- Auth tokens (single-user local machine; add if exposing over network)
