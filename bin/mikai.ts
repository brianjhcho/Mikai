#!/usr/bin/env tsx
/**
 * bin/mikai.ts — CLI entry point for MIKAI
 *
 * Subcommands:
 *   init    — Create ~/.mikai/, SQLite DB, detect API key, print Claude config
 *   serve   — Start MCP server (stdio) reading from local SQLite
 *   sync    — Sync Apple Notes + import folder into local DB
 *   build   — Extract graph + segments + score nodes
 *   status  — Print knowledge base stats
 *
 * Usage:
 *   npx @chobus/mikai init
 *   npx @chobus/mikai serve
 *   npx @chobus/mikai sync
 *   npx @chobus/mikai build
 *   npx @chobus/mikai status
 */

import fs from 'fs';
import path from 'path';
import os from 'os';
import { execSync } from 'child_process';
import readline from 'readline';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIKAI_DIR = path.join(os.homedir(), '.mikai');
const CONFIG_PATH = path.join(MIKAI_DIR, 'config.json');
const DB_PATH = path.join(MIKAI_DIR, 'mikai.db');
const IMPORT_DIR = path.join(MIKAI_DIR, 'import');

function loadConfig() {
  try { return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')); }
  catch { return null; }
}

function saveConfig(config) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
}

function prompt(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(question, (answer) => { rl.close(); resolve(answer.trim()); }));
}

// ── INIT ────────────────────────────────────────────────────────────────────

async function cmdInit() {
  console.log('MIKAI — Intent Intelligence Engine');
  console.log('===================================\n');

  // 1. Create directories
  fs.mkdirSync(MIKAI_DIR, { recursive: true });
  fs.mkdirSync(IMPORT_DIR, { recursive: true });
  console.log(`✓ Created ${MIKAI_DIR}`);

  // 2. Detect or prompt for Anthropic API key
  let anthropicKey = process.env.ANTHROPIC_API_KEY;
  if (!anthropicKey) {
    anthropicKey = await prompt('Enter your Anthropic API key (sk-ant-...): ');
  }
  if (!anthropicKey || !anthropicKey.startsWith('sk-ant-')) {
    console.error('Invalid Anthropic API key. Get one at https://console.anthropic.com/');
    process.exit(1);
  }
  console.log('✓ Anthropic API key detected');

  // 3. Create SQLite database
  const { openDatabase, initDatabase } = await import('../lib/store-sqlite.ts');
  const db = openDatabase(DB_PATH);
  initDatabase(db);
  db.close();
  console.log(`✓ Database created at ${DB_PATH}`);

  // 4. Download embedding model
  console.log('\nDownloading embedding model (one-time, ~130MB)...');
  const { warmup } = await import('../lib/embeddings-local.ts');
  await warmup();
  console.log('✓ Embedding model ready\n');

  // 5. Save config
  const config = {
    store: 'sqlite',
    dbPath: DB_PATH,
    anthropicKey,
    importDir: IMPORT_DIR,
    createdAt: new Date().toISOString(),
  };
  saveConfig(config);
  console.log(`✓ Config saved to ${CONFIG_PATH}`);

  // 6. Print Claude Desktop config
  const pkgRoot = path.resolve(__dirname, '..');
  const serverPath = path.join(pkgRoot, 'surfaces', 'mcp', 'server.ts');

  console.log('\n───────────────────────────────────────────');
  console.log('Add this to your Claude Desktop config at:');
  console.log(`~/Library/Application Support/Claude/claude_desktop_config.json\n`);
  console.log(JSON.stringify({
    mcpServers: {
      mikai: {
        command: 'npx',
        args: ['tsx', serverPath],
        env: {
          MIKAI_LOCAL: 'true',
          ANTHROPIC_API_KEY: anthropicKey,
        }
      }
    }
  }, null, 2));
  console.log('\n───────────────────────────────────────────');

  // 7. Offer launchd setup
  console.log('\nAutomatic sync (every 30 minutes):');
  const setupSync = await prompt('Install launchd scheduler? [Y/n] ');
  if (setupSync.toLowerCase() !== 'n') {
    const plistName = 'com.mikai.auto-sync';
    const plistPath = path.join(os.homedir(), 'Library', 'LaunchAgents', `${plistName}.plist`);
    const syncScript = path.join(pkgRoot, 'bin', 'mikai.ts');

    const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${plistName}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${process.execPath}</string>
    <string>${syncScript}</string>
    <string>sync-and-build</string>
  </array>
  <key>StartInterval</key><integer>1800</integer>
  <key>StandardOutPath</key><string>${MIKAI_DIR}/sync.log</string>
  <key>StandardErrorPath</key><string>${MIKAI_DIR}/sync-error.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ANTHROPIC_API_KEY</key><string>${anthropicKey}</string>
    <key>MIKAI_LOCAL</key><string>true</string>
    <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
  </dict>
</dict>
</plist>`;

    fs.mkdirSync(path.dirname(plistPath), { recursive: true });
    fs.writeFileSync(plistPath, plist);
    try {
      execSync(`launchctl load "${plistPath}"`, { stdio: 'pipe' });
      console.log(`✓ Auto-sync installed (every 30 minutes)`);
    } catch {
      console.log(`⚠ Could not load launchd plist. Load manually: launchctl load "${plistPath}"`);
    }
  }

  console.log('\n===================================');
  console.log('Setup complete! Next steps:');
  console.log('  1. npx @chobus/mikai sync     # Ingest your Apple Notes');
  console.log('  2. npx @chobus/mikai build    # Build knowledge graph');
  console.log('  3. Restart Claude Desktop');
  console.log('  4. Ask Claude: "What tensions am I holding?"');
  console.log('===================================\n');
}

// ── SYNC ────────────────────────────────────────────────────────────────────

async function cmdSync() {
  const config = loadConfig();
  if (!config) { console.error('Run "mikai init" first.'); process.exit(1); }

  const { openDatabase, insertSource, updateSource } = await import('../lib/store-sqlite.ts');
  const { cleanContent } = await import('../engine/ingestion/preprocess.ts');
  const db = openDatabase(config.dbPath);

  let synced = 0;

  // 1. Apple Notes via osascript
  console.log('Syncing Apple Notes...');
  try {
    const script = `
      tell application "Notes"
        set noteList to {}
        repeat with n in notes of default account
          set end of noteList to {name of n, plaintext of n}
        end repeat
        return noteList
      end tell
    `;
    const raw = execSync(`osascript -e '${script.replace(/'/g, "'\\''")}'`, {
      maxBuffer: 50 * 1024 * 1024,
      timeout: 120000,
    }).toString();

    // Parse osascript output: {{title, content}, {title, content}, ...}
    // The output format is comma-separated pairs
    const notePattern = /([^,{]+),\s*([^}]+)/g;
    let match;
    const existingLabels = new Set(
      (db.prepare('SELECT label FROM sources WHERE source = ?').all('apple-notes') as any[]).map(r => r.label)
    );

    // Simple parsing: split by line pairs
    const lines = raw.split(', ');
    for (let i = 0; i < lines.length - 1; i += 2) {
      const title = lines[i].replace(/^{/, '').trim();
      const content = lines[i + 1]?.replace(/}$/, '').trim();
      if (!title || !content || content.length < 50) continue;
      if (existingLabels.has(title)) continue;

      const cleaned = cleanContent(content, 'apple-notes');
      if (cleaned.length < 50) continue;

      const { id } = insertSource(db, {
        type: 'note',
        label: title,
        raw_content: cleaned,
        source: 'apple-notes',
        chunk_count: 1,
      });
      synced++;
    }
    console.log(`  ✓ Apple Notes: ${synced} new notes`);
  } catch (err) {
    console.log(`  ⚠ Apple Notes sync failed: ${(err as Error).message?.slice(0, 80)}`);
  }

  // 2. Import folder
  const importSynced = await syncImportFolder(db, config.importDir);
  if (importSynced > 0) console.log(`  ✓ Import folder: ${importSynced} files`);

  db.close();
  console.log(`\nSync complete. ${synced + importSynced} sources ingested.`);
}

async function syncImportFolder(db: any, importDir: string): Promise<number> {
  if (!fs.existsSync(importDir)) return 0;

  const { cleanContent } = await import('../engine/ingestion/preprocess.ts');
  const { insertSource } = await import('../lib/store-sqlite.ts');
  const existingLabels = new Set(
    (db.prepare('SELECT label FROM sources').all() as any[]).map((r: any) => r.label)
  );

  let count = 0;
  const files = fs.readdirSync(importDir).filter((f: string) => /\.(md|txt|json)$/i.test(f));

  for (const file of files) {
    const filePath = path.join(importDir, file);
    const raw = fs.readFileSync(filePath, 'utf8');
    const label = path.basename(file, path.extname(file)).replace(/[-_]/g, ' ');
    if (existingLabels.has(label)) continue;

    const ext = path.extname(file).toLowerCase();
    const cleanType = ext === '.json' ? 'claude-export' : 'markdown';
    const content = cleanContent(raw, cleanType);
    if (content.length < 50) continue;

    insertSource(db, {
      type: ext === '.json' ? 'llm_thread' : 'document',
      label,
      raw_content: content,
      source: ext === '.json' ? 'claude-thread' : 'manual',
      chunk_count: 1,
    });
    count++;
  }
  return count;
}

// ── BUILD ───────────────────────────────────────────────────────────────────

async function cmdBuild() {
  const config = loadConfig();
  if (!config) { console.error('Run "mikai init" first.'); process.exit(1); }

  process.env.ANTHROPIC_API_KEY = config.anthropicKey;

  const store = await import('../lib/store-sqlite.ts');
  const { embedText, embedDocuments } = await import('../lib/embeddings-local.ts');
  const { extractGraph } = await import('../lib/ingest-pipeline.ts');
  const { smartSplit } = await import('../engine/graph/smart-split.js');

  const db = store.openDatabase(config.dbPath);

  // 1. Build graph (Track A extraction)
  const sources = store.getSourcesToProcess(db, { requireChunks: true, excludeProcessed: true, limit: 50 });
  console.log(`\nBuilding graph: ${sources.length} sources to process\n`);

  for (const source of sources) {
    process.stdout.write(`"${source.label?.slice(0, 60)}"... `);

    try {
      const graph = await extractGraph(source.raw_content, source.label);
      if (graph.nodes.length === 0) {
        console.log('0 nodes — skipping');
        store.updateSource(db, source.id, { node_count: -1 });
        continue;
      }

      const embeddings = await embedDocuments(graph.nodes.map(n => n.content));

      const insertedNodes = store.insertNodes(db, graph.nodes.map((node, j) => ({
        source_id: source.id,
        label: node.label,
        content: node.content,
        node_type: node.type,
        embedding: embeddings[j],
        has_action_verb: /\b(buy|book|schedule|call|send|order|plan|confirm)\b/i.test(node.content),
        confidence_weight: 1.0,
      })));

      const nodeIdMap = new Map(insertedNodes.map(n => [n.label, n.id]));
      let edgeCount = 0;
      for (const edge of graph.edges) {
        const fromId = nodeIdMap.get(edge.from_label);
        const toId = nodeIdMap.get(edge.to_label);
        if (fromId && toId) {
          store.insertEdge(db, { from_node: fromId, to_node: toId, relationship: edge.relationship, note: edge.note });
          edgeCount++;
        }
      }

      store.updateSource(db, source.id, { node_count: insertedNodes.length, edge_count: edgeCount });
      console.log(`${insertedNodes.length} nodes, ${edgeCount} edges`);
    } catch (err) {
      console.log(`ERROR: ${(err as Error).message?.slice(0, 80)}`);
    }
  }

  // 2. Build segments (Track C)
  const segSources = store.getSourcesToProcess(db, {
    requireChunks: true,
    excludeProcessed: false,
    sourceFilter: ['apple-notes', 'perplexity', 'manual', 'claude-thread'],
    limit: 100,
  });

  // Filter to sources without segments
  const sourcesWithSegments = new Set(
    (db.prepare('SELECT DISTINCT source_id FROM segments').all() as any[]).map(r => r.source_id)
  );
  const segToProcess = segSources.filter(s => !sourcesWithSegments.has(s.id));

  console.log(`\nBuilding segments: ${segToProcess.length} sources to process\n`);

  for (const source of segToProcess) {
    process.stdout.write(`"${source.label?.slice(0, 60)}"... `);
    try {
      const splits = smartSplit(source.raw_content, source.source);
      if (splits.length === 0) { console.log('0 segments'); continue; }

      const embeddings = await embedDocuments(splits.map(s => s.condensed_content));

      store.insertSegments(db, splits.map((s, i) => ({
        source_id: source.id,
        topic_label: s.topic_label,
        processed_content: s.condensed_content,
        embedding: embeddings[i],
      })));

      console.log(`${splits.length} segments`);
    } catch (err) {
      console.log(`ERROR: ${(err as Error).message?.slice(0, 80)}`);
    }
  }

  // 3. Score nodes
  console.log('\nScoring nodes...');
  const scored = store.scoreAllNodes(db);
  console.log(`✓ Scored ${scored} nodes`);

  db.close();
  console.log('\nBuild complete.');
}

// ── SYNC-AND-BUILD (for launchd) ────────────────────────────────────────────

async function cmdSyncAndBuild() {
  await cmdSync();
  await cmdBuild();
}

// ── STATUS ──────────────────────────────────────────────────────────────────

async function cmdStatus() {
  const config = loadConfig();
  if (!config) { console.error('Run "mikai init" first.'); process.exit(1); }

  const { openDatabase, getStats } = await import('../lib/store-sqlite.ts');
  const db = openDatabase(config.dbPath);
  const stats = getStats(db);
  db.close();

  console.log('MIKAI Knowledge Base Status');
  console.log('────────────────────────────');
  console.log(`Sources: ${stats.totalSources}`);
  for (const [type, count] of Object.entries(stats.sourcesByType)) {
    console.log(`  ${type}: ${count}`);
  }
  console.log(`\nNodes: ${stats.totalNodes}`);
  console.log(`Segments: ${stats.totalSegments}`);
  console.log(`\nLast ingestion: ${stats.lastIngestion ?? 'never'}`);
  console.log(`Last segmentation: ${stats.lastSegmentation ?? 'never'}`);
}

// ── SERVE (delegates to MCP server) ─────────────────────────────────────────

async function cmdServe() {
  // Set env flag so server.ts knows to use SQLite
  process.env.MIKAI_LOCAL = 'true';
  const config = loadConfig();
  if (config?.anthropicKey) process.env.ANTHROPIC_API_KEY = config.anthropicKey;

  // Dynamic import of the MCP server — it handles its own startup
  await import('../surfaces/mcp/server.ts');
}

// ── Main ────────────────────────────────────────────────────────────────────

const command = process.argv[2];

const commands = {
  init: cmdInit,
  serve: cmdServe,
  sync: cmdSync,
  build: cmdBuild,
  status: cmdStatus,
  'sync-and-build': cmdSyncAndBuild,
};

if (!command || !commands[command]) {
  console.log(`Usage: mikai <command>

Commands:
  init     Create ~/.mikai/, set up database, configure Claude Desktop
  serve    Start the MCP server (stdio transport)
  sync     Sync Apple Notes + import folder
  build    Extract graph + segments + score nodes
  status   Show knowledge base stats
`);
  process.exit(command ? 1 : 0);
}

commands[command]().catch(err => {
  console.error(`Error: ${err.message}`);
  process.exit(1);
});
