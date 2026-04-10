# Build: YouTube Recommendation Steering via MCP

## What We're Building

A new MCP tool `get_youtube_recommendations` that bridges MIKAI's cross-platform knowledge graph to YouTube's recommendation engine. When I ask Claude "what should I watch on YouTube?", the tool:

1. Queries L3 for my active exploration topics (across Claude threads, Perplexity, Apple Notes, iMessage, Gmail)
2. Translates those graph concepts into optimized YouTube search queries
3. Calls YouTube Data API v3 to find videos
4. Returns results ranked by graph relevance, with explanations of WHY each video connects to my cross-platform research

This is NOT a keyword search. The value is that YouTube doesn't know I've been researching Ethiopian coffee processing on Claude and fermentation science in Apple Notes — but MIKAI does, and it translates that cross-platform knowledge into YouTube discovery.

## Architecture Constraints

- Add the tool to the EXISTING MCP server at `surfaces/mcp/server.ts` — follow the exact patterns used by existing tools (search_knowledge, get_threads, etc.)
- YouTube Data API v3 search endpoint only. No OAuth needed — API key auth is sufficient for search
- Add `YOUTUBE_API_KEY` to the `.env.local` loading pattern already in `surfaces/mcp/server.ts`
- DO NOT modify any existing tools, types, or pipeline code
- DO NOT create a new source type or ingestion pipeline yet — this is read-only against the existing graph
- Keep it simple. One file for the YouTube logic, one tool registration in server.ts

## Technical Spec

### Step 1: Create `surfaces/mcp/youtube.ts`

This module handles query generation and YouTube API calls.

```typescript
// surfaces/mcp/youtube.ts
// Two exports:
//   generateSearchQueries(threads, graphContext) → string[]
//   searchYouTube(queries, apiKey) → VideoResult[]
```

**generateSearchQueries logic:**
- Takes active L4 threads (from `getActiveThreads()`) and their member nodes
- For each thread in exploring/evaluating/acting state:
  - Extract the thread label + top 3 member node labels
  - Combine concept pairs connected by `extends`, `supports`, or `depends_on` edges into compound queries
  - Avoid concepts from threads in `completed` or `dormant` state
- Return 3-5 search queries max (YouTube API quota: 100 units per search, 10,000 units/day)
- Queries should be specific concept combinations, NOT just topic labels
  - BAD: "coffee"
  - GOOD: "washed vs natural process Ethiopian coffee"
  - The specificity comes from edge relationships in the graph

**searchYouTube logic:**
- Call `GET https://www.googleapis.com/youtube/v3/search`
  - `part=snippet`
  - `q={query}`
  - `type=video`
  - `maxResults=5`
  - `relevanceLanguage=en`
  - `order=relevance`
  - `key={YOUTUBE_API_KEY}`
- For each result, also fetch video details (`/videos?part=contentDetails,statistics`) to get duration and view count
- Deduplicate across queries by videoId
- Return array of: `{ videoId, title, channelTitle, description, publishedAt, duration, viewCount, thumbnailUrl, sourceQuery, url }`

### Step 2: Create the MCP tool in `surfaces/mcp/server.ts`

Add a new tool `get_youtube_recommendations` following the exact registration pattern of existing tools.

**Tool definition:**
```
name: get_youtube_recommendations
description: "Get YouTube video recommendations based on topics you're actively exploring across all your apps (Claude, Perplexity, Apple Notes, etc). Uses your cross-platform knowledge graph to find videos YouTube's algorithm wouldn't suggest."
parameters:
  - limit: number (optional, default 10, max 20) — total videos to return
  - topic_filter: string (optional) — narrow to a specific topic/thread
  - refresh: boolean (optional, default false) — re-run L4 inference before generating
```

**Tool handler logic:**
1. Load active threads via `getActiveThreads(db)` (already imported in server.ts)
2. If `topic_filter` provided, filter threads by label similarity
3. If `refresh`, call the L4 inference for matching threads
4. Get thread members and edges for the active threads (use `getThreadMembers()` and `getThreadEdges()` already imported)
5. Call `generateSearchQueries()` with threads + members + edges
6. Call `searchYouTube()` with generated queries
7. Format response as:

```
## Recommended Videos

Based on your active research across [source count] apps:

### [Thread: Ethiopian Coffee Processing] (exploring)
Cross-platform sources: Claude thread, Apple Notes, Perplexity

1. **[Video Title]** — [Channel] ([duration])
   [views] views · [published date]
   🔗 https://youtube.com/watch?v={id}
   📊 Connects to: [which graph concepts this relates to]

2. ...

### [Thread: Fermentation Science] (synthesizing)
...
```

### Step 3: Add YouTube API key to env

Add to `.env.local`:
```
YOUTUBE_API_KEY=your_key_here
```

The key loads via the existing `loadEnv()` in server.ts. Reference it as:
```typescript
const YOUTUBE_API_KEY = process.env.YOUTUBE_API_KEY;
```

Don't fail startup if missing — just make the tool return an error message telling me to add the key.

## Getting a YouTube API Key

1. Go to https://console.cloud.google.com/
2. Create project or select existing
3. Enable "YouTube Data API v3"
4. Create credentials → API key
5. Restrict to YouTube Data API v3 only

## What NOT to Build

- No browser extension (that's Phase 2)
- No new ingestion source type for YouTube watch history (Phase 2)
- No new domain config (use existing personal-projects)
- No changes to L3/L4 pipeline code
- No database migrations
- No separate HTTP server

## Testing

After building, I should be able to:
1. Restart MCP server (`npm run mcp`)
2. In Claude Desktop, call the tool: "What should I watch on YouTube?"
3. Get back videos that connect to topics I've been exploring across my other apps
4. Verify the queries are concept-specific (not just topic labels)

## Files to Create/Modify

- **CREATE:** `surfaces/mcp/youtube.ts` — query generation + YouTube API wrapper
- **MODIFY:** `surfaces/mcp/server.ts` — add tool registration + handler
- **MODIFY:** `.env.local` — add YOUTUBE_API_KEY placeholder

That's it. Three file touches.
