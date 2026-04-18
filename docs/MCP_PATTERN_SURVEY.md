# MCP Output Patterns Survey: Graph-Memory Projects

Survey of 4 knowledge-graph and memory-focused MCP implementations to identify transport, auth, tool naming, state-sharing, and session patterns relevant to MIKAI's /mcp layer design.

## Projects Surveyed

| Project | Type | Transport | Auth |
|---------|------|-----------|------|
| **mcp-memory-service** (doobidoo) | Enterprise memory graph | SSE (Streamable HTTP) + REST | OAuth 2.0 + DCR, Bearer, Anonymous |
| **mcp-knowledge-graph** (shaneholloman) | Local memory with AIM prefix | stdio (npx) | None (file-system based) |
| **@modelcontextprotocol/server-memory** (official) | Reference implementation | stdio (npx) | None |
| **MIKAI Graphiti sidecar** (mcp-layer) | L3 knowledge graph via Graphiti | Streamable HTTP (SSE) | None (in-process, secured via sidecar) |

---

## Transport Choices

**mcp-memory-service:** Supports both **Streamable HTTP via SSE** for remote Claude Desktop/mobile/browser clients and **stdio** for local desktop. REST API available for framework-agnostic access. Full state-sharing between transports via shared backend.

**mcp-knowledge-graph:** **stdio transport only** via `npx mcp-knowledge-graph --memory-path /path/to/memory`. No remote or HTTP variant.

**@modelcontextprotocol/server-memory:** **stdio transport** via `npx -y @modelcontextprotocol/server-memory`. Reference implementation emphasizing local deployment.

**MIKAI:** **Streamable HTTP (SSE) only**, mounted at `/mcp` inside FastAPI sidecar (`infra/graphiti/sidecar/main.py:14`). Uses FastMCP with `streamable_http_path = "/"` (`mcp_tools.py:44`). Shares Graphiti singleton with REST endpoints (/search, /episode, /communities).

**Difference:** MIKAI commits to HTTP-only transport for multi-surface support (Claude Desktop, mobile, browser) and explicit in-process state sharing via FastAPI mount. mcp-memory-service mirrors this pattern; most others default to stdio.

---

## Tool Naming & Shape Conventions

**mcp-memory-service:** No fixed prefix. Tools organized by function: `add_memory`, `retrieve_memory`, `search_memory`, `link_memory`, `get_memory_tag`. Uses `conversation_id` parameter for session scoping.

**mcp-knowledge-graph:** Strict **`aim_` prefix** grouping: `aim_memory_store`, `aim_memory_search`, `aim_memory_get`, `aim_memory_link`, `aim_memory_list_stores`. Prefix stated as best practice for multi-tool setups.

**@modelcontextprotocol/server-memory:** snake_case without prefix: `create_entities`, `add_observations`, `delete_relations`, `search_nodes`, `open_nodes`. Operations grouped by knowledge-graph semantics (entities/relations/observations).

**MIKAI:** snake_case without prefix (`mcp_tools.py:46-187`): `search`, `get_history`, `add_note`, `get_stats`. Grouped by L3 query/write semantics. No L4 tools (tensions, threads, brief) per D-041.

**Difference:** MIKAI follows official MCP server patterns (no prefix, semantic grouping). shaneholloman's `aim_` prefix is project-specific; valuable only if multi-namespace collision risk exists. MIKAI avoids prefix overhead.

---

## Authentication Approaches

**mcp-memory-service:** **OAuth 2.0 + DCR** (Dynamic Client Registration) for enterprise multi-user. Bearer token for API access. `MCP_ALLOW_ANONYMOUS_ACCESS=true` flag for anonymous mode. Per-user access control via `X-Agent-ID` header.

**mcp-knowledge-graph:** **No authentication**. File-system based access control via `--memory-path` directory. Optional `autoapprove` config for read operations: `aim_memory_search`, `aim_memory_get`, `aim_memory_read_all`, `aim_memory_list_stores`.

**@modelcontextprotocol/server-memory:** **No authentication** documented. Assumes deployment-context security (stdio process, local file).

**MIKAI:** **No MCP-layer auth** (per D-043 decision pending hardener task #2). Protected by sidecar's HTTP isolation (localhost or internal network). Notes indicate bearer token and logging planned.

**Difference:** Enterprise-grade memory services (mcp-memory-service) implement OAuth + multi-user. Local/reference servers omit auth entirely, delegating to deployment context. MIKAI matches local pattern for now; hardener task #2 will add bearer auth.

---

## State Sharing Between REST and MCP

**mcp-memory-service:** Shared SQLite backend or Cloudflare sync. REST endpoints and MCP tools read/write same data store. SSE event streams notify clients of updates across both interfaces. Tag-based inter-agent messaging via sentinel tags (e.g., `msg:cluster`).

**mcp-knowledge-graph:** **File-based persistence only**. All agents share `.aim` directory. File-system safety markers (`{"type":"_aim","source":"mcp-knowledge-graph"}`) prevent overwrites. No REST API.

**@modelcontextprotocol/server-memory:** File-based JSONL persistence (default: `memory.jsonl`). No REST variant documented.

**MIKAI:** **In-process Graphiti singleton** (`main.py:41, mcp_tools.py:36`). REST endpoints (`/search`, `/episode`, `/communities`) and MCP tools (`search`, `add_note`, `get_stats`) share same Graphiti instance via `get_graphiti()` closure. One codebase, one connection.

**Difference:** MIKAI's in-process singleton avoids multi-client serialization complexity. mcp-memory-service uses event streams for cross-interface consistency (more robust for distributed deployments). mcp-knowledge-graph relies on file-system atomicity (simple but less scalable).

---

## Session & Concurrency Management

**mcp-memory-service:** `conversation_id` parameter scopes queries to conversation context. `X-Agent-ID` header for agent identity tagging. Multi-user via OAuth; handles concurrent clients with per-user access control. SSE keeps connections live for real-time updates.

**mcp-knowledge-graph:** **No explicit sessions**. Auto-detects `.aim` directory for project-local context vs. `--memory-path` global config. File-locking implicit in file-system semantics. Single stdio connection per process instance.

**@modelcontextprotocol/server-memory:** **File-based locking** via JSONL format. Single stdio connection. No multi-client support documented.

**MIKAI:** **Per-request stateless** (FastAPI HTTP). Each `/mcp` request is independent. Graphiti driver handles connection pooling internally. No explicit conversation scoping yet (L4 thread detection pending).

**Difference:** mcp-memory-service supports multi-user concurrency with session/agent scoping. MIKAI and stdio servers are single-client or file-locked, simpler but less flexible for collaborative scenarios. Conversation scoping (conversation_id pattern) could be added to MIKAI L4 tools when threads/tasks are built.

---

## Key Design Decisions for MIKAI

1. **Streamable HTTP + in-process singleton is validated** — mcp-memory-service uses identical pattern for multi-surface support.

2. **Skip tool prefixing** — Official servers avoid prefixes; shaneholloman's `aim_` is project-specific. MIKAI's semantic grouping is cleaner.

3. **Auth via hardener (task #2) should use bearer token** — Simpler than OAuth for single-sidecar deployment, matches mcp-memory-service's REST API pattern.

4. **Conversation scoping (conversation_id) deferred to L4** — Thread/task state depends on tensions/briefly detection logic currently under design (feat/l4-engine). Can be added to future tools without breaking MCP transport.

5. **File-safety markers not needed** — In-process state avoids multi-writer collision risk that shaneholloman's `aim_` prefix guards against.

---

## References

- **mcp-memory-service:** Enterprise SSE + REST state-sharing, OAuth + multi-user, conversation scoping. Retrieved via WebFetch GitHub analysis.
- **mcp-knowledge-graph:** File-based local memory with `aim_` prefix convention for tool grouping. Retrieved via WebFetch GitHub analysis.
- **@modelcontextprotocol/server-memory:** Reference JSONL persistence, stdio transport, no auth. Retrieved via WebFetch GitHub analysis.
- **MIKAI Graphiti sidecar:** `infra/graphiti/sidecar/main.py:L1-19`, `mcp_tools.py:L36-187`. Streamable HTTP, in-process singleton, L3-only tools (search, get_history, add_note, get_stats).
