# AlphaCouncil

> A multi-agent investment research system built on LangGraph — four-way hybrid retrieval, citation-grounded answers, and full-chain LLM observability.

[![CI](https://github.com/OWNER/alphacouncil/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/alphacouncil/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/OWNER/alphacouncil/branch/main/graph/badge.svg)](https://codecov.io/gh/OWNER/alphacouncil)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**English** | [简体中文](README.zh-CN.md)

---

## Why this project

Most RAG demos are chatbots bolted onto a vector store. Investment research is a harder problem:

- **It needs multiple retrieval strategies.** A semantic question ("what are the market's concerns about this company") and a factual one ("Q3 gross margin") cannot be served by the same index. Entity-relationship questions ("who are this company's upstream suppliers") need a graph, not embeddings.
- **It needs multiple perspectives.** Valuation, technicals, sentiment, and risk are genuinely different analytical frames — and they disagree with each other.
- **It needs verifiability.** An unsourced claim in investment research is worthless. Every conclusion must trace back to a document.

AlphaCouncil treats these as first-class engineering problems rather than prompt-engineering problems.

## Architecture

```
                        ┌──────────────────┐
                        │  Orchestrator    │  LangGraph state graph
                        └────────┬─────────┘
        ┌────────────┬───────────┼───────────┬────────────┐
        ▼            ▼           ▼           ▼            ▼
   ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐
   │  Data   │ │Retrieval │ │Technical│ │Fundamen-│ │Sentiment │
   │  Agent  │ │  Agent   │ │ Analyst │ │  tal    │ │  Agent   │
   └────┬────┘ └────┬─────┘ └────┬────┘ └────┬────┘ └────┬─────┘
        └───────────┴────────────┼───────────┴───────────┘
                                  ▼
                        ┌──────────────────┐
                        │ Research Agent   │  synthesizes views
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │  Risk Agent      │  risk review
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │  Critic Agent    │  adversarial challenge
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │  Human Review    │  human-in-the-loop
                        └────────┬─────────┘
                                 ▼
                        Citation-grounded report
```

### Retrieval layer

Single-vector retrieval fails on three of the four question types we care about, so the retrieval layer runs four strategies in parallel and fuses them:

| Route | Backend | Serves |
|---|---|---|
| Dense vector | Qdrant + BGE-M3 | Semantic / thematic questions |
| Sparse lexical | BM25 / SPLADE | Exact terms, tickers, figures |
| Graph | LightRAG | Entity and relationship questions |
| Structured | Text-to-SQL | Aggregations over financial data |

Results are fused with **Reciprocal Rank Fusion**, re-ranked with a cross-encoder, then compressed before reaching the agent.

## Key features

- **Graph-orchestrated multi-agent workflow** with conditional routing and failure retry (LangGraph)
- **Four-way hybrid retrieval** with RRF fusion and cross-encoder re-ranking
- **RAG evaluation harness** — RAGAS metrics over a curated question set, wired into CI
- **Full-chain observability** — every agent step, tool call, and retrieval traced in Langfuse
- **Citation grounding** — every claim carries `doc_id`, page, and source snippet
- **Adversarial Critic agent** — a dedicated agent whose only job is to challenge the research
- **Human-in-the-loop** — research conclusions require explicit human approval before finalization

## Tech stack

| Layer | Choice |
|---|---|
| Agent orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| Retrieval framework | [LlamaIndex](https://github.com/run-llama/llama_index) |
| Vector store | [Qdrant](https://github.com/qdrant/qdrant) |
| Graph retrieval | [LightRAG](https://github.com/HKUDS/LightRAG) |
| Observability | [Langfuse](https://github.com/langfuse/langfuse) |
| Backend | FastAPI + Pydantic v2 |
| Frontend | Next.js + shadcn/ui + Vercel AI SDK |
| Data | [AKShare](https://github.com/akfamily/akshare) |
| Quality | Ruff · mypy · pytest · pre-commit · GitHub Actions |

## Quick start

```bash
git clone https://github.com/OWNER/alphacouncil.git
cd alphacouncil
cp .env.example .env          # fill in your API keys
make install                  # create venv + install deps
make test                     # run the test suite
make dev                      # start backend + frontend
```

Requires Python 3.12+ and Node 20+.

## Project structure

```
alphacouncil/
├── .ai/                  # Agent-driven development framework
│   ├── constitution.md   # Non-negotiable project rules
│   ├── agents/           # Role definitions (architect/dev/tester/reviewer)
│   ├── specs/            # Spec-driven feature specs
│   └── logs/             # Append-only review and change ledgers
├── backend/
│   ├── src/alphacouncil/
│   │   ├── agents/       # Agent implementations
│   │   ├── retrieval/    # Four-way retrieval, fusion, re-ranking
│   │   ├── graph/        # LangGraph state graph
│   │   ├── tools/        # Tool registry
│   │   ├── models/       # Pydantic domain models
│   │   ├── api/          # FastAPI routes
│   │   └── core/         # Config, logging, observability
│   └── tests/            # unit / integration / eval
├── frontend/             # Next.js application
├── docs/                 # Architecture docs and ADRs
└── deploy/               # Docker Compose
```

## Development

This repository is developed by AI agents under a spec-driven workflow. Before contributing — human or agent — read [`.ai/constitution.md`](.ai/constitution.md). It defines the non-negotiable rules: tech stack lock, type-annotation requirements, test coverage gates, and forbidden patterns.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

## Roadmap

- [x] **P0** Scaffolding, agent dev framework, CI
- [ ] **P1** Data layer — AKShare ingestion into local store
- [ ] **P2** Retrieval layer — four-way recall + fusion + re-ranking + eval harness
- [ ] **P3** Agent layer — LangGraph orchestration
- [ ] **P4** Observability — Langfuse tracing
- [ ] **P5** Frontend — research UI with live agent trace
- [ ] **P6** Open-source polish — docs, screenshots, first release

## Disclaimer

AlphaCouncil is a research tool. It produces **analyst-style research notes with citations**, not trading signals. It does not connect to any brokerage, does not place orders, and nothing it outputs constitutes investment advice.

## License

[MIT](LICENSE)
