"""Run the red-line evaluation set and report an honest pass rate.

    python scripts/eval.py            # human table on stderr, JSON on stdout
    python scripts/eval.py --json     # JSON only (`.ai/error-codes.md` §1.1)

**What this is for.** The constitution lists fifteen product red lines and, in
the third column of that table, the mechanism each one claims to be enforced
by. Until now nothing checked that column. This runner does, and the first
honest measurement is unflattering:

    full 5 · partial 2 · none 8  →  5 / 15 guarded

That number is the point. "We enforce our red lines in code" is a claim, and
until something counts them it is a claim in the same category as the v1
architecture document that described four packages nobody had built.

**The rule that makes it useful — T-19, applied to the product's own promises.**
A red line with no verifier counts as a **failure**, not as "not applicable" and
not as a skip. The alternative is the failure mode this project has already
been bitten by twice: a check that never runs, reported as passing
(``.ai/regressions/0002``, and the ``skipped`` gate in ``0003``'s index).

So this command **exits 1 today**, on purpose, and the baseline it is measured
against is recorded in ``redlines.json`` *before* anything was fixed — so the
number cannot be inflated by the act of measuring it.

Two tiers of verifier, and the difference is not cosmetic:

``static``
    A rule in ``.ai/checks/static/``. **Executed now**, via
    ``python -m checks --json``. The rule must be registered, must have
    actually run (a skipped rule has not passed), and must report zero errors.

``gate``
    A test enforced by a gate in ``scripts/dev.py`` ``CHECK``. **Not executed
    here** — that is the gate's job, on every ``dev.py check``. What ``eval``
    verifies is that the declaration **cannot rot**: the gate must still be in
    ``CHECK``, and the named test must still exist in its source file. Delete
    the E2E test without updating this registry and ``eval`` fails.

Claiming a ``gate`` tier is ``executed`` would be exactly the kind of
overstatement this project keeps punishing, so the output labels them
separately.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from _console import use_utf8

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
REGISTRY = REPO_ROOT / ".ai" / "eval" / "redlines.json"

Verdict = Literal["pass", "fail"]


@dataclass(frozen=True)
class Result:
    """One red line's outcome."""

    redline_id: int
    title: str
    coverage: str
    verdict: Verdict
    #: ``executed`` — this run ran it. ``declared`` — verified to exist, run by a gate.
    tier: str
    why: str
    gap: str | None


def _load() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return loaded


def _run_rule(check_id: str) -> dict[str, Any]:
    """Run one static rule and return its JSON report.

    **One subprocess per rule, on purpose.** The runner's ``--json`` contract
    (``checks/__main__.py``, ``.ai/error-codes.md`` §1.1) reports a *summary*
    plus a flat ``issues`` list — it carries **no per-rule attribution**, so a
    single run cannot tell you which rule produced which finding, nor which
    rules ran. Widening that contract is a change to another module's
    documented behaviour; asking for one rule at a time gets the same answer
    through the interface that already exists. Five subprocesses, about eight
    seconds, no contract touched.

    A failure to produce JSON is raised, not swallowed: every static verifier
    depends on it, so returning an empty report would quietly turn "the check
    runner is broken" into "the red lines are unguarded" — a much bigger
    problem wearing a smaller one.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "checks", "--json", "--strict", "--only", check_id],
        cwd=BACKEND,
        capture_output=True,
        check=False,
    )
    stderr = completed.stderr.decode("utf-8", "replace")
    if not completed.stdout.strip():
        if "unknown rule" in stderr:
            return {"__unknown_rule__": True}
        msg = (
            f"the static-check runner produced no JSON for {check_id}; "
            f"exit={completed.returncode} stderr={stderr[:400]}"
        )
        raise RuntimeError(msg)
    decoded: dict[str, Any] = json.loads(completed.stdout.decode("utf-8"))
    return decoded


def _static_ok(check_id: str) -> tuple[bool, str]:
    """Did one static rule run, cleanly?

    A skipped rule fails. ``skipped`` means the rule had nothing to scan, and a
    rule that did not look at anything has not found anything — T-19 again, and
    it is exactly how S-09 sat dark until a component existed to scan.
    """
    report = _run_rule(check_id)
    if report.get("__unknown_rule__"):
        return False, f"{check_id} is not a registered rule (the registry names a missing one)"

    summary = report.get("summary", {})
    ran = summary.get("rules_ran", 0)
    skipped = summary.get("rules_skipped", 0)
    crashed = summary.get("rules_crashed", 0)

    if ran == 0:
        detail = f"skipped={skipped} crashed={crashed}"
        return False, f"{check_id} did not run ({detail}) — nothing to scan is not a pass (T-19)"
    if crashed:
        return False, f"{check_id} crashed ({crashed} rule crash(es))"
    if skipped:
        return False, f"{check_id} was skipped — nothing to scan is not a pass (T-19)"

    errors = [i for i in report.get("issues", []) if i.get("severity") == "error"]
    if errors:
        codes = ", ".join(sorted({str(e.get("code")) for e in errors}))
        return False, f"{check_id} reported {len(errors)} error finding(s): {codes}"
    return True, f"{check_id} ran clean"


def _gate_ok(spec: dict[str, Any]) -> tuple[bool, str]:
    """Is a gate-backed declaration still true?

    Two mechanical questions, both answerable without a browser:
    is the gate still part of ``dev.py check``, and does the named test still
    exist in its file.
    """
    import dev

    gate = spec.get("gate")
    if not gate:
        return False, "verifier has no gate name"
    if gate not in dev.GATES:
        return False, f"gate '{gate}' does not exist in dev.py GATES"
    if gate not in dev.CHECK:
        return False, f"gate '{gate}' is not in dev.py CHECK — a gate that never runs is not a gate"

    path = REPO_ROOT / str(spec.get("file", ""))
    if not path.is_file():
        return False, f"{spec.get('file')} does not exist"
    selector = str(spec.get("selector", ""))
    if selector and selector not in path.read_text(encoding="utf-8"):
        return False, f"test {selector!r} is no longer in {spec.get('file')}"
    return True, f"enforced by the '{gate}' gate; test still present"


def evaluate() -> tuple[list[Result], dict[str, Any]]:
    """Evaluate every red line in the registry."""
    registry = _load()
    results: list[Result] = []

    for entry in registry["redlines"]:
        coverage = entry["coverage"]
        verifier = entry.get("verifier")
        gap = entry.get("gap")

        if verifier is None:
            results.append(
                Result(
                    redline_id=entry["id"],
                    title=entry["title"],
                    coverage=coverage,
                    verdict="fail",
                    tier="none",
                    why="no verifier registered",
                    gap=gap,
                )
            )
            continue

        kind = verifier["kind"]
        if kind == "static":
            ok, why = _static_ok(verifier["check"])
            tier = "executed"
        elif kind == "gate":
            ok, why = _gate_ok(verifier)
            tier = "declared"
        else:  # pragma: no cover - guarded by a registry test
            ok, why, tier = False, f"unknown verifier kind {kind!r}", "none"

        # `partial` never passes: the verifier covers part of the red line and
        # the rest is written down in `gap`. Counting it as a pass would make
        # the number prettier and the document a lie.
        if coverage == "partial":
            ok = False
            why = f"{why} — but coverage is 'partial', which does not pass"

        results.append(
            Result(
                redline_id=entry["id"],
                title=entry["title"],
                coverage=coverage,
                verdict="pass" if ok else "fail",
                tier=tier,
                why=why,
                gap=gap,
            )
        )

    return results, registry


def _summary(results: list[Result]) -> dict[str, int]:
    return {
        "total": len(results),
        "pass": sum(1 for r in results if r.verdict == "pass"),
        "fail": sum(1 for r in results if r.verdict == "fail"),
        "full": sum(1 for r in results if r.coverage == "full"),
        "partial": sum(1 for r in results if r.coverage == "partial"),
        "none": sum(1 for r in results if r.coverage == "none"),
    }


def main(argv: list[str] | None = None) -> int:
    """Report the pass rate. Returns 0 only when every red line is guarded."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="write one JSON document to stdout")
    args = parser.parse_args(argv)

    # This file's own red lines are full of Chinese, and its output is piped
    # into a JSON parser. Without this, a cp936 console truncates the document
    # mid-string — and it did, once, on the day it was written
    # (`.ai/regressions/0004`, and S-13 which now enforces it).
    use_utf8()

    results, registry = evaluate()
    counts = _summary(results)
    rate = counts["pass"] / counts["total"] if counts["total"] else 0.0
    threshold = registry["policy"].get("threshold", 1.0)

    document = {
        "counts": counts,
        "pass_rate": round(rate, 4),
        "threshold": threshold,
        "baseline": registry.get("baseline"),
        "redlines": [
            {
                "id": r.redline_id,
                "title": r.title,
                "coverage": r.coverage,
                "verdict": r.verdict,
                "tier": r.tier,
                "why": r.why,
                "gap": r.gap,
            }
            for r in results
        ],
    }

    if args.json:
        json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0 if rate >= threshold else 1

    out = sys.stderr
    print("", file=out)
    print("=" * 78, file=out)
    print("  AlphaCouncil · eval — product red lines", file=out)
    print("=" * 78, file=out)
    for r in results:
        mark = "PASS" if r.verdict == "pass" else "FAIL"
        print(f"  [{mark}] red line {r.redline_id:>2}  {r.title}", file=out)
        print(f"          coverage={r.coverage}  tier={r.tier}", file=out)
        print(f"          {r.why}", file=out)
        if r.gap:
            first = r.gap.strip().splitlines()[0]
            print(f"          gap: {first}", file=out)
    print("-" * 78, file=out)
    print(
        f"  {counts['pass']} / {counts['total']} guarded "
        f"({rate * 100:.1f}%)  ·  coverage: full {counts['full']} · "
        f"partial {counts['partial']} · none {counts['none']}",
        file=out,
    )
    base = registry.get("baseline")
    if base:
        delta = counts["pass"] - base.get("pass", 0)
        print(
            f"  baseline {base['date']}: {base['pass']} / {base['total']} "
            f"({delta:+d} since)",
            file=out,
        )
    if rate < threshold:
        print("", file=out)
        print(
            "  FAILED — a red line with no check has not passed, it has not been checked (T-19).",
            file=out,
        )
        print(f"  Threshold is {threshold:.0%}. Red today is the expected state:", file=out)
        print("  the honest baseline is recorded above so progress is measurable.", file=out)
        return 1
    print("\n  every red line has a verifier that runs", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
