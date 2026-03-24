# Intent Intelligence: A Manifesto

## The Problem: Every Conversation Starts Cold

You open Claude or ChatGPT. The LLM has no model of what you're working through, what tensions you're holding, or where your thinking has stalled. It doesn't know you're deciding between two job offers and can't sleep. It doesn't know you've been researching the same problem for six weeks without moving forward. It doesn't know what you've already tried, what contradicted your stated beliefs, or what you're avoiding deciding.

Each conversation begins in amnesia.

Memory systems — Mem0, Zep, Letta, Rewind — solve the retrieval problem: "what did I say?" They store what you wrote. They retrieve it when you ask. This is plumbing. Necessary, but not sufficient.

The harder problem, the one nobody is solving, is inference: "what am I trying to do? Where am I stuck? What should I do next?" This is different from memory. A chatbot can remember that you mentioned job offers in a conversation three weeks ago. It cannot infer that you're stalled between two competing visions of your future, that each offer represents a different self-model, and that the real decision isn't about compensation — it's about which version of yourself you want to become.

Memory is what you said. Intent intelligence is what you meant.

---

## The Three Layers of AI Personalization

Current systems collapse personalization into a single dimension: memory. But there are three distinct layers, and they compound differently.

**Layer 1: Memory Interface**
The API contract between an application and a memory system — HTTP endpoints, semantic search, structured retrieval. MCP, LangChain integrations, chat context windows. This is commodity. Every LLM vendor is building this. Pinecone, Supabase, vector stores — competition is fierce. Margins are thin. This layer is converging to commodity because the problem is well-defined and the solution is straightforward.

**Layer 2: Memory Infrastructure**
The backend that stores and indexes memory — vector embeddings, retrieval architectures, temporal modeling, graph databases. This layer is currently diverging (Pinecone, Weaviate, Graphiti, PuppyGraph all competing) but will converge to commodity over the next 18 months. The problem has structure. The solution is replicable. The infrastructure will collapse to a few winners and everyone else will use them.

**Layer 3: Intention-Behavior Gap Detection**
The capacity to model what someone said they wanted versus what they actually did, what they believe they value versus where they spend time, where they've stated intentions but actions have stalled, which of their stated beliefs contradict each other. This requires cross-referencing behavior across multiple contexts — conversations, sources, time — and building a persistent model of the gaps.

Nobody is building this. It's the frontier.

---

## The Epistemic Edge Vocabulary

Intent inference requires a formal framework for modeling reasoning relationships. Most systems use generic edges — "related to," "similar to," "contains." These dissolve nuance. Real reasoning has structure.

We built MIKAI using six edge types:

1. **supports** — Node A provides evidence or justification for Node B. "I want to move to Nairobi" supported by "Lower cost of living makes the salary go further."

2. **contradicts** — Node A is logically incompatible with Node B. "AI will displace knowledge workers" contradicts "AI will mostly augment human judgment." Both are held simultaneously. This is the interior conflict.

3. **extends** — Node A elaborates or refines Node B. "I want to build AI infrastructure" extends "I want to work on systems that scale."

4. **depends_on** — Node A cannot be decided until Node B is resolved. "Choosing a job offer" depends_on "Understanding what kind of work energizes me."

5. **unresolved_tension** — Nodes A and B coexist in active discomfort without resolution. "I want to be a founder" held alongside "I want predictable income." This is not contradiction (they could coexist in a hybrid structure). It's tension — the unresolved pull between competing goods.

6. **partially_answers** — Node A provides some but not all of the answer to Node B. "Survey of emerging markets" partially_answers "Which geographic markets should I target?"

These edges are load-bearing. They're not decorative. A system that models only "supports" edges will miss the tensions. A system that treats contradictions as noise rather than signal will paper over the real decision points.

When you ask MIKAI "what tensions am I holding about my company?", the system finds all unresolved_tension edges in your graph. It surfaces them with their evidence nodes. It shows you exactly where your thinking is in conflict. This is what inference means.

---

## Why "What You're Stuck On" Is the Killer Feature

Current tools optimize for engagement. Mem0 surfaces what you know. Rewind surfaces what you said. The query is "remind me about X" or "what did I learn about Y?" The system succeeds when you use it frequently.

Intent intelligence optimizes for action. MIKAI surfaces what you're avoiding deciding, what contradicts your stated beliefs, where intentions have stalled. The query is "what tensions am I holding?" or "where have I been circling without moving forward?" The system succeeds when the user acts on a surfaced intention.

These are different training signals. Over time, they produce fundamentally different products.

A system trained to maximize engagement will prioritize novelty, frequency, and breadth. It will surface more, more often, in more formats. The Sumimasen principle — every notification is a trust transaction, default to silence — is the opposite of engagement logic.

A system trained to maximize action will prioritize accuracy, precision, and timing. It will surface fewer things, only when confidence is high, only when the user is likely to act. It will track whether the user acted. It will learn which surfaced items generated behavior change and which were ignored.

The difference compounds. After a year, one system is a dashboard of reminders. The other is a personal context layer that anticipates what you need before you articulate it.

The query "what tensions am I holding about my company?" is something no other product can answer today. Notion doesn't. Roam doesn't. Claude can't, because it has no model of you. MIKAI can, because it's been building your graph continuously, tracking where your thinking has changed, where contradictions have emerged, and where you've stalled.

---

## The Action-Optimization Thesis

This is the strategic wedge that separates memory infrastructure from intent intelligence.

A memory system succeeds when you retrieve something. You get value. The system survives. Engagement metrics go up. That's the product loop.

An intent intelligence system succeeds when you're prompted with something you weren't consciously thinking about, and you act on it before you would have done so anyway. Not "you remembered to do this." But "this prompt caused you to do something you were avoiding or hadn't yet decided."

This is harder to measure. It requires:

1. **Behavioral baseline.** What would you have done anyway, in the absence of MIKAI's prompt?

2. **Prompt causal attribution.** Did you act because of the system, or would you have acted regardless?

3. **Stall detection.** Knowing which intentions have stalled is harder than knowing which intentions exist.

The payoff is proportional to the difficulty. A system that can reliably detect stalled instrumental desires — the trip you've wanted to book for six weeks, the meeting you've been meaning to schedule, the decision you've been deferring — and surface them at the moment you're likely to act, has a different economic moat than a system that just retrieves memories.

Memory is symmetric: if I can retrieve your data, competitors can build the same system. Behavioral signal — what you do in response to what you're shown — is asymmetric. It's your data. It's your patterns. It's not replicable by someone who doesn't know you.

---

## The Neuroscience Grounding

This isn't metaphorical. Memory is reconstruction, not retrieval. The moment you retrieve a memory, your brain is reconstructing it. Neuroscience has shown that episodic memory (what happened in a specific context) and semantic memory (stable facts about the world) are distinct neural systems with different recovery pathways, different vulnerability to distortion, and different temporal dynamics.

The implication: the gap between what someone said and what they actually meant, what they believe and what they do, what they intend and where they stall — these gaps are not bugs. They're features of how human cognition works.

A system that tries to bridge this gap by surfacing contradictions and tensions isn't creating confusion. It's modeling how thinking actually works.

The self-model is constructed, not discovered. You don't have privileged access to why you do things. You infer it the same way an outside observer does — by observing your behavior over time. MIKAI does this inference across your digital ecosystem. It sees patterns in what you research, what you save, what you return to, what you abandon. It builds a model. That model is often more accurate than your introspection.

When MIKAI tells you "you've been researching remote work for two months but every time you get close to applying, you change direction" — that's not the system being intrusive. That's the system saying back to you what your behavior is already showing. The system is a mirror, not a judge.

---

## Practical Implementation: The Personal Context Layer

MIKAI works like this in practice:

1. **Passive observation.** Connect your sources: Apple Notes, iMessage, Gmail, Claude conversation exports, Perplexity, browser history (future). The system reads what you've written, not what you're searching for. It observes patterns without storing raw data — just the graph.

2. **Graph construction.** An intent agent extracts concepts, decisions, tensions, and questions from your writing. It types the edges between them. It builds a persistent graph that belongs to you, lives in your database (Supabase, stored encrypted), and doesn't belong to MIKAI or any cloud vendor.

3. **Intent inference.** The system clusters your nodes by temporal proximity and semantic similarity. It detects when you revisit the same concept. It tracks when your position on something has changed. It flags contradictions. It identifies unresolved tensions. It finds stalled desires — things you've stated you want to do, but actions have frozen.

4. **Context injection.** When you open Claude or ChatGPT, MIKAI injects a ~400-token snapshot of your current graph into the conversation context. "Your recent tensions: X, Y, Z. Your stalled projects: A, B, C. Your emerging trajectory: toward D." No extra interaction required. It's ambient.

5. **Proactive surfacing.** MIKAI monitors your graph over time. When an instrumental desire (a concrete action: book a trip, schedule a meeting, make a decision) has stalled for longer than your baseline, the system notifies you. Not as a reminder. As a "this is something you've been meaning to do, and the moment feels right."

This is the wedge. No behavior change required. You're not switching to a new app. You're not installing a new interface. It's context injection into tools you already use.

---

## The Epistemic Moat

The competitive advantage isn't the graph database. Supabase, Postgres, and pgvector are commodities. The advantage is the inference model: what features predict stalled desires? What evidence patterns indicate a genuine tension vs. a passing thought? How do you distinguish between "this person is genuinely stuck" and "this person is just exploring options"?

These are learned patterns. They're proprietary. They compound as more people use the system. A user's behavioral feedback — "did you act on this prompt?" — trains the model to get better at detecting stalled desires for everyone.

This is why MIKAI doesn't need to track everything. It needs to track the right things. The epistemic edge vocabulary is part of this. The other part is the rule engine: what behavioral patterns (revisiting the same research multiple times, staying in the decision phase without action, expressing both desire and fear about the same outcome) predict stall?

Over time, the system learns which nodes, which edge types, which temporal patterns are most predictive of actionable intelligence. A system trained on this converges to a model of human decision-making that is genuinely valuable, because it's trained on behavior, not just on language.

---

## Why This Matters Now

The LLM ceiling is becoming visible. ChatGPT 4 is not obviously smarter than ChatGPT 3.5 for most practical tasks. The derivative improvements are real but marginal. The massive gains will come from context.

An LLM with access to your full behavioral graph is not just better at answering questions about you. It's a different category of tool. The question changes from "what should I do?" to "given everything I've been thinking about, what is the move right now?" The system can reason about your constraints, your values, your contradictions, and your trajectory.

This is the edge that matters. Not bigger models. Better context.

Founders, researchers, and writers live in the space between intention and action. You hold multiple competing visions. You research deeply without deciding. You contradict yourself and know it. You're stuck in the pull between what you want and what you're afraid of.

Current tools don't see this interior complexity. They see what you said. MIKAI sees what you meant.

---

## What This Means Practically

MIKAI is a local-first MCP server. Download it, install it, connect your sources. The data lives in your Supabase database. You own the graph. You can export it, move it, delete it. The system doesn't train on your data. It doesn't sell your data. It doesn't use it to train competitors.

You plug it into Claude. In every conversation, Claude has your graph in context. It's not intrusive. It's there if Claude needs it. You can query it directly: "what tensions am I holding about this decision?" The system shows you the exact edges and evidence.

Over time, as the system learns your patterns, it surfaces things before you ask. Not notifications. Contextual. "I noticed you've been researching Y for two weeks and keep deferring the decision. Here's what your notes suggest you actually care about." Or: "Your stated value is X but your behavior suggests priority Y. Worth a conversation?"

This isn't magic. It's engineering against a clear problem: the gap between what you said and what you meant, where you've stalled, and what you should do next.

---

## The Invitation

If you're building infrastructure for AI, if you're thinking about how humans and AI should relate, if you're wrestling with the question of how to preserve human agency while gaining AI's analytical power — this is the space.

Memory SDKs are table stakes. They're being built. They'll be commodities.

Intent intelligence is the frontier. It requires a different philosophy. Different metrics. A commitment to action over engagement. A belief that the best AI is one that understands not just what you said, but what you're avoiding deciding and what you should do next.

MIKAI is open. The MCP server is live. The source code is available. The architecture is documented. Contribute. Fork. Build a surface on top. Connect your own sources. Test whether the system actually surfaces actionable intelligence for you.

The question isn't whether intent graphs are possible. We've built one. The question is whether the inference model — the ability to detect stalled desires, model your tensions, and surface the right thing at the right time — can be learned from behavior and generalized across people.

That's the work ahead.

---

## North Star

In the end, MIKAI should work like a persistent assistant living in your shoulder, aware of everything you're thinking about. It surfaces what matters, when it matters, in the medium you prefer. Not by guessing. By knowing you — your contradictions, your stalled decisions, your emerging trajectory, what you actually care about versus what you think you should care about.

This assistant doesn't work for engagement metrics. It works for action. It succeeds when you do something you wouldn't have done otherwise, because you finally saw clearly what you'd been avoiding.

That's intent intelligence. That's the frontier.

---

*MIKAI is available at [github.com/briancho/MIKAI](https://github.com/briancho/MIKAI) with full source and documentation. The MCP server runs local-first. Data is yours. Build with it. Contribute to it. The category is still forming. Help define it.*
