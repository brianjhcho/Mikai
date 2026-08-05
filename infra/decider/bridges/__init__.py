"""MIKAI bridge adapters for external agent stacks.

These modules define the MCP-shaped surface MIKAI exposes to (or consumes
from) other agent systems. Per docs/COMPARISON.md:

- MIKAI's moat is packaging + Sumimasen intervention-timing +
  declarative life-tier ontology + consent-required approval loop.
- MIKAI's L5 actuation and messaging ingestion are DELEGATED to
  external systems: OpenClaw (100+ integrations, file ops, browser
  actions) and Hermes Agent (CLI + memory + skill creation).
- These bridges are how the delegation happens without inheriting the
  wiring burden the consumer is meant to be shielded from.

Design commitment (2026-07-17): code shape only in v1. No credentials,
no live wiring, no ntfy dispatch through these paths yet. The point is
to lock in the interface so when Brian is back and decides the
wire-up approach, the shape is already right.

Files:

- hermes_bridge.py: MIKAI ↔ Hermes Agent memory + skill creation
- openclaw_bridge.py: MIKAI ↔ OpenClaw actuation + messaging
"""
