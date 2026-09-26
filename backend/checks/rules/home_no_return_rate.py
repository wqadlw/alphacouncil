"""S-07 — the home page must not show a rate of return.

**Defect guarded:** product red line 9. A rate of return on the first screen is
a score, and a score on the first screen is what the product is not. It converts
"did I decide well?" into "am I up?", which is the substitution this whole system
exists to prevent — and it does so before the user has asked a single question.

Anti-pattern (forbidden)::

    <Header>
      <Stat label="今年收益率" value="+18.4%" />
      <Stat label="跑赢大盘" value="+6.2%" />
    </Header>

Correct form::

    <Header>
      <Stat label="在场天数" value="412" />
      <Stat label="今天要处理" value="3 项" />
    </Header>

Why a test cannot catch this: an E2E test asserting the home page renders will
pass whether or not a return figure is on it. Only an assertion that the string
is *absent* catches it — and that assertion belongs in E2E
(``.ai/checks/static/README.md`` §3.2). This rule is the cheap first line: it
fails the build the moment the phrase is typed, before anyone runs a browser.

Severity is ``error``, not ``warning``: red line 9 is not a style preference, and
a warning on the home page would be ignored within a week.
"""

from __future__ import annotations

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target
from checks.frontend import home_pages, skip_reason

CODE = "CHECK_RETURN_RATE_LEAK"

META = CheckMeta(
    check_id="S-07",
    slug="home-no-return-rate",
    title="home page does not display a rate of return",
    priority="P1",
    code=CODE,
)


#: Phrases that name a score rather than a fact. `涨跌幅` is deliberately absent:
#: a price moved, that is a fact, and the home page may say so.
BANNED_PHRASES = (
    "收益率",
    "年化收益",
    "回报率",
    "超额收益",
    "跑赢大盘",
    "跑输大盘",
    "累计收益",
    "账户收益",
)

_FIX = (
    "Show facts on the home page — 在场天数, 持仓市值, 今天要处理的事项. A rate of "
    "return belongs on the review screen, next to the process score, or nowhere. "
    "Red line 9."
)


def run(ctx: ScanContext) -> CheckResult:
    """Search the home-page candidates for return-shaped wording."""
    result = CheckResult()
    pages = home_pages(ctx)
    if not pages:
        result.skipped = skip_reason()
        return result

    for path in pages:
        result.files.append(path)
        for lineno, line in enumerate(ctx.text(path).splitlines(), start=1):
            hit = next((phrase for phrase in BANNED_PHRASES if phrase in line), None)
            if hit is None:
                continue
            result.error(
                CODE,
                f"home page shows a rate of return (`{hit}`)",
                target=format_target(ctx, path, lineno),
                fix=_FIX,
            )
    return result


__all__ = ["META", "run"]
