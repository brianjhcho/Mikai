const VOYAGE_API_KEY = process.env.VOYAGE_API_KEY!;
const VOYAGE_API_URL = 'https://api.voyageai.com/v1/embeddings';

/**
 * Calls Voyage AI REST API to generate embeddings.
 * @param texts - Array of strings to embed
 * @param inputType - 'query' for search queries, 'document' for content being indexed
 * @returns Array of 1024-dimensional float arrays
 */
async function embed(texts: string[], inputType: 'query' | 'document'): Promise<number[][]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);

  try {
    const response = await fetch(VOYAGE_API_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${VOYAGE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ model: 'voyage-3', input: texts, input_type: inputType }),
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Voyage AI error ${response.status}: ${error}`);
    }

    const data = await response.json();
    return data.data.map((item: { embedding: number[] }) => item.embedding);
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Voyage AI request timed out after 30s');
    }
    throw err;
  }
}

/**
 * Generates a vector embedding for a search query using Voyage AI voyage-3.
 * @param text - The query string to embed
 * @returns A 1024-dimensional float array
 */
export async function embedText(text: string): Promise<number[]> {
  const [embedding] = await embed([text], 'query');
  return embedding;
}

/**
 * Generates embeddings for a batch of documents using Voyage AI voyage-3.
 * @param texts - Array of document strings to embed
 * @returns Array of 1024-dimensional float arrays
 */
export async function embedDocuments(texts: string[]): Promise<number[][]> {
  return embed(texts, 'document');
}
