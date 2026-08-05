# Cockpit organization: function vs. topic

*2026-08-05 · Design decision. Inputs: the anatomy plate ("The Second Brain, Sectioned"), the live cockpit at `~/.mikai/brain/cockpit.html`, and `docs/COCKPIT_STRUCTURE_RESEARCH.md`. The ecosystem survey is settled there and not reopened here.*

## 1. What each view answers (and what it can't)

The function view answers *how the organism works*. It shows the afferent flow — capture → memory → state → gate → execution — and makes structural claims auditable: which stratum is underbuilt (S3 is the contested one), where data enters and under what provenance, and why MIKAI is not Pulse, Orbit, or Mem0 (they stop at S2 or skip S3; the plate makes the omission visible). It is a thesis rendered as anatomy. What it cannot answer: anything indexed to *now*. You cannot look at the plate and learn that the proposal thread has sat in `exploring` for 36 days. The plate is true on any given morning in exactly the same way, which is precisely why it is not a cockpit.

The topic view answers *where my life is*. Seven hubs, threads as nodes, state encoded in styling, hover revealing next steps. It answers: what am I currently doing, what has stalled, where should attention go before coffee. What it cannot answer: why any of it should be trusted. It is silent on provenance, on whether the substrate beneath it is honest, on what distinguishes this sky from a hand-maintained Notion board. The topic view shows the output of the machine while saying nothing about the machine.

## 2. Who each view serves

The function view serves the builder, the writer, and the dogfooder-as-auditor. Its moments: deciding what to build next (which stratum is thinnest), writing the essay or the pitch (the plate *is* the argument), and the periodic honesty audit — does the running system actually have five strata, or is S4 still cron wearing a thalamus costume? These are seated, reflective, occasional tasks. The plate is read maybe weekly, deliberately.

The topic view serves the operator. Its moment recurs daily: waking up, opening the cockpit, deciding what today is for. Secondary: noticing a thread gone hollow, catching a stall before Sumimasen must interrupt about it. The operator does not care which stratum computed the stall. The operator cares that it is 36 days old.

## 3. The trap in mixing them

The Tana lesson from the research pass cuts precisely here: "one substrate, many views" works for *data-shaped* output — tables, boards, calendars, work surfaces where the register is uniform and interchangeable. It fails for *portraits*. The anatomy plate and the constellation are both portraits, and each has a signature register: sectional, editorial, citational versus ambient, live, celestial. A MAP/FUNCTION toggle forces both into one chrome, and each loses what makes it work — the plate loses its long-form scientific voice (you cannot hover-gate a thesis), the constellation loses its calm (a mode switcher announces "dashboard," and the cockpit becomes the productivity surface it must not be). The cognitive cost is worse than the aesthetic one: a toggle implies the two views are alternative slices of one question. They are not. They answer different questions on different timescales, and merging them teaches the operator to audit at 7am and the builder to operate mid-essay.

## 4. The honest recommendation

**(A). Topic view only in the cockpit; the anatomy plate stays a separate editorial artifact.** One line: the cockpit is for the operator, the plate is for the auditor, and neither register survives cohabitation. The cost accepted: the cockpit will never tell Brian the substrate is underbuilt or dishonest — that audit now depends on deliberately opening a second document, and two artifacts can drift apart in what they claim MIKAI is. That drift is a real maintenance tax. Accept it.

## 5. Effect on the entity-edges recommendation

Entity edges belong to the topic view and strengthen (A) rather than reopening it. "Entangled with" is live cross-thread structure — operator information. But it is also the one place function becomes *legible through behavior*: edges exist only because an L3 entity layer exists, so the cockpit proves the anatomy without drawing it. The function view gets demonstrated, not toggled. Part 4 stands.
