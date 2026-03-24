#!/usr/bin/env tsx
/**
 * engine/ingestion/ingest-cli.ts
 *
 * CLI wrapper around ingest-direct.ts. Ingests notes directly to Supabase
 * without requiring the Next.js dev server.
 *
 * Usage:
 *   # Via --notes flag (JSON array of notes):
 *   npx tsx engine/ingestion/ingest-cli.ts --notes '[{"content":"...","label":"...","type":"note","source":"manual"}]'
 *
 *   # Via stdin (JSON object with notes array):
 *   echo '{"notes":[{"content":"...","label":"...","type":"note","source":"manual"}]}' | npx tsx engine/ingestion/ingest-cli.ts
 *
 *   # Via npm script:
 *   npm run ingest -- --notes '[...]'
 */

import { ingestNotes, type NoteInput } from './ingest-direct.ts';

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  let notes: NoteInput[] | null = null;

  // ── --notes '[...]' flag ───────────────────────────────────────────────────
  const notesIdx = args.indexOf('--notes');
  if (notesIdx !== -1 && args[notesIdx + 1]) {
    try {
      const parsed = JSON.parse(args[notesIdx + 1]);
      notes = Array.isArray(parsed) ? parsed : parsed.notes;
    } catch (err) {
      console.error('Failed to parse --notes JSON:', (err as Error).message);
      process.exit(1);
    }
  }

  // ── stdin ─────────────────────────────────────────────────────────────────
  if (!notes && !process.stdin.isTTY) {
    const chunks: Buffer[] = [];
    for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
    const raw = Buffer.concat(chunks).toString('utf8').trim();
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        notes = Array.isArray(parsed) ? parsed : parsed.notes;
      } catch (err) {
        console.error('Failed to parse stdin JSON:', (err as Error).message);
        process.exit(1);
      }
    }
  }

  if (!notes || notes.length === 0) {
    console.error('No notes provided. Use --notes \'[...]\' or pipe JSON to stdin.');
    console.error('');
    console.error('Examples:');
    console.error('  npx tsx engine/ingestion/ingest-cli.ts --notes \'[{"content":"...","label":"...","type":"note","source":"manual"}]\'');
    console.error('  echo \'{"notes":[...]}\' | npx tsx engine/ingestion/ingest-cli.ts');
    process.exit(1);
  }

  console.log(`Ingesting ${notes.length} note(s) directly to Supabase...`);

  const results = await ingestNotes(notes);

  let succeeded = 0;
  let failed = 0;

  for (const r of results) {
    if (r.error) {
      console.error(`  x ${r.label} — ${r.error}`);
      failed++;
    } else {
      console.log(`  + ${r.label}  (chunks: ${r.chunks}, id: ${r.source_id})`);
      succeeded++;
    }
  }

  console.log(`\nDone. ${succeeded} ingested, ${failed} failed.`);

  if (failed > 0) process.exit(1);
}

main().catch((err) => {
  console.error('Fatal:', (err as Error).message);
  process.exit(1);
});
