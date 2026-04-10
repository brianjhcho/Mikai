/**
 * engine/l4/domain-config.ts
 *
 * Pluggable L4 domain configuration. Defines the state machine, thread
 * detection filters, classification rules, and delivery SLAs for a specific
 * use case. L3 is universal; L4 is domain-specific via this config.
 *
 * Two validated domains:
 *   - personal-projects (default): tracks active work, research, decisions
 *   - physio-office (planned): tracks patient journeys from inquiry to completion
 */

// ── Domain Config Type ──────────────────────────────────────────────────────

export interface DomainState {
  name: string;
  description: string;
  terminal: boolean;          // if true, thread won't be reclassified
}

export interface DomainConfig {
  id: string;
  name: string;
  description: string;

  /** Ordered states — first is default for new threads */
  states: DomainState[];

  /** Valid transitions: from_state → [to_states] */
  transitions: Record<string, string[]>;

  /** Node types that anchor thread detection (threads must contain at least one) */
  anchorNodeTypes: string[];

  /** Node types included as enrichment (added to threads but don't anchor them) */
  enrichmentNodeTypes: string[];

  /** Node types excluded from thread detection entirely */
  excludedNodeTypes: string[];

  /** Source types to include for node-based detection */
  nodeSourceTypes: string[];

  /** Source types whose content is research (action patterns discounted) */
  researchOnlySources: string[];

  /** Temporal thresholds */
  temporal: {
    /** Days since last activity to consider a thread stale */
    staleDays: number;
    /** Days since last activity to consider a thread dormant (resurfacing candidate) */
    dormantDays: number;
    /** Days of recency required to trust content-based action signals */
    actionRecencyDays: number;
  };

  /** Delivery SLAs (optional — personal use has no SLAs) */
  deliverySLA?: {
    /** Max hours before a thread in a given state should be surfaced */
    maxResponseHours: Record<string, number>;
  };
}

// ── Personal Projects Config ────────────────────────────────────────────────

export const PERSONAL_PROJECTS: DomainConfig = {
  id: 'personal-projects',
  name: 'Personal Projects',
  description: 'Active work, research, decisions, shopping journeys. State machine for things with goals and endpoints.',

  states: [
    { name: 'exploring', description: 'Gathering info, no direction yet', terminal: false },
    { name: 'evaluating', description: 'Comparing options, weighing tradeoffs', terminal: false },
    { name: 'decided', description: 'Made a choice but haven\'t acted', terminal: false },
    { name: 'acting', description: 'Actively working on it', terminal: false },
    { name: 'stalled', description: 'Was progressing but stopped — resurfacing candidate', terminal: false },
    { name: 'completed', description: 'Done — confirmed resolution', terminal: true },
  ],

  transitions: {
    exploring:  ['evaluating', 'decided', 'acting', 'stalled', 'completed'],
    evaluating: ['decided', 'acting', 'stalled', 'completed'],
    decided:    ['acting', 'stalled', 'completed'],
    acting:     ['stalled', 'completed'],
    stalled:    ['exploring', 'evaluating', 'decided', 'acting', 'completed'],
    completed:  [],
  },

  // Only create threads anchored by project/decision nodes or research segments
  anchorNodeTypes: ['project', 'decision'],
  enrichmentNodeTypes: ['question', 'concept', 'tension'],
  excludedNodeTypes: [],

  nodeSourceTypes: ['apple-notes', 'manual', 'imessage'],
  researchOnlySources: ['perplexity', 'claude-thread'],

  temporal: {
    staleDays: 7,
    dormantDays: 30,
    actionRecencyDays: 7,
  },
};

// ── Physio Office Config (planned) ──────────────────────────────────────────

export const PHYSIO_OFFICE: DomainConfig = {
  id: 'physio-office',
  name: 'Physio Office',
  description: 'Patient journeys from inquiry to treatment completion. SLA-driven delivery.',

  states: [
    { name: 'inquiry', description: 'Patient asked about a service', terminal: false },
    { name: 'booked', description: 'Appointment scheduled', terminal: false },
    { name: 'attended', description: 'Patient attended appointment', terminal: false },
    { name: 'treatment_plan', description: 'Treatment plan created', terminal: false },
    { name: 'active_treatment', description: 'Ongoing sessions', terminal: false },
    { name: 'follow_up', description: 'Post-treatment check-in needed', terminal: false },
    { name: 'completed', description: 'Treatment complete', terminal: true },
    { name: 'no_response', description: 'Patient hasn\'t responded — needs follow-up', terminal: false },
  ],

  transitions: {
    inquiry:          ['booked', 'no_response', 'completed'],
    booked:           ['attended', 'no_response', 'completed'],
    attended:         ['treatment_plan', 'follow_up', 'completed'],
    treatment_plan:   ['active_treatment', 'completed'],
    active_treatment: ['follow_up', 'completed'],
    follow_up:        ['completed', 'active_treatment'],
    no_response:      ['inquiry', 'booked', 'completed'],
    completed:        [],
  },

  anchorNodeTypes: ['patient', 'appointment', 'treatment_plan'],
  enrichmentNodeTypes: ['concern', 'service'],
  excludedNodeTypes: [],

  nodeSourceTypes: ['email', 'sms', 'booking'],
  researchOnlySources: [],

  temporal: {
    staleDays: 3,      // patient journeys move faster
    dormantDays: 14,
    actionRecencyDays: 3,
  },

  deliverySLA: {
    maxResponseHours: {
      inquiry: 48,       // respond to inquiry within 48h
      booked: 24,        // send reminder 24h before appointment
      no_response: 72,   // follow up after 72h of silence
      follow_up: 720,    // 30-day post-treatment check-in
    },
  },
};

// ── Config Registry ─────────────────────────────────────────────────────────

const CONFIGS: Record<string, DomainConfig> = {
  'personal-projects': PERSONAL_PROJECTS,
  'physio-office': PHYSIO_OFFICE,
};

/** Get domain config by ID. Defaults to personal-projects. */
export function getDomainConfig(id?: string): DomainConfig {
  return CONFIGS[id ?? 'personal-projects'] ?? PERSONAL_PROJECTS;
}

/** Get valid next states for a given current state */
export function getValidTransitions(config: DomainConfig, currentState: string): string[] {
  return config.transitions[currentState] ?? [];
}

/** Check if a state is terminal (thread won't be reclassified) */
export function isTerminalState(config: DomainConfig, state: string): boolean {
  return config.states.find(s => s.name === state)?.terminal ?? false;
}

/** Get the default state for new threads */
export function getDefaultState(config: DomainConfig): string {
  return config.states[0]?.name ?? 'exploring';
}
