/**
 * engine/ingestion/ingest-direct.ts
 *
 * Standalone ingestion module — writes directly to Supabase without requiring
 * the Next.js dev server. Replicates the exact chunking + upsert logic from
 * app/api/ingest/batch/route.ts.
 *
 * Usage:
 *   import { ingestNotes } from './ingest-direct.ts';
 *   const results = await ingestNotes(notes);
 */

import fs from 'fs';
import path from 'path';
import { createHash } from 'crypto';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Env loader (same pattern as sync scripts) ─────────────────────────────────

function readEnvFile(filePath: string): Record<string, string> {
  const env: Record<string, string> = {};
  try {
    for (const line of fs.readFileSync(filePath, 'utf8').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx < 0) continue;
      env[trimmed.slice(0, eqIdx).trim()] = trimmed.slice(eqIdx + 1).trim();
    }
  } catch { /* file not found — env stays empty */ }
  return env;
}

function loadEnv(): void {
  const envPath = path.join(__dirname, '../../.env.local');
  const env = readEnvFile(envPath);
  for (const [key, value] of Object.entries(env)) {
    if (!process.env[key]) process.env[key] = value;
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

const VALID_TYPES = ['llm_thread', 'note', 'voice', 'web_clip', 'document'] as const;
type SourceType = typeof VALID_TYPES[number];

const VALID_SOURCES = ['apple-notes', 'claude-thread', 'perplexity', 'browser', 'manual', 'imessage', 'gmail', 'other'] as const;
type SourceOrigin = typeof VALID_SOURCES[number];

export interface NoteInput {
  content: string;
  label: string;
  type: string;
  source: string;
  source_id?: string;
}

export interface IngestResult {
  source_id?: string;
  label: string;
  chunks?: number;
  error?: string;
}

// ── Chunking — identical to lib/ingest-pipeline.ts chunkContent() ─────────────

function chunkContent(text: string): string[] {
  const paragraphs = text.split(/\n{2,}/).map((p) => p.trim()).filter((p) => p.length > 40);
  const chunks: string[] = [];
  let current = '';

  for (const para of paragraphs) {
    const wordCount = (current + ' ' + para).split(/\s+/).length;
    if (wordCount > 600 && current) {
      chunks.push(current.trim());
      current = para;
    } else {
      current = current ? current + '\n\n' + para : para;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks.length > 0 ? chunks : [text.trim()];
}

// ── Supabase REST client (no @/ imports, no SDK required) ─────────────────────

interface SupabaseClient {
  insert(table: string, row: Record<string, unknown>): Promise<{ data: { id: string } | null; error: { message: string } | null }>;
  update(table: string, values: Record<string, unknown>, matchCol: string, matchVal: string): Promise<{ error: { message: string } | null }>;
}

function createSupabaseClient(supabaseUrl: string, supabaseKey: string): SupabaseClient {
  const headers = {
    'Content-Type': 'application/json',
    'apikey': supabaseKey,
    'Authorization': `Bearer ${supabaseKey}`,
    'Prefer': 'return=representation',
  };

  return {
    async insert(table, row) {
      const res = await fetch(`${supabaseUrl}/rest/v1/${table}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(row),
      });
      if (!res.ok) {
        const text = await res.text();
        return { data: null, error: { message: `HTTP ${res.status}: ${text}` } };
      }
      const rows = await res.json();
      const data = Array.isArray(rows) ? rows[0] : rows;
      return { data: data ?? null, error: null };
    },

    async update(table, values, matchCol, matchVal) {
      const res = await fetch(`${supabaseUrl}/rest/v1/${table}?${matchCol}=eq.${encodeURIComponent(matchVal)}`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify(values),
      });
      if (!res.ok) {
        const text = await res.text();
        return { error: { message: `HTTP ${res.status}: ${text}` } };
      }
      return { error: null };
    },
  };
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Ingests an array of notes directly into Supabase, without requiring the
 * Next.js dev server. Replicates the logic in POST /api/ingest/batch.
 *
 * @param rawNotes - Array of notes to ingest
 * @returns Array of per-note results (source_id + chunk count, or error)
 */
export async function ingestNotes(rawNotes: NoteInput[]): Promise<IngestResult[]> {
  loadEnv();

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    throw new Error('SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env.local');
  }

  const db = createSupabaseClient(supabaseUrl, supabaseKey);

  if (!Array.isArray(rawNotes) || rawNotes.length === 0) {
    return [];
  }

  // Normalize and filter — same logic as the API route
  const notes = rawNotes
    .map((n) => ({
      content: n.content?.trim() ?? '',
      label: n.label?.trim() || 'Untitled',
      type: (VALID_TYPES.includes(n.type as SourceType) ? n.type : 'note') as SourceType,
      source: (VALID_SOURCES.includes(n.source as SourceOrigin) ? n.source : 'other') as SourceOrigin,
      source_id: n.source_id,
    }))
    .filter((n) => n.content.length >= 50);

  if (notes.length === 0) return [];

  // Step 1: Create source records
  const sourceInserts = await Promise.all(
    notes.map((n) => {
      if (n.source_id) {
        return Promise.resolve({ data: { id: n.source_id }, error: null });
      }
      const content_hash = createHash('sha256').update(n.content).digest('hex');
      return db.insert('sources', {
        type: n.type,
        label: n.label,
        raw_content: n.content,
        source: n.source,
        content_hash,
      });
    })
  );

  // Step 2: Chunk and update chunk_count
  const results: IngestResult[] = [];

  for (let i = 0; i < notes.length; i++) {
    const note = notes[i];
    const { data: source, error: sourceError } = sourceInserts[i];

    if (sourceError || !source) {
      results.push({ label: note.label, error: sourceError?.message ?? 'source insert failed' });
      continue;
    }

    const chunks = chunkContent(note.content);

    const { error: updateError } = await db.update('sources', { chunk_count: chunks.length }, 'id', source.id);

    if (updateError) {
      console.error(`ingest-direct: failed to update chunk_count for "${note.label}":`, updateError.message);
    }

    results.push({
      source_id: source.id,
      label: note.label,
      chunks: chunks.length,
    });
  }

  return results;
}
