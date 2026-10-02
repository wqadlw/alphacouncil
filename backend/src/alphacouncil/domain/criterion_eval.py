"""Evaluating a kill criterion — turning 「到期」 into 「触发」 (spec 040).

## Why this module exists

``GET /api/v1/today`` used to ask one question per criterion: **is the date here yet?**
The ``metric``, ``operator`` and ``threshold`` the reader typed were carried all the way
to the frontend and never compared to anything, because nothing could put a number on
``metric``.

The Today page papered over it with a sentence that has since become false — the clause
after 「到期不等于触发」 was 「系统还没有指标数据源」. The data source arrived in
spec 034/037/038. ⭐ What never arrived was this file.

## ⭐ The part that matters is the negative answers

Three of the four outcomes say **we cannot tell you**. That is the whole design, and it
is the failure constitution §4.6 exists to prevent: 「把『无法判断』降级成『看起来合理』
的默认值」.

⭐ A criterion that silently never fires is not silence — **it is the program speaking
for the reader**, telling them something about their own record that nobody checked. The
three indistinguishable cases:

* the metric is in the catalogue but its warm-up has not closed
* the metric is not in the catalogue at all (D4 will bring some; this build guesses none)
* the source has no bars for this instrument

Each needs a different reader action — 「回来等一周」/「这里永远不会有」/「换个代码」 —
so each is its own verdict. ⭐ Collapsing them into 「条件没成立」 would be the single most
misleading thing this product could do, because the reader would conclude their own
judgement had been vindicated.

## ⭐ No notification. Not a close call.

Red line 8: 功能是「拦截」不是「推荐」. ``.ai/status.md`` records the permitted shape as
「今日页上的一行陈述而非通知」. So a crossed criterion adds **one line to the page you
already open** and nothing else — no badge, no sound, no email, no push.

That is not a compromise. ⭐ A crossed kill criterion *is* the definition of 拦截: a
condition the reader wrote about their own record, arriving on the day it says it would.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from alphacouncil.domain.decision import ComparisonOperator, KillCriterion
from alphacouncil.metrics import MetricReading, MetricStatus, read_metric
from alphacouncil.models.market import Quote

__all__ = [
    "CriterionEvaluation",
    "CriterionVerdict",
    "compare",
    "evaluate",
]


class CriterionVerdict(StrEnum):
    """What today's reading says about one criterion.

    ⭐ **Six, and they are not degrees.** Two of them are facts about a comparison; the
    other four are four *different* facts about us — warm-up, an unknown name, no bars, and
    no announcement yet. `regressions/0011`: a count in a docstring is a claim about the code.
    """

    #: Due, we have the number, and the comparison came out true.
    CROSSED = "crossed"
    #: Due, we have the number, and the comparison came out false. ⭐ **This is a
    #: statement about the market, not a verdict on the reader** — the page must not
    #: dress it up as either relief or a warning.
    NOT_CROSSED = "not_crossed"
    #: Due, and the metric's warm-up has not closed. Not "did not hold".
    WARMING = "warming"
    #: Due, and the catalogue has no such metric. Not "did not hold", and not the same
    #: sentence as `WARMING` either.
    UNDETERMINED = "undetermined"
    #: Due, and the source has no bars for this instrument.
    NO_BARS = "no_bars"
    #: ⭐⭐ **Due, the metric is one we compute, and its report had not been announced on
    #: this date.** A fourth kind of 「we do not know」, and ⭐ **the only one whose remedy is a
    #: calendar rather than more data.**
    #:
    #: ⚠️ **Its own remedy sentence must carry the latest period we knew** —
    #: `research.md` §四: the period is the x-axis and the cutoff is the lens, so a reader who is
    #: told only 「it has not been announced」 learns nothing they can act on.
    NOT_ANNOUNCED = "not_announced"
    #: ⚠️ 与 `MetricStatus.NOT_ANNOUNCED` 同状:**已声明、未可达**(2026-10-02)。
    #: 它有句子、有前端镜像、有路由映射,但**没有任何读数路径会产生它**。
    #: → 接线完成后这两行必须删掉;留着就是在说谎。

    @property
    def answerable(self) -> bool:
        """Whether this verdict is a fact about the comparison rather than about us."""
        return self in (CriterionVerdict.CROSSED, CriterionVerdict.NOT_CROSSED)


def compare(value: float, operator: ComparisonOperator, threshold: float) -> bool:
    """Apply the reader's operator. ⭐ Total, and the only place the six symbols act.

    ⭐ ``==`` and ``!=`` on floats are here because the domain offers them and a criterion
    the reader typed must not be quietly re-interpreted. For a price or an indicator this
    will almost never be true, and that is the reader's choice to make — the alternative
    is a stored predicate that means something other than what it says.
    """
    match operator:
        case ComparisonOperator.LT:
            return value < threshold
        case ComparisonOperator.LTE:
            return value <= threshold
        case ComparisonOperator.GT:
            return value > threshold
        case ComparisonOperator.GTE:
            return value >= threshold
        case ComparisonOperator.EQ:
            return value == threshold
        case ComparisonOperator.NEQ:
            return value != threshold


@dataclass(frozen=True, slots=True)
class CriterionEvaluation:
    """One criterion, as of one day: its verdict and whatever we know about the metric."""

    verdict: CriterionVerdict
    #: The reading that produced the verdict. ⭐ Kept whole rather than flattened into
    #: ``value: float | None`` because the label and the as-of date travel with it, and
    #: 「MA20 现在 1185.3」 is not the same sentence as 「1185.3」.
    reading: MetricReading
    criterion: KillCriterion

    @property
    def observed(self) -> float | None:
        return self.reading.value


_VERDICT_FOR_STATUS: dict[MetricStatus, CriterionVerdict] = {
    MetricStatus.OK: CriterionVerdict.NOT_CROSSED,
    MetricStatus.WARMING: CriterionVerdict.WARMING,
    MetricStatus.UNKNOWN_METRIC: CriterionVerdict.UNDETERMINED,
    MetricStatus.NO_BARS: CriterionVerdict.NO_BARS,
    MetricStatus.NOT_ANNOUNCED: CriterionVerdict.NOT_ANNOUNCED,
}


def _bars_as_of(bars: Sequence[Quote], as_of: date) -> list[Quote]:
    """The bars a reader on ``as_of`` could have seen.

    ⭐ Usually every bar, because the daily endpoint defaults to ``end=today``. But
    「usually」 is not an invariant, and reading the *last* bar when a later one has
    arrived would evaluate a Thursday criterion against Friday's close — a forward
    reference, which is the one thing a criterion must never be.
    """
    return [bar for bar in bars if bar.trade_date <= as_of]


def evaluate(
    criterion: KillCriterion, bars: Sequence[Quote], *, as_of: date
) -> CriterionEvaluation:
    """Evaluate one criterion against a series of daily bars, as of one day."""
    reading = read_metric(criterion.metric, _bars_as_of(bars, as_of))
    verdict = _VERDICT_FOR_STATUS[reading.status]
    # ⭐ Only an `ok` reading reaches the comparison. Every other status keeps its own
    # verdict, so 「we don't know」 can never fall through into 「it didn't hold」.
    observed = reading.value if reading.status is MetricStatus.OK else None
    if observed is not None and compare(observed, criterion.operator, criterion.threshold):
        verdict = CriterionVerdict.CROSSED
    return CriterionEvaluation(verdict=verdict, reading=reading, criterion=criterion)
