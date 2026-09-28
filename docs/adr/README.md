# `docs/adr/` — intentionally empty

**Architecture Decision Records live in [`../../.ai/memory/decisions.md`](../../.ai/memory/decisions.md).**

This directory used to hold a second copy. `0001-agent-orchestration-langgraph.md`
said **Status: Accepted** and described a *research* workflow with a `graph/`
package at ≥90% coverage, while the authoritative ADR had already been
repositioned on 2026-09-26 and the repository contained no `langgraph`
dependency, no `graph/` package, and no `agents/` at all.

Nothing referenced the duplicate — no document, no workflow, no test. It was
invisible to every mechanism the project has, and it was still wrong in the way
that matters most: a reviewer opening `docs/adr/` would have demanded a module
with 90% coverage that has never existed.

That conflict is recorded as regression [`0005`](../../.ai/regressions/0005-arch-doc-and-adr-divergence.md),
and the duplicate was deleted rather than corrected. A second store of
decisions is not a thing to maintain; it is a thing to not have. The
constitution already says decisions live in `.ai/memory/decisions.md`, and
`docs/ARCHITECTURE.md` now points there for the same reason.

If you are about to write a decision: append it to `.ai/memory/decisions.md`,
give it the next `ADR-NNNN`, and add a row to the 决策索引 table at the bottom of
that file. Do not create a file here.
