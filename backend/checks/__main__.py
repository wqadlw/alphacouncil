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
from pathlib import Path

from checks.framework import Issue, ScanContext, Severity, apply_exemptions
from checks.registry import RULES, Rule, registry_meta

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

LABEL_WIDTH = 34


def main(argv: list[str] | None = None) -> int:
    """Run the selected rules and report. Returns the process exit code."""
    args = _parse_args(argv)

    repo_root = Path(args.root).resolve()
    if not (repo_root / "backend").is_dir():
        print(f"usage error: {repo_root} has no backend/ directory", file=sys.stderr)
        return 2

    selected, unknown = _select(args.only)
    if unknown:
        print(f"usage error: unknown rule id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    ctx = ScanContext(repo_root=repo_root, registry=registry_meta())
    findings: list[Issue] = []
    skipped: list[tuple[str, str]] = []
    crashed: list[str] = []
    ran = 0

    for rule in selected:
        check_id = rule.meta.check_id
        try:
            result = rule.run(ctx)
        except Exception as exc:  # a crashing rule must not hide the other eleven
            crashed.append(check_id)
            findings.append(
                Issue(
                    Severity.ERROR,
                    "CHECK_RUNNER_ERROR",
                    f"rule `{check_id}` raised {type(exc).__name__}: {exc}",
                    f"backend/checks/rules/{rule.meta.slug.replace('-', '_')}.py",
                    "Fix the rule. A check that crashes is indistinguishable from "
                    "a check that passes, which is the failure mode this whole "
                    "subsystem exists to prevent.",
                )
            )
            continue

        apply_exemptions(ctx, result)
        ran += 1
        if result.skipped:
            skipped.append((check_id, result.skipped))
        findings.extend(result.issues)

    findings = _dedupe(findings)
    if args.json:
        _write_json(selected, findings, skipped, crashed, ran)
    else:
        _write_human(selected, findings, skipped, crashed, ran)

    errors = sum(1 for issue in findings if issue.severity is Severity.ERROR)
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
    parser.add_argument("--json", action="store_true", help="write one JSON document to stdout")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when there are errors or a rule could not run",
    )
    return parser.parse_args(argv)


def _select(only: str | None) -> tuple[list[Rule], list[str]]:
    """The rules to run, plus any requested id that does not exist."""
    if not only:
        return list(RULES), []
    wanted = [part.strip().upper() for part in only.split(",") if part.strip()]
    by_id = {rule.meta.check_id: rule for rule in RULES}
    unknown = [check_id for check_id in wanted if check_id not in by_id]
    return [by_id[check_id] for check_id in wanted if check_id in by_id], unknown


def _dedupe(findings: list[Issue]) -> list[Issue]:
    """Collapse identical findings.

    Several rules can reach the same conclusion about the same file — an
    unreasoned ``# noqa`` is spotted by every rule that opens that file — and a
    report that lists it nine times gets skimmed.
    """
    seen: set[tuple[str, str | None, str]] = set()
    unique: list[Issue] = []
    for issue in findings:
        key = (issue.code, issue.target, issue.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _write_human(
    selected: list[Rule],
    findings: list[Issue],
    skipped: list[tuple[str, str]],
    crashed: list[str],
    ran: int,
) -> None:
    """Full report on stderr. Nothing is elided (``.ai/error-codes.md`` §4)."""
    out = sys.stderr
    skipped_ids = {check_id for check_id, _ in skipped}
    crashed_ids = set(crashed)

    # Counts come from the deduplicated findings, attributed by error code.
    # Counting while the rules ran inflated every rule that opened a file
    # containing an unreasoned `# noqa`, because the framework adds that finding
    # once per rule that opened it.
    owner = {rule.meta.code: rule.meta.check_id for rule in selected}
    per_rule: dict[str, tuple[int, int]] = {}
    for issue in findings:
        check_id = owner.get(issue.code)
        if check_id is None:
            continue
        errors, warnings = per_rule.get(check_id, (0, 0))
        if issue.severity is Severity.ERROR:
            per_rule[check_id] = (errors + 1, warnings)
        elif issue.severity is Severity.WARNING:
            per_rule[check_id] = (errors, warnings + 1)

    print("", file=out)
    print("=" * 72, file=out)
    print("  AlphaCouncil · check-static", file=out)
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

    ordered = sorted(findings, key=lambda issue: list(Severity).index(issue.severity))
    if ordered:
        print("-" * 72, file=out)
        for issue in ordered:
            print(f"  {issue.render()}", file=out)

    counts = dict.fromkeys(Severity, 0)
    for issue in findings:
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
    selected: list[Rule],
    findings: list[Issue],
    skipped: list[tuple[str, str]],
    crashed: list[str],
    ran: int,
) -> None:
    """One JSON document on stdout, and nothing else (``.ai/error-codes.md`` §1.1)."""
    counts = dict.fromkeys(Severity, 0)
    for issue in findings:
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
        "issues": [issue.as_dict() for issue in findings],
        "skipped": [{"check": check_id, "reason": reason} for check_id, reason in skipped],
        "crashed": crashed,
    }
    json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
