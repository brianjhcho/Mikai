import fs from 'fs';
import path from 'path';
import { createClient } from '@supabase/supabase-js';

// Load .env.local manually
function loadEnv(envPath) {
  const raw = fs.readFileSync(envPath, 'utf8');
  const env = {};
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim();
    env[key] = value;
  }
  return env;
}

const envPath = path.resolve('/Users/briancho/Desktop/MIKAI/.env.local');
const env = loadEnv(envPath);

const SUPABASE_URL = env.SUPABASE_URL;
const SUPABASE_SERVICE_KEY = env.SUPABASE_SERVICE_KEY;
const VOYAGE_API_KEY = env.VOYAGE_API_KEY || env.VOYAGEAI_API_KEY;

if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY || !VOYAGE_API_KEY) {
  console.error('Missing required env vars:', { SUPABASE_URL: !!SUPABASE_URL, SUPABASE_SERVICE_KEY: !!SUPABASE_SERVICE_KEY, VOYAGE_API_KEY: !!VOYAGE_API_KEY });
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

async function getEmbedding(text) {
  const res = await fetch('https://api.voyageai.com/v1/embeddings', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${VOYAGE_API_KEY}`,
    },
    body: JSON.stringify({ input: [text], model: 'voyage-3' }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Voyage AI error ${res.status}: ${body}`);
  }
  const data = await res.json();
  return data.data[0].embedding;
}

const queries = [
  "what tensions am I holding about MIKAI?",
  "what decisions am I second-guessing?",
  "where does my thinking contradict itself?",
  "what depends on something I haven't resolved?",
  "what am I avoiding deciding?",
];

async function runQuery(query) {
  const startMs = Date.now();

  // Get embedding
  const embedding = await getEmbedding(query);

  // Search seed nodes
  const { data: seeds, error: seedErr } = await supabase.rpc('search_nodes', {
    query_embedding: embedding,
    match_count: 5,
  });
  if (seedErr) throw new Error(`search_nodes error: ${seedErr.message}`);

  const seedNodeIds = (seeds || []).map(n => n.id);
  const seedNodeLabels = (seeds || []).map(n => n.label || n.content?.slice(0, 60) || n.id);

  // Fetch edges connected to seed nodes
  let edges = [];
  if (seedNodeIds.length > 0) {
    const idList = seedNodeIds.join(',');
    const { data: edgeData, error: edgeErr } = await supabase
      .from('edges')
      .select('from_node,to_node,relationship,note')
      .or(`from_node.in.(${idList}),to_node.in.(${idList})`);
    if (edgeErr) throw new Error(`edges error: ${edgeErr.message}`);
    edges = edgeData || [];
  }

  // Collect connected node IDs (one hop)
  const seedSet = new Set(seedNodeIds);
  const connectedIds = new Set();
  for (const edge of edges) {
    if (!seedSet.has(edge.from_node)) connectedIds.add(edge.from_node);
    if (!seedSet.has(edge.to_node)) connectedIds.add(edge.to_node);
  }

  // Fetch connected nodes
  let connectedNodes = [];
  const connectedIdArr = [...connectedIds].slice(0, 10); // cap
  if (connectedIdArr.length > 0) {
    const { data: connData, error: connErr } = await supabase
      .from('nodes')
      .select('id,label,content,node_type')
      .in('id', connectedIdArr);
    if (connErr) throw new Error(`connected nodes error: ${connErr.message}`);
    connectedNodes = connData || [];
  }

  const totalNodeCount = Math.min(seedNodeIds.length + connectedNodes.length, 15);

  // Count tension/contradiction edges
  const tensionEdgeCount = edges.filter(e =>
    e.relationship === 'unresolved_tension' || e.relationship === 'contradicts'
  ).length;

  const latencyMs = Date.now() - startMs;

  return {
    query,
    seedNodeIds,
    seedNodeLabels,
    supabase: {
      nodeCount: totalNodeCount,
      tensionEdgeCount,
      latencyMs,
    },
  };
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function main() {
  console.log('Starting harvest for', queries.length, 'queries...');
  // Voyage AI free tier: 3 RPM — wait 21s between calls to stay safe
  const RATE_DELAY_MS = 21000;
  const results = [];
  for (let i = 0; i < queries.length; i++) {
    const query = queries[i];
    if (i > 0) {
      console.log(`  Waiting ${RATE_DELAY_MS / 1000}s for rate limit...`);
      await sleep(RATE_DELAY_MS);
    }
    console.log(`\nQuery ${i + 1}/${queries.length}: "${query}"`);
    try {
      const result = await runQuery(query);
      results.push(result);
      console.log(`  Seeds: ${result.seedNodeIds.length}, nodeCount: ${result.supabase.nodeCount}, tensions: ${result.supabase.tensionEdgeCount}, latency: ${result.supabase.latencyMs}ms`);
      console.log(`  Labels: ${result.seedNodeLabels.join(' | ')}`);
    } catch (err) {
      console.error(`  ERROR: ${err.message}`);
      results.push({ query, error: err.message });
    }
  }

  const output = {
    date: '2026-03-15',
    queries: results,
  };

  const outPath = '/Users/briancho/Desktop/MIKAI/.omc/research/harvest-results.json';
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2));
  console.log(`\nResults written to ${outPath}`);
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
