# PuppyGraph Experiment — Phase 1.5

Goal: Add PuppyGraph on top of the existing Supabase Postgres instance (zero migration), test whether typed edge traversal produces meaningfully different recall versus vector search alone. The result gates the FalkorDB migration decision.

---

## 1. PuppyGraph Docker Setup

PuppyGraph runs as a stateless query layer on top of Postgres. It does not move or copy data — it reads directly from the existing Supabase tables.

### Parse your Postgres host from SUPABASE_URL

Your `.env.local` contains:
```
SUPABASE_URL=https://<project-ref>.supabase.co
```

The direct Postgres host is:
```
db.<project-ref>.supabase.co
```

### Docker run command

```bash
docker run -d \
  --name puppygraph \
  -p 8080:8080 \
  -p 7687:7687 \
  -e PUPPYGRAPH_USERNAME=puppygraph \
  -e PUPPYGRAPH_PASSWORD=puppygraph123 \
  puppygraph/puppygraph:stable
```

PuppyGraph does not need direct env vars for the Postgres connection at startup — the Postgres credentials are supplied in the schema YAML (see `puppygraph-schema.yaml`). The schema is uploaded via the web UI or REST API after the container starts.

### Postgres connection details (from .env.local)

| Field | Value |
|-------|-------|
| host | `db.<project-ref>.supabase.co` |
| port | `5432` |
| database | `postgres` |
| user | `postgres` |
| password | Value of `SUPABASE_SERVICE_KEY` in `.env.local` |

### Web UI

PuppyGraph's web UI is available at: `http://localhost:8080`

Use it to:
- Upload the schema YAML (`puppygraph-schema.yaml`)
- Run Cypher queries interactively
- Inspect vertex/edge counts to confirm schema loaded correctly

### Upload schema via REST API (alternative to UI)

```bash
curl -XPOST -u puppygraph:puppygraph123 \
  -H "Content-Type: application/x-yaml" \
  --data-binary @engine/eval/puppygraph-schema.yaml \
  http://localhost:7474/schema
```

---

## 2. Schema Mapping

The existing Supabase tables map to PuppyGraph vertices and edges as follows. Full YAML is in `engine/eval/puppygraph-schema.yaml`.

| Supabase table / column | PuppyGraph type | Notes |
|-------------------------|-----------------|-------|
| `nodes` | Vertex: `Node` | id, label, content, node_type, source_id |
| `sources` | Vertex: `Source` | id, label, type |
| `edges` (from_node → to_node) | Edge: `Relationship` | relationship and note as properties |
| `nodes.source_id → sources.id` | Edge: `BelongsTo` | Derived from FK, no separate table |

---

## 3. Cypher Queries

These replicate the two traversal patterns in `lib/graph-retrieval.ts`.

### Query 1 — One-hop expansion from seed nodes

Replicates `buildSubgraph()` lines 85–133: fetch all edges touching any seed node and return all directly connected nodes.

```cypher
MATCH (seed:Node)-[r:Relationship]-(connected:Node)
WHERE seed.id IN $seedIds
RETURN seed, r, connected
```

**Parameters:** `$seedIds` — array of UUID strings from the vector search step (the `id` field of each `SeedNode`).

**Post-processing note:** The current TypeScript implementation ranks connected nodes by edge priority (`unresolved_tension=0, contradicts=1, ...`) and caps the total subgraph at 15 nodes. PuppyGraph returns the full one-hop neighborhood; apply the same ranking and cap client-side if needed, or extend the query:

```cypher
MATCH (seed:Node)-[r:Relationship]-(connected:Node)
WHERE seed.id IN $seedIds
RETURN seed, r, connected,
  CASE r.relationship
    WHEN 'unresolved_tension' THEN 0
    WHEN 'contradicts'        THEN 1
    WHEN 'depends_on'         THEN 2
    WHEN 'partially_answers'  THEN 3
    WHEN 'supports'           THEN 4
    WHEN 'extends'            THEN 5
    ELSE 99
  END AS priority
ORDER BY priority ASC
LIMIT 15
```

### Query 2 — Tension-only traversal (high-priority edges only)

Replicates the `highPriorityEdges` filter in `serializeSubgraph()` (line 168–170): surface only `unresolved_tension` and `contradicts` edges and their nodes.

```cypher
MATCH (seed:Node)-[r:Relationship]-(connected:Node)
WHERE seed.id IN $seedIds
  AND r.relationship IN ['unresolved_tension', 'contradicts']
RETURN seed, r, connected
```

### Cypher dialect notes

PuppyGraph supports openCypher. Differences from Neo4j standard to be aware of:
- Parameter syntax uses `$param` (same as Neo4j) — no change needed.
- `IN [...]` list literals use square brackets — confirmed compatible with the queries above.
- `CASE` expressions are supported in `RETURN` clauses.
- If PuppyGraph does not support `CASE` in `ORDER BY`, move the priority logic to application code after the raw query returns.
- Multi-hop patterns (`-[*1..2]-`) are supported but not needed for this experiment.

---

## 4. Comparison Methodology

### Step 1: Pick test queries

Use queries that exercise the tension/contradiction edges specifically. Suggested set:

1. "what tensions am I holding about MIKAI?"
2. "what decisions am I second-guessing?"
3. "where does my thinking contradict itself?"
4. "what depends on something I haven't resolved?"
5. "what am I avoiding deciding?"

### Step 2: Run current vector search — capture seed node IDs

Hit the existing chat endpoint or run the vector search directly:

```bash
# Via chat endpoint — check app/api/chat/route.ts for the vector search call
# Capture the seed node IDs logged or returned in the response
```

The seed node IDs are the `id` fields of the top-5 `SeedNode` results from Voyage AI similarity search.

### Step 3: Run PuppyGraph Query 1 with those seed IDs — capture subgraph JSON

```bash
# Via PuppyGraph Bolt endpoint (port 7687) using a Neo4j-compatible driver
# or via the web UI's query runner
# Export result as JSON
```

### Step 4: Compare on four dimensions

| Dimension | Current (Supabase) | PuppyGraph | Winner |
|-----------|-------------------|------------|--------|
| Node count | count from supabase response | count from cypher result | |
| Tension/contradiction edge count | count edges where relationship IN ['unresolved_tension','contradicts'] | same | |
| Subjective relevance | 1–5 rating | 1–5 rating | |
| Latency (ms) | time from request to subgraph ready | time for cypher query | |

Rate subjective relevance as: 1=irrelevant, 2=tangentially related, 3=related, 4=clearly relevant, 5=directly answers the question with non-obvious connections.

### Step 5: Record results

Save each test run as:

```
engine/eval/results/puppygraph-comparison-{YYYY-MM-DD}.json
```

Schema:

```json
{
  "date": "2026-03-15",
  "query": "what tensions am I holding about MIKAI?",
  "seedNodeIds": ["uuid1", "uuid2", "uuid3", "uuid4", "uuid5"],
  "supabase": {
    "nodeCount": 12,
    "tensionEdgeCount": 3,
    "relevanceRating": 4,
    "latencyMs": 180
  },
  "puppygraph": {
    "nodeCount": 14,
    "tensionEdgeCount": 5,
    "relevanceRating": 5,
    "latencyMs": 95
  }
}
```

### Decision gate

Run the comparison across all 5 test queries. Compute average delta in tension/contradiction edge count (PuppyGraph minus Supabase).

| Outcome | Decision |
|---------|----------|
| PuppyGraph returns >= 2 more relevant tension nodes on average | Migrate to FalkorDB before Phase 2 |
| Delta < 2 (marginal difference) | Stay on Supabase; graph traversal adds negligible recall |

Record the decision and evidence in `docs/DECISIONS.md` as a new ARCH decision entry before starting Phase 2.
