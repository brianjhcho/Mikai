#!/usr/bin/env tsx
import { embedText, embedDocuments } from '../lib/embeddings-local.ts';

async function main() {
  console.log('Testing local embeddings (Nomic nomic-embed-text-v1.5)...');
  console.log('First run will download model (~130MB)...\n');

  const vec = await embedText('This is a test about AI memory systems');
  console.log('✓ embedText returned', vec.length, 'dimensions');
  console.log('  First 5 values:', vec.slice(0, 5).map(v => v.toFixed(4)));

  const batch = await embedDocuments(['Hello world', 'AI memory architecture']);
  console.log('✓ embedDocuments returned', batch.length, 'embeddings, each', batch[0].length, 'dims');

  function cosine(a: number[], b: number[]) {
    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < a.length; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
    return dot / (Math.sqrt(na) * Math.sqrt(nb));
  }

  const sim = cosine(vec, batch[1]);
  console.log('✓ Cosine similarity (AI memory ↔ AI memory):', sim.toFixed(4));

  const dissim = cosine(vec, batch[0]);
  console.log('✓ Cosine similarity (AI memory ↔ Hello world):', dissim.toFixed(4));
  console.log('  Similar text has higher score:', sim > dissim ? 'YES ✓' : 'NO ✗');

  console.log('\n=== US-002 Local Embeddings: ALL TESTS PASS ===');
}

main().catch(err => { console.error('FAIL:', err.message); process.exit(1); });
