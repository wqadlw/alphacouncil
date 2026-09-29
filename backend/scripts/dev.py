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

  ⭐ **Spec 035 added the other half of that rule.** T-19 is about gates that are
  *declared but skipped*; this was the opposite — a whole test directory that was
  **never declared at all**, so nothing reported it missing. Three migration tests
  sat red through six migrations while `check` printed 10/10. ⭐ A gate that silently
  skips part of what it covers fails the same way as one that promises more than it
  does, because the gap is invisible in both cases.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from _console import use_utf8

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"

# Replaced with the resolved interpreter before the command is run.
_PY = "{py}"
# Replaced with the resolved `npm` executable. Resolved at run time rather than
# written as a bare `npm` because on Windows the launcher is `npm.cmd`, and
# CreateProcess does not apply PATHEXT — a bare `npm` in argv is a
# FileNotFoundError, not a missing-tool message.
_NPM = "{npm}"


@dataclass(frozen=True)
class Gate:
    """One quality gate."""

    name: str
    what: str
    argv: tuple[str, ...] = ()
    implemented: bool = True
    why_not: str = ""
    #: Working directory. `None` means the backend package, which is where every
    #: Python gate runs from. The frontend gates pass `FRONTEND` instead, because
    #: that is where `package.json` is.
    cwd: Path | None = None


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
    # ⭐ **Spec 035.** `tests/integration` had never been in the gate — it migrates real
    # databases, and three of its tests sat **red through six migrations** while the gate
    # reported 10/10. A guardrail that silently skips part of what it covers fails the same
    # way as one that promises more than it does: the gap is invisible either way.
    #
    # Separate from `test` on purpose, so a failure names which half failed. Merging them
    # would also have hidden this: the reason nobody noticed for six migrations is that
    # nobody ran them, and a merged step reads as 「the tests pass」.
    "test-integration": Gate(
        "test-integration",
        "pytest tests/integration (real migrations, real databases)",
        (_PY, "-m", "pytest", "tests/integration", "-q"),
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
        "static checks S-01..S-14 (.ai/checks/static/)",
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
    # ---------------------------------------------------------------------
    # Frontend. These four exist because they did not, and CI has run them
    # since 2026-09-26 — so `check` claimed to run "every gate CI runs" while a
    # broken frontend passed locally. That is the same defect CI's `frontend`
    # job was added to fix, one layer down: a check that never ran, reported as
    # passing. Keep this list in step with `.github/workflows/ci.yml`.
    # ---------------------------------------------------------------------
    "frontend-typecheck": Gate(
        "frontend-typecheck",
        "tsc -b (app / node / test projects)",
        (_NPM, "run", "typecheck"),
        cwd=FRONTEND,
    ),
    "frontend-lint": Gate(
        "frontend-lint",
        "oxlint",
        (_NPM, "run", "lint"),
        cwd=FRONTEND,
    ),
    "frontend-test": Gate(
        "frontend-test",
        "vitest run",
        (_NPM, "test"),
        cwd=FRONTEND,
    ),
    "frontend-build": Gate(
        "frontend-build",
        "vite build (production bundle)",
        (_NPM, "run", "build"),
        cwd=FRONTEND,
    ),
    "e2e": Gate(
        "e2e",
        "playwright test (built app on Edge/Chromium)",
        (_NPM, "run", "test:e2e"),
        cwd=FRONTEND,
    ),
}

# `check` is the CI gate set: everything, including the not-yet-written ones, so
# the run cannot claim to be complete while gates are missing.
CHECK: tuple[str, ...] = (
    "lint",
    "typecheck",
    "licenses",
    "check-static",
    "test",
    # ⭐ Spec 035: the integration suite migrates real databases. It was never in
    # either set, so three of its tests sat red through six migrations.
    "test-integration",
    "frontend-typecheck",
    "frontend-lint",
    "frontend-test",
    "frontend-build",
    "e2e",
)
# `check-lite` is the daily driver: only the gates that actually exist. The four
# frontend gates are in here too — they take about four seconds together, and a
# gate that only runs in CI is a gate that runs after the commit that broke it.
CHECK_LITE: tuple[str, ...] = (
    "lint",
    "typecheck",
    "licenses",
    "test",
    # ⭐ 4.4s measured, against 3 minutes for the unit suite — and this is the daily
    # driver, whose own comment says a gate that only runs in CI is a gate that runs
    # after the commit that broke it.
    "test-integration",
    "frontend-typecheck",
    "frontend-lint",
    "frontend-test",
    "frontend-build",
)


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


def _resolve(argv: tuple[str, ...], python: str) -> list[str] | None:
    """Substitute the placeholders, or return ``None`` if a tool is missing.

    ``None`` rather than an exception: "npm is not installed" is a fact the run
    should report as a failed gate, not a traceback that buries the other eight
    results. A gate that cannot run has not passed (T-19).
    """
    resolved: list[str] = []
    for part in argv:
        if part == _PY:
            resolved.append(python)
        elif part == _NPM:
            npm = shutil.which("npm")
            if npm is None:
                return None
            resolved.append(npm)
        else:
            resolved.append(part)
    return resolved


def _run(gate: Gate, python: str) -> bool:
    """Run one gate, streaming its output, and report whether it passed."""
    argv = _resolve(gate.argv, python)

    # The banner shows the command that will actually run — resolved paths, not
    # placeholders — because the resolved path is the thing worth being able to
    # copy out of the log and re-run.
    _say(f"\n{'=' * 72}")
    _say(f"  {gate.name}: {' '.join(argv if argv is not None else gate.argv)}")
    _say(f"{'=' * 72}")

    if argv is None:
        _say("  cannot run: `npm` is not on PATH.")
        _say("  The frontend gates need Node. Install it, or accept that the")
        _say("  frontend is unverified — which is what a green run would claim.")
        return False

    cwd = gate.cwd or BACKEND
    # A frontend gate with no `node_modules` fails with "tsc: not found", which
    # reads like a broken repository rather than an uninstalled dependency. Say
    # which one it is.
    if gate.cwd is not None and not (cwd / "node_modules").is_dir():
        _say(f"  cannot run: {cwd.name}/node_modules is missing.")
        _say("  Run `npm install` in frontend/ first.")
        return False

    completed = subprocess.run(argv, cwd=cwd, check=False)
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
    _say("  clean           remove caches and build artefacts")
    _say("  eval            product red lines: how many are actually guarded\n")
    _say("gates:")
    for name, gate in GATES.items():
        flag = "" if gate.implemented else "   [NOT IMPLEMENTED]"
        _say(f"  {name:<14}{gate.what}{flag}")


def main(argv: list[str]) -> int:
    """Dispatch a command."""
    # Before anything is printed. This script's whole job is to report whether
    # ten gates passed, and on a cp936 console the `✓` it ends with is not
    # encodable — which used to turn a green run into exit code 1
    # (`regressions/0004`).
    use_utf8()
    if not argv or argv[0] in {"help", "-h", "--help"}:
        _print_help()
        return 0

    command = argv[0]
    if command == "clean":
        return _clean()
    if command == "eval":
        # Delegated, and deliberately **not** a gate in CHECK. `eval` is red
        # today and red is its honest state: 5 of 15 red lines have a verifier
        # that runs. Putting it in CHECK would make `dev.py check` permanently
        # red and train everyone to ignore the summary — which is how a gate
        # stops being a gate. It stays a command you have to ask for, and its
        # baseline is recorded in `.ai/eval/redlines.json`.
        from eval import main as eval_main

        return eval_main(argv[1:])
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
