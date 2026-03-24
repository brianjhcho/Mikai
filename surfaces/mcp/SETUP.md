# MIKAI MCP — Claude Desktop Setup

## Adding the custom instruction

Claude Desktop does not support custom instructions via `claude_desktop_config.json`. You must add them manually:

1. Open Claude Desktop
2. Go to **Settings** (⌘,)
3. Click **Custom Instructions**
4. Paste the following text and save:

```
At the start of conversations about my work, projects, thinking, or decisions, call get_brief from MIKAI to load my knowledge base context. For simple factual questions unrelated to my personal work (weather, coding help, translations), don't call MIKAI tools. For depth on any topic from the brief, use search_knowledge or search_graph.
```

## What this does

The `get_brief` tool returns a ~400 token snapshot of the knowledge base (tensions, stalled items, source stats, last sync time) at the start of relevant conversations. This gives Claude awareness of your graph without making expensive depth tool calls for every message.

## Tools available

| Tool | When to use |
|------|-------------|
| `get_brief` | Conversation start — loads KB context automatically |
| `search_knowledge` | Depth query on a specific topic (semantic segment search) |
| `search_graph` | Traverse relationships around a concept (node + edge expansion) |
| `get_tensions` | Full list of tension nodes ordered by edge count |
| `get_stalled` | Full list of stalled nodes above a probability threshold |
| `get_status` | KB health snapshot: counts, timestamps, pending work |

## Verifying the server is running

The MCP server starts automatically when Claude Desktop launches (configured in `claude_desktop_config.json`). To confirm:

1. Open Claude Desktop
2. Start a new conversation
3. Type: "Call get_brief"
4. You should see a knowledge base summary with source counts, tensions, and stalled items

To watch the server log:
```
tail -f ~/Library/Logs/Claude/mcp-server-mikai.log
```
