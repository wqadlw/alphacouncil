# Architecture

> Audience: contributors, reviewers, and anyone evaluating this project.
> For *what* each component must do, see `.ai/specs/`. For *why* the key choices
> were made, see `.ai/memory/decisions.md`. For *what is left to build*, see
> `.ai/status.md`.
>
> **Corrected twice on 2026-09-28 — read this before trusting anything below.**
>
> **Correction 1.** The previous version of this file described LangGraph, Qdrant,
> LightRAG, RRF fusion, a four-route retrieval layer, and three packages
> (`graph/`, `agents/`, `retrieval/`) that do not exist in this repository. That
> text was left over from v1.
>
> **Correction 2 (mine, hours later, and the more embarrassing one).** The first
> correction said the constitution "removed every one of those technologies on
> 2026-09-26" and filed LangGraph under [deliberate non-goals](#deliberate-non-goals).
> **That was false.** The v1 → v2 removal (constitution item 2) covered the
> *retrieval* stack — LlamaIndex, Qdrant, LightRAG, AKShare, Next.js (ADR-0002 /
> 0003 / 0004 / 0006). **LangGraph was not on that list.** It is listed in the
> constitution's locked stack (第三条) and ADR-0001 is **Accepted**; the second
> copy of that ADR, under `docs/adr/`, was simply never updated and nobody
> referenced it. A grep of a mis-encoded line is not a source of truth, and
> generalising a removal list into "everything in the old architecture doc was
> removed" is exactly the confidently-wrong error this file existed to fix.
> Recorded as regression `0005`.
>
> The accurate statement is the boring one, and it is in
> [Adopted but not implemented](#adopted-but-not-implemented).

---

## What this system is

A single-user Windows desktop application that keeps **a stock's data, the
judgement you wrote about it, and what happened next** on one page — and makes
you write down your reasoning *before* you know the outcome.

It is a knowledge system, not a trading workbench. The asset it protects is the
user's own record of their reasoning.

## The one structural idea

The product's confrontation with the user and the pipeline's confrontation with
the code are the same mechanism:

| Toward the user | Toward the code |
|---|---|
| Require the reason, **before** the outcome | Require the spec, **before** the implementation |
| Force the "counter-evidence" field | Force the reviewer to supply counter-examples |
| "You have said this three times" | "This failure mode has been fixed three times" |
| Separate decision quality from outcome | Separate code quality from "it ran green" |
| Lesson → spaced-repetition card | Incident → regression record |

`.ai/` is not a sidecar to the product. It is the product's own machinery,
applied to the product's development — which is why both halves share data
models (decision log / ledger / score) and the same red lines.

## Layering

Dependencies point downward only. A module may import from layers below it and
never from above.

```
┌───────────────────────────────────────────────────────────────┐
│ api/          FastAPI routes, request/response models         │
├───────────────────────────────────────────────────────────────┤
│ domain/       business rules — pure, no I/O, no framework     │
├───────────────────────────────────────────────────────────────┤
│ storage/      SQLite, migrations, repositories                │
│ providers/    market data: capabilities, routing, cache       │
├───────────────────────────────────────────────────────────────┤
│ models/       shared contracts (market data, four states)     │
├───────────────────────────────────────────────────────────────┤
│ core/         config, logging, error codes, time, trace        │
└───────────────────────────────────────────────────────────────┘
```

`core` is the foundation: it must not import from any other layer. That is what
lets configuration, logging, and tracing be tested in isolation, with no
network, no database, and no LLM.

`domain/` is the only place a business rule may live. It is pure Python — no
SQLite, no HTTP, no FastAPI — which is why it reaches 100% test coverage while
the rest of the system does not.

**The two developer-tooling trees are outside this diagram on purpose**, because
they are not part of the shipped application:

```
checks/    12 static checks (AST + text). Type-checked, linted, unit-tested.
scripts/   dev.py (the gate runner), check_licenses.py, _console.py.
           NOT type-checked — a recorded gap, see .ai/status.md §5.
```

## Request flow

```
GET /api/v1/today
      │
      ▼
  dependencies: one SQLite connection per request, never shared
      │      (deps.py — SQLite connections are not thread-safe;
      │       a pooled singleton would reintroduce regression 0003)
      ▼
  route (api/routes/today.py)
      │
      ├─► storage/repositories/  ─► SQLite (decisions, instruments, cards)
      │
      └─► providers/router ─┬─► eastmoney   ─┐  capability-routed,
                           ├─► tencent     ─┤  each with a declared
                           └─► sina        ─┘  failure mode
                                    │
                                    └─► cache: TTL, then disk (SqliteCache)
      │
      ▼
  domain/ evaluates pure rules  ─►  four-state result  (ok / no_data /
      │                            error / unavailable)
      ▼
  Pydantic response model ─► JSON      trace record appended (never blocking)
```

Three decisions in that diagram are load-bearing:

1. **The provider is chosen by declared capability, never by name.** Adding a
   fourth source is a registration, not a new `if`.
2. **Degradation is explicit and ordered**: `ok` > `no_data` > `stale` >
   `error`. A source saying "there is nothing" outranks our cache saying "here
   is yesterday" — the first is a statement about *now*.
3. **A source that answers 403/429 is put in cooldown.** Retrying a refusal is
   how an IP gets banned.

## Storage

SQLite, one file, migrated forward only.

- **Two PRAGMA profiles** (`storage/db.py`, ADR-0012): the application runs
  `synchronous=NORMAL`; a migration runs `synchronous=FULL` plus
  `temp_store=FILE`. The second is a memory bound, not tuning — the wealthfolio
  measurements are quoted in that module's docstring.
- **Migrations** (`storage/migrate.py`) are an explicit `manifest.json`, applied
  with the DDL and the version bump **in one transaction**, preceded by a
  `VACUUM INTO` snapshot and a SHA-256 of it. A database from a newer build is
  **refused**, not downgraded.
- **Append-only is enforced by the database**, not by discipline: trigger pairs
  make `decisions`, `watchlist_events`, and `card_events` un-updatable and
  un-deletable. `storage/constraints.json` is the ledger of those constraints,
  and it is itself cross-checked against the live schema.
- **`repositories/`** are the only code that writes SQL. They take a connection
  and return rows; they do not decide anything.

## Data has four states, not two

`models/market.py` encodes a constitutional rule as types: `ok` / `no_data` /
`error` / `unavailable`. "The source says there is nothing" and "the source is
broken" are different facts, and collapsing them is how a system starts lying
about what it knows. An unmature outcome is left **blank**; it is never `0`.

Every externally-sourced value carries `source` and `fetched_at` — provenance
is not optional.

## Observability

`core/trace.py` writes one replayable JSONL record per request, borrowing
Langfuse's model: **Trace → Observation → Score**.

Two rules shape every line: the file is **append-only**, and it contains **no
user content** — routes, statuses, durations, error codes, and payload *hashes*
only. The trace middleware never reads a request body.

Writing a trace must never break the thing being traced: every disk fault is
logged and swallowed.

## Frontend

React + Vite + TypeScript, in `frontend/`. Hash-based routing, hand-written —
TanStack Router/Query are **not** dependencies, and replacing the hand-written
versions is a recorded leftover, not an oversight.

The E2E suite (Playwright) runs against the **built bundle** with the API
layer mocked at the route boundary, so it is deterministic and needs no live
market data. The UI red lines it pins are: no return-rate metric anywhere
(red line 9), the stop-loss panel must state the years needed to recover
(red line 12), and the submit button stays disabled until the required fields
exist (red line 13).

## Testing strategy

| Layer | What it covers | External deps |
|---|---|---|
| `tests/unit` | domain rules, storage, API, providers, migrations, static checks | none; the network is `respx`-stubbed |
| `tests/integration` | the real migration chain, snapshots, upgrade paths | none |
| `frontend/src/*.test.ts` | pure logic: formatting, routing, quote summary, recovery maths | none |
| `frontend/e2e` | red lines, in a browser, on the built bundle | API mocked |

**The hard rule: tests never touch the network.** HTTP clients are injected and
stubbed, so a failing test always means a code problem rather than a flaky
vendor.

Two disciplines that are easy to state and hard to keep:

- **Mutation checking.** A bug fix must answer *"if I deliberately break this,
  will a test go red?"* — and then actually do it. Two of the four recorded
  regressions exist because a check had **never run** rather than because it
  reported the wrong answer.
- **A test may not apply the fix it is testing.** Regression 0004's first test
  draft called the very helper it was meant to verify, and passed for the wrong
  reason. The rule is now `regressions/README.md` §4 rule 8.

## Deliberate non-goals

These are **choices**, not omissions. All of them were removed *from this
repository* on 2026-09-26 (ADR-0002 / 0003 / 0004 / 0006, superseded by ADR-0006)
and are listed so nobody re-adds them by accident — `pyproject.toml` carries the
same list next to the dependency block:

| Not used | Why |
|---|---|
| Qdrant / dense retrieval | Replaced by SQLite FTS5 when it is built. A vector database is not a knowledge base. |
| LightRAG / graph retrieval | Same removal. |
| LlamaIndex | Same removal. |
| Four-route recall + RRF fusion + cross-encoder rerank | The "intelligent retrieval layer" was v1's mistaken product claim. |
| `akshare` | Measured as rate-limited and key-dependent. |
| `pandas` | The standard library is sufficient for OHLCV. |
| Next.js | SSR is dead weight inside a desktop shell. |
| Brokerage integration | The system produces records, not orders. Product *and* security decision. |
| Recommendations, target prices, forecasts | Red line 1. Not a missing feature. |
| Fine-tuned models | Not a cost this project is willing to pay yet. |

> ⚠️ **This list once wrongly contained LangGraph.** It does not belong here —
> see the next section. If you are checking whether something was *removed*, the
> authority is `.ai/memory/decisions.md` §决策索引, not this file.

## Adopted but not implemented

A third category, and the one that is easiest to get wrong in both directions.
These are **adopted decisions that have never been built**:

| Decision | Status | What exists today |
|---|---|---|
| **LangGraph** for agent orchestration (ADR-0001, constitution 第三条) | ✅ Accepted · ❌ not installed | **No dependency, no `graph/` package.** The pipeline that actually runs is `.ai/` — spec → implement → review → verify → ledger — and it is carried by written discipline, not by a state machine |
| **Langfuse** observability (constitution 第三条) | ✅ Accepted as the data model · ❌ service not wired | `core/trace.py` hand-rolls Langfuse's `Trace → Observation → Score` model as local JSONL. The constitution marks Langfuse "可替换/降级"; the hand-rolled writer *is* the degradation |
| **fastmcp** tool protocol (constitution 第三条) | ✅ Accepted · ❌ not installed | No MCP server. Red line 15's read-only-tool rule is currently enforced by *not having tools*, which is weaker than it sounds |
| **`fsrs`** spaced repetition | ✅ dependency declared · ❌ never imported | K3 is unwritten |
| **SQLAlchemy 2 + Alembic** (constitution 第三条, 数据 row) | ⚠️ **superseded in practice** | `storage/` hand-rolls both on raw `sqlite3`. `sqlalchemy` / `aiosqlite` are still declared in `pyproject.toml` and imported nowhere — the residue of the original intent |
| **`py-fsrs`** (constitution 第三条, 记忆调度 row) | ⚠️ **factually wrong name** | The distribution is `fsrs`; `py-fsrs` does not exist on PyPI (verified 2026-09-26, recorded in `pyproject.toml`) |

Two things follow, and both matter more than the table:

1. **There is no agent in the shipped product, and that is not a bug.** Spec 003's
   own banner says the agent is "只是数据的搬运工…不是产品差异化核心". Every product
   capability shipped so far (S1–S4, K1, K2) is satisfied without an LLM.
2. **The resume claim is therefore about the *development* pipeline, not a
   runtime agent.** What can honestly be demonstrated today: an append-only
   ledger, a constitution, per-change specs, 12 static checks, mutation-checked
   regressions, and replayable traces. What cannot: "I shipped an agent
   pipeline", because there isn't one at runtime — and `make eval` does not exist
   yet, which is the piece that would make the claim measurable.

> Three runtime dependencies are declared in `backend/pyproject.toml` and
> imported **nowhere**: `sqlalchemy`, `aiosqlite`, `fsrs`. The first two are the
> residue of an intent the code outgrew (raw `sqlite3` won); the third is staged
> for K3. `scripts/check_licenses.py` counts them, and PyInstaller will bundle
> them, for nothing. Removing the first two needs an ADR. See `.ai/status.md` §5.

## Extension points

| To add | Touch | Must also |
|---|---|---|
| A market data source | a provider module + register its capabilities | declare its failure mode (batch vs per-symbol) |
| A rule that reads a database | `checks/rules/` + register in `checks/registry.py` | state the four things in `.ai/checks/static/README.md`, and add *both* a failing and a passing fixture |
| A knowledge-card state | `domain/card.py` + an event type | the event must be append-only, and `card_events` must learn the new type |
| A page | `frontend/src/` + a route | pin its red lines in `frontend/e2e/` |
| An error code | `core/error_codes.py` **and** `.ai/error-codes.md` | S-05 fails the build if the two disagree |
| **A technology decision** | **`.ai/memory/decisions.md` only** | that file is the single source of truth. `docs/adr/` is a pointer, not a second store — two ADR stores is what produced regression `0005` |

## Known structural gaps

Recorded rather than smoothed over; details and current status in
`.ai/status.md`.

- No financial data (D4), so a `KillCriterion` can say **due** but never
  **triggered** — the metric is not in the system yet.
- No agent orchestration at runtime, and no `make eval`; the resume-grade
  requirement for an evaluation set is still open.
- `scripts/` is outside mypy's `files`, so the gate runner that decides whether
  the project is verified is itself untyped.
- The desktop shell is not built: `frontend/dist` is not yet packaged by
  PyInstaller, and offline start-up has never been measured.
