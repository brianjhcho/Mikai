/**
 * lib/embeddings-local.ts
 *
 * Local ONNX embeddings via @huggingface/transformers.
 * Uses Nomic nomic-embed-text-v1.5 (768-dim).
 *
 * Model is lazy-loaded: import does NOT trigger download.
 * First call to embedText() or embedDocuments() downloads the model
 * (~130MB, cached in ~/.cache/huggingface/).
 *
 * This is the default embedding provider for the `npx @mikai/mcp` path.
 * The existing Voyage AI path (lib/embeddings.ts) remains for npm run scripts.
 */

let embedder: any = null;

async function getEmbedder(): Promise<any> {
  if (!embedder) {
    const { pipeline, env } = await import('@huggingface/transformers');
    // Disable local model check warning
    env.allowLocalModels = true;
    process.stderr.write('MIKAI: Loading embedding model (first run downloads ~130MB)...\n');
    embedder = await pipeline('feature-extraction', 'nomic-ai/nomic-embed-text-v1.5', {
      dtype: 'q8',  // quantized for smaller download + faster inference
    });
    process.stderr.write('MIKAI: Embedding model ready.\n');
  }
  return embedder;
}

/**
 * Embed a single text (query mode).
 * Returns a 768-dimensional number array.
 */
export async function embedText(text: string): Promise<number[]> {
  const pipe = await getEmbedder();
  const output = await pipe(text, { pooling: 'mean', normalize: true });
  return Array.from(output.data as Float32Array).slice(0, 768);
}

/**
 * Embed multiple texts (document mode).
 * Returns an array of 768-dimensional number arrays.
 * Processes in batches of BATCH_SIZE for speed while staying within memory.
 */
const EMBED_BATCH_SIZE = 12;

export async function embedDocuments(texts: string[]): Promise<number[][]> {
  const pipe = await getEmbedder();
  const results: number[][] = [];

  for (let i = 0; i < texts.length; i += EMBED_BATCH_SIZE) {
    const batch = texts.slice(i, i + EMBED_BATCH_SIZE);
    // Process batch concurrently — ONNX handles internal parallelism
    const batchResults = await Promise.all(
      batch.map(async (text) => {
        const output = await pipe(text, { pooling: 'mean', normalize: true });
        return Array.from(output.data as Float32Array).slice(0, 768);
      })
    );
    results.push(...batchResults);
  }

  return results;
}

/**
 * Pre-download the model without embedding anything.
 * Used by the init wizard to trigger the download upfront.
 */
export async function warmup(): Promise<void> {
  await getEmbedder();
}
