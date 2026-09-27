"""Trace writing — one replayable record per run (spec 011, `.ai/traces/README.md`).

The data model is Langfuse's, borrowed through the wealthfolio deep-dive:
**Trace** (one complete run) → **Observation** (each step inside it, with
duration and outcome) → **Score** (a judgement about the run). Three questions
this answers and nothing else in the repo can: what happened inside a request
(regression 0003 was exactly such a mystery), what did a run cost, and — once
an evaluation set exists — what passed.

Two hard rules shape every line written here:

* **Append-only.** A trace file is opened once and appended to; no tool ever
  rewrites a line (constitution §9).
* **No reader content.** Request bodies, reasons, quoted text — never. Only
  routes, statuses, durations, four-state outcomes, error codes, and payload
  *hashes* (constitution §6.3: the audit says what was done, not what was
  said).

And one discipline inherited from the cache: writing a trace must never break
the thing being traced. Every disk fault is logged and swallowed.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)

__all__ = ["Trace", "TraceHook", "TraceWriter", "current_trace", "set_current_trace"]

_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar(
    "alphacouncil_current_trace", default=None
)


def set_current_trace(trace: Trace | None) -> contextvars.Token[Trace | None]:
    """Bind ``trace`` to the current context; returns a resettable token."""
    return _current_trace.set(trace)


def current_trace() -> Trace | None:
    """The trace bound to this context, or ``None`` outside any request."""
    return _current_trace.get()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class _ObservationSlot(dict[str, Any]):
    """What an observation's body can adjust while it runs.

    A provider writes the four-state outcome into ``status`` / ``error_code``
    after the call returns; whatever is in the slot at exit is what lands on
    disk.
    """


class TraceHook(Protocol):
    """The tracer surface the router depends on.

    Implemented by :class:`TraceWriter` (which no-ops when no trace is
    bound to the current context, e.g. during startup warm-up).
    """

    def observation(
        self, name: str, *, meta: dict[str, Any] | None = None
    ) -> contextlib.AbstractContextManager[dict[str, Any]]:
        """Time one step; yields a slot the caller may adjust before exit."""
        ...


class Trace:
    """One run's handle: appends its own observations to its own JSONL file."""

    def __init__(self, writer: TraceWriter, trace_id: str, name: str, file: Path) -> None:
        self.id = trace_id
        self.name = name
        self._writer = writer
        self._file = file

    def __enter__(self) -> Trace:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @contextmanager
    def observation(
        self,
        name: str,
        *,
        token_count: int | None = None,
        cost_usd: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Time one step inside this run.

        The duration is measured with a monotonic clock — it means "how long
        the step took", never "what time it was". An exception inside the
        block is recorded (status=error, exception type) and re-raised: the
        trace describes the failure, it does not swallow it.
        """
        started = time.monotonic()
        started_at = _now_iso()
        slot: _ObservationSlot = _ObservationSlot(status="ok", error_code=None)
        try:
            yield slot
        except Exception as exc:
            self._writer._append(
                self._file,
                {
                    "kind": "observation",
                    "trace_id": self.id,
                    "name": name,
                    "started_at": started_at,
                    "ended_at": _now_iso(),
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    "status": "error",
                    "error_code": None,
                    "error": type(exc).__name__,
                    "token_count": token_count,
                    "cost_usd": cost_usd,
                    "meta": {**(meta or {}), **slot},
                },
            )
            raise
        self._writer._append(
            self._file,
            {
                "kind": "observation",
                "trace_id": self.id,
                "name": name,
                "started_at": started_at,
                "ended_at": _now_iso(),
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "status": slot["status"],
                "error_code": slot["error_code"],
                "error": None,
                "token_count": token_count,
                "cost_usd": cost_usd,
                "meta": meta or {},
            },
        )

    def score(self, name: str, value: float, *, comment: str | None = None) -> None:
        """Attach a score to this trace (the eval layer's landing point)."""
        self._writer._score(self.id, name, value, comment=comment)


class TraceWriter:
    """Owns the traces directory and the append-only disk policy."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def start(self, name: str) -> Trace:
        """Open a new trace: one dated file, one header line. Never raises."""
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        run_id = f"{stamp}-{secrets.token_hex(4)}"
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        file = self._root / day / f"{run_id}.jsonl"
        trace = Trace(self, run_id, name, file)
        self._append(
            file,
            {"kind": "trace", "id": run_id, "name": name, "started_at": _now_iso()},
            create_dirs=True,
        )
        return trace

    def observation(
        self, name: str, *, meta: dict[str, Any] | None = None
    ) -> contextlib.AbstractContextManager[dict[str, Any]]:
        """Hook for callers outside a request: no current trace → no-op."""
        trace = current_trace()
        if trace is None:
            return contextlib.nullcontext(_ObservationSlot(status="ok", error_code=None))
        return trace.observation(name, meta=meta)

    def _append(self, file: Path, record: dict[str, Any], *, create_dirs: bool = False) -> None:
        """Append one JSON line. The single disk policy: append, never rewrite;
        on any failure, log and move on — tracing must not break the traced."""
        try:
            if create_dirs:
                file.parent.mkdir(parents=True, exist_ok=True)
            with file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            log.warning("trace.write_failed", file=str(file), error=str(exc))

    def _score(
        self,
        trace_id: str,
        name: str,
        value: float,
        *,
        comment: str | None,
    ) -> None:
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        file = self._root / "scores" / f"{day}.jsonl"
        self._append(
            file,
            {
                "kind": "score",
                "trace_id": trace_id,
                "name": name,
                "value": value,
                "comment": comment,
                "scored_at": _now_iso(),
            },
            create_dirs=True,
        )
