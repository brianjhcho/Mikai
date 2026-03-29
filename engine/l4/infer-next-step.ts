/**
 * engine/l4/infer-next-step.ts
 *
 * LLM-powered next-step inference — the noonchi moment.
 *
 * Given a thread's current state, trajectory, and content context,
 * infers the logical next action the user should take.
 *
 * This is the ONE place in L4 that uses an LLM call.
 * Uses Claude Haiku for speed and cost efficiency.
 */

import Anthropic from '@anthropic-ai/sdk';
import type Database from 'better-sqlite3';
import {
  getActiveThreads, getStalledThreads, getThreadMembers,
  getTransitionHistory, updateThread,
} from './store.js';
import type { Thread, NextStepResult, ThreadState, ActionCategory } from './types.js';
import { ACTION_CATEGORIES } from './types.js';

// ── Configuration ────────────────────────────────────────────────────────────

const MODEL = 'claude-haiku-4-5-20251001';
const MAX_CONTEXT_TOKENS = 2000;   // keep prompt compact
const MAX_THREADS_PER_RUN = 15;    // budget: ~15 Haiku calls per cycle

// ── Client ───────────────────────────────────────────────────────────────────

let client: Anthropic | null = null;

function getClient(): Anthropic {
  if (!client) {
    client = new Anthropic(); // reads ANTHROPIC_API_KEY from env
  }
  return client;
}

// ── Context builder ──────────────────────────────────────────────────────────

function buildThreadContext(db: Database.Database, thread: Thread): string {
  const members = getThreadMembers(db, thread.id);
  const transitions = getTransitionHistory(db, thread.id);

  // Gather segment content (most recent first, truncated to budget)
  const segmentIds = members.filter(m => m.segment_id).map(m => m.segment_id!);
  let segmentContent = '';
  if (segmentIds.length > 0) {
    const placeholders = segmentIds.map(() => '?').join(',');
    const segments = db.prepare(`
      SELECT topic_label, processed_content, created_at FROM segments
      WHERE id IN (${placeholders})
      ORDER BY created_at DESC
    `).all(...segmentIds) as { topic_label: string; processed_content: string; created_at: string }[];

    // Truncate to fit budget
    let charBudget = MAX_CONTEXT_TOKENS * 3; // rough chars-to-tokens
    for (const seg of segments) {
      if (charBudget <= 0) break;
      const chunk = `[${seg.topic_label}] ${seg.processed_content}\n`;
      segmentContent += chunk.slice(0, charBudget);
      charBudget -= chunk.length;
    }
  }

  // Gather node labels for additional context
  const nodeIds = members.filter(m => m.node_id).map(m => m.node_id!);
  let nodeContext = '';
  if (nodeIds.length > 0) {
    const placeholders = nodeIds.map(() => '?').join(',');
    const nodes = db.prepare(`
      SELECT label, node_type FROM nodes WHERE id IN (${placeholders}) LIMIT 20
    `).all(...nodeIds) as { label: string; node_type: string }[];
    nodeContext = nodes.map(n => `- ${n.node_type}: ${n.label}`).join('\n');
  }

  // State trajectory
  const trajectory = transitions.length > 0
    ? transitions.map(t => `${t.from_state ?? '(new)'} → ${t.to_state}: ${t.reason ?? 'no reason'}`).join('\n')
    : 'No state changes yet (initial state)';

  const sourceTypes: string[] = JSON.parse(thread.source_types || '[]');

  return [
    `Thread: ${thread.label}`,
    `Current state: ${thread.state}`,
    `Active since: ${thread.first_seen_at}`,
    `Last activity: ${thread.last_activity_at}`,
    `Sources: ${sourceTypes.join(', ') || 'unknown'}`,
    `Source count: ${thread.source_count}`,
    '',
    '--- State trajectory ---',
    trajectory,
    '',
    '--- Related concepts ---',
    nodeContext || '(none)',
    '',
    '--- Content (most recent) ---',
    segmentContent || '(no content available)',
  ].join('\n');
}

// ── Action category parser ──────────────────────────────────────────────

function parseActionCategory(text: string): ActionCategory | null {
  const match = text.match(/^\[(\w+)\]/i);
  if (!match) return null;
  const raw = match[1].toLowerCase();
  if (ACTION_CATEGORIES.includes(raw as ActionCategory)) {
    return raw as ActionCategory;
  }
  return null;
}

// ── Inference ────────────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are a task-state awareness engine. Given a user's "thread" — a topic they're tracking across multiple apps — you infer the single most useful next step they should take.

Action categories (choose exactly one):
- Search: look up more information about the topic
- Create: draft a message, document, or task
- Capture: save, bookmark, or archive something
- Share: send something to someone
- Schedule: set a reminder, book something, add a deadline
- Navigate: open a reference or switch to an app
- Configure: update a list, modify a plan

Rules:
- First identify the action category, then the specific concrete step.
- Be specific and actionable. "Think about X" is useless. "Draft a message to Y about Z" is good.
- Match the thread's state:
  - exploring: Search or Navigate actions
  - evaluating: Search or Create (comparison document) actions
  - decided: Create or Share actions (execute the decision)
  - acting: Create, Share, or Schedule actions (continue the work)
  - stalled: any action that unblocks — often Search, Share, or Schedule
- Format your response as: [CATEGORY] Specific action description
- Keep to 1-2 sentences max.
- If there's genuinely not enough context, say "Not enough context to suggest a next step."
- Never suggest the user "review" or "reflect" — they came to you for forward momentum.`;

async function inferForThread(db: Database.Database, thread: Thread): Promise<NextStepResult | null> {
  const context = buildThreadContext(db, thread);
  const anthropic = getClient();

  try {
    const response = await anthropic.messages.create({
      model: MODEL,
      max_tokens: 200,
      system: SYSTEM_PROMPT,
      messages: [{
        role: 'user',
        content: `What should I do next on this thread?\n\n${context}`,
      }],
    });

    const text = response.content
      .filter(block => block.type === 'text')
      .map(block => (block as { type: 'text'; text: string }).text)
      .join('');

    if (!text || text.includes('Not enough context')) return null;

    const now = new Date().toISOString();

    // Parse action category from [CATEGORY] prefix
    const actionCategory = parseActionCategory(text);
    const cleanedStep = text.replace(/^\[(?:SEARCH|CREATE|CAPTURE|SHARE|SCHEDULE|NAVIGATE|CONFIGURE)\]\s*/i, '').trim();

    // Persist to thread
    updateThread(db, thread.id, {
      next_step: cleanedStep,
      next_step_generated_at: now,
      action_category: actionCategory,
    } as any);

    return {
      thread_id: thread.id,
      next_step: cleanedStep,
      action_category: actionCategory,
      reasoning: `State: ${thread.state}, Sources: ${thread.source_count}`,
      confidence: thread.state === 'stalled' ? 0.6 : 0.75,
      generated_at: now,
    };
  } catch (err) {
    process.stderr.write(`L4 inference error for thread ${thread.id}: ${err}\n`);
    return null;
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────

export interface InferResult {
  threadsProcessed: number;
  nextStepsGenerated: number;
  errors: number;
  results?: NextStepResult[];
}

/**
 * Run next-step inference.
 * If threadIds is provided (from evaluation gate), only process those threads.
 * Otherwise falls back to stalled + active thread selection.
 */
export async function inferNextSteps(db: Database.Database, threadIds?: string[]): Promise<InferResult> {
  let threads: Thread[];

  if (threadIds && threadIds.length > 0) {
    // Gate-selected threads
    threads = threadIds
      .map(id => db.prepare('SELECT * FROM threads WHERE id = ?').get(id) as Thread | undefined)
      .filter((t): t is Thread => t !== undefined);
  } else {
    // Fallback: prioritize stalled, then active
    const stalled = getStalledThreads(db, 0.3, 5);
    const active = getActiveThreads(db, MAX_THREADS_PER_RUN);
    const seen = new Set<string>();
    threads = [];
    for (const t of [...stalled, ...active]) {
      if (seen.has(t.id)) continue;
      seen.add(t.id);
      threads.push(t);
      if (threads.length >= MAX_THREADS_PER_RUN) break;
    }
  }

  let nextStepsGenerated = 0;
  let errors = 0;
  const results: NextStepResult[] = [];

  // Process sequentially to respect rate limits
  for (const thread of threads) {
    const result = await inferForThread(db, thread);
    if (result) {
      nextStepsGenerated++;
      results.push(result);
    } else {
      errors++;
    }
  }

  return {
    threadsProcessed: threads.length,
    nextStepsGenerated,
    errors,
    results,
  };
}

// ── Single thread inference (for MCP tool use) ──────────────────────────────

export async function inferForSingleThread(
  db: Database.Database,
  threadId: string,
): Promise<NextStepResult | null> {
  const thread = db.prepare('SELECT * FROM threads WHERE id = ?').get(threadId) as Thread | undefined;
  if (!thread) return null;
  return inferForThread(db, thread);
}
