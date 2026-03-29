<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-03-27 -->

# mcp

## Purpose
MCP (Model Context Protocol) server — the primary product surface. Exposes MIKAI's knowledge graph and task-state awareness to Claude Desktop, Cursor, and other MCP-compatible clients via stdio.

## Key Files
| File | Description |
|------|-------------|
| `server.ts` | MCP server with 11 tools: 8 L3 tools + 3 L4 tools |

## MCP Tools
| Tool | Layer | Purpose |
|------|-------|---------|
| `get_brief` | L1 | ~400-token context snapshot at conversation start |
| `search_knowledge` | L2 | Semantic search over 25K+ segments |
| `search_graph` | L3 | Graph traversal: 5 seeds → 1-hop expansion |
| `get_tensions` | L3 | Top unresolved tensions ranked by connectivity |
| `get_stalled` | L3 | Desires/projects gone quiet |
| `mark_resolved` | Write | Mark something as done |
| `add_note` | Write | Save insight from conversation |
| `get_status` | Meta | KB health check |
| `get_threads` | **L4** | List active threads with states and next steps |
| `get_thread_detail` | **L4** | Deep view of one thread — history, members, edges |
| `get_next_steps` | **L4** | The noonchi surface — what to do next |

## For AI Agents

### Working In This Directory
- Server runs as standalone stdio process — NOT inside any framework
- Loads `.env.local` manually (no dotenv)
- Has TWO database paths: Supabase (default) and local SQLite (`MIKAI_LOCAL=1`)
- L4 tools only work in local mode
- Start with `npm run mcp` or `npx tsx surfaces/mcp/server.ts`

### Testing Requirements
- Test by running `npm run mcp` and checking stderr for "MIKAI MCP: env loaded"
- Integration test: configure in Claude Desktop and verify tools appear
