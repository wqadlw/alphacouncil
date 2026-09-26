# AlphaCouncil — backend

Python backend for AlphaCouncil, a practice-oriented knowledge management system
for stock market investors.

**Full project description, architecture and product rationale: see the
[repository README](../README.md).**

## Layout

| Path | Contents |
|---|---|
| `src/alphacouncil/models/` | Data contracts. The boundary between external sources and everything above them. |
| `src/alphacouncil/providers/` | Market data sources (Tencent / Sina / Eastmoney) and the router that chooses between them. |
| `src/alphacouncil/core/` | Configuration and logging. |
| `src/alphacouncil/api/` | FastAPI application. |
| `tests/unit/` | Tests that must not touch the network. |
| `scripts/` | Developer tooling — `dev.py` is the single command entry point. |

## Commands

```bash
python scripts/dev.py check-lite   # every gate that exists today
python scripts/dev.py check        # every gate CI runs; skipped gates fail
python scripts/dev.py help
```

> `make` targets in the repository root wrap the same commands, but **`make` is
> not installed everywhere** — `scripts/dev.py` is the real implementation.

## Licence

MIT. See the [repository LICENSE](../LICENSE).
