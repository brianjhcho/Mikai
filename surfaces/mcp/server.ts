/**
 * surfaces/mcp/server.ts
 *
 * MCP (Model Context Protocol) server that exposes MIKAI's knowledge graph to
 * Claude Desktop, Cursor, and other MCP-compatible clients.
 *
 * Runs as a standalone stdio process — NOT inside Next.js. Loads .env.local
 * the same way the engine scripts do (manual line-by-line parse).
 *
 * Tools exposed:
 *   search_knowledge  — vector similarity search over segments (Track C)
 *   search_graph      — seed nodes + 1-hop edge expansion (Track A/B)
 *   get_tensions      — nodes of type 'tension' ordered by edge count
 *   get_stalled       — nodes with stall_probability above threshold
 *   mark_resolved     — set resolved_at + stall_probability=0 on a node
 *   add_note          — create a source+segments from a conversation note
 *
 * Usage:
 *   npx tsx surfaces/mcp/server.ts
 *   npm run mcp
 */

import fs   from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { z } from 'zod';
import { McpServer }          from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createClient }        from '@supabase/supabase-js';

// ── Env loader ────────────────────────────────────────────────────────────────
// Mirror the pattern used in engine/graph/build-segments.js

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function loadEnv(): void {
  const envPath = path.join(__dirname, '../../.env.local');
  try {
    for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx < 0) continue;
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim();
      if (!process.env[key]) process.env[key] = val;
    }
  } catch {
    // .env.local not found — env assumed already set by caller
  }
}

loadEnv();
process.stderr.write('MIKAI MCP: env loaded\n');

// ── Clients ───────────────────────────────────────────────────────────────────

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;
const VOYAGE_API_KEY = process.env.VOYAGE_API_KEY;

if (!process.env.MIKAI_LOCAL && (!SUPABASE_URL || !SUPABASE_KEY)) {
  process.stderr.write('MIKAI MCP: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY\n');
  process.exit(1);
}

if (!process.env.MIKAI_LOCAL && !VOYAGE_API_KEY) {
  process.stderr.write('MIKAI MCP: Missing VOYAGE_API_KEY\n');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

// ── Embeddings ────────────────────────────────────────────────────────────────
// Inline copy of the embedText logic from lib/embeddings.ts.
// The MCP server is a standalone process and cannot import @/ aliases.

const VOYAGE_API_URL = 'https://api.voyageai.com/v1/embeddings';

async function embedText(text: string): Promise<number[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);

  try {
    const response = await fetch(VOYAGE_API_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${VOYAGE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'voyage-3',
        input: [text],
        input_type: 'query',
      }),
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Voyage AI error ${response.status}: ${error}`);
    }

    const data = await response.json() as { data: Array<{ embedding: number[] }> };
    return data.data[0].embedding;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Voyage AI request timed out after 30s');
    }
    throw err;
  }
}

// ── Edge priority (mirrors lib/graph-retrieval.ts — do not reorder) ───────────

const EDGE_PRIORITY: Record<string, number> = {
  unresolved_tension: 0,
  contradicts:        1,
  depends_on:         2,
  partially_answers:  3,
  supports:           4,
  extends:            5,
};

// ── Tool implementations ───────────────────────────────────────────────────────

/**
 * search_knowledge: embed query → search_segments RPC → formatted segments.
 * Mirrors searchSegments() + serializeSegments() from lib/segment-retrieval.ts.
 */
async function searchKnowledge(query: string, matchCount: number): Promise<string> {
  const embedding = await embedText(query);

  const { data, error } = await supabase.rpc('search_segments', {
    query_embedding: embedding,
    match_count:     matchCount,
  });

  if (error) throw new Error(`search_segments RPC failed: ${error.message}`);

  const segments = (data ?? []) as Array<{
    id: string;
    source_id: string;
    topic_label: string;
    processed_content: string;
    similarity: number;
    source_label: string;
    source_type: string;
    source_origin: string;
  }>;

  if (segments.length === 0) return 'No relevant segments found.';

  const lines: string[] = ['## Relevant passages from your notes and threads\n'];

  for (const seg of segments) {
    const similarity = Math.round(seg.similarity * 100);
    lines.push(`### [${seg.topic_label}]`);
    lines.push(`Source: "${seg.source_label}" (${seg.source_origin}) — ${similarity}% match`);
    lines.push('');
    lines.push(seg.processed_content);
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * search_graph: embed query → vector seed nodes → 1-hop edge expansion → serialized subgraph.
 * Mirrors searchSeeds() + buildSubgraph() + serializeSubgraph() from lib/graph-retrieval.ts.
 */
async function searchGraph(query: string): Promise<string> {
  const embedding = await embedText(query);

  // Find seed nodes via vector similarity
  const { data: seedData, error: seedError } = await supabase.rpc('search_nodes', {
    query_embedding: embedding,
    match_count:     5,
  });

  if (seedError) throw new Error(`search_nodes RPC failed: ${seedError.message}`);

  const seedNodes = (seedData ?? []) as Array<{
    id: string;
    label: string;
    content: string;
    node_type: string;
    similarity: number;
  }>;

  if (seedNodes.length === 0) return 'No relevant nodes found in the knowledge graph.';

  const seedIds    = seedNodes.map((n) => n.id);
  const seedIdSet  = new Set(seedIds);

  // Fetch edges touching any seed node (1-hop expansion)
  const { data: rawEdges, error: edgeError } = await supabase
    .from('edges')
    .select('from_node, to_node, relationship, note')
    .or(`from_node.in.(${seedIds.join(',')}),to_node.in.(${seedIds.join(',')})`);

  if (edgeError) {
    // Return seed nodes only if edge fetch fails
    return serializeNodes(seedNodes.map((n) => ({ ...n, isSeed: true })), [], []);
  }

  const edges = rawEdges ?? [];

  // Rank connected (non-seed) nodes by best edge priority
  const connectedPriority = new Map<string, number>();

  for (const edge of edges) {
    const priority = EDGE_PRIORITY[edge.relationship] ?? 99;
    for (const nodeId of [edge.from_node, edge.to_node]) {
      if (seedIdSet.has(nodeId)) continue;
      const current = connectedPriority.get(nodeId) ?? 99;
      if (priority < current) connectedPriority.set(nodeId, priority);
    }
  }

  const remainingSlots = Math.max(0, 15 - seedNodes.length);
  const connectedIds = [...connectedPriority.entries()]
    .sort((a, b) => a[1] - b[1])
    .slice(0, remainingSlots)
    .map(([id]) => id);

  let connectedNodes: Array<{ id: string; label: string; content: string; node_type: string; isSeed: false }> = [];

  if (connectedIds.length > 0) {
    const { data: nodeData } = await supabase
      .from('nodes')
      .select('id, label, content, node_type')
      .in('id', connectedIds);

    connectedNodes = (nodeData ?? []).map((n) => ({ ...n, isSeed: false as const }));
  }

  const allIds = new Set([...seedIds, ...connectedIds]);
  const filteredEdges = edges.filter(
    (e) => allIds.has(e.from_node) && allIds.has(e.to_node),
  );

  return serializeNodes(
    [
      ...seedNodes.map((n) => ({ ...n, isSeed: true as const })),
      ...connectedNodes,
    ],
    filteredEdges,
    seedIds,
  );
}

function serializeNodes(
  nodes: Array<{ id: string; label: string; content: string; node_type: string; isSeed: boolean; similarity?: number }>,
  edges: Array<{ from_node: string; to_node: string; relationship: string; note: string | null }>,
  seedIds: string[],
): string {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const seedIdSet = new Set(seedIds);
  const lines: string[] = [];

  const seedNodes      = nodes.filter((n) => n.isSeed);
  const connectedNodes = nodes.filter((n) => !n.isSeed);

  const highPriorityEdges = edges.filter(
    (e) => e.relationship === 'unresolved_tension' || e.relationship === 'contradicts',
  );
  const otherEdges = edges.filter(
    (e) => e.relationship !== 'unresolved_tension' && e.relationship !== 'contradicts',
  );

  lines.push('## Nodes retrieved by semantic similarity\n');
  for (const node of seedNodes) {
    lines.push(`[${node.node_type.toUpperCase()}: ${node.label}]`);
    lines.push(node.content);
    lines.push('');
  }

  if (highPriorityEdges.length > 0) {
    lines.push('## Active tensions and contradictions\n');
    for (const edge of highPriorityEdges) {
      const from = nodeMap.get(edge.from_node);
      const to   = nodeMap.get(edge.to_node);
      if (!from || !to) continue;
      lines.push(`[${from.label}] ←${edge.relationship}→ [${to.label}]`);
      if (edge.note) lines.push(`  ${edge.note}`);
      lines.push('');
    }
  }

  if (connectedNodes.length > 0) {
    lines.push('## Connected nodes (one hop from seed nodes)\n');
    for (const node of connectedNodes) {
      lines.push(`[${node.node_type.toUpperCase()}: ${node.label}]`);
      lines.push(node.content);
      const relatedEdges = edges.filter(
        (e) => e.from_node === node.id || e.to_node === node.id,
      );
      for (const edge of relatedEdges) {
        const otherId = edge.from_node === node.id ? edge.to_node : edge.from_node;
        const other   = nodeMap.get(otherId);
        if (other) {
          lines.push(`  → ${edge.relationship} [${other.label}]${edge.note ? `: ${edge.note}` : ''}`);
        }
      }
      lines.push('');
    }
  }

  if (otherEdges.length > 0) {
    lines.push('## Other relationships\n');
    for (const edge of otherEdges) {
      const from = nodeMap.get(edge.from_node);
      const to   = nodeMap.get(edge.to_node);
      if (!from || !to) continue;
      const noteStr = edge.note ? ` — ${edge.note}` : '';
      lines.push(`[${from.label}] →${edge.relationship}→ [${to.label}]${noteStr}`);
    }
  }

  return lines.join('\n');
}

/**
 * get_tensions: query nodes table for type='tension', ordered by edge count DESC.
 */
async function getTensions(limit: number): Promise<string> {
  // Fetch tension nodes
  const { data: tensions, error } = await supabase
    .from('nodes')
    .select('id, label, content, node_type, stall_probability')
    .eq('node_type', 'tension')
    .limit(limit * 3); // over-fetch to allow edge-count ranking

  if (error) throw new Error(`get_tensions query failed: ${error.message}`);
  if (!tensions || tensions.length === 0) return 'No tension nodes found in the knowledge graph.';

  const tensionIds = tensions.map((n) => n.id);

  // Count edges per tension node
  const { data: edgeData } = await supabase
    .from('edges')
    .select('from_node, to_node')
    .or(`from_node.in.(${tensionIds.join(',')}),to_node.in.(${tensionIds.join(',')})`);

  const edgeCounts = new Map<string, number>();
  for (const id of tensionIds) edgeCounts.set(id, 0);

  for (const edge of edgeData ?? []) {
    if (edgeCounts.has(edge.from_node)) edgeCounts.set(edge.from_node, (edgeCounts.get(edge.from_node) ?? 0) + 1);
    if (edgeCounts.has(edge.to_node))   edgeCounts.set(edge.to_node,   (edgeCounts.get(edge.to_node)   ?? 0) + 1);
  }

  const ranked = tensions
    .sort((a, b) => (edgeCounts.get(b.id) ?? 0) - (edgeCounts.get(a.id) ?? 0))
    .slice(0, limit);

  const lines: string[] = [`## Top ${ranked.length} tension nodes (by edge count)\n`];

  for (const node of ranked) {
    const count = edgeCounts.get(node.id) ?? 0;
    const stall = node.stall_probability != null
      ? ` | stall_probability: ${Number(node.stall_probability).toFixed(2)}`
      : '';
    lines.push(`### ${node.label} (${count} edges${stall})`);
    lines.push(node.content);
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * get_status: aggregate counts and timestamps for a knowledge base health snapshot.
 */
async function getStatus(): Promise<string> {
  // Run all independent queries in parallel
  const [
    sourcesAll,
    sourcesByType,
    segmentsCount,
    nodesCount,
    lastIngestion,
    lastSegmentation,
    sourcesInNodes,
    sourcesInSegments,
  ] = await Promise.all([
    // Total source count
    supabase.from('sources').select('id', { count: 'exact', head: true }),
    // Source count by type
    supabase.from('sources').select('source'),
    // Total segment count
    supabase.from('segments').select('id', { count: 'exact', head: true }),
    // Total node count
    supabase.from('nodes').select('id', { count: 'exact', head: true }),
    // Most recent source ingestion
    supabase.from('sources').select('created_at').order('created_at', { ascending: false }).limit(1),
    // Most recent segment creation
    supabase.from('segments').select('created_at').order('created_at', { ascending: false }).limit(1),
    // Source IDs already in nodes (for pending graph extraction)
    supabase.from('nodes').select('source_id'),
    // Source IDs already in segments (for pending segmentation)
    supabase.from('segments').select('source_id'),
  ]);

  if (sourcesAll.error) throw new Error(`get_status sources query failed: ${sourcesAll.error.message}`);
  if (segmentsCount.error) throw new Error(`get_status segments query failed: ${segmentsCount.error.message}`);
  if (nodesCount.error) throw new Error(`get_status nodes query failed: ${nodesCount.error.message}`);

  const totalSources   = sourcesAll.count ?? 0;
  const totalSegments  = segmentsCount.count ?? 0;
  const totalNodes     = nodesCount.count ?? 0;

  // Count by source type
  const typeCounts: Record<string, number> = {};
  for (const row of sourcesByType.data ?? []) {
    const t = (row.source as string) ?? 'unknown';
    typeCounts[t] = (typeCounts[t] ?? 0) + 1;
  }

  const knownTypes = ['apple-notes', 'perplexity', 'claude-thread', 'gmail', 'imessage', 'manual'];
  const otherCount = Object.entries(typeCounts)
    .filter(([k]) => !knownTypes.includes(k))
    .reduce((sum, [, v]) => sum + v, 0);

  // Format timestamps
  function fmtTs(ts: string | null | undefined): string {
    if (!ts) return 'N/A';
    const d = new Date(ts);
    const yyyy = d.getUTCFullYear();
    const mm   = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd   = String(d.getUTCDate()).padStart(2, '0');
    const hh   = String(d.getUTCHours()).padStart(2, '0');
    const min  = String(d.getUTCMinutes()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd} ${hh}:${min} UTC`;
  }

  const lastIngestTs  = fmtTs(lastIngestion.data?.[0]?.created_at);
  const lastSegmentTs = fmtTs(lastSegmentation.data?.[0]?.created_at);

  // Pending graph extraction: sources with chunk_count > 0 not in nodes
  const nodeSourceIds = new Set((nodesCount.error ? [] : (sourcesInNodes.data ?? [])).map((r: { source_id: string }) => r.source_id));
  const segSourceIds  = new Set((segmentsCount.error ? [] : (sourcesInSegments.data ?? [])).map((r: { source_id: string }) => r.source_id));

  const { data: pendingGraphSources } = await supabase
    .from('sources')
    .select('id')
    .gt('chunk_count', 0);

  const pendingGraph = (pendingGraphSources ?? []).filter((r) => !nodeSourceIds.has(r.id)).length;
  const pendingSegmentation = (pendingGraphSources ?? []).filter((r) => !segSourceIds.has(r.id)).length;

  // Format numbers with commas
  function fmt(n: number): string {
    return n.toLocaleString('en-US');
  }

  const typeLines = knownTypes
    .filter((t) => (typeCounts[t] ?? 0) > 0)
    .map((t) => `  ${t}: ${fmt(typeCounts[t] ?? 0)}`);
  if (otherCount > 0) typeLines.push(`  other: ${fmt(otherCount)}`);

  const lines = [
    'MIKAI Knowledge Base Status',
    '────────────────────────────',
    `Sources: ${fmt(totalSources)} total`,
    ...typeLines,
    '',
    `Segments: ${fmt(totalSegments)}`,
    `Nodes: ${fmt(totalNodes)}`,
    '',
    `Last ingestion: ${lastIngestTs}`,
    `Last segmentation: ${lastSegmentTs}`,
    '',
    `Pending graph extraction: ${fmt(pendingGraph)} sources`,
    `Pending segmentation: ${fmt(pendingSegmentation)} sources`,
  ];

  return lines.join('\n');
}

/**
 * get_brief: compact ~400 token knowledge base context block for L1 injection.
 */
async function getBrief(): Promise<string> {
  // Run all queries in parallel
  const [
    sourcesCount,
    sourcesByType,
    segmentsCount,
    tensionNodes,
    stalledNodes,
    lastSync,
    lastSegmentation,
  ] = await Promise.all([
    // a) Total source count
    supabase.from('sources').select('id', { count: 'exact', head: true }),
    // b) Source count by type
    supabase.from('sources').select('source'),
    // a) Total segment count
    supabase.from('segments').select('id', { count: 'exact', head: true }),
    // c) Top tension nodes (over-fetch to allow edge-count ranking)
    supabase.from('nodes').select('id, label').eq('node_type', 'tension').limit(30),
    // d) Top stalled items
    supabase.from('nodes').select('id, label').gt('stall_probability', 0.7).order('stall_probability', { ascending: false }).limit(3),
    // e) Last sync timestamp
    supabase.from('sources').select('created_at').order('created_at', { ascending: false }).limit(1),
    // f) Last segmentation timestamp
    supabase.from('segments').select('created_at').order('created_at', { ascending: false }).limit(1),
  ]);

  const totalSources  = sourcesCount.count ?? 0;
  const totalSegments = segmentsCount.count ?? 0;

  // b) Group source types manually
  const typeCounts: Record<string, number> = {};
  for (const row of sourcesByType.data ?? []) {
    const t = (row.source as string) ?? 'unknown';
    typeCounts[t] = (typeCounts[t] ?? 0) + 1;
  }
  const sourceTypesStr = Object.entries(typeCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([t, n]) => `${t} (${n})`)
    .join(', ');

  // c) Rank tension nodes by edge count
  const tensionIds = (tensionNodes.data ?? []).map((n) => n.id);
  let rankedTensions: Array<{ id: string; label: string }> = tensionNodes.data ?? [];

  if (tensionIds.length > 0) {
    const { data: edgeData } = await supabase
      .from('edges')
      .select('from_node, to_node')
      .or(`from_node.in.(${tensionIds.join(',')}),to_node.in.(${tensionIds.join(',')})`);

    const edgeCounts = new Map<string, number>();
    for (const id of tensionIds) edgeCounts.set(id, 0);
    for (const edge of edgeData ?? []) {
      if (edgeCounts.has(edge.from_node)) edgeCounts.set(edge.from_node, (edgeCounts.get(edge.from_node) ?? 0) + 1);
      if (edgeCounts.has(edge.to_node))   edgeCounts.set(edge.to_node,   (edgeCounts.get(edge.to_node)   ?? 0) + 1);
    }
    rankedTensions = (tensionNodes.data ?? [])
      .sort((a, b) => (edgeCounts.get(b.id) ?? 0) - (edgeCounts.get(a.id) ?? 0))
      .slice(0, 5);
  }

  // e) Format last sync as relative time
  function timeAgo(ts: string | null | undefined): string {
    if (!ts) return 'unknown';
    const diff = Date.now() - new Date(ts).getTime();
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  }

  const syncedAgo = timeAgo(lastSync.data?.[0]?.created_at);

  const tensionLines = rankedTensions.map((n) => `• ${n.label}`).join('\n');
  const stalledLines = (stalledNodes.data ?? []).map((n) => `• ${n.label}`).join('\n');

  const lines = [
    `MIKAI Knowledge Base | ${totalSources} sources | ${totalSegments} segments | synced ${syncedAgo}`,
    '',
    'Tensions (top 5):',
    tensionLines || '• (none)',
    '',
    'Stalled (top 3):',
    stalledLines || '• (none)',
    '',
    `Active source types: ${sourceTypesStr || 'none'}`,
    '',
    '→ For depth on any topic: search_knowledge, search_graph, get_tensions, get_stalled tools available',
  ];

  return lines.join('\n');
}

/**
 * get_stalled: query nodes with stall_probability > threshold, ordered DESC.
 */
async function getStalled(threshold: number): Promise<string> {
  const { data, error } = await supabase
    .from('nodes')
    .select('id, label, content, node_type, stall_probability')
    .gt('stall_probability', threshold)
    .order('stall_probability', { ascending: false })
    .limit(20);

  if (error) throw new Error(`get_stalled query failed: ${error.message}`);
  if (!data || data.length === 0) {
    return `No stalled nodes found with stall_probability > ${threshold}.`;
  }

  const lines: string[] = [`## Stalled nodes (stall_probability > ${threshold})\n`];

  for (const node of data) {
    const prob = Number(node.stall_probability).toFixed(2);
    lines.push(`### [${node.node_type.toUpperCase()}] ${node.label} — stall: ${prob}`);
    lines.push(node.content);
    lines.push('');
  }

  return lines.join('\n');
}

// ── embedDocuments: batch embed multiple texts as documents ───────────────────

async function embedDocuments(texts: string[]): Promise<number[][]> {
  const response = await fetch(VOYAGE_API_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${VOYAGE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'voyage-3',
      input: texts,
      input_type: 'document',
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Voyage AI error ${response.status}: ${error}`);
  }

  const data = await response.json() as { data: Array<{ embedding: number[] }> };
  return data.data.map((d) => d.embedding);
}

/**
 * mark_resolved: set resolved_at = now() and stall_probability = 0 on a node.
 */
async function markResolved(node_id: string): Promise<string> {
  // First fetch the node label for the confirmation message
  const { data: node, error: fetchError } = await supabase
    .from('nodes')
    .select('id, label')
    .eq('id', node_id)
    .single();

  if (fetchError || !node) {
    return `Node not found: no node with id "${node_id}".`;
  }

  const { error: updateError } = await supabase
    .from('nodes')
    .update({
      resolved_at:      new Date().toISOString(),
      stall_probability: 0,
    })
    .eq('id', node_id);

  if (updateError) throw new Error(`mark_resolved update failed: ${updateError.message}`);

  return `Node "${node.label}" marked as resolved.`;
}

/**
 * add_note: create a source + segments from a note added via conversation.
 * The note is immediately embedded and searchable via search_knowledge.
 */
async function addNote(content: string, label?: string): Promise<string> {
  const noteLabel = label ?? content.slice(0, 60).trimEnd();

  // Insert source row
  const { data: source, error: sourceError } = await supabase
    .from('sources')
    .insert({
      raw_content: content,
      label:       noteLabel,
      source:      'mcp-note',
      type:        'note',
      chunk_count: 1,
    })
    .select('id')
    .single();

  if (sourceError || !source) {
    throw new Error(`add_note source insert failed: ${sourceError?.message ?? 'no data returned'}`);
  }

  const sourceId = source.id as string;

  // Split content into segments
  const { smartSplit } = await import('../../engine/graph/smart-split.js') as {
    smartSplit: (content: string, sourceOrigin: string) => Array<{ topic_label: string; condensed_content: string }>;
  };

  const splits = smartSplit(content, 'mcp-note');

  // Fall back to a single segment if splitter returns nothing (short notes)
  const segments = splits.length > 0
    ? splits
    : [{ topic_label: noteLabel, condensed_content: content }];

  // Embed all segments in one batch call
  const embeddings = await embedDocuments(segments.map((s) => s.condensed_content));

  // Insert segments
  const segmentRows = segments.map((s, i) => ({
    source_id:         sourceId,
    topic_label:       s.topic_label,
    processed_content: s.condensed_content,
    embedding:         embeddings[i],
  }));

  const { error: segError } = await supabase
    .from('segments')
    .insert(segmentRows);

  if (segError) throw new Error(`add_note segment insert failed: ${segError.message}`);

  return `Note saved: '${noteLabel}' — ${segments.length} segment(s) created.`;
}

// ── Local SQLite backend (when MIKAI_LOCAL=true) ──────────────────────────────

const USE_LOCAL = process.env.MIKAI_LOCAL === 'true';
let localDb: any = null;
let localStore: any = null;
let localEmbed: ((text: string) => Promise<number[]>) | null = null;
let localEmbedDocs: ((texts: string[]) => Promise<number[][]>) | null = null;

if (USE_LOCAL) {
  process.stderr.write('MIKAI MCP: using local SQLite backend\n');
  const homedir = (await import('os')).homedir();
  const configPath = (await import('path')).join(homedir, '.mikai', 'config.json');
  try {
    const config = JSON.parse((await import('fs')).readFileSync(configPath, 'utf8'));
    localStore = await import('../../lib/store-sqlite.js');
    localDb = localStore.openDatabase(config.dbPath);
    const embedMod = await import('../../lib/embeddings-local.js');
    localEmbed = embedMod.embedText;
    localEmbedDocs = embedMod.embedDocuments;
    process.stderr.write(`MIKAI MCP: SQLite loaded (${config.dbPath})\n`);
  } catch (err: any) {
    process.stderr.write(`MIKAI MCP: local backend failed — ${err.message}\n`);
    process.stderr.write('MIKAI MCP: falling back to Supabase\n');
  }
}

// ── Local tool implementations ────────────────────────────────────────────────

async function localSearchKnowledge(query: string, matchCount: number): Promise<string> {
  if (!localDb || !localEmbed || !localStore) throw new Error('Local backend not initialized');
  const embedding = await localEmbed(query);
  const segments = localStore.searchSegments(localDb, embedding, matchCount);
  if (segments.length === 0) return 'No relevant segments found.';

  const lines: string[] = ['## Relevant passages from your notes and threads\n'];
  for (const seg of segments) {
    const similarity = Math.round((seg.similarity ?? 0) * 100);
    lines.push(`### [${seg.topic_label}]`);
    lines.push(`Source: "${seg.source_label ?? 'unknown'}" (${seg.source_origin ?? 'unknown'}) — ${similarity}% match`);
    lines.push('');
    lines.push(seg.processed_content);
    lines.push('');
  }
  return lines.join('\n');
}

async function localSearchGraph(query: string): Promise<string> {
  if (!localDb || !localEmbed || !localStore) throw new Error('Local backend not initialized');
  const embedding = await localEmbed(query);
  const seedNodes = localStore.searchNodes(localDb, embedding, 5);
  if (seedNodes.length === 0) return 'No relevant nodes found in the knowledge graph.';

  const seedIds = seedNodes.map((n: any) => n.id);
  const seedIdSet = new Set(seedIds);
  const edges = localStore.getEdgesTouchingNodes(localDb, seedIds);

  const connectedPriority = new Map<string, number>();
  for (const edge of edges) {
    const priority = EDGE_PRIORITY[edge.relationship] ?? 99;
    for (const nodeId of [edge.from_node, edge.to_node]) {
      if (seedIdSet.has(nodeId)) continue;
      const current = connectedPriority.get(nodeId) ?? 99;
      if (priority < current) connectedPriority.set(nodeId, priority);
    }
  }

  const remainingSlots = Math.max(0, 15 - seedNodes.length);
  const connectedIds = [...connectedPriority.entries()]
    .sort((a, b) => a[1] - b[1])
    .slice(0, remainingSlots)
    .map(([id]) => id);

  let connectedNodes: any[] = [];
  if (connectedIds.length > 0) {
    const placeholders = connectedIds.map(() => '?').join(',');
    connectedNodes = localDb.prepare(`SELECT * FROM nodes WHERE id IN (${placeholders})`).all(...connectedIds)
      .map((n: any) => ({ ...n, isSeed: false }));
  }

  const allIds = new Set([...seedIds, ...connectedIds]);
  const filteredEdges = edges.filter((e: any) => allIds.has(e.from_node) && allIds.has(e.to_node));

  return serializeNodes(
    [...seedNodes.map((n: any) => ({ ...n, isSeed: true })), ...connectedNodes],
    filteredEdges,
    seedIds,
  );
}

async function localGetTensions(limit: number): Promise<string> {
  if (!localDb || !localStore) throw new Error('Local backend not initialized');
  const tensions = localStore.getNodesByType(localDb, 'tension', limit);
  if (tensions.length === 0) return 'No tension nodes found in the knowledge graph.';

  const tensionIds = tensions.map((n: any) => n.id);
  const edgeData = localStore.getEdgesTouchingNodes(localDb, tensionIds);

  const edgeCounts = new Map<string, number>();
  for (const id of tensionIds) edgeCounts.set(id, 0);
  for (const edge of edgeData) {
    if (edgeCounts.has(edge.from_node)) edgeCounts.set(edge.from_node, (edgeCounts.get(edge.from_node) ?? 0) + 1);
    if (edgeCounts.has(edge.to_node)) edgeCounts.set(edge.to_node, (edgeCounts.get(edge.to_node) ?? 0) + 1);
  }

  const ranked = tensions.sort((a: any, b: any) => (edgeCounts.get(b.id) ?? 0) - (edgeCounts.get(a.id) ?? 0)).slice(0, limit);

  const lines: string[] = [`## Top ${ranked.length} tension nodes (by edge count)\n`];
  for (const node of ranked) {
    const count = edgeCounts.get(node.id) ?? 0;
    const stall = node.stall_probability != null ? ` | stall_probability: ${Number(node.stall_probability).toFixed(2)}` : '';
    lines.push(`### ${node.label} (${count} edges${stall})`);
    lines.push(node.content);
    lines.push('');
  }
  return lines.join('\n');
}

async function localGetStalled(threshold: number): Promise<string> {
  if (!localDb || !localStore) throw new Error('Local backend not initialized');
  const nodes = localStore.getNodesAboveStall(localDb, threshold, 20);
  if (nodes.length === 0) return `No stalled nodes found with stall_probability > ${threshold}.`;

  const lines: string[] = [`## Stalled nodes (stall_probability > ${threshold})\n`];
  for (const node of nodes) {
    const prob = Number(node.stall_probability).toFixed(2);
    lines.push(`### [${node.node_type.toUpperCase()}] ${node.label} — stall: ${prob}`);
    lines.push(node.content);
    lines.push('');
  }
  return lines.join('\n');
}

async function localGetStatus(): Promise<string> {
  if (!localDb || !localStore) throw new Error('Local backend not initialized');
  const stats = localStore.getStats(localDb);

  const lines = [
    'MIKAI Knowledge Base Status (Local)',
    '────────────────────────────',
    `Sources: ${stats.totalSources} total`,
  ];
  for (const [type, count] of Object.entries(stats.sourcesByType)) {
    lines.push(`  ${type}: ${count}`);
  }
  lines.push('', `Segments: ${stats.totalSegments}`, `Nodes: ${stats.totalNodes}`, '',
    `Last ingestion: ${stats.lastIngestion ?? 'N/A'}`,
    `Last segmentation: ${stats.lastSegmentation ?? 'N/A'}`);
  return lines.join('\n');
}

async function localGetBrief(): Promise<string> {
  if (!localDb || !localStore) throw new Error('Local backend not initialized');
  const stats = localStore.getStats(localDb);
  const tensions = localStore.getNodesByType(localDb, 'tension', 5);
  const stalled = localStore.getNodesAboveStall(localDb, 0.7, 3);

  const tensionLines = tensions.map((n: any) => `• ${n.label}`).join('\n');
  const stalledLines = stalled.map((n: any) => `• ${n.label}`).join('\n');

  return [
    `MIKAI Knowledge Base | ${stats.totalSources} sources | ${stats.totalSegments} segments`,
    '', 'Tensions (top 5):', tensionLines || '• (none)',
    '', 'Stalled (top 3):', stalledLines || '• (none)',
    '', '→ For depth: search_knowledge, search_graph, get_tensions, get_stalled tools available',
  ].join('\n');
}

async function localMarkResolved(nodeId: string): Promise<string> {
  if (!localDb || !localStore) throw new Error('Local backend not initialized');
  const node = localDb.prepare('SELECT id, label FROM nodes WHERE id = ?').get(nodeId) as any;
  if (!node) return `Node not found: no node with id "${nodeId}".`;
  localStore.updateNode(localDb, nodeId, { resolved_at: new Date().toISOString(), stall_probability: 0 });
  return `Node "${node.label}" marked as resolved.`;
}

async function localAddNote(content: string, label?: string): Promise<string> {
  if (!localDb || !localStore || !localEmbedDocs) throw new Error('Local backend not initialized');
  const noteLabel = label ?? content.slice(0, 60).trimEnd();

  const { id: sourceId } = localStore.insertSource(localDb, {
    type: 'note', label: noteLabel, raw_content: content, source: 'mcp-note', chunk_count: 1,
  });

  const { smartSplit } = await import('../../engine/graph/smart-split.js') as any;
  const splits = smartSplit(content, 'mcp-note');
  const segments = splits.length > 0 ? splits : [{ topic_label: noteLabel, condensed_content: content }];
  const embeddings = await localEmbedDocs(segments.map((s: any) => s.condensed_content));

  localStore.insertSegments(localDb, segments.map((s: any, i: number) => ({
    source_id: sourceId,
    topic_label: s.topic_label,
    processed_content: s.condensed_content,
    embedding: embeddings[i],
  })));

  return `Note saved: '${noteLabel}' — ${segments.length} segment(s) created.`;
}

// ── MCP server setup ──────────────────────────────────────────────────────────

const server = new McpServer({
  name:    'mikai',
  version: '1.0.0',
});

server.registerTool(
  'search_knowledge',
  {
    description: 'Search MIKAI\'s knowledge base using semantic similarity. Returns relevant condensed passages with source provenance.',
    inputSchema: {
      query:       z.string().describe('Natural language query to search for'),
      match_count: z.number().int().min(1).max(20).optional().describe('Number of segments to return (default 8)'),
    },
  },
  async ({ query, match_count }) => {
    const count = match_count ?? 8;
    const result = USE_LOCAL && localDb ? await localSearchKnowledge(query, count) : await searchKnowledge(query, count);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'search_graph',
  {
    description: 'Search MIKAI\'s knowledge graph by semantic similarity, then expand via one-hop edge traversal. Returns seed nodes plus connected nodes, with tensions and contradictions surfaced first.',
    inputSchema: {
      query: z.string().describe('Natural language query to search the knowledge graph'),
    },
  },
  async ({ query }) => {
    const result = USE_LOCAL && localDb ? await localSearchGraph(query) : await searchGraph(query);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_tensions',
  {
    description: 'Retrieve the top tension nodes from the knowledge graph, ordered by how many edges they have (most connected = most active tensions).',
    inputSchema: {
      limit: z.number().int().min(1).max(50).optional().describe('Number of tension nodes to return (default 10)'),
    },
  },
  async ({ limit }) => {
    const result = USE_LOCAL && localDb ? await localGetTensions(limit ?? 10) : await getTensions(limit ?? 10);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_stalled',
  {
    description: 'Retrieve nodes with high stall probability — desires or projects that have gone quiet. Ordered by stall probability descending.',
    inputSchema: {
      threshold: z.number().min(0).max(1).optional().describe('Minimum stall_probability to include (default 0.7)'),
    },
  },
  async ({ threshold }) => {
    const result = USE_LOCAL && localDb ? await localGetStalled(threshold ?? 0.7) : await getStalled(threshold ?? 0.7);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_status',
  {
    description: 'Returns a snapshot of the MIKAI knowledge base: source counts by type, segment and node totals, last ingestion and segmentation timestamps, and counts of sources pending processing.',
    inputSchema: {},
  },
  async () => {
    const result = USE_LOCAL && localDb ? await localGetStatus() : await getStatus();
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_brief',
  {
    description: 'Returns a compact knowledge base context brief (~400 tokens). Call this at conversation start to understand what\'s in the knowledge base before answering questions about the user\'s work, thinking, or projects.',
    inputSchema: {},
  },
  async () => {
    const result = USE_LOCAL && localDb ? await localGetBrief() : await getBrief();
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'mark_resolved',
  {
    description: 'Mark a node (tension, stalled item, or desire) as resolved. Use this when the user confirms they\'ve acted on something or a tension has been resolved.',
    inputSchema: {
      node_id: z.string().describe('ID of the node to mark as resolved'),
    },
  },
  async ({ node_id }) => {
    const result = USE_LOCAL && localDb ? await localMarkResolved(node_id) : await markResolved(node_id);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'add_note',
  {
    description: 'Save a new note to the knowledge base from this conversation. The note is immediately segmented and searchable. Use this when the user shares an insight, decision, or reflection worth preserving.',
    inputSchema: {
      content: z.string().describe('The text content of the note to save'),
      label:   z.string().optional().describe('Optional label for the note (defaults to first 60 chars of content)'),
    },
  },
  async ({ content, label }) => {
    const result = USE_LOCAL && localDb ? await localAddNote(content, label) : await addNote(content, label);
    return { content: [{ type: 'text', text: result }] };
  },
);

// ── Start ─────────────────────────────────────────────────────────────────────

process.stderr.write('MIKAI MCP: starting transport\n');
const transport = new StdioServerTransport();
server.connect(transport).then(() => {
  process.stderr.write('MIKAI MCP: connected and running\n');
}).catch((err: Error) => {
  process.stderr.write(`MIKAI MCP: failed — ${err.message}\n`);
  process.exit(1);
});
