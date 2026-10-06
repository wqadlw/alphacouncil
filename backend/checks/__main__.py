"""Runner for the static checks.

    python -m checks            # human summary on stderr
    python -m checks --strict   # exit 1 when anything is not clean
    python -m checks --json     # one JSON document on stdout
    python -m checks --only S-01,S-05

Output routing follows ``.ai/error-codes.md`` §1.1: **all human text goes to
stderr**, so ``--json`` output can be piped straight into ``jq`` without
filtering. That rule is applied unconditionally rather than only under
``--json``, because a mode-dependent stream is how a stray banner ends up
breaking a parser six months from now.

Exit codes (``.ai/error-codes.md`` §3):

====  ==========================================================================
``0``  the checks ran to completion — *including* when they found problems
``1``  execution failed (a rule crashed), or ``--strict`` was given and the run
       was not clean
``2``  usage error (``argparse`` produces this; ``main`` never returns it)
====  ==========================================================================

``--strict`` exists because "``0`` means it ran" is right for an inspector and
unusable as a CI gate. The gate is opt-in rather than a change to the documented
contract, and ``scripts/dev.py`` is the only caller that asks for it. Under
``--strict`` a **skipped** rule also fails the run: a rule with nothing to scan
has not passed, it has not run. That is decision T-19 — *a green light is not
the same as a finished job*.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

# `python -m checks` puts `backend/` on sys.path, not `backend/scripts/`, so the
# shared console helper is one directory further away than usual. Added
# explicitly rather than left implicit, because the alternative — not calling
# `use_utf8` here — costs nothing until it does: `sys.stderr` uses
# `backslashreplace`, so an unencodable `✓` does not crash, it is written as the
# six literal characters `\u2713` while the process still exits 0. An exit code
# that is right and an output that lies is the harder failure to notice.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _console import use_utf8

from checks.data_registry import DATA_RULES, DataRule
from checks.framework import Issue, ScanContext, Severity, apply_exemptions
from checks.registry import RULES, Rule, registry_meta

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

LABEL_WIDTH = 34


def main(argv: list[str] | None = None) -> int:
    """Run the selected rules and report. Returns the process exit code."""
    use_utf8()
    args = _parse_args(argv)

    repo_root = Path(args.root).resolve()
    if not (repo_root / "backend").is_dir():
        print(f"usage error: {repo_root} has no backend/ directory", file=sys.stderr)
        return 2

    registry = tuple(DATA_RULES) if args.data else tuple(RULES)
    selected, unknown = _select(args.only, registry)
    if unknown:
        print(f"usage error: unknown rule id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    metas = tuple(rule.meta for rule in selected) or registry_meta()
    ctx = ScanContext(repo_root=repo_root, registry=metas)
    findings: list[tuple[str, Issue]] = []
    skipped: list[tuple[str, str]] = []
    crashed: list[str] = []
    ran = 0
    per_rule: dict[str, tuple[int, int]] = {}

    for rule in selected:
        check_id = rule.meta.check_id
        try:
            result = rule.run(ctx)
        except Exception as exc:  # a crashing rule must not hide the other eleven
            crashed.append(check_id)
            findings.append(
                (
                    check_id,
                    Issue(
                        Severity.ERROR,
                        "CHECK_RUNNER_ERROR",
                        f"rule `{check_id}` raised {type(exc).__name__}: {exc}",
                        f"backend/checks/rules/{rule.meta.slug.replace('-', '_')}.py",
                        "Fix the rule. A check that crashes is indistinguishable from "
                        "a check that passes, which is the failure mode this whole "
                        "subsystem exists to prevent.",
                    ),
                )
            )
            continue

        apply_exemptions(ctx, result, check_id)
        ran += 1
        if result.skipped:
            skipped.append((check_id, result.skipped))
        findings.extend((check_id, issue) for issue in result.issues)

    # ⭐⭐ Counts are taken **before** the dedupe, ⭐⭐ and that order is the whole point:
    # ⭐⭐ dedupe is deliberately cross-rule (one unreasoned suppression comment is found by
    # ⭐⭐ every rule that opens the file, ⭐⭐ and listing it nine times gets skimmed), ⭐⭐
    # ⭐⭐ so a rule whose finding was the duplicate would otherwise report 「clean」 ⭐⭐ —
    # ⭐⭐ **having reported it.** ⭐⭐ The rule did the work; ⭐⭐ the dedupe only decided
    # ⭐⭐ which copy to print. ⭐⭐ (`ruff parses a suppression directive written inside a
    # ⭐⭐ comment as a real one, ⭐⭐ which both warns on every run and silently exempts
    # ⭐⭐ the line ⭐⭐ — ⭐⭐ so the directive is spelled out here rather than used. ⭐⭐
    # ⭐⭐ See `.ai/status.md` §五 and the note in :func:`_write_human`.)
    for check_id, issue in findings:
        if issue.severity is Severity.ERROR:
            errors, warnings = per_rule.get(check_id, (0, 0))
            per_rule[check_id] = (errors + 1, warnings)
        elif issue.severity is Severity.WARNING:
            errors, warnings = per_rule.get(check_id, (0, 0))
            per_rule[check_id] = (errors, warnings + 1)

    findings = _dedupe(findings)
    if args.json:
        _write_json(selected, findings, per_rule, skipped, crashed, ran)
    else:
        _write_human(
            "check-data" if args.data else "check-static",
            selected,
            findings,
            per_rule,
            skipped,
            crashed,
            ran,
        )

    errors = sum(1 for _, issue in findings if issue.severity is Severity.ERROR)
    if crashed:
        return 1
    if args.strict and (errors or skipped):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse arguments. ``argparse`` exits with 2 on a usage error, by design."""
    parser = argparse.ArgumentParser(
        prog="python -m checks",
        description="Static checks for the defects tests cannot catch.",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root to scan")
    parser.add_argument("--only", default=None, help="comma-separated rule ids, e.g. S-01,S-05")
    parser.add_argument(
        "--data",
        action="store_true",
        help="run the data checks (D-nn) instead of the static ones (S-nn)",
    )
    parser.add_argument("--json", action="store_true", help="write one JSON document to stdout")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when there are errors or a rule could not run",
    )
    return parser.parse_args(argv)


def _select(
    only: str | None, registry: tuple[Rule | DataRule, ...]
) -> tuple[list[Rule | DataRule], list[str]]:
    """The rules to run, plus any requested id that does not exist.

    ⭐ The registry is a parameter rather than a module global because ``S-01`` and
    ⭐ ``D-01`` have the same shape, ⭐ and an id that does not resolve in the registry the
    ⭐ flag selected must be a **usage error** ⭐ — ⭐ not a silent no-op, ⭐ because
    ⭐ ``scripts/eval.py:226-229`` already set the rule this repository holds: ⭐ a thing
    ⭐ that never runs is not a thing, ⭐ and its mirror is that a selection which
    ⭐ resolves to nothing is not a selection.
    """
    if not only:
        return list(registry), []
    wanted = [part.strip().upper() for part in only.split(",") if part.strip()]
    by_id = {rule.meta.check_id: rule for rule in registry}
    unknown = [check_id for check_id in wanted if check_id not in by_id]
    return [by_id[check_id] for check_id in wanted if check_id in by_id], unknown


def _dedupe(findings: list[tuple[str, Issue]]) -> list[tuple[str, Issue]]:
    """Collapse identical findings, keeping the rule that found it.

    Several rules can reach the same conclusion about the same file — an
    unreasoned ``# noqa`` is spotted by every rule that opens that file — and a
    report that lists it nine times gets skimmed.

    ⭐⭐ **The key is deliberately cross-rule** ⭐⭐ — it excludes the owning check id, ⭐⭐
    because the skimming this function exists to prevent is worse than a rule sharing a
    finding. ⭐⭐ **Which is exactly why the per-rule counts are taken before this call**
    ⭐⭐ (see :func:`main`): ⭐⭐ a rule that found the duplicate did the work, ⭐⭐ and must
    ⭐⭐ not be told 「clean」.
    """
    seen: set[tuple[str, str | None, str]] = set()
    unique: list[tuple[str, Issue]] = []
    for check_id, issue in findings:
        key = (issue.code, issue.target, issue.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append((check_id, issue))
    return unique


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _write_human(
    gate: str,
    selected: Sequence[Rule | DataRule],
    findings: list[tuple[str, Issue]],
    per_rule: dict[str, tuple[int, int]],
    skipped: list[tuple[str, str]],
    crashed: list[str],
    ran: int,
) -> None:
    """Full report on stderr. Nothing is elided (``.ai/error-codes.md`` §4).

    ⭐⭐ **`per_rule` is computed by :func:`main` before the dedupe and passed in here.**
    ⭐⭐ It used to be recomputed from `issue.code` ⭐⭐ — ⭐⭐ which named the wrong rule,
    ⭐⭐ because every data rule shares the code ``CHECK_DATA_INTEGRITY`` ⭐⭐ (and S-05
    ⭐⭐ requires that code to be a registered *category*, ⭐⭐ not a per-rule id, ⭐⭐ so
    ⭐⭐ codes can never identify a rule). ⭐⭐ The map comprehension took the **last**
    ⭐⭐ registered rule, ⭐⭐ so `D-02`'s finding was charged to `D-22`: ⭐⭐ the gate
    ⭐⭐ said `[FAIL] D-22 audit-detail-length` ⭐⭐ above an error whose own message said
    ⭐⭐ `D-02`. ⭐⭐ **A red gate naming the wrong file is worse than no gate** ⭐⭐ — ⭐⭐
    ⭐⭐ the reader opens the wrong rule, sees nothing wrong, and concludes the gate lies.
    """
    out = sys.stderr
    skipped_ids = {check_id for check_id, _ in skipped}
    crashed_ids = set(crashed)

    print("", file=out)
    print("=" * 72, file=out)
    print(f"  AlphaCouncil · {gate}", file=out)
    print("=" * 72, file=out)
    for rule in selected:
        check_id = rule.meta.check_id
        label = f"{check_id} {rule.meta.slug}"
        errors, warnings = per_rule.get(check_id, (0, 0))
        if check_id in crashed_ids:
            status, note = "[CRASH]", "raised — see the finding below"
        elif check_id in skipped_ids:
            status = "[SKIP ]"
            note = next(reason for cid, reason in skipped if cid == check_id)
        elif errors:
            status, note = "[FAIL ]", f"{errors} error(s), {warnings} warning(s)"
        elif warnings:
            status, note = "[WARN ]", f"{warnings} warning(s)"
        else:
            status, note = "[PASS ]", "clean"
        print(f"  {status} {label:<{LABEL_WIDTH}} {note}", file=out)

    ordered = sorted(findings, key=lambda pair: list(Severity).index(pair[1].severity))
    if ordered:
        print("-" * 72, file=out)
        for check_id, issue in ordered:
            # ⭐⭐ The owner is printed on every finding, ⭐⭐ not just in its message text.
            # ⭐⭐ `D-02`'s message happens to begin 「D-02: …」 ⭐⭐ and a rule that omits the
            # ⭐⭐ prefix would then be the only unattributable one ⭐⭐ — ⭐⭐ so the label
            # ⭐⭐ comes from the runner, ⭐⭐ which cannot get it wrong.
            print(f"  [{check_id}] {issue.render()}", file=out)

    counts = dict.fromkeys(Severity, 0)
    for _, issue in findings:
        counts[issue.severity] += 1
    print("-" * 72, file=out)
    print(
        f"  ran {ran} · skipped {len(skipped)} · crashed {len(crashed)} · "
        f"findings {len(findings)} ({counts[Severity.ERROR]} error, "
        f"{counts[Severity.WARNING]} warning, {counts[Severity.INFO]} info)",
        file=out,
    )
    if skipped:
        print("", file=out)
        print("  ⚠️  a skipped rule has not passed — it has not run (T-19)", file=out)
    clean = not (counts[Severity.ERROR] or skipped or crashed)
    print(f"  {'✓' if clean else '✗'} {'PASSED' if clean else 'FAILED'}", file=out)
    print("", file=out)


def _write_json(
    selected: Sequence[Rule | DataRule],
    findings: list[tuple[str, Issue]],
    per_rule: dict[str, tuple[int, int]],
    skipped: list[tuple[str, str]],
    crashed: list[str],
    ran: int,
) -> None:
    """One JSON document on stdout, and nothing else (``.ai/error-codes.md`` §1.1).

    ⭐⭐ **`check` is added to every issue, ⭐⭐ and it is the fix for the same defect the
    human report had** ⭐⭐ — ⭐⭐ a consumer reading `issues[]` had no way to tell which
    ⭐⭐ rule produced which finding, ⭐⭐ because the code is a shared category. ⭐⭐ The
    ⭐⭐ key is **not** part of the ``Issue`` envelope ⭐⭐ (``.ai/error-codes.md`` §1 owns
    ⭐⭐ that, ⭐⭐ and ``Issue.as_dict`` is unchanged ⭐⭐ — ⭐⭐ the runner adds it, ⭐⭐
    ⭐⭐ because the runner is what knows.
    """
    counts = dict.fromkeys(Severity, 0)
    for _, issue in findings:
        counts[issue.severity] += 1
    document = {
        "summary": {
            "rules_selected": len(selected),
            "rules_ran": ran,
            "rules_skipped": len(skipped),
            "rules_crashed": len(crashed),
            "findings": len(findings),
            "errors": counts[Severity.ERROR],
            "warnings": counts[Severity.WARNING],
            "infos": counts[Severity.INFO],
        },
        "issues": [{"check": check_id, **issue.as_dict()} for check_id, issue in findings],
        "per_rule": {
            rule.meta.check_id: {"errors": per_rule.get(rule.meta.check_id, (0, 0))[0],
                                 "warnings": per_rule.get(rule.meta.check_id, (0, 0))[1]}
            for rule in selected
        },
        "skipped": [{"check": check_id, "reason": reason} for check_id, reason in skipped],
        "crashed": crashed,
    }
    json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
