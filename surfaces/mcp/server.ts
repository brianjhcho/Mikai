/**
 * surfaces/mcp/server.ts
 *
 * MCP server exposing MIKAI's knowledge graph + task-state awareness to
 * Claude Desktop, Cursor, and other MCP-compatible clients.
 *
 * Local-first: SQLite + sqlite-vec + FTS5. No cloud dependencies.
 * Uses hybrid search (vec + BM25 + RRF) from the L3 Graphiti upgrade.
 * L4-aware: threads, state classification, next steps.
 *
 * Tools (9):
 *   search           — Hybrid retrieval over segments + knowledge graph
 *   get_brief        — L4-aware context brief (~400 tokens)
 *   get_tensions     — Active tensions, valid edges only, with thread context
 *   get_threads      — Thread-level view with state filter
 *   get_thread_detail — Deep view on one thread
 *   get_next_steps   — Noonchi surface: what to do next
 *   get_history       — Temporal query: graph state at a point in time
 *   add_note         — Save insight from conversation
 *   mark_resolved    — Resolve a node or thread
 *
 * Usage:
 *   npx tsx surfaces/mcp/server.ts
 *   npm run mcp
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import os from 'os';
import { z } from 'zod';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  openDatabase, initDatabase, getStats,
  insertSource, insertSegments, updateNode,
} from '../../lib/store-sqlite.js';
import type { NodeRow, EdgeRow } from '../../lib/store-sqlite.js';
import { embedText, embedDocuments } from '../../lib/embeddings-local.js';
import { searchSegmentsHybrid, hybridGraphSearch } from '../../engine/l3/hybrid-search.js';
import { initL4Schema } from '../../engine/l4/schema.js';
import {
  getActiveThreads, getThread, getStalledThreads,
  getThreadsWithNextSteps, getThreadMembers, getL4Stats,
  getTransitionHistory, getThreadEdges, getThreadsForNode,
  updateThread,
} from '../../engine/l4/store.js';
import { inferForSingleThread } from '../../engine/l4/infer-next-step.js';
import type Database from 'better-sqlite3';

// ── Database ─────────────────────────────────────────────────────────────────

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function getDbPath(): string {
  const configPath = path.join(os.homedir(), '.mikai', 'config.json');
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    if (config.dbPath) return config.dbPath;
  } catch { /* fall through */ }
  return path.join(os.homedir(), '.mikai', 'mikai.db');
}

const dbPath = getDbPath();
process.stderr.write(`MIKAI MCP: opening ${dbPath}\n`);

let db: Database.Database;
try {
  db = openDatabase(dbPath);
  initDatabase(db);
  initL4Schema(db);
  process.stderr.write('MIKAI MCP: database ready\n');
} catch (err: any) {
  process.stderr.write(`MIKAI MCP: database init failed — ${err.message}\n`);
  process.exit(1);
}

// ── Constants ────────────────────────────────────────────────────────────────

const EDGE_PRIORITY: Record<string, number> = {
  unresolved_tension: 0,
  contradicts:        1,
  depends_on:         2,
  partially_answers:  3,
  supports:           4,
  extends:            5,
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(ts: string | null | undefined): string {
  if (!ts) return 'unknown';
  const diff = Date.now() - new Date(ts).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Format an edge for display, using fact field and episode provenance when available. */
function formatEdge(
  edge: EdgeRow,
  nodeMap: Map<string, NodeRow>,
  opts?: { showProvenance?: boolean },
): string | null {
  const from = nodeMap.get(edge.from_node);
  const to = nodeMap.get(edge.to_node);
  if (!from || !to) return null;

  // Use fact field for readable description when available, fall back to note
  const description = edge.fact
    ? edge.fact
    : edge.note ?? '';

  let line = `[${from.label}] →${edge.relationship}→ [${to.label}]`;
  if (description) line += ` — ${description}`;

  // Episode provenance: show source labels that established this edge
  if (opts?.showProvenance) {
    try {
      const episodes: string[] = typeof edge.episodes === 'string'
        ? JSON.parse(edge.episodes)
        : (edge.episodes ?? []);
      const validEpisodes = episodes.filter(Boolean);
      if (validEpisodes.length > 0) {
        const placeholders = validEpisodes.map(() => '?').join(',');
        const sources = db.prepare(
          `SELECT label, source FROM sources WHERE id IN (${placeholders})`,
        ).all(...validEpisodes) as { label: string; source: string }[];
        if (sources.length > 0) {
          const sourceStr = sources.map(s => `${s.label} (${s.source})`).join(', ');
          line += `\n  _Evidence: ${sourceStr}_`;
        }
      }
    } catch { /* episodes parse failed, skip */ }
  }

  // Temporal context
  if (edge.valid_at) {
    line += `\n  _Established: ${edge.valid_at}_`;
  }

  return line;
}

// ── Tool: search ─────────────────────────────────────────────────────────────
// Unified hybrid search: vec + BM25 + RRF over both segments and graph.
// Returns passages AND knowledge graph structure in one response.

async function search(query: string, matchCount: number): Promise<string> {
  const embedding = await embedText(query);
  const lines: string[] = [];

  // ── Hybrid segment search ──────────────────────────────────────────────
  const segments = searchSegmentsHybrid(db, query, embedding, matchCount);

  if (segments.length > 0) {
    lines.push('## Relevant passages\n');
    for (const { item: seg, score, source } of segments) {
      lines.push(`### [${seg.topic_label}]`);
      lines.push(`Source: "${seg.source_label ?? 'unknown'}" (${seg.source_origin ?? 'unknown'}) — match: ${source}`);
      lines.push('');
      lines.push(seg.processed_content);
      lines.push('');
    }
  }

  // ── Hybrid graph search ────────────────────────────────────────────────
  const graph = hybridGraphSearch(db, query, embedding, { limit: 15 });

  if (graph.nodes.length > 0) {
    // Filter out invalidated and expired edges — only show current facts
    const validEdges = graph.edges.filter(e => !e.invalid_at && !e.expired_at);

    const seedIdSet = new Set(graph.seeds);
    const seedNodes = graph.nodes.filter(n => seedIdSet.has(n.id));
    const connectedNodes = graph.nodes.filter(n => !seedIdSet.has(n.id));
    const nodeMap = new Map(graph.nodes.map(n => [n.id, n]));

    const highPriority = validEdges.filter(
      e => e.relationship === 'unresolved_tension' || e.relationship === 'contradicts',
    );
    const otherEdges = validEdges.filter(
      e => e.relationship !== 'unresolved_tension' && e.relationship !== 'contradicts',
    );

    lines.push('\n## Knowledge graph\n');

    lines.push('### Seed nodes\n');
    for (const node of seedNodes) {
      lines.push(`[${node.node_type.toUpperCase()}: ${node.label}]`);
      lines.push(node.content);
      lines.push('');
    }

    if (highPriority.length > 0) {
      lines.push('### Active tensions and contradictions\n');
      for (const edge of highPriority) {
        const line = formatEdge(edge, nodeMap, { showProvenance: true });
        if (line) { lines.push(line); lines.push(''); }
      }
    }

    if (connectedNodes.length > 0) {
      lines.push('### Connected nodes\n');
      for (const node of connectedNodes) {
        lines.push(`[${node.node_type.toUpperCase()}: ${node.label}]`);
        lines.push(node.content);
        const related = validEdges.filter(
          e => e.from_node === node.id || e.to_node === node.id,
        );
        for (const edge of related) {
          const line = formatEdge(edge, nodeMap);
          if (line) lines.push(`  ${line}`);
        }
        lines.push('');
      }
    }

    if (otherEdges.length > 0) {
      lines.push('### Other relationships\n');
      for (const edge of otherEdges) {
        const line = formatEdge(edge, nodeMap);
        if (line) lines.push(line);
      }
    }
  }

  if (lines.length === 0) return 'No results found.';
  return lines.join('\n');
}

// ── Tool: get_brief ──────────────────────────────────────────────────────────
// L4-aware context brief: thread summary, valid tensions, stalled threads.

async function getBrief(): Promise<string> {
  const stats = getStats(db);

  // L4 thread summary
  let threadSummary = '';
  try {
    const l4Stats = getL4Stats(db);
    const stateStr = Object.entries(l4Stats.byState)
      .filter(([, v]) => v > 0)
      .map(([k, v]) => `${k}: ${v}`)
      .join(', ');
    threadSummary = `\nThreads: ${l4Stats.totalThreads} total (${stateStr})`;
  } catch { /* L4 tables may not exist yet */ }

  // Top 5 tensions — valid edges only, resolved filtered out
  const tensions = db.prepare(`
    SELECT n.id, n.label FROM nodes n
    WHERE n.node_type = 'tension' AND n.resolved_at IS NULL
    ORDER BY n.created_at DESC
    LIMIT 30
  `).all() as { id: string; label: string }[];

  let rankedTensions: { id: string; label: string }[] = [];
  if (tensions.length > 0) {
    const tensionIds = tensions.map(t => t.id);
    const placeholders = tensionIds.map(() => '?').join(',');
    const edgeData = db.prepare(`
      SELECT from_node, to_node FROM edges
      WHERE (from_node IN (${placeholders}) OR to_node IN (${placeholders}))
        AND invalid_at IS NULL AND expired_at IS NULL
    `).all(...tensionIds, ...tensionIds) as { from_node: string; to_node: string }[];

    const edgeCounts = new Map<string, number>();
    for (const id of tensionIds) edgeCounts.set(id, 0);
    for (const edge of edgeData) {
      if (edgeCounts.has(edge.from_node)) edgeCounts.set(edge.from_node, (edgeCounts.get(edge.from_node) ?? 0) + 1);
      if (edgeCounts.has(edge.to_node)) edgeCounts.set(edge.to_node, (edgeCounts.get(edge.to_node) ?? 0) + 1);
    }
    rankedTensions = tensions
      .sort((a, b) => (edgeCounts.get(b.id) ?? 0) - (edgeCounts.get(a.id) ?? 0))
      .slice(0, 5);
  }

  // Top 3 stalled threads (thread-level, not node-level)
  let stalledLines = '• (none)';
  try {
    const stalled = getStalledThreads(db, 0.3, 3);
    if (stalled.length > 0) {
      stalledLines = stalled.map(t => `• ${t.label} (${timeAgo(t.last_activity_at)})`).join('\n');
    }
  } catch { /* L4 may not exist */ }

  const tensionLines = rankedTensions.length > 0
    ? rankedTensions.map(n => `• ${n.label}`).join('\n')
    : '• (none)';

  const sourceTypesStr = Object.entries(stats.sourcesByType)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .map(([t, n]) => `${t} (${n})`)
    .join(', ');

  return [
    `MIKAI | ${stats.totalSources} sources | ${stats.totalSegments} segments | ${stats.totalNodes} nodes | synced ${timeAgo(stats.lastIngestion)}`,
    threadSummary,
    '',
    'Active tensions (valid edges only):',
    tensionLines,
    '',
    'Stalled threads:',
    stalledLines,
    '',
    `Sources: ${sourceTypesStr || 'none'}`,
    '',
    '→ Tools: search, get_tensions, get_threads, get_thread_detail, get_next_steps, get_history',
  ].join('\n');
}

// ── Tool: get_tensions ───────────────────────────────────────────────────────
// Active tensions filtered by validity + recency, with thread context.

async function getTensions(limit: number): Promise<string> {
  const tensions = db.prepare(`
    SELECT n.id, n.label, n.content, n.node_type, n.stall_probability, n.created_at
    FROM nodes n
    WHERE n.node_type = 'tension' AND n.resolved_at IS NULL
    LIMIT ?
  `).all(limit * 3) as (NodeRow & { created_at: string })[];

  if (tensions.length === 0) return 'No active tension nodes found.';

  const tensionIds = tensions.map(t => t.id);
  const placeholders = tensionIds.map(() => '?').join(',');

  // Count only VALID edges (not invalidated or expired)
  const edgeData = db.prepare(`
    SELECT from_node, to_node FROM edges
    WHERE (from_node IN (${placeholders}) OR to_node IN (${placeholders}))
      AND invalid_at IS NULL AND expired_at IS NULL
  `).all(...tensionIds, ...tensionIds) as { from_node: string; to_node: string }[];

  const edgeCounts = new Map<string, number>();
  for (const id of tensionIds) edgeCounts.set(id, 0);
  for (const edge of edgeData) {
    if (edgeCounts.has(edge.from_node)) edgeCounts.set(edge.from_node, (edgeCounts.get(edge.from_node) ?? 0) + 1);
    if (edgeCounts.has(edge.to_node)) edgeCounts.set(edge.to_node, (edgeCounts.get(edge.to_node) ?? 0) + 1);
  }

  // Rank by valid edge count, recency as tiebreaker
  const ranked = tensions
    .sort((a, b) => {
      const countDiff = (edgeCounts.get(b.id) ?? 0) - (edgeCounts.get(a.id) ?? 0);
      if (countDiff !== 0) return countDiff;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    })
    .slice(0, limit);

  const lines: string[] = [`## Active tensions (${ranked.length}, valid edges only)\n`];

  for (const node of ranked) {
    const count = edgeCounts.get(node.id) ?? 0;

    // Show which threads this tension belongs to
    let threadInfo = '';
    try {
      const threads = getThreadsForNode(db, node.id);
      if (threads.length > 0) {
        threadInfo = ` | in: ${threads.map(t => `"${t.label}" [${t.state}]`).join(', ')}`;
      }
    } catch { /* L4 may not exist */ }

    lines.push(`### ${node.label} (${count} valid edges${threadInfo})`);
    lines.push(node.content);
    lines.push('');
  }

  return lines.join('\n');
}

// ── Tool: get_threads ────────────────────────────────────────────────────────
// Thread-level view with state filter. Replaces node-level get_stalled.

async function getThreadsList(state?: string, limit?: number): Promise<string> {
  const maxThreads = limit ?? 10;
  let threads: any[];

  if (state) {
    threads = db.prepare(
      'SELECT * FROM threads WHERE state = ? AND resolved_at IS NULL ORDER BY last_activity_at DESC LIMIT ?',
    ).all(state, maxThreads);
  } else {
    threads = getActiveThreads(db, maxThreads);
  }

  if (!threads || threads.length === 0) {
    return state
      ? `No threads in state "${state}". Run the L4 pipeline: npm run l4`
      : 'No active threads found. Run the L4 pipeline: npm run l4';
  }

  let stats;
  try { stats = getL4Stats(db); } catch { stats = null; }

  let output = stats
    ? `## Threads (${stats.totalThreads} total)\n\nStates: ${Object.entries(stats.byState).map(([k, v]) => `${k}: ${v}`).join(', ')}\n\n`
    : '## Threads\n\n';

  for (const thread of threads) {
    const sourceTypes: string[] = JSON.parse(thread.source_types || '[]');
    output += `### ${thread.label}\n`;
    output += `- **State**: ${thread.state}`;
    if (thread.stall_probability > 0.5) output += ` ⚠️ stall risk: ${(thread.stall_probability * 100).toFixed(0)}%`;
    output += `\n`;
    output += `- **Sources**: ${sourceTypes.join(', ') || 'unknown'} (${thread.source_count} total)\n`;
    output += `- **Active**: ${thread.first_seen_at} → ${thread.last_activity_at}\n`;
    if (thread.next_step) output += `- **Next step**: ${thread.next_step}\n`;
    output += `\n`;
  }

  return output;
}

// ── Tool: get_thread_detail ──────────────────────────────────────────────────
// Deep view on one thread: state history, members, related threads.

async function getThreadDetail(threadId: string, includeContent: boolean): Promise<string> {
  const thread = getThread(db, threadId);
  if (!thread) return `Thread not found: ${threadId}`;

  const members = getThreadMembers(db, threadId);
  const transitions = getTransitionHistory(db, threadId);
  const edges = getThreadEdges(db, threadId);

  let output = `## Thread: ${thread.label}\n\n`;
  output += `| Field | Value |\n|-------|-------|\n`;
  output += `| State | ${thread.state} |\n`;
  output += `| Confidence | ${(thread.confidence * 100).toFixed(0)}% |\n`;
  output += `| Stall risk | ${((thread.stall_probability ?? 0) * 100).toFixed(0)}% |\n`;
  output += `| Sources | ${thread.source_count} (${JSON.parse(thread.source_types || '[]').join(', ')}) |\n`;
  output += `| First seen | ${thread.first_seen_at} |\n`;
  output += `| Last activity | ${thread.last_activity_at} |\n`;
  if (thread.next_step) output += `| Next step | ${thread.next_step} |\n`;
  output += `\n`;

  if (transitions.length > 0) {
    output += `### State History\n`;
    for (const t of transitions) {
      output += `- ${t.from_state ?? '(new)'} → **${t.to_state}**: ${t.reason ?? 'no reason'} (${t.created_at})\n`;
    }
    output += `\n`;
  }

  const segmentIds = members.filter((m: any) => m.segment_id).map((m: any) => m.segment_id!);
  const nodeIds = members.filter((m: any) => m.node_id).map((m: any) => m.node_id!);
  output += `### Members: ${members.length} total (${segmentIds.length} segments, ${nodeIds.length} nodes)\n\n`;

  if (includeContent && segmentIds.length > 0) {
    const ph = segmentIds.map(() => '?').join(',');
    const segs = db.prepare(
      `SELECT topic_label, processed_content FROM segments WHERE id IN (${ph}) LIMIT 10`,
    ).all(...segmentIds) as any[];
    for (const seg of segs) {
      output += `> **${seg.topic_label}**: ${seg.processed_content.slice(0, 200)}...\n\n`;
    }
  }

  if (includeContent && nodeIds.length > 0) {
    const ph = nodeIds.map(() => '?').join(',');
    const nodes = db.prepare(
      `SELECT label, content, node_type FROM nodes WHERE id IN (${ph}) LIMIT 10`,
    ).all(...nodeIds) as any[];
    for (const node of nodes) {
      output += `> [${node.node_type}] **${node.label}**: ${node.content.slice(0, 200)}\n\n`;
    }
  }

  if (edges.length > 0) {
    output += `### Related Threads\n`;
    for (const e of edges as any[]) {
      const otherId = e.from_thread === threadId ? e.to_thread : e.from_thread;
      const other = getThread(db, otherId);
      const direction = e.from_thread === threadId ? '→' : '←';
      output += `- ${direction} ${e.relationship}: ${other?.label ?? otherId}${e.note ? ` (${e.note})` : ''}\n`;
    }
  }

  return output;
}

// ── Tool: get_next_steps ─────────────────────────────────────────────────────
// Noonchi surface: what should the user do next?

async function getNextSteps(limit: number, refresh: boolean): Promise<string> {
  if (refresh) {
    const active = getActiveThreads(db, limit);
    for (const thread of active) {
      await inferForSingleThread(db, thread.id);
    }
  }

  const threads = getThreadsWithNextSteps(db, limit);
  const stalled = getStalledThreads(db, 0.5, 3);

  if (threads.length === 0 && stalled.length === 0) {
    return 'No next steps available. Run the L4 pipeline: npm run l4';
  }

  let output = `## What to Do Next\n\n`;

  if (stalled.length > 0) {
    output += `### Stalled\n`;
    for (const t of stalled) {
      output += `- **${t.label}** (${t.state}, stall: ${((t.stall_probability ?? 0) * 100).toFixed(0)}%)`;
      if (t.next_step) output += `\n  → ${t.next_step}`;
      output += `\n`;
    }
    output += `\n`;
  }

  output += `### Active\n`;
  const seen = new Set(stalled.map(s => s.id));
  for (const t of threads) {
    if (seen.has(t.id)) continue;
    output += `- **${t.label}** (${t.state})`;
    output += `\n  → ${t.next_step}`;
    const sourceTypes = JSON.parse(t.source_types || '[]');
    if (sourceTypes.length > 1) output += `\n  _Tracked in: ${sourceTypes.join(', ')}_`;
    output += `\n`;
  }

  return output;
}

// ── Tool: get_history ────────────────────────────────────────────────────────
// Temporal query: graph state at a point in time. Graphiti-style temporal retrieval.

async function getHistory(query: string, asOf?: string, includeInvalidated?: boolean): Promise<string> {
  const embedding = await embedText(query);

  // Find seed nodes via hybrid search (same as regular search)
  const { searchNodesHybrid } = await import('../../engine/l3/hybrid-search.js');
  const hybridResults = searchNodesHybrid(db, query, embedding, 10);

  if (hybridResults.length === 0) return 'No relevant nodes found for temporal query.';

  const seeds = hybridResults.slice(0, 5).map(r => r.item);
  const seedIds = seeds.map(n => n.id);
  const nodeMap = new Map(seeds.map(n => [n.id, n]));

  // Fetch ALL edges (including invalidated) touching seed nodes
  const placeholders = seedIds.map(() => '?').join(',');
  const allEdges = db.prepare(`
    SELECT * FROM edges
    WHERE (from_node IN (${placeholders}) OR to_node IN (${placeholders}))
      AND expired_at IS NULL
    ORDER BY valid_at ASC
  `).all(...seedIds, ...seedIds) as EdgeRow[];

  // Filter by temporal window if asOf is specified
  let filteredEdges = allEdges;
  if (asOf) {
    const asOfDate = new Date(asOf).toISOString();
    filteredEdges = allEdges.filter(e => {
      const validAfterStart = !e.valid_at || e.valid_at <= asOfDate;
      const validBeforeEnd = !e.invalid_at || e.invalid_at > asOfDate;
      return validAfterStart && validBeforeEnd;
    });
  } else if (!includeInvalidated) {
    // Default: show current state only
    filteredEdges = allEdges.filter(e => !e.invalid_at);
  }

  // Fetch connected nodes
  const connectedIds = new Set<string>();
  for (const edge of filteredEdges) {
    connectedIds.add(edge.from_node);
    connectedIds.add(edge.to_node);
  }
  for (const id of seedIds) connectedIds.delete(id);

  if (connectedIds.size > 0) {
    const connPh = [...connectedIds].map(() => '?').join(',');
    const connNodes = db.prepare(
      `SELECT * FROM nodes WHERE id IN (${connPh})`,
    ).all(...connectedIds) as NodeRow[];
    for (const n of connNodes) nodeMap.set(n.id, n);
  }

  // Build output
  const lines: string[] = [];

  if (asOf) {
    lines.push(`## Knowledge graph as of ${asOf}\n`);
  } else if (includeInvalidated) {
    lines.push('## Full knowledge graph history (including superseded facts)\n');
  } else {
    lines.push('## Current knowledge graph\n');
  }

  // Separate current vs invalidated edges
  const currentEdges = filteredEdges.filter(e => !e.invalid_at);
  const invalidatedEdges = filteredEdges.filter(e => e.invalid_at);

  if (currentEdges.length > 0) {
    lines.push('### Current facts\n');
    for (const edge of currentEdges) {
      const line = formatEdge(edge, nodeMap, { showProvenance: true });
      if (line) { lines.push(line); lines.push(''); }
    }
  }

  if (invalidatedEdges.length > 0) {
    lines.push('### Superseded facts (no longer true)\n');
    for (const edge of invalidatedEdges) {
      const from = nodeMap.get(edge.from_node);
      const to = nodeMap.get(edge.to_node);
      if (!from || !to) continue;

      const description = edge.fact ?? edge.note ?? '';
      let line = `~~[${from.label}] →${edge.relationship}→ [${to.label}]~~`;
      if (description) line += ` — ${description}`;
      line += `\n  _Valid: ${edge.valid_at ?? 'unknown'} → invalidated: ${edge.invalid_at}_`;
      lines.push(line);
      lines.push('');
    }
  }

  // Show how thinking evolved
  if (invalidatedEdges.length > 0 && currentEdges.length > 0) {
    lines.push('### Evolution summary\n');
    lines.push(`${currentEdges.length} current facts, ${invalidatedEdges.length} superseded.`);
    lines.push('The user\'s thinking on this topic has evolved — superseded facts show earlier beliefs that were revised.');
  }

  if (filteredEdges.length === 0) {
    lines.push('No edges found for this query');
    if (asOf) lines.push(` as of ${asOf}`);
    lines.push('.');
  }

  return lines.join('\n');
}

// ── Tool: add_note ───────────────────────────────────────────────────────────
// Save insight from conversation. Immediately embedded and searchable.

async function addNote(content: string, label?: string): Promise<string> {
  const noteLabel = label ?? content.slice(0, 60).trimEnd();

  const { id: sourceId } = insertSource(db, {
    type: 'note',
    label: noteLabel,
    raw_content: content,
    source: 'mcp-note',
    chunk_count: 1,
  });

  const { smartSplit } = await import('../../engine/graph/smart-split.js') as any;
  const splits = smartSplit(content, 'mcp-note');
  const segments = splits.length > 0
    ? splits
    : [{ topic_label: noteLabel, condensed_content: content }];

  const embeddings = await embedDocuments(segments.map((s: any) => s.condensed_content));

  insertSegments(db, segments.map((s: any, i: number) => ({
    source_id: sourceId,
    topic_label: s.topic_label,
    processed_content: s.condensed_content,
    embedding: embeddings[i],
  })));

  return `Note saved: "${noteLabel}" — ${segments.length} segment(s) created and searchable.`;
}

// ── Tool: mark_resolved ──────────────────────────────────────────────────────
// Resolve a node or thread. Propagates to containing threads for nodes.

async function markResolved(id: string): Promise<string> {
  // Try as node first
  const node = db.prepare('SELECT id, label FROM nodes WHERE id = ?').get(id) as
    { id: string; label: string } | undefined;

  if (node) {
    updateNode(db, id, { resolved_at: new Date().toISOString(), stall_probability: 0 } as any);

    // Propagate to threads containing this node
    let threadInfo = '';
    try {
      const threads = getThreadsForNode(db, id);
      for (const thread of threads) {
        threadInfo += ` Thread "${thread.label}" notified.`;
      }
    } catch { /* L4 may not exist */ }

    return `Node "${node.label}" marked as resolved.${threadInfo}`;
  }

  // Try as thread
  const thread = getThread(db, id);
  if (thread) {
    updateThread(db, id, { state: 'completed', resolved_at: new Date().toISOString() } as any);
    return `Thread "${thread.label}" marked as completed.`;
  }

  return `Not found: no node or thread with id "${id}".`;
}

// ── MCP Server ───────────────────────────────────────────────────────────────

const server = new McpServer({
  name: 'mikai',
  version: '2.0.0',
});

server.registerTool(
  'search',
  {
    description: 'Search MIKAI using hybrid retrieval (semantic + keyword). Returns relevant passages AND knowledge graph structure (nodes, edges, tensions, contradictions). This is the primary retrieval tool — use it when the user asks about any topic.',
    inputSchema: {
      query: z.string().describe('Natural language query'),
      match_count: z.number().int().min(1).max(20).optional()
        .describe('Max segments to return (default 8)'),
    },
  },
  async ({ query, match_count }) => {
    const result = await search(query, match_count ?? 8);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_brief',
  {
    description: 'Compact context brief (~400 tokens): knowledge base stats, active threads by state, top tensions (valid edges only), stalled threads. Call at conversation start to understand what the user is working on.',
    inputSchema: {},
  },
  async () => {
    const result = await getBrief();
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_tensions',
  {
    description: 'Active unresolved tensions from the knowledge graph. Only counts valid (non-superseded) edges. Shows which threads each tension belongs to. Use when the user asks about conflicts, tradeoffs, or unresolved questions.',
    inputSchema: {
      limit: z.number().int().min(1).max(50).optional()
        .describe('Number of tensions to return (default 10)'),
    },
  },
  async ({ limit }) => {
    const result = await getTensions(limit ?? 10);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_threads',
  {
    description: 'List threads — topics tracked across apps with state (exploring/evaluating/decided/acting/stalled/completed), source types, and next steps. Filter by state to find stalled threads, active work, or completed items.',
    inputSchema: {
      state: z.enum(['exploring', 'evaluating', 'decided', 'acting', 'stalled', 'completed']).optional()
        .describe('Filter by thread state'),
      limit: z.number().optional().default(10)
        .describe('Max threads to return'),
    },
  },
  async (args) => {
    const result = await getThreadsList(args.state, args.limit);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_thread_detail',
  {
    description: 'Deep view of a single thread: state history, member segments/nodes, and relationships to other threads. Use when the user asks about a specific project or topic in depth.',
    inputSchema: {
      thread_id: z.string().describe('The thread ID to inspect'),
      include_content: z.boolean().optional().default(false)
        .describe('Include full segment/node content'),
    },
  },
  async (args) => {
    const result = await getThreadDetail(args.thread_id, args.include_content ?? false);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_next_steps',
  {
    description: 'The noonchi surface — what should the user do next? Returns prioritized next steps across active threads, with stalled threads highlighted. Use at conversation START for proactive guidance.',
    inputSchema: {
      limit: z.number().optional().default(5)
        .describe('Max threads to show'),
      refresh: z.boolean().optional().default(false)
        .describe('Re-run inference for fresh next steps (slower, uses LLM)'),
    },
  },
  async (args) => {
    const result = await getNextSteps(args.limit ?? 5, args.refresh ?? false);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'get_history',
  {
    description: 'Temporal knowledge graph query. Shows how your thinking on a topic has evolved over time — current facts, superseded beliefs, and the evolution between them. Optionally view graph state at a specific date. Use when the user asks "what did I used to think about X?" or "how has my thinking on X changed?"',
    inputSchema: {
      query: z.string().describe('Topic to trace through time'),
      as_of: z.string().optional()
        .describe('ISO date to view graph state at (e.g., "2026-01-15"). Omit for full history.'),
      include_invalidated: z.boolean().optional().default(true)
        .describe('Include superseded facts in the output (default true)'),
    },
  },
  async (args) => {
    const result = await getHistory(args.query, args.as_of, args.include_invalidated ?? true);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'add_note',
  {
    description: 'Save a note to the knowledge base from this conversation. Immediately segmented, embedded, and searchable via the search tool. Use when the user shares an insight, decision, or reflection worth preserving.',
    inputSchema: {
      content: z.string().describe('The text content to save'),
      label: z.string().optional()
        .describe('Optional label (defaults to first 60 chars)'),
    },
  },
  async ({ content, label }) => {
    const result = await addNote(content, label);
    return { content: [{ type: 'text', text: result }] };
  },
);

server.registerTool(
  'mark_resolved',
  {
    description: 'Mark a node or thread as resolved/completed. Accepts either a node ID or thread ID. For nodes, propagates resolution to containing threads. Use when the user confirms something is done.',
    inputSchema: {
      id: z.string().describe('ID of the node or thread to resolve'),
    },
  },
  async ({ id }) => {
    const result = await markResolved(id);
    return { content: [{ type: 'text', text: result }] };
  },
);

// ── Start ────────────────────────────────────────────────────────────────────

process.stderr.write('MIKAI MCP: starting transport\n');
const transport = new StdioServerTransport();
server.connect(transport).then(() => {
  process.stderr.write('MIKAI MCP: connected (v2.0 — local-first, hybrid search, L4-aware)\n');
}).catch((err: Error) => {
  process.stderr.write(`MIKAI MCP: failed — ${err.message}\n`);
  process.exit(1);
});
