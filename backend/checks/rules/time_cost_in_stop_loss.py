"""S-09 — a stop-loss prompt must state the cost in time.

**Defect guarded:** product red line 12 and constitution 12.1. "Cut your losses"
is advice; "this position needs 7 years of gains to get back to even" is a fact
about the world. The second one changes behaviour, because it converts a number
the user is emotionally attached to into a number about their life. A stop-loss
dialog that shows only the percentage is the version everyone already ignores.

Anti-pattern (forbidden)::

    <StopLossDialog>
      <p>当前亏损 32%</p>
      <Button>卖出</Button>
    </StopLossDialog>

Correct form::

    <StopLossDialog>
      <p>当前亏损 32%</p>
      <p>恢复所需年数：约 2.3 年（按年化 15% 计）</p>
      <Button>卖出</Button>
    </StopLossDialog>

Why a test cannot catch this: a render test asserts the dialog opens and shows
the loss. Nothing in the assertion says the time-cost line is *missing*, because
absence is not a render failure. The line has to be required, and a requirement
is checked by looking for it, not by running something.

Scope note: a file counts as the stop-loss component when its **stem** names it
(``StopLossDialog``, ``stop_loss_dialog``, ``止损``). Matching on content would
sweep in every file that merely mentions the word. E2E covers the rest
(``.ai/checks/static/README.md`` §3.2).
"""

from __future__ import annotations

from pathlib import Path

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target
from checks.frontend import files, skip_reason

CODE = "CHECK_TIME_COST_MISSING"

META = CheckMeta(
    check_id="S-09",
    slug="time-cost-in-stop-loss",
    title="stop-loss prompt states the time needed to recover",
    priority="P1",
    code=CODE,
)


#: Stem fragments that identify a stop-loss component, matched case-insensitively
#: after stripping separators.
STEM_MARKERS = ("stoploss", "stop_loss", "stoplossdialog", "止损")

#: Any one of these satisfies the requirement. Several spellings are accepted
#: because the frontend naming convention is not settled yet, and a rule that
#: fires on a correct implementation gets deleted.
TIME_COST_MARKERS = (
    "恢复所需年数",
    "恢复所需",
    "recoveryYears",
    "recovery_years",
    "yearsToRecover",
    "years_to_recover",
    "timeToRecover",
)


def _is_stop_loss(path: Path) -> bool:
    """Whether a file is the stop-loss component, judged by its name."""
    stem = path.stem.lower().replace("-", "").replace("_", "")
    return any(marker.replace("_", "").lower() in stem for marker in STEM_MARKERS)


def run(ctx: ScanContext) -> CheckResult:
    """Require the time-cost line in every stop-loss component."""
    result = CheckResult()
    sources = files(ctx)
    if not sources:
        result.skipped = skip_reason()
        return result

    found_any = False
    for path in sources:
        if not _is_stop_loss(path):
            continue
        found_any = True
        result.files.append(path)
        text = ctx.text(path)
        if any(marker in text for marker in TIME_COST_MARKERS):
            continue
        result.error(
            CODE,
            "stop-loss component does not state how long recovery would take",
            target=format_target(ctx, path),
            fix="Add a line such as `恢复所需年数：约 {years} 年（按年化 {rate}% 计）`, "
            "computed from the current drawdown. Red line 12: a loss percentage is "
            "forgotten, a number of years is not.",
        )

    if not found_any:
        result.skipped = (
            "no stop-loss component exists yet — the rule has nothing to require "
            "the time-cost line of until S3 lands the decision screens"
        )
    return result


__all__ = ["META", "run"]
