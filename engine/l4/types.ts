/**
 * engine/l4/types.ts
 *
 * L4 Task-State Awareness types.
 *
 * A "thread" is a topic or concern tracked across multiple apps and sources.
 * L4 sits on top of L3's knowledge graph, consuming nodes, segments, and
 * sources as inputs to detect threads, classify their state, and infer
 * next steps.
 *
 * State machine: exploring → evaluating → decided → acting → stalled → completed
 */

// ── Thread States ────────────────────────────────────────────────────────────

export const THREAD_STATES = [
  'exploring',   // gathering info, no direction yet
  'evaluating',  // comparing options, weighing tradeoffs
  'decided',     // made a choice but hasn't acted
  'acting',      // actively working on it
  'stalled',     // was acting but activity dropped off
  'completed',   // done — confirmed resolution
] as const;

export type ThreadState = typeof THREAD_STATES[number];

// Valid state transitions (forward + stall/unstall)
export const VALID_TRANSITIONS: Record<ThreadState, ThreadState[]> = {
  exploring:  ['evaluating', 'decided', 'acting', 'stalled', 'completed'],
  evaluating: ['decided', 'acting', 'stalled', 'completed'],
  decided:    ['acting', 'stalled', 'completed'],
  acting:     ['stalled', 'completed'],
  stalled:    ['exploring', 'evaluating', 'decided', 'acting', 'completed'],
  completed:  [], // terminal
};

// ── Thread ───────────────────────────────────────────────────────────────────

export interface Thread {
  id: string;
  label: string;                    // human-readable thread name
  summary: string | null;           // auto-generated summary
  state: ThreadState;
  state_changed_at: string | null;
  first_seen_at: string;            // earliest source timestamp
  last_activity_at: string;         // most recent source activity
  source_count: number;             // how many sources contribute
  source_types: string;             // JSON array of source types involved
  next_step: string | null;         // LLM-inferred next action
  next_step_generated_at: string | null;
  confidence: number;               // confidence in state classification (0-1)
  stall_probability: number;        // computed stall score (0-1)
  resolved_at: string | null;
  created_at: string;
  // Delivery fields (L4 research integration)
  delivery_score: number;           // Sumimasen gate score (0-1)
  dismissed_count: number;          // PPP training signal
  acted_count: number;              // PPP training signal
  last_surfaced_at: string | null;  // cooldown tracking
  edge_types_within: string;        // JSON array of L3 edge types in thread
  action_category: string | null;   // last inferred OmniActions category
}

export interface ThreadInsert {
  label: string;
  summary?: string;
  state?: ThreadState;
  first_seen_at: string;
  last_activity_at: string;
  source_count?: number;
  source_types?: string[];
  confidence?: number;
}

// ── Thread Members ───────────────────────────────────────────────────────────
// Links threads to their constituent L3 entities

export type ContributionType = 'origin' | 'evidence' | 'action' | 'stall_signal' | 'resolution';

export interface ThreadMember {
  id: string;
  thread_id: string;
  source_id: string | null;
  node_id: string | null;
  segment_id: string | null;
  contribution_type: ContributionType;
  created_at: string;
}

export interface ThreadMemberInsert {
  thread_id: string;
  source_id?: string;
  node_id?: string;
  segment_id?: string;
  contribution_type: ContributionType;
}

// ── State Transitions ────────────────────────────────────────────────────────

export interface ThreadTransition {
  id: string;
  thread_id: string;
  from_state: ThreadState | null;
  to_state: ThreadState;
  reason: string | null;            // what triggered the transition
  evidence_node_id: string | null;  // which node triggered it
  created_at: string;
}

// ── Thread Edges (L4 relationships between threads) ──────────────────────────

export const THREAD_EDGE_TYPES = [
  'led_to',        // this thread's resolution spawned the other
  'blocked_by',    // can't progress until the other resolves
  'resumed_from',  // re-activated version of a stalled thread
  'resolved_by',   // the other thread's outcome resolved this one
] as const;

export type ThreadEdgeType = typeof THREAD_EDGE_TYPES[number];

export interface ThreadEdge {
  id: string;
  from_thread: string;
  to_thread: string;
  relationship: ThreadEdgeType;
  note: string | null;
  created_at: string;
}

// ── Detection types ──────────────────────────────────────────────────────────

export interface SegmentCluster {
  segments: { id: string; source_id: string; source_type: string; topic_label: string; content: string }[];
  centroid_label: string;
  source_types: Set<string>;
}

// ── Classification signals ───────────────────────────────────────────────────

export interface ClassificationSignals {
  source_type_count: number;
  has_comparison_language: boolean;
  has_decision_language: boolean;
  has_action_evidence: boolean;
  days_since_last_activity: number;
  activity_frequency: number;        // activities per week
  has_resolution_signal: boolean;
  stall_probability: number;
  node_types_involved: string[];
  // Graph enrichment signals (from L3 edges within thread)
  graph_edge_types: string[];
  has_contradiction_edges: boolean;
  has_dependency_chain: boolean;
  has_support_chain: boolean;
}

// ── Graph enrichment signals ─────────────────────────────────────────────────

export interface GraphSignals {
  hasEdges: boolean;
  edgeTypes: string[];
  edgeCount: number;
  graphConfidenceBoost: number;       // 0 or 0.15 if graph edges found
}

// ── Action categories (OmniActions taxonomy) ─────────────────────────────────

export const ACTION_CATEGORIES = [
  'search',     // look up more information
  'create',     // draft a message, document, or task
  'capture',    // save, bookmark, screenshot
  'share',      // send to someone, post
  'schedule',   // set reminder, book, add deadline
  'navigate',   // open reference, switch to app
  'configure',  // update a list, modify a plan
] as const;

export type ActionCategory = typeof ACTION_CATEGORIES[number];

// ── Next-step inference ──────────────────────────────────────────────────────

export interface NextStepResult {
  thread_id: string;
  next_step: string;
  action_category: ActionCategory | null;
  reasoning: string;
  confidence: number;
  generated_at: string;
}

// ── Delivery events (PPP training signal) ────────────────────────────────────

export const USER_RESPONSES = ['acted', 'dismissed', 'ignored', 'deferred'] as const;
export type UserResponse = typeof USER_RESPONSES[number];

export interface DeliveryEvent {
  id: string;
  thread_id: string;
  next_step: string;
  action_category: ActionCategory | null;
  delivery_score: number;
  user_response: UserResponse | null;
  response_at: string | null;
  delivered_at: string;
}

export interface DeliveryEventInsert {
  thread_id: string;
  next_step: string;
  action_category?: ActionCategory | null;
  delivery_score?: number;
}
