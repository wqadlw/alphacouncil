#!/usr/bin/env python
"""Single entry point for every developer command.

**Why a script and not only a Makefile:** `make` is *not installed* on this
machine — verified 2026-09-26, `which make` finds nothing. A gate that cannot be
run is not a gate; it is a sentence in a document. The Makefile stays as a thin
wrapper for environments that do have make, and this file is the real
implementation behind it.

Two constitution rules are enforced here rather than remembered:

* **§9 — a single command entry point.** Everything goes through this script.
* **T-19 — `check` must report what ran and what was skipped.** A green light
  must never be mistaken for a complete run. This is not theoretical: on
  2026-09-26 `pytest tests/unit -m unit` printed *"54 passed, 47 deselected"* and
  still looked green. Skipped gates therefore fail `check`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# Replaced with the resolved interpreter before the command is run.
_PY = "{py}"


@dataclass(frozen=True)
class Gate:
    """One quality gate."""

    name: str
    what: str
    argv: tuple[str, ...] = ()
    implemented: bool = True
    why_not: str = ""


GATES: dict[str, Gate] = {
    "lint": Gate("lint", "ruff check", (_PY, "-m", "ruff", "check", ".")),
    "typecheck": Gate("typecheck", "mypy (strict)", (_PY, "-m", "mypy")),
    "licenses": Gate(
        "licenses",
        "dependency licence scan (ADR-0024 · L-06)",
        (_PY, "scripts/check_licenses.py"),
    ),
    "test": Gate(
        "test",
        "pytest tests/unit",
        (_PY, "-m", "pytest", "tests/unit", "-m", "unit", "-q"),
    ),
    "test-cov": Gate(
        "test-cov",
        "pytest tests/unit with coverage",
        (
            _PY,
            "-m",
            "pytest",
            "tests/unit",
            "-m",
            "unit",
            "-q",
            "--cov",
            "--cov-report=term-missing",
        ),
    ),
    "check-static": Gate(
        "check-static",
        "static checks S-01..S-12 (.ai/checks/static/)",
        # `--strict` because `python -m checks` alone follows the documented
        # contract: exit 0 means "it ran", even when it found problems. A gate
        # needs the other signal, so it is asked for explicitly.
        (_PY, "-m", "checks", "--strict"),
    ),
    "check-data": Gate(
        "check-data",
        "database consistency scan (.ai/checks/data/)",
        implemented=False,
        why_not="24 checks specified, 0 written",
    ),
}

# `check` is the CI gate set: everything, including the not-yet-written ones, so
# the run cannot claim to be complete while gates are missing.
CHECK: tuple[str, ...] = ("lint", "typecheck", "licenses", "check-static", "test")
# `check-lite` is the daily driver: only the gates that actually exist.
CHECK_LITE: tuple[str, ...] = ("lint", "typecheck", "licenses", "test")


def _say(message: str = "") -> None:
    """Print with an explicit flush.

    Child processes write straight to the file descriptor, unbuffered; our own
    ``print`` would sit in a buffer and then appear *after* output it preceded.
    Verified on 2026-09-26: the gate banners showed up below the results they
    were introducing.
    """
    print(message, flush=True)


def _venv_python() -> str:
    """Return the project interpreter, falling back to the current one."""
    for candidate in (
        BACKEND / ".venv" / "Scripts" / "python.exe",
        BACKEND / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _run(gate: Gate, python: str) -> bool:
    """Run one gate, streaming its output, and report whether it passed."""
    argv = [python if part == _PY else part for part in gate.argv]
    _say(f"\n{'=' * 72}")
    _say(f"  {gate.name}: {' '.join(argv)}")
    _say(f"{'=' * 72}")
    completed = subprocess.run(argv, cwd=BACKEND, check=False)
    return completed.returncode == 0


def _summarise(command: str, results: list[tuple[str, str]]) -> int:
    """Print the T-19 summary and return the exit code."""
    passed = [name for name, outcome in results if outcome == "PASS"]
    failed = [name for name, outcome in results if outcome == "FAIL"]
    skipped = [name for name, outcome in results if outcome == "SKIP"]

    _say(f"\n{'=' * 72}")
    _say(f"  AlphaCouncil · {command}")
    _say(f"{'=' * 72}")
    for name, outcome in results:
        gate = GATES[name]
        note = f"   <- {gate.why_not}" if outcome == "SKIP" else ""
        _say(f"  [{outcome}] {name:<14} {gate.what}{note}")
    _say("")
    _say(
        f"  ran {len(results)} · passed {len(passed)} · "
        f"failed {len(failed)} · skipped {len(skipped)}"
    )

    if failed:
        _say(f"\n✗ FAILED — {', '.join(failed)}")
        return 1
    if skipped and command == "check":
        _say(f"\n✗ INCOMPLETE — {', '.join(skipped)} did not run (not implemented).")
        _say("  A skipped gate is not a passing gate.")
        _say("  Use `check-lite` to run only the gates that exist today.")
        return 1
    if skipped:
        _say(f"\n  note: {len(skipped)} gate(s) skipped by design for `{command}`.")
    _say("\n✓ every gate that ran, passed")
    return 0


def _clean() -> int:
    """Remove caches and build artefacts.

    Done here rather than in a Makefile recipe because the recipe needed
    ``rm -rf`` and ``find``, which are not guaranteed on Windows.
    """
    removed: list[str] = []
    for pattern in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"):
        for path in BACKEND.rglob(pattern):
            shutil.rmtree(path, ignore_errors=True)
            removed.append(str(path.relative_to(BACKEND)))
    for name in ("htmlcov", "coverage.xml", ".coverage", "build", "dist"):
        path = BACKEND / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(name)
        elif path.is_file():
            path.unlink()
            removed.append(name)
    _say(f"removed {len(removed)} path(s)")
    for entry in removed:
        _say(f"  {entry}")
    return 0


def _print_help() -> None:
    """List the available commands."""
    _say("usage: python scripts/dev.py <command>\n")
    _say("commands:")
    _say("  check           every gate CI runs; skipped gates fail the run")
    _say("  check-lite      only the gates that exist today")
    _say("  clean           remove caches and build artefacts\n")
    _say("gates:")
    for name, gate in GATES.items():
        flag = "" if gate.implemented else "   [NOT IMPLEMENTED]"
        _say(f"  {name:<14}{gate.what}{flag}")


def main(argv: list[str]) -> int:
    """Dispatch a command."""
    if not argv or argv[0] in {"help", "-h", "--help"}:
        _print_help()
        return 0

    command = argv[0]
    if command == "clean":
        return _clean()
    if command in GATES:
        names: tuple[str, ...] = (command,)
    elif command == "check":
        names = CHECK
    elif command == "check-lite":
        names = CHECK_LITE
    else:
        _say(f"unknown command: {command}\n")
        _print_help()
        return 2

    python = _venv_python()
    results: list[tuple[str, str]] = []
    for name in names:
        gate = GATES[name]
        if not gate.implemented:
            results.append((name, "SKIP"))
            continue
        results.append((name, "PASS" if _run(gate, python) else "FAIL"))

    return _summarise(command, results)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
