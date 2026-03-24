# MIKAI Brief Routing Test Protocol

## Purpose
Validate that the L1 brief (get_brief) correctly prevents unnecessary MIKAI tool calls
while still enabling depth queries when needed.

## Setup
1. Restart Claude Desktop (loads updated MCP server with get_brief)
2. Add custom instruction in Claude Desktop Settings → Custom Instructions
3. Open MCP log for monitoring: `tail -f ~/Library/Logs/Claude/mcp-server-mikai.log`

## Test Queries

### Category A: Should trigger ZERO MIKAI calls
These are general questions unrelated to personal knowledge.

| # | Query | Expected | Tool calls | Result |
|---|-------|----------|-----------|--------|
| A1 | "What time is it in Vancouver right now?" | General answer, no MIKAI | 0 | |
| A2 | "Help me write a Python function to sort a list" | Code help, no MIKAI | 0 | |

### Category B: Should be answerable from brief alone (0-1 calls)
The brief should contain enough context. get_brief may fire once at conversation start.

| # | Query | Expected | Tool calls | Result |
|---|-------|----------|-----------|--------|
| B1 | "What do I think about the coffee industry?" | Answer from brief context or 1 search_knowledge | 0-1 | |
| B2 | "How many sources are in my knowledge base?" | Number from brief | 0-1 (get_brief only) | |
| B3 | "Am I stalling on anything?" | Stalled items from brief | 0-1 (get_brief only) | |

### Category C: Should trigger exactly 1 depth tool call
Brief provides awareness, tool provides detail.

| # | Query | Expected tool | Result |
|---|-------|--------------|--------|
| C1 | "What specifically do I think about Kenya's coffee market?" | search_knowledge | |
| C2 | "What contradicts my passive capture thesis?" | search_graph | |
| C3 | "Give me the full details on my trust cliff tension" | search_knowledge | |
| C4 | "What was I thinking about last week?" | search_knowledge | |
| C5 | "Show me all my stalled items with details" | get_stalled | |

## Scoring

- Category A: 0 MIKAI calls = PASS, any calls = FAIL
- Category B: 0-1 calls (get_brief only) = PASS, depth calls = FAIL
- Category C: exactly 1 depth call = PASS, 0 calls = FAIL
- **Pass threshold: 8/10 correct routing**

## How to check tool calls
Watch the MCP log. Each tool invocation appears as:
```
Message from client: {"method":"tools/call","params":{"name":"search_knowledge",...}}
```
Count the `tools/call` messages per query.

## Results
Date: ___
Score: ___/10
Notes: ___
