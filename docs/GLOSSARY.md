# MIKAI Naming Glossary

> **What this file is:** the canonical mapping of MIKAI's internal codenames to their formal (industry / academic) names and their code identifiers. First reference in any doc should name both codename and formal term (e.g., "Noonchi (ambient task-state awareness)"). After that, either is fine — pick the register that fits the audience.
>
> **Rule:** internal / verbal / Slack = codenames. Docs / published writing / talks / investor comms = formal terms. Code = whatever identifier already ships (do not rename shipping code).

---

## System-level terms

| Codename | Formal name | Scope | Code identifier |
|---|---|---|---|
| **MIKAI** | The system as a whole | Product name | `mikai`, `com.mikai.*` |
| **Noonchi** (Korean: 눈치, "reading the room") | Ambient Task-State Awareness | The L4 layer — cross-source personal task-state model | n/a (concept-level) |
| **Surface Engine** | Surface Engine | The whole surfacing pipeline: candidate reading → priority scoring → gating → dispatch | `mikai_decide.py`, `figs-*` LaunchAgents |
| **Sumimasen** (Japanese: すみません, "excuse me for interrupting") | Intervention Timing | The `delivery_cost⁻¹` gate inside the Surface Engine — the "when to interrupt" decision, distinct from "what to surface" | `delivery_cost` in surface_priority formula |
| **Dream** | Consolidation pass | Nightly async LLM pass that reads raw episodes + previous wiki, writes updated wiki | `dream-runner.sh` |
| **Wiki** | Consolidated markdown substrate | Per-thread pages with frontmatter, source of truth for Surface Engine state | `~/mikai/wiki/wiki.md` |
| **Registry** | User Needs Registry | Brian-authored YAML explicit needs, highest Surface Engine priority | `docs/USER_NEEDS_REGISTRY.md` |

---

## Component-level terms inside the Surface Engine

The Surface Engine composes six things. Sumimasen is one of them.

| Term | Role | Where it lives |
|---|---|---|
| Candidate reading | Pull threads from registry + wiki + graph + adapters | `mikai_decide.py` |
| State weighting | Multiply by thread state (acting / stalled / blocked / ...) | `state_weight` factor |
| Tension pressure | Multiply by tension count on the thread | `tension_pressure` factor |
| Delivery value | LLM judgment: worth surfacing now? | `delivery_value` factor |
| **Sumimasen / Intervention Timing** | **Multiply by inverse cost of interrupting: time-of-day, recent-dismiss, fatigue, interruption-level** | **`delivery_cost⁻¹` factor** |
| Dispatch | Fire via ntfy / Calendar / osascript / terminal-notifier | `dispatch_*.py` |

---

## Why the code keeps `figs`

The Surface Engine ships as `mikai_decide.py` and `com.mikai.figs-*` LaunchAgents. Renaming code identifiers now would require touching stable LaunchAgent labels, plist filenames, and runner scripts — churn without functional gain. The docs use "Surface Engine" for clarity; the code retains `figs` for operational stability.

If code is ever refactored (e.g., a rewrite pass), the identifier can migrate to `surface_engine`. Until then, `figs` in code = Surface Engine in concept.

---

## Related industry / academic sources

- **Ambient Agent** (industry, 2025–2026 dominant category): Chase / LangChain Jan 2025
- **Personal Knowledge Graph** (academic substrate): Chakraborty et al. arXiv:2204.11428; EpisTwin arXiv:2603.06290
- **Opportune-Moment Detection** (HCI): Fogarty / Hudson / Iqbal & Bailey "cost of interruption" lineage
- **Proactive Intervention** (2025–2026 papers): ProMemAssist UIST 2025 arXiv:2507.21378; OmniActions CHI 2024 arXiv:2405.03901; Sensible Agent arXiv:2509.09255; EgoSocial arXiv:2510.13105; Proactive Systems in HCI and AI arXiv:2606.25149
