"""The metric catalogue — the only names this build can put a number on.

## ⭐ The admission rule, and it is one sentence

> **A metric enters the catalogue only if its definition is already pinned down
> somewhere else in this codebase.**

Everything here is therefore borrowed, never invented:

* the indicators from :mod:`alphacouncil.indicators` (spec 037, six forks written down)
* the price facts the :class:`~alphacouncil.models.market.Quote` model already defines

⭐ 5-day momentum was the tempting exclusion. 「5 根」means five *trading* days, or five
*calendar* days? Both readings exist, neither is pinned, and a 20%-moving choice changes
which side of a threshold a criterion lands on. ⭐ So it is not in here, and the honest
answer for it is ``unknown_metric`` rather than a number that is right most of the time.

That is spec 037 §2 applied one level up: **every fork changes digits, and a fork with
no owner is not a definition.**

## ⭐ Why this is a catalogue and not an enum on ``KillCriterion``

:class:`~alphacouncil.domain.decision.KillCriterion` validates ``metric`` by *shape*
(``[a-z][a-z0-9_]*``) and says why in its own docstring: the catalogue belongs to the
financial-data layer (D4), which is not built, and inventing a closed set here would mean
rejecting a valid metric the day D4 lands.

Narrowing that field would weld shut a door the domain deliberately left open.
⭐ So the domain stays open and this module is the **smaller, honest** subset: everything
it can answer today, and an explicit answer for everything it cannot.

## The fourth state is the whole point

``unknown_metric`` and ``warming`` are both 「we cannot answer」, and they are kept apart
because they call for different reader actions: one is 「come back in a week」, the other
is 「this will never be answerable here」.

⭐ Collapsing either into "the criterion did not hold" is the failure constitution §4.6
names explicitly: 「把'无法判断'降级成'看起来合理'的默认值」. A criterion that silently
never fires is **the program speaking for the reader** — telling them a thing about their
own record that nobody checked.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from alphacouncil.indicators import (
    Indicator,
    annualised_volatility,
    atr,
    bollinger,
    ema,
    kdj,
    macd,
    rma,
    rsi,
    sma,
)
from alphacouncil.models.market import Quote

__all__ = [
    "CATALOGUE",
    "FINANCIAL_CATALOGUE",
    "MetricReading",
    "MetricStatus",
    "catalogue_labels",
    "read_metric",
]


class MetricGrain(StrEnum):
    """⭐ What one row of a reading measures, and it is **not** a decoration.

    Two families share one catalogue. A price fact is a **point**: the value is what was true
    on a day. A reported figure is a **span**: it summarises a period, so it is meaningless
    without which period.

    > Declare the grain — define exactly what a single row represents;
    > **different grains must not be mixed in one table.**

    ⚠️ That rule is why this is a tag rather than a nullable field. `MetricReading`
    already carries `period` meaning 「how many bars」, and `criterion_sentence.py`
    subtracts `bars_available` from it, so a report period dropped into that field would
    produce 「还差 3 根日线」. ⭐ And the tag belongs **on the type**:
    「which field is null」 is an inference, and an inference is how a sentence lies.
    """

    #: A point in time: the value is what was true on `as_of`.
    POINT = "point"
    #: A span: the value summarises `period_end`, so it has no meaning without it.
    PERIOD = "period"


class MetricStatus(StrEnum):
    """What we can say about a metric name today. ⭐ Four, not two."""

    OK = "ok"
    #: In the catalogue, but the indicator's warm-up has not closed. ⭐ **Not** zero,
    #: and **not** "the criterion did not hold".
    WARMING = "warming"
    #: The catalogue has no such metric. ⭐ D4 will bring some; this build guesses none.
    UNKNOWN_METRIC = "unknown_metric"
    #: The catalogue knows it and the source has no bars for this instrument.
    NO_BARS = "no_bars"
    #: ⭐⭐ **The metric is in the catalogue and the pipeline works, but no report had been
    #: announced on or before the reader's cutoff.**
    #:
    #: ⚠️ **Not `WARMING`, and the difference is the whole point.** `WARMING` counts
    #: *bars*, and 「还差 N 根日线才有值」 is a promise that resolves on its own — which is what
    #: makes
    #: it different from a shrug. This one has **no such promise**: the announcement lag was
    #: measured at 25 / 46 / 93 days (`providers/financial.py:372-377`), so ⭐ **any number
    #: here would be invented**. `spec 043:41-45` already overturned the vendor's
    #: 「约 2 个月」 once because it did the arithmetic and called it a measurement.
    #:
    #: ⇒ So the reading carries the **latest period we knew** rather than a date to wait for.
    NOT_ANNOUNCED = "not_announced"
    #: ⭐⭐ **The report for that period was announced, and it does not carry
    #: this figure.** Not `NOT_ANNOUNCED`, which would be a lie: the report is out.
    #:
    #: ⚠️ Measured, not imagined: `_number` (`providers/financial.py:292-298`)
    #: turns `"--"`, `""` and `"n/a"` into `None`, and the schema's eight figure
    #: columns are all nullable. The same docstring already carries the rule this
    #: state exists to keep: 「a company that reported nothing did not report zero」.
    #:
    #: ⭐ **And no promise at all** — not even the cautious one `NOT_ANNOUNCED` makes.
    #: A `--` is how a company says the number is undefined, so it may never appear.
    NOT_REPORTED = "not_reported"
    #: ⚠️ **今天还没有生产路径能返回它**(spec 051 的前半段,2026-10-02)。
    #: `read_metric()` 只有四个返回:
    #: UNKNOWN_METRIC / NO_BARS / WARMING / OK。
    #: ⇒ 这里说的是**已声明、未可达**,而不是说它已经能产生。
    #: 同一个事实在本仓已经有一份记录写法:`no_route_drift.py`
    #: 把 `/api/v1/capabilities` 故意留在表外,让它继续被报。


@dataclass(frozen=True, slots=True)
class MetricReading:
    """One metric's current value, or the reason there isn't one.

    ⭐ ``value is None`` covers two statuses (``WARMING`` and ``UNKNOWN_METRIC``),
    which is why ``status`` is not optional and cannot be inferred from ``value``.
    """

    status: MetricStatus
    value: float | None
    as_of: date | None
    label: str
    #: ⭐ How many bars this metric needs before it has a value, when that is a fixed
    #: number (``ma60`` → 60). ⭐ It is what lets 「预热中」 say 「12 根里还差 48 根」 instead
    #: of 「算不出来」 — a deferral with a date attached rather than a dead end. ``None``
    #: for a price fact, which needs exactly one bar and so never warms up.
    period: int | None
    #: ⭐ Which grain this row is at. Defaults to `POINT` so the four existing construction
    #: sites are correct **unchanged**, which is the cheapest proof the tag is not decorative.
    grain: MetricGrain = MetricGrain.POINT
    #: ⭐ The span a `PERIOD` row summarises. `None` for a `POINT` row, and ⚠️ **`None`
    #: for a `PERIOD` row is a defect** — the two together are the value.
    period_end: date | None = None
    #: ⭐ The latest report period that *had* been announced, when the current one had not.
    #: This is the fact `NOT_ANNOUNCED` exists to carry; without it the sentence would say
    #: 「还没公告」 and the reader would not know what they could see.
    latest_announced_period_end: date | None = None


def _last(series: Sequence[Indicator]) -> Indicator:
    return series[-1] if series else None


def _closes(bars: Sequence[Quote]) -> list[float]:
    return [bar.close for bar in bars]


def _highs(bars: Sequence[Quote]) -> list[float]:
    return [bar.high for bar in bars]


def _lows(bars: Sequence[Quote]) -> list[float]:
    return [bar.low for bar in bars]


#: A catalogue entry is ``(label, period, reader)``. ⭐ ``period`` is what the page needs
#: to say 「还差 48 根」 instead of 「算不出来」 — see :attr:`MetricReading.period`.
#: A price fact's period is ``None``: it needs one bar and never warms up.
_CatalogueEntry = tuple[str, int | None, Callable[[Sequence[Quote]], Indicator]]


def _moving_average(period: int) -> Callable[[Sequence[Quote]], Indicator]:
    return lambda bars: _last(sma(_closes(bars), period))


def _exponential(period: int) -> Callable[[Sequence[Quote]], Indicator]:
    return lambda bars: _last(ema(_closes(bars), period))


def _wilder(period: int) -> Callable[[Sequence[Quote]], Indicator]:
    return lambda bars: _last(rma(_closes(bars), period))


def _kdj_part(part: str) -> Callable[[Sequence[Quote]], Indicator]:
    # ⭐ KDJ needs highs and lows, not just closes — its denominator is the window's
    # high-low range. Reading it off closes alone would have been a second, quieter
    # definition of KDJ, and KDJ is exactly the indicator platforms disagree about most.
    return lambda bars: _last(getattr(kdj(_highs(bars), _lows(bars), _closes(bars)), part))


def _bollinger_part(part: str) -> Callable[[Sequence[Quote]], Indicator]:
    return lambda bars: _last(getattr(bollinger(_closes(bars)), part))


def _macd_part(part: str) -> Callable[[Sequence[Quote]], Indicator]:
    return lambda bars: _last(getattr(macd(_closes(bars)), part))


#: name → (label, period, reader). ⭐ An ordered mapping rather than a list of names, so
#: the label and the period cannot drift away from the function beside them.
CATALOGUE: dict[str, _CatalogueEntry] = {
    # -- price facts, already defined by the Quote model -------------------------
    "close": ("收盘价", None, lambda bars: bars[-1].close if bars else None),
    "open": ("今开", None, lambda bars: bars[-1].open if bars else None),
    "high": ("最高", None, lambda bars: bars[-1].high if bars else None),
    "low": ("最低", None, lambda bars: bars[-1].low if bars else None),
    "volume": ("成交量", None, lambda bars: bars[-1].volume if bars else None),
    # ⭐ **`change_pct` is deliberately absent**, and it is the clearest case of the
    # admission rule biting. The name is already bound to `RealtimeQuote`, where it means
    # 「vs 昨收」. A daily reading would be 「vs 上一根」 — a *second definition under the
    # same name*, which is exactly what spec 037 §2 exists to prevent, and `Quote` has no
    # such field to borrow. Bar-over-bar is almost certainly the right number; "almost
    # certainly" is not a definition, and a criterion evaluated against an undefined
    # metric is a criterion nobody can audit. It joins the day D4 pins one down.
    # -- spec 037's indicators, by their own names --------------------------------
    "ma5": ("MA5", 5, _moving_average(5)),
    "ma10": ("MA10", 10, _moving_average(10)),
    "ma20": ("MA20", 20, _moving_average(20)),
    "ma60": ("MA60", 60, _moving_average(60)),
    "ema12": ("EMA12", 12, _exponential(12)),
    "ema26": ("EMA26", 26, _exponential(26)),
    "rma14": ("RMA14", 14, _wilder(14)),
    "rsi14": ("RSI14", 15, lambda bars: _last(rsi(_closes(bars)).rsi)),
    "atr14": (
        "ATR14",
        15,
        lambda bars: _last(atr(_highs(bars), _lows(bars), _closes(bars))),
    ),
    "annualised_volatility": (
        "年化波动率",
        20,
        lambda bars: _last(annualised_volatility(_closes(bars))),
    ),
    # ⭐ MACD's warm-up is 26 + 9 - 1, not 26 — the signal line is an EMA **of DIF**, and
    # DIF itself starts at bar 26 (spec 037 §7, and the defect in `regressions/0010`).
    # ⭐ Reporting 26 here would say 「还差 N 根」 and then not deliver a value at that bar,
    # which is a promise the page keeps failing.
    "dif": ("DIF", 26, _macd_part("dif")),
    "dea": ("DEA", 34, _macd_part("dea")),
    "macd_histogram": ("MACD 柱", 34, _macd_part("histogram")),
    "kdj_k": ("KDJ·K", 9, _kdj_part("k")),
    "kdj_d": ("KDJ·D", 9, _kdj_part("d")),
    "kdj_j": ("KDJ·J", 9, _kdj_part("j")),
    "bollinger_upper": ("布林上轨", 20, _bollinger_part("upper")),
    "bollinger_middle": ("布林中轨", 20, _bollinger_part("middle")),
    "bollinger_lower": ("布林下轨", 20, _bollinger_part("lower")),
}

#: ⭐ **The eight reported figures, at a different grain** (research.md §8). A second
#: catalogue rather than a widened reader: `_CatalogueEntry`'s reader takes `Sequence[Quote]`,
#: so widening it would touch all 24 existing readers, and ⚠️ **not one of them needs
#: the second parameter.**
#:
#: The admission rule at the top of this module is **already satisfied** — each of these is a
#: named field on `FinancialPeriod` (`providers/financial.py:114-153`). The rule was not waiting
#: for an exception; it was waiting for this.
#:
#: The column is spelled out per entry instead of assumed equal to the name, because
#: `revenue` is `MBRevenue` at the provider (`financial.py:441`): guessing works today and
#: silently yields `None` the day the two names diverge.
_FinancialEntry = tuple[str, str]

FINANCIAL_CATALOGUE: dict[str, _FinancialEntry] = {
    "roe_avg": ("ROE 平均", "roe_avg"),
    "np_margin": ("销售净利率", "np_margin"),
    "gp_margin": ("销售毛利率", "gp_margin"),
    "net_profit": ("净利润", "net_profit"),
    "eps_ttm": ("EPS 滚动十二个月", "eps_ttm"),
    "revenue": ("营业收入", "revenue"),
    "total_shares": ("总股本", "total_shares"),
    "float_shares": ("流通股本", "float_shares"),
}



def catalogue_labels() -> dict[str, str]:
    """``name -> label`` for the frontend's picker. ⭐ A copy, not a live view.

    ⚠️ **It has no callers**, so a metric entering either catalogue does not reach a
    picker. That is recorded rather than fixed here — whether a picker exists is a decision
    about the reader, not about this function.
    """
    prices = {name: label for name, (label, _, _) in CATALOGUE.items()}
    reported = {name: label for name, (label, _) in FINANCIAL_CATALOGUE.items()}
    return {**prices, **reported}


def _read_reported(
    entry: _FinancialEntry, row: Mapping[str, object] | None
) -> MetricReading:
    """⭐ The three answers a stored report can give, and **no more than three**.

    Cutoff-agnostic on purpose: the row is whatever the caller decided to hand over, and
    ⛔ which row that is — today's knowledge or the reader's — is the route's decision, not
    this function's. Baking either one in here would make the other impossible to test.

    1. **No row** → `NOT_ANNOUNCED`, and no period to name — nothing was known by the cutoff.
    2. **Row, figure present** → `OK`, with the period attached, because a reported figure is
       meaningless without the period it summarises (`research.md` §8).
    3. **Row, figure absent** → `NOT_REPORTED`, with the period attached, because the report
       *was* announced and saying otherwise would be a lie about a fact we hold.
    """
    label, column = entry
    if row is None:
        return MetricReading(
            status=MetricStatus.NOT_ANNOUNCED,
            value=None,
            as_of=None,
            label=label,
            period=None,
            grain=MetricGrain.PERIOD,
            period_end=None,
            latest_announced_period_end=None,
        )

    period_end = row.get("period_end")
    period = period_end if isinstance(period_end, str) else None
    raw = row.get(column)
    value = raw if isinstance(raw, float | int) else None
    return MetricReading(
        status=MetricStatus.OK if value is not None else MetricStatus.NOT_REPORTED,
        value=float(value) if value is not None else None,
        # ⚠️ `as_of` stays `None`: for a price reading it is 「the bar the value came
        # from」, and there is no bar here. The two dates this reading carries are `period_end`
        # (which period) and, on `NOT_ANNOUNCED`, the latest period we did know.
        as_of=None,
        label=label,
        period=None,
        grain=MetricGrain.PERIOD,
        period_end=date.fromisoformat(period) if period is not None else None,
        latest_announced_period_end=None,
    )


def read_metric(
    metric: str, bars: Sequence[Quote], *, financial: Mapping[str, object] | None = None
) -> MetricReading:
    """Read one metric off a series of daily bars.

    ⭐ The order of the three early returns is the whole design. An unknown name is
    checked **first**, so a name this build cannot answer never reaches an indicator
    that might return something plausible for it.
    """
    entry = CATALOGUE.get(metric)
    reported = FINANCIAL_CATALOGUE.get(metric)
    if reported is not None:
        return _read_reported(reported, financial)
    if entry is None:
        return MetricReading(
            status=MetricStatus.UNKNOWN_METRIC,
            value=None,
            as_of=None,
            label=metric,
            period=None,
        )

    label, period, reader = entry
    if not bars:
        # ⭐ The catalogue knows this metric and the source has nothing. That is
        # `no_data` in constitution §4.6's vocabulary, and it is a different sentence
        # from "we don't know this metric" — one may resolve tomorrow, the other will not.
        return MetricReading(
            status=MetricStatus.NO_BARS, value=None, as_of=None, label=label, period=period
        )

    value = reader(bars)
    as_of = bars[-1].trade_date
    if value is None:
        return MetricReading(
            status=MetricStatus.WARMING,
            value=None,
            as_of=as_of,
            label=label,
            period=period,
        )
    return MetricReading(
        status=MetricStatus.OK, value=value, as_of=as_of, label=label, period=period
    )
