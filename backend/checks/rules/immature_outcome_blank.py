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

#: ⭐⭐⭐ **Names whose value does not exist yet at the moment the reader is asking** — a
#: financial figure whose report has not been announced, as opposed to a decision's result.
#:
#: These are **not** outcomes, and keeping them in a second list is the point rather than
#: the tidiness:
#:
#:     an outcome   belongs to the decision; the reader waits for *their own* call to mature
#:     a figure     belongs to the world;  the reader waits for *the company to publish it*
#:
#: Same rendering rule (render nothing), a different sentence, and a different date on it.
#:
#: ⚠️⚠️ **This list exists because the gate was blind, not because the vocabulary was
#: complete.** Measured 2026-10-02, with these three lines written into a real frontend
#: source and `S-08` run against them:
#:
#:     roe_avg ?? 0      -> clean
#:     revenue ?? 0      -> clean
#:     net_profit ?? 0   -> clean
#:
#: Those are **constitution §4.4 verbatim as code** — 「公告前一律空值,**绝不填 0**」 — and
#: `OUTCOME_NAMES` held ten names, none of them financial. ⭐ **So the risk was never that
#: the gate would stop me; it was that the gate thought it had** (`F-218`: the mechanisms
#: exist and still do not reach).
#:
#: Both spellings are listed because the codebase holds both: the provider maps
#: `roeAvg`/`MBRevenue` (`providers/financial.py:436-443`) while the column names are
#: `roe_avg`/`revenue`. ⭐ Naming one spelling would have left the other blind, and a
#: half-fixed blind spot is worse than none — it looks covered.
UNPUBLISHED_NAMES = (
    "roe_avg",
    "roeAvg",
    "np_margin",
    "npMargin",
    "gp_margin",
    "gpMargin",
    "net_profit",
    "netProfit",
    "eps_ttm",
    "epsTTM",
    "revenue",
    "MBRevenue",
    "total_shares",
    "totalShare",
    "float_shares",
    "liqaShare",
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
            # ⭐ Two vocabularies, and the line has to say **which one** matched, because the
            # advice differs: an outcome is gated on the reader's own field, a figure is
            # gated on the announcement calendar.
            unpublished = any(name in line for name in UNPUBLISHED_NAMES)
            if not unpublished and not any(name in line for name in OUTCOME_NAMES):
                continue
            # ⭐ Named, because the message needs it and the f-string that inlined the
            # conditional was 101 columns — and the reader wants to see which of the two
            # vocabularies matched either way.
            shape = "figure" if unpublished else "outcome"
            for match in _FALLBACK.finditer(line):
                value = match.group("value").strip()
                if value in _ZERO_PLACEHOLDERS:
                    result.error(
                        CODE,
                        f"immature {shape} falls back to `{value}` "
                        f"— a zero reads as a result",
                        target=format_target(ctx, path, lineno),
                        fix=(
                            "Gate on the announcement date and render nothing: a figure whose "
                            "report was not published on the criterion's `as_of` has no "
                            "value at all. Constitution 4.4. Red line 6."
                            if unpublished
                            else "Render nothing: use `?? ''`, or gate the element on "
                            "`resultScore !== null`. Red line 6."
                        ),
                    )
                elif value in _DASH_PLACEHOLDERS:
                    result.error(
                        CODE,
                        f"immature {shape} falls back to `{value}` "
                        f"— a dash still renders a slot",
                        target=format_target(ctx, path, lineno),
                        fix=(
                            "Gate on the announcement date and render nothing: a figure whose "
                            "report was not published on the criterion's `as_of` has no "
                            "value at all. Constitution 4.4. Red line 6."
                            if unpublished
                            else "Render nothing: use `?? ''`, or gate the element on "
                            "`resultScore !== null`. Red line 6."
                        ),
                    )
    return result


__all__ = ["META", "run"]
