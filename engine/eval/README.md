# MIKAI Test Suite

Unified testing system that consolidates all eval protocols into one automated runner.

## Quick Start

```bash
npm test              # Run all automated tests
npm run test:quick    # Pipeline health + cost only (fast, no LLM calls)
npm run test:segments # Segmentation quality only (uses Haiku, ~$0.02)
npm run test:retrieval # Retrieval quality only (requires dev server)
npm run test:cost     # Cost tracking only
```

You can also combine flags directly:

```bash
tsx engine/eval/test-suite.ts --pipeline --cost
tsx engine/eval/test-suite.ts --brief
tsx engine/eval/test-suite.ts --all
```

## Test Categories

### 1. Pipeline Health (`--pipeline`)
Automated, no LLM calls. Verifies the pipeline is functioning:
- **pipeline.sources** -- Are sources being ingested? Count by type.
- **pipeline.segments** -- Are segments being created?
- **pipeline.nodes** -- Are graph nodes being extracted? Count by type.
- **pipeline.freshness** -- Is the most recent source < 1 hour old?
- **pipeline.mcp** -- Can we reach the dev server?

### 2. Segmentation Quality (`--segments`)
Uses Claude Haiku as a judge (~$0.02 per run). Picks 5 random sources with segments and runs a 3-pass evaluation:
- **Pass 1 -- Topic Inventory:** Lists every distinct topic in the raw content.
- **Pass 2 -- Coverage Score:** Which topics are captured vs. missing in segments.
- **Pass 3 -- Fidelity + Voice:** Per-segment quality scores (1-5).

PASS threshold: 70% average coverage.

### 3. Retrieval Quality (`--retrieval`)
Requires `npm run dev` running on localhost:3000. Runs 5 predefined queries against `/api/chat/synthesize`:
- **retrieval.relevance** -- Average segment similarity scores (threshold: 0.3).
- **retrieval.grounding** -- Do answers contain source citations?
- **retrieval.mode_comparison** -- Both Mode B (graph) and Mode D (segments) return responses.

### 4. Cost Tracking (`--cost`)
No LLM calls. Queries `extraction_logs` for the last 24 hours:
- Sums input/output tokens by operation and model.
- Estimates cost using per-model pricing.
- Reports cost per source (WARN if > $0.005/source).

### 5. Brief Routing (`--brief`)
Cannot be fully automated (requires Claude Desktop interaction). Generates a test template at `engine/eval/results/brief-routing-template.md` with the 10 test queries from `eval-brief-routing.md`. Run the queries manually in Claude Desktop and fill in results.

## Interpreting Results

Each test returns one of:
- **PASS** -- Meets threshold.
- **WARN** -- Works but below ideal (e.g., freshness > 1 hour, cost above threshold).
- **FAIL** -- Broken or below required threshold.
- **SKIP** -- Could not run (e.g., dev server not available for retrieval tests).
- **MANUAL** -- Requires human interaction (brief routing).

## Output

The console shows a formatted report. A JSON file is also saved to:
```
engine/eval/results/test-suite-{timestamp}.json
```

## When to Run

- **After each pipeline rebuild:** `npm run test:quick` to verify pipeline health and cost.
- **After segmentation changes:** `npm run test:segments` to validate extraction quality.
- **Before beta releases:** `npm test` to run the full suite.
- **After every phase gate:** Full suite as evidence for phase completion.

## Existing Eval Scripts

The unified test suite does not replace the standalone eval scripts, which are useful for deep-dive investigations:

| Script | Purpose | Interactive? |
|--------|---------|-------------|
| `npm run eval` | Graph node quality (accuracy + non-obviousness) | Yes (manual rating) |
| `npm run eval:stall` | Stall detection quality (genuinely stalled + would act) | Yes (manual rating) |
| `npm run eval:segments` | Segment extraction quality (3-pass Haiku judge) | No (automated) |
