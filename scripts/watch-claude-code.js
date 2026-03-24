#!/usr/bin/env node
/**
 * scripts/watch-claude-code.js
 *
 * Watches ~/.claude/projects/ for new or modified Claude Code .jsonl session files.
 * When a session file is detected or updated, parses the conversation and ingests
 * it into MIKAI via the direct ingest module (no Next.js dev server required).
 *
 * Usage:
 *   node scripts/watch-claude-code.js
 *   npm run watch:claude-code
 *
 * One-shot scan (all unsynced sessions):
 *   node scripts/watch-claude-code.js --scan
 *
 * State:
 *   scripts/.claude-code-synced.json — tracks { [sessionId]: { size, ingestedAt } }
 *   On modification, only sessions whose file size has changed are re-processed.
 *
 * JSONL format (Claude Code):
 *   Each line is a JSON object. We extract:
 *     - type: "user", message.content is a string  → user message
 *     - type: "assistant", message.content[].type === "text" → assistant text
 *   We skip: tool_use, tool_result, thinking, progress, file-history-snapshot, etc.
 */

import fs   from 'fs';
import path from 'path';
import os   from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT      = path.join(__dirname, '..');

const CLAUDE_PROJECTS_DIR = path.join(os.homedir(), '.claude', 'projects');
const STATE_FILE          = path.join(__dirname, '.claude-code-synced.json');
const DEBOUNCE_MS         = 5000;

const SCAN_MODE = process.argv.includes('--scan');

// ── State helpers ─────────────────────────────────────────────────────────────

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch {
    return {};
  }
}

function saveState(state) {
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

// ── JSONL parser ──────────────────────────────────────────────────────────────

/**
 * Parse a Claude Code .jsonl file into a list of { sender, text, created_at }.
 * Returns null if the file yields fewer than 2 messages (not worth ingesting).
 */
function parseSession(filePath) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    console.error(`  Read error: ${err.message}`);
    return null;
  }

  const lines = raw.split('\n').filter((l) => l.trim());
  const messages = [];
  let sessionId   = null;
  let projectCwd  = null;
  let slug        = null;

  for (const line of lines) {
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      continue;
    }

    // Capture metadata from first entry that has it
    if (!sessionId && obj.sessionId)  sessionId  = obj.sessionId;
    if (!projectCwd && obj.cwd)       projectCwd = obj.cwd;
    if (!slug && obj.slug)            slug       = obj.slug;

    const type    = obj.type;
    const message = obj.message;
    if (!message) continue;

    const role      = message.role;
    const content   = message.content;
    const timestamp = obj.timestamp;

    // ── User messages ─────────────────────────────────────────────────────────
    // content is a plain string for real user prompts.
    // content is an array for tool_result payloads — skip those.
    if (type === 'user' && role === 'user' && typeof content === 'string' && content.trim()) {
      messages.push({
        sender:     'user',
        text:       content.trim(),
        created_at: timestamp || new Date().toISOString(),
      });
    }

    // ── Assistant messages ────────────────────────────────────────────────────
    // content is an array; extract only type:"text" blocks.
    if (type === 'assistant' && role === 'assistant' && Array.isArray(content)) {
      const textBlocks = content
        .filter((c) => c && c.type === 'text' && typeof c.text === 'string' && c.text.trim())
        .map((c) => c.text.trim())
        .join('\n\n');

      if (textBlocks) {
        messages.push({
          sender:     'assistant',
          text:       textBlocks,
          created_at: timestamp || new Date().toISOString(),
        });
      }
    }
  }

  if (messages.length < 2) return null;

  return { sessionId, projectCwd, slug, messages };
}

// ── Conversation builder ──────────────────────────────────────────────────────

/**
 * Build a MIKAI NoteInput from parsed session data.
 */
function buildNote(parsed, projectDirName) {
  const { sessionId, projectCwd, slug, messages } = parsed;

  // Derive title: slug (human-readable) > first user message > project dir name
  let title;
  if (slug) {
    // slug format: "foamy-prancing-bear" → "Foamy Prancing Bear"
    title = slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  } else {
    const firstUser = messages.find((m) => m.sender === 'user');
    if (firstUser) {
      title = firstUser.text.slice(0, 80).replace(/\n/g, ' ').trim();
      if (title.length === 80) title += '…';
    } else {
      title = projectDirName || sessionId || 'Claude Code Session';
    }
  }

  // Prefix with project cwd basename for context
  const projectName = projectCwd ? path.basename(projectCwd) : null;
  if (projectName && projectName !== title) {
    title = `[${projectName}] ${title}`;
  }

  // Build plain-text content: interleaved conversation
  const content = messages
    .map((m) => {
      const prefix = m.sender === 'user' ? 'User' : 'Claude';
      return `${prefix}: ${m.text}`;
    })
    .join('\n\n---\n\n');

  return {
    content,
    label:     title,
    type:      'llm_thread',
    source:    'claude-thread',
    source_id: undefined,  // let ingest-direct generate a UUID + hash
  };
}

// ── Ingest ────────────────────────────────────────────────────────────────────

async function ingestSession(filePath, projectDirName, state) {
  const fileName = path.basename(filePath);
  const sessionId = fileName.replace('.jsonl', '');

  let stat;
  try {
    stat = fs.statSync(filePath);
  } catch {
    return;
  }

  const fileSize = stat.size;

  // Skip if unchanged
  const prev = state[sessionId];
  if (prev && prev.size === fileSize) {
    return;
  }

  console.log(`  Processing: ${fileName} (${(fileSize / 1024).toFixed(1)} KB)`);

  const parsed = parseSession(filePath);
  if (!parsed) {
    console.log(`  Skipped: fewer than 2 messages or unreadable`);
    state[sessionId] = { size: fileSize, ingestedAt: new Date().toISOString(), skipped: true };
    return;
  }

  const note = buildNote(parsed, projectDirName);
  console.log(`  Title: ${note.label}`);
  console.log(`  Messages: ${parsed.messages.length}`);

  try {
    // Dynamic import so tsx can resolve the TypeScript module at runtime
    const { ingestNotes } = await import('../engine/ingestion/ingest-direct.ts');
    const results = await ingestNotes([note]);

    for (const r of results) {
      if (r.error) {
        console.error(`  Ingest error: ${r.error}`);
      } else {
        console.log(`  Ingested: source_id=${r.source_id}, chunks=${r.chunks}`);
        state[sessionId] = {
          size:       fileSize,
          sourceId:   r.source_id,
          ingestedAt: new Date().toISOString(),
        };
      }
    }
  } catch (err) {
    console.error(`  Ingest failed: ${err.message}`);
  }
}

// ── Scan all project directories ──────────────────────────────────────────────

async function scanAll(state) {
  if (!fs.existsSync(CLAUDE_PROJECTS_DIR)) {
    console.error(`Claude projects dir not found: ${CLAUDE_PROJECTS_DIR}`);
    return;
  }

  const projectDirs = fs.readdirSync(CLAUDE_PROJECTS_DIR)
    .filter((name) => {
      const full = path.join(CLAUDE_PROJECTS_DIR, name);
      return fs.statSync(full).isDirectory();
    });

  console.log(`Scanning ${projectDirs.length} project director${projectDirs.length === 1 ? 'y' : 'ies'}...`);

  for (const dirName of projectDirs) {
    const dirPath = path.join(CLAUDE_PROJECTS_DIR, dirName);
    let files;
    try {
      files = fs.readdirSync(dirPath).filter((f) => f.endsWith('.jsonl'));
    } catch {
      continue;
    }

    for (const file of files) {
      await ingestSession(path.join(dirPath, file), dirName, state);
    }
  }

  saveState(state);
}

// ── Watcher ───────────────────────────────────────────────────────────────────

function startWatcher(state) {
  if (!fs.existsSync(CLAUDE_PROJECTS_DIR)) {
    console.error(`Claude projects dir not found: ${CLAUDE_PROJECTS_DIR}`);
    process.exit(1);
  }

  console.log(`Watching: ${CLAUDE_PROJECTS_DIR}`);
  console.log(`Debounce: ${DEBOUNCE_MS / 1000}s after last change\n`);

  // Map of filePath → debounce timer
  const pending = new Map();

  // Watch the top-level projects directory for new project subdirs
  fs.watch(CLAUDE_PROJECTS_DIR, { recursive: true }, (eventType, filename) => {
    if (!filename || !filename.endsWith('.jsonl')) return;

    // filename from recursive watch is relative: "projectDir/sessionId.jsonl"
    const fullPath = path.join(CLAUDE_PROJECTS_DIR, filename);
    const projectDirName = path.dirname(filename);

    // Debounce: reset timer on every event for this file
    if (pending.has(fullPath)) {
      clearTimeout(pending.get(fullPath));
    }

    const timer = setTimeout(async () => {
      pending.delete(fullPath);
      console.log(`\n[${new Date().toLocaleTimeString()}] Changed: ${filename}`);
      await ingestSession(fullPath, projectDirName, state);
      saveState(state);
    }, DEBOUNCE_MS);

    pending.set(fullPath, timer);
  });

  console.log('Watcher active. Ctrl+C to stop.\n');
}

// ── Entry point ───────────────────────────────────────────────────────────────

const state = loadState();

if (SCAN_MODE) {
  console.log(`[${new Date().toLocaleTimeString()}] One-shot Claude Code session scan\n`);
  await scanAll(state);
  console.log('\nScan complete.');
} else {
  // Run an initial scan to catch anything missed, then start watching
  console.log(`[${new Date().toLocaleTimeString()}] Claude Code session watcher starting...\n`);
  console.log('Running initial scan...');
  await scanAll(state);
  console.log('\nInitial scan complete. Starting file watcher...\n');
  startWatcher(state);
}
