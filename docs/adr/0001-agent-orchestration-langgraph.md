# ADR-0001 · Use LangGraph for agent orchestration

- **Status**: Accepted
- **Date**: 2026-09-25
- **Deciders**: Architect
- **Supersedes**: —

## Context

The system must orchestrate several specialist agents into one research workflow.
The workflow has three properties that constrain the choice of framework:

1. **Conditional routing** — different question types require different agent
   combinations. A semantic question does not need the structured-data agent.
2. **Cycles** — the Critic agent may reject a draft and send it back for further
   research. The graph must support bounded loops.
3. **Human interruption** — conclusions require explicit human approval, so the
   workflow must be pausable and resumable.

Candidates evaluated (star counts as of 2026-09-25):

| Framework | Stars | Model |
|---|---|---|
| AutoGen | 61,152 | Conversational multi-agent |
| CrewAI | 59,006 | Role-playing crews |
| Agno | 42,335 | High-performance agents |
| **LangGraph** | **42,257** | **Graph + shared state** |
| OpenAI Agents SDK | 29,693 | Lightweight handoffs |
| Pydantic AI | 20,167 | Type-safe agents |
| Google ADK | 21,638 | Google's agent toolkit |

## Decision

Use **LangGraph** as the orchestration backbone.

## Rationale

1. **The three workflow properties above map directly onto graph primitives.**
   Conditional edges express routing; cycles express the Critic loop; interrupts
   express human-in-the-loop. In a conversational framework these must be
   simulated with prompts and conventions, which is fragile and hard to test.
2. **Shared state is explicit.** `ResearchState` is a `TypedDict`, so what each
   node reads and writes is visible and type-checked. In dialogue-based
   frameworks, state lives implicitly in the message history.
3. **Testability.** Nodes are plain functions over a state object. They can be
   unit-tested without an LLM, which is what makes the 90% coverage requirement
   for `graph/` achievable at all.
4. **Explainability under questioning.** "Why a graph rather than a chain" has a
   concrete, defensible answer — which matters for a project intended to
   demonstrate architecture judgement.

## Alternatives rejected

**CrewAI** — fastest to a working demo, but the abstraction hides the control
flow. Fine for prototyping, poor for demonstrating that the author understands
scheduling, state and failure handling.

**AutoGen** — strong for open-ended multi-agent conversation. Our workflow is
constrained and auditable rather than exploratory, so the conversational model is
a mismatch.

**Pydantic AI** — appealing for type safety, but less mature for graph-shaped
control flow with interrupts.

**Custom implementation** — maximum control, but reinvents scheduling, checkpointing
and persistence. The project's goal is to build on mature frameworks, not to
reimplement them.

## Consequences

**Positive**

- Control flow is explicit and reviewable.
- Nodes are independently testable.
- Checkpointing and resume come from the framework.
- Interrupts give us human-in-the-loop without bespoke machinery.

**Negative**

- `ResearchState` must be designed up front; adding fields later touches every
  node.
- More ceremony than a linear chain for simple cases.
- LangGraph's API is still evolving pre-1.0; upgrades may require migration work.

## Compliance

- `graph/` must maintain ≥90% test coverage (constitution §3).
- Every node must emit a Langfuse span (spec 003 FR-8).
- Bounded loops: the Critic may trigger at most two research revisions
  (spec 003, boundary table).
