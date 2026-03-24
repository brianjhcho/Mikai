import Anthropic from '@anthropic-ai/sdk';

export const VALID_TYPES = ['llm_thread', 'note', 'voice', 'web_clip', 'document'] as const;
export type SourceType = typeof VALID_TYPES[number];

export const VALID_SOURCES = ['apple-notes', 'claude-thread', 'perplexity', 'browser', 'manual', 'imessage', 'gmail', 'other'] as const;
export type SourceOrigin = typeof VALID_SOURCES[number];

export interface ExtractedNode {
  label: string;
  type: 'concept' | 'project' | 'resource' | 'question' | 'decision' | 'tension';
  content: string;
}

export interface ExtractedEdge {
  from_label: string;
  to_label: string;
  relationship: 'supports' | 'contradicts' | 'extends' | 'questions' | 'depends_on' | 'unresolved_tension' | 'partially_answers';
  note?: string;
}

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! });

/**
 * Splits content into paragraph-based chunks.
 * Merges short paragraphs, caps at ~600 words per chunk.
 */
export function chunkContent(text: string): string[] {
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

/**
 * Uses Claude to extract nodes and edges from the raw content.
 * Returns structured JSON with node labels, types, and relationships.
 * Times out after 30s to prevent hanging.
 */
export async function extractGraph(
  content: string,
  label: string
): Promise<{ nodes: ExtractedNode[]; edges: ExtractedEdge[] }> {
  const truncated = content.slice(0, 8000);

  const extraction = anthropic.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 4096,
    system: `You are extracting a reasoning map from a personal note written by a specific individual. Your goal is not to summarize topics — it is to capture the structure of their thinking: what they are trying to resolve, what tensions exist, what conclusions they've reached, and what questions remain open.

Node types:
- concept: an idea, belief, or mental model the person is working with
- question: something unresolved they are circling — use this liberally
- decision: a conclusion or commitment they have reached
- tension: a contradiction or tradeoff they are holding
- project: a specific initiative or goal they are pursuing

Edge types:
- supports: one node provides evidence or reasoning for another
- contradicts: one node conflicts with or undermines another
- unresolved_tension: two nodes are in active conflict without resolution
- partially_answers: one node addresses but doesn't fully resolve a question
- extends: one node builds on or deepens another
- depends_on: one node requires another to be true first

Return ONLY valid JSON:
{
  "nodes": [
    { "label": "short label", "type": "concept|question|decision|tension|project", "content": "one sentence capturing the person's actual thinking, not a generic description" }
  ],
  "edges": [
    { "from_label": "label1", "to_label": "label2", "relationship": "edge_type", "note": "one phrase explaining why this relationship exists" }
  ]
}

Rules:
- Extract 3–7 nodes. Prefer depth over coverage.
- Labels must be 2–5 words, written as the person would think them — not academic categories.
- At least one node must be type "question" or "tension" unless the note is purely factual.
- Edges must carry a "note" field explaining the relationship — not just labeling it.
- Write content fields in first person where the note is personal ("I'm trying to figure out..." not "The author considers...").
- If the note contains a genuine unresolved conflict, name it explicitly as a tension node.`,
    messages: [
      {
        role: 'user',
        content: `Source label: "${label}"\nAuthor context: This is a personal note from a founder building an AI knowledge infrastructure product, based in Nairobi. The notes span strategic thinking, personal reflection, and research.\n\nContent:\n${truncated}`,
      },
    ],
  });

  // 30s timeout
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('Claude extraction timed out after 30s')), 30_000)
  );

  let message: Awaited<typeof extraction>;
  try {
    message = await Promise.race([extraction, timeout]);
  } catch (err) {
    console.error('extractGraph error:', (err as Error).message);
    return { nodes: [], edges: [] };
  }

  const text = message.content[0].type === 'text' ? message.content[0].text : '{}';

  try {
    const match = text.match(/\{[\s\S]*\}/);
    const parsed = JSON.parse(match?.[0] ?? '{}');
    return {
      nodes: parsed.nodes ?? [],
      edges: parsed.edges ?? [],
    };
  } catch {
    console.error('Claude extraction parse error:', text);
    return { nodes: [], edges: [] };
  }
}
