"""S-08 — an immature outcome renders as nothing, never as ``0`` or ``—``.

**Defect guarded:** product red line 6 and constitution 5.2 rule 13. A decision
whose outcome has not matured has *no* result. Rendering ``0`` says "this made
nothing", and rendering ``—`` says "this made nothing but we dressed it up".
Both are the same lie in different clothes: the user reads a number where the
truth is "not yet knowable", and the whole point of separating process from
result collapses.

Anti-pattern (forbidden)::

    <Score>{review.resultScore ?? 0}</Score>
    <Score>{review.resultScore || '—'}</Score>

Correct form::

    {review.resultScore !== null && <Score>{review.resultScore}</Score>}
    // or, explicitly:
    <Score>{review.resultScore ?? ''}</Score>

Why a test cannot catch this: ``resultScore ?? 0`` renders *something* in every
case, so a render test passes. The defect only shows up months later, as a row
of zeroes that nobody can distinguish from a real break-even — which is exactly
the failure red line 6 exists to prevent.

Scope note: only outcome-specific names are inspected (``outcome``,
``resultScore``, ``realized`` …), not a bare ``score``. A *process* score of zero
is meaningful and must be allowed to render; a result score of zero is a claim
about the world that cannot be true yet. E2E is the final guarantee
(``.ai/checks/static/README.md`` §3.2).
"""

from __future__ import annotations

import re

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target
from checks.frontend import files, skip_reason

CODE = "CHECK_IMMATURE_OUTCOME"

META = CheckMeta(
    check_id="S-08",
    slug="immature-outcome-blank",
    title="immature outcomes render blank, not 0 or an em dash",
    priority="P1",
    code=CODE,
)


#: Names that mean "the result of the decision" as opposed to "how the decision
#: was made". Deliberately outcome-only — see the scope note above.
OUTCOME_NAMES = (
    "outcome",
    "resultScore",
    "result_score",
    "resultPct",
    "result_pct",
    "actualReturn",
    "actual_return",
    "realized",
    "pnl",
    "maturedResult",
)

#: `x ?? fallback` / `x || fallback`
_FALLBACK = re.compile(r"(?:\?\?|\|\|)\s*(?P<value>[^,;\n})]+)")

#: Placeholders that stand in for "no value yet" but read as a value.
_ZERO_PLACEHOLDERS = frozenset({"0", "'0'", '"0"', "{0}"})
_DASH_PLACEHOLDERS = frozenset(
    {"'—'", "'–'", "'-'", "'--'", '"—"', "'N/A'", '"N/A"', "'n/a'", "'暂无'", "'待定'"}
)


def run(ctx: ScanContext) -> CheckResult:
    """Find outcome fallbacks that render a value where there is none."""
    result = CheckResult()
    sources = files(ctx)
    if not sources:
        result.skipped = skip_reason()
        return result

    for path in sources:
        result.files.append(path)
        for lineno, line in enumerate(ctx.text(path).splitlines(), start=1):
            if not any(name in line for name in OUTCOME_NAMES):
                continue
            for match in _FALLBACK.finditer(line):
                value = match.group("value").strip()
                if value in _ZERO_PLACEHOLDERS:
                    result.error(
                        CODE,
                        f"immature outcome falls back to `{value}` — a zero reads as a result",
                        target=format_target(ctx, path, lineno),
                        fix="Render nothing: use `?? ''`, or gate the element on "
                        "`resultScore !== null`. Red line 6.",
                    )
                elif value in _DASH_PLACEHOLDERS:
                    result.error(
                        CODE,
                        f"immature outcome falls back to `{value}` — a dash still renders a slot",
                        target=format_target(ctx, path, lineno),
                        fix="Render nothing: use `?? ''`, or gate the element on "
                        "`resultScore !== null`. Red line 6.",
                    )
    return result


__all__ = ["META", "run"]
