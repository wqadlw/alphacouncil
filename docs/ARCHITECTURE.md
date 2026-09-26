# Architecture

> Audience: contributors, reviewers, and anyone evaluating this project.
> For *what* each component must do, see `.ai/specs/`. For *why* the key choices
> were made, see `.ai/memory/decisions.md`.

## Layering

Dependencies point downward only. A module may import from layers below it and
never from layers above.

```
┌──────────────────────────────────────────────┐
│ api/          FastAPI routes, request models │
├──────────────────────────────────────────────┤
│ graph/        LangGraph state machine        │
├──────────────────────────────────────────────┤
│ agents/       individual agent nodes         │
├──────────────────────────────────────────────┤
│ retrieval/    four-way recall, fusion, rerank│
├──────────────────────────────────────────────┤
│ models/       shared domain models           │
├──────────────────────────────────────────────┤
│ core/         config, logging, observability │
└──────────────────────────────────────────────┘
```

`core` is the foundation: it must not import from any other layer. This is what
lets us test configuration and logging in isolation, with no network or LLM.

## Request flow

```
POST /api/v1/research
        │
        ▼
   ResearchRequest validated (Pydantic)
        │
        ▼
   LangGraph invoked with initial ResearchState
        │
        ├─► Data Agent ────────► SQLite/Postgres (quotes, financials)
        │
        ├─► Retrieval Agent ───► Qdrant (dense + sparse)
        │                        LightRAG (graph)
        │                        Text-to-SQL (structured)
        │                        → RRF fusion → cross-encoder rerank
        │
        ├─► Analyst Agents ────► technical / fundamental / sentiment views
        │
        ├─► Research Agent ────► draft with citations
        │
        ├─► Risk Agent ────────► risk notes
        │
        ├─► Critic Agent ──────► challenges unsupported claims
        │                        (may loop back to Research, max 2×)
        │
        └─► Human review ──────► interrupt; resume with approval
                    │
                    ▼
            ResearchReport (with citations)
```

Every node emits a Langfuse span carrying its inputs, outputs, latency and token
usage, so a completed run can be replayed step by step.

## Why four retrieval routes

A single dense index answers semantic questions well and everything else badly.
The four routes exist because the four question types are genuinely different
problems:

| Route | Serves | Fails at |
|---|---|---|
| Dense (Qdrant + BGE-M3) | Thematic and semantic questions | Exact codes and figures |
| Sparse (BM25) | Ticker codes, precise terms, numbers | Paraphrase and synonymy |
| Graph (LightRAG) | Entity and relationship questions | Free-text narrative |
| Structured (Text-to-SQL) | Aggregations, growth rates, comparisons | Anything not in a table |

Fusion uses **Reciprocal Rank Fusion** rather than weighted score addition,
because RRF needs no per-route weight tuning and degrades gracefully when one
route returns nothing. Fusion deduplicates by `doc_id` before ranking, keeping
the best rank per document.

## Testing strategy

| Layer | What it covers | External deps |
|---|---|---|
| `tests/unit` | Pure logic: fusion, scoring, transforms, config, models | None |
| `tests/integration` | Graph traversal, retrieval chain end to end | Mocked LLM, in-process Qdrant |
| `tests/eval` | Retrieval quality (RAGAS over a curated question set) | Local corpus |

The hard rule: **tests never touch the network.** HTTP clients are injected and
stubbed with `respx`. This keeps CI fast and deterministic, and means a failing
test always indicates a code problem rather than a flaky vendor.

## Configuration

All configuration flows through `core.config.Settings`, which validates at import
time. Two classes of guard exist deliberately:

- **Range guards** — e.g. `rerank_top_k` must not exceed `recall_top_k`. Without
  this, a typo silently yields empty results.
- **Environment guards** — production runs must have credentials for the selected
  provider. Failing at startup beats failing on the first user request.

Secrets use `SecretStr`, so they cannot leak through `repr()`, tracebacks or logs.

## Deliberate non-goals

- **No brokerage integration.** The system produces research notes, not orders.
  This is both a product decision and a security one.
- **No real-time streaming data.** Research is batch-oriented; reproducibility
  matters more than freshness.
- **No fine-tuned models.** Retrieval quality comes from the retrieval design,
  not from training. Fine-tuning is a cost we are not willing to pay yet.

## Extension points

| To add… | Touch |
|---|---|
| A new retrieval route | `retrieval/` + register in the fusion node; add eval cases |
| A new agent | `agents/` + wire into `graph/`; add an integration test |
| A new tool | `tools/` registry; document the schema the agent sees |
| A new data source | `retrieval/` or the data layer, behind the existing interface |
