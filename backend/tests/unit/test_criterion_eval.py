"""The kill-criterion evaluator (spec 040).

The four states are the feature, so most of what is tested here is **which sentence a
reader gets**, not the arithmetic — the arithmetic is ``ComparisonOperator``'s and
``indicators.py``'s, and both are pinned elsewhere.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from alphacouncil.domain.criterion_eval import (
    CriterionVerdict,
    compare,
    evaluate,
)
from alphacouncil.domain.decision import ComparisonOperator, KillCriterion
from alphacouncil.metrics import CATALOGUE, MetricStatus, read_metric
from alphacouncil.models.market import Market, Quote, Symbol

SYMBOL = Symbol(market=Market.SH, code="600519")
D0 = date(2025, 1, 1)
#: The last bar `bars(40)` produces. ⭐ Tests pass this as `as_of` rather than D0:
#: `evaluate` filters to bars on or before the date, so `D0` would leave one bar.
LAST = D0 + timedelta(days=39)
#: ⭐ A `datetime`, not the ISO string the JSON carries: `Quote.fetched_at` is typed, and a
#: fixture that leans on pydantic's coercion is one edit away from failing for a reason
#: that has nothing to do with the code under test.
STAMP = datetime(2026, 9, 29, tzinfo=UTC)


def bars(count: int, *, step: float = 1.0) -> list[Quote]:
    """``count`` bars on consecutive calendar days, closing at ``100 + i * step``."""
    return [
        Quote(
            symbol=SYMBOL,
            trade_date=D0 + timedelta(days=index),
            open=100.0 + index * step,
            high=101.0 + index * step,
            low=99.0 + index * step,
            close=100.0 + index * step,
            volume=1000.0 + index,
            adj_factor=1.0,
            amount=None,
            source="fixture",
            fetched_at=STAMP,
        )
        for index in range(count)
    ]


def criterion(
    metric: str = "ma20",
    operator: ComparisonOperator = ComparisonOperator.LT,
    threshold: float = 1e9,
    as_of: date = date(2026, 9, 29),
) -> KillCriterion:
    return KillCriterion(metric=metric, operator=operator, threshold=threshold, as_of=as_of)


class TestTheCatalogueAdmitsOnlyBorrowedDefinitions:
    def test_every_entry_has_a_label_and_a_reader(self) -> None:
        for name, (label, _period, reader) in CATALOGUE.items():
            assert label, f"{name} has no label"
            assert callable(reader)

    def test_no_entry_uses_a_computation_this_project_did_not_already_pin(self) -> None:
        """⭐ The admission rule, as an executable statement.

        The catalogue is spec 037's indicator set plus the Quote model's own fields. A
        name invented here would be a fork with no owner, so the test is a closed-set
        assertion rather than a comment.
        """
        indicators = {
            "ma5", "ma10", "ma20", "ma60", "ema12", "ema26", "rma14", "rsi14",
            "atr14", "annualised_volatility", "dif", "dea", "macd_histogram",
            "kdj_k", "kdj_d", "kdj_j",
            "bollinger_upper", "bollinger_middle", "bollinger_lower",
        }
        facts = {"close", "open", "high", "low", "volume"}
        assert set(CATALOGUE) == indicators | facts

    def test_change_pct_is_not_in_the_catalogue(self) -> None:
        """⭐ The rule biting, as a test, because it bit in the first draft.

        The name is bound to ``RealtimeQuote`` (「vs 昨收」). A daily reading would be
        「vs 上一根」 — a second definition under one name.
        """
        assert "change_pct" not in CATALOGUE
        reading = read_metric("change_pct", bars(30))
        assert reading.status is MetricStatus.UNKNOWN_METRIC

    def test_a_price_fact_declares_no_period(self) -> None:
        """⭐ It needs one bar and so never warms up; a period would be a fiction."""
        assert CATALOGUE["close"][1] is None

    def test_macd_signal_line_declares_the_two_stage_warmup(self) -> None:
        """⭐ 34, not 26 — see ``regressions/0010``."""
        assert CATALOGUE["dif"][1] == 26
        assert CATALOGUE["dea"][1] == 34


class TestFourStatesAndNotTwo:
    def test_a_well_formed_criterion_on_long_enough_history_is_ok(self) -> None:
        reading = read_metric("ma20", bars(40))
        assert reading.status is MetricStatus.OK
        assert reading.value is not None
        assert reading.period == 20

    def test_a_short_history_is_warming_and_carries_no_number(self) -> None:
        # ⭐ 红线 6: the value is `None`, and the as-of date is still present — which is
        # what separates this from "we will never know" without even reading the state.
        reading = read_metric("ma20", bars(5))
        assert reading.status is MetricStatus.WARMING
        assert reading.value is None
        assert reading.as_of == D0 + timedelta(days=4)
        assert reading.period == 20

    def test_an_unknown_name_is_unknown_metric_not_no_data(self) -> None:
        # ⭐ Two different sentences: one may resolve tomorrow, the other never will.
        reading = read_metric("gross_margin", bars(40))
        assert reading.status is MetricStatus.UNKNOWN_METRIC
        assert reading.as_of is None
        assert reading.period is None

    def test_no_bars_is_its_own_state(self) -> None:
        reading = read_metric("ma20", [])
        assert reading.status is MetricStatus.NO_BARS
        assert reading.label == "MA20"
        assert reading.as_of is None

    def test_an_unknown_name_never_reaches_an_indicator(self) -> None:
        """⭐ Checked **first** in ``read_metric``, so no plausible-looking value escapes."""
        assert read_metric("ma20e", bars(40)).status is MetricStatus.UNKNOWN_METRIC
        assert read_metric("m20", bars(40)).status is MetricStatus.UNKNOWN_METRIC
        assert read_metric("", bars(40)).status is MetricStatus.UNKNOWN_METRIC


class TestEvaluate:
    def test_a_crossed_criterion_says_crossed(self) -> None:
        # 40 bars closing 100…139, so MA20 = mean(120…139) = 129.5 and every MA20 > 0.
        rows = bars(40)
        out = evaluate(criterion(operator=ComparisonOperator.GT, threshold=0.0), rows, as_of=LAST)
        assert out.verdict is CriterionVerdict.CROSSED
        assert out.observed == pytest.approx(129.5)

    def test_a_held_criterion_says_not_crossed(self) -> None:
        out = evaluate(
            criterion(operator=ComparisonOperator.LT, threshold=0.0), bars(40), as_of=LAST
        )
        assert out.verdict is CriterionVerdict.NOT_CROSSED

    def test_a_warming_metric_never_becomes_not_crossed(self) -> None:
        # ⭐ THE defect this module exists to prevent. Threshold 0.0 is unreachable for a
        # price, so a leaking `None` would read as `not_crossed` and the page would tell
        # the reader their own criterion had held.
        out = evaluate(
            criterion(operator=ComparisonOperator.LT, threshold=0.0), bars(5), as_of=LAST
        )
        assert out.verdict is CriterionVerdict.WARMING
        assert not out.verdict.answerable

    def test_an_unknown_metric_never_becomes_not_crossed(self) -> None:
        out = evaluate(
            criterion(metric="gross_margin", operator=ComparisonOperator.LT, threshold=0.0),
            bars(40),
            as_of=D0,
        )
        assert out.verdict is CriterionVerdict.UNDETERMINED

    def test_a_metric_reading_from_a_later_bar_is_not_used(self) -> None:
        # ⭐ 40 bars ending 2025-02-09, evaluated as of the 20th bar. Reading bars[-1]
        # would evaluate a Thursday criterion against a fortnight-later close — a forward
        # reference, the one thing a criterion must never be.
        #
        # ⭐ `close` and not `ma20`, because the subject here is the **date filter**. MA20
        # has a 20-bar warm-up, so it would be `warming` on the 20th bar and the test
        # would pass for the wrong reason. `close` needs one bar, so the only thing that
        # can make it wrong is the filter.
        rows = bars(40)
        as_of = rows[19].trade_date
        out = evaluate(
            criterion(metric="close", operator=ComparisonOperator.GT, threshold=0.0),
            rows,
            as_of=as_of,
        )
        assert out.reading.as_of == as_of
        assert out.observed == pytest.approx(119.0)
        # ⭐ And the same criterion one bar later is a different number, which is the
        # whole point of a criterion being date-stamped.
        later = evaluate(
            criterion(metric="close", operator=ComparisonOperator.GT, threshold=0.0),
            rows,
            as_of=rows[20].trade_date,
        )
        assert later.observed == pytest.approx(120.0)

    def test_an_empty_series_is_no_bars_and_never_a_comparison(self) -> None:
        # ⭐ **This state is unreachable from the route** — `/today` pre-checks the bars
        # and sends `metric: null` instead — so a mutation check found it untested and
        # therefore unpinned. ⭐ `evaluate` is a public function and must be total: called
        # with no bars it owes the caller `no_bars`, not a wrong answer.
        out = evaluate(
            criterion(operator=ComparisonOperator.LT, threshold=0.0), [], as_of=LAST
        )
        assert out.verdict is CriterionVerdict.NO_BARS
        assert out.observed is None
        assert out.reading.label == "MA20"

    def test_only_two_verdicts_are_about_the_comparison(self) -> None:
        assert CriterionVerdict.CROSSED.answerable
        assert CriterionVerdict.NOT_CROSSED.answerable
        for verdict in (
            CriterionVerdict.WARMING,
            CriterionVerdict.UNDETERMINED,
            CriterionVerdict.NO_BARS,
        ):
            assert not verdict.answerable


class TestCompareIsTotal:
    @pytest.mark.parametrize(
        ("value", "operator", "threshold", "expected"),
        [
            (1.0, ComparisonOperator.LT, 2.0, True),
            (2.0, ComparisonOperator.LT, 2.0, False),
            (2.0, ComparisonOperator.LTE, 2.0, True),
            (2.0, ComparisonOperator.GT, 1.0, True),
            (2.0, ComparisonOperator.GTE, 2.0, True),
            (2.0, ComparisonOperator.EQ, 2.0, True),
            (2.0, ComparisonOperator.NEQ, 2.0, False),
        ],
    )
    def test_every_operator_acts(
        self,
        value: float,
        operator: ComparisonOperator,
        threshold: float,
        expected: bool,
    ) -> None:
        assert compare(value, operator, threshold) is expected

    def test_an_equality_on_a_price_is_reachable_and_honoured(self) -> None:
        # ⭐ The domain offers `==` and a stored predicate must not be quietly
        # reinterpreted. It will almost never be true for a float, and that is the
        # reader's choice to make.
        rows = bars(40)
        out = evaluate(
            criterion(metric="close", operator=ComparisonOperator.EQ, threshold=139.0),
            rows,
            as_of=LAST,
        )
        assert out.verdict is CriterionVerdict.CROSSED

    def test_equality_against_a_moving_indicator_is_exact_or_false(self) -> None:
        # ⭐ A second, quieter reason not to compare indicators for equality: MA20 moves
        # every bar, so `ma20 == 129.5` is a statement about one date and nothing else.
        # ⭐ It is **honoured exactly** rather than approximated — and the test asserts
        # both sides of that, because a tolerance here would be a quiet second definition
        # of equality and the reader would never know which one fired.
        exact = evaluate(
            criterion(operator=ComparisonOperator.EQ, threshold=129.5), bars(40), as_of=LAST
        )
        assert exact.verdict is CriterionVerdict.CROSSED

        off_by_a_cent = evaluate(
            criterion(operator=ComparisonOperator.EQ, threshold=129.51), bars(40), as_of=LAST
        )
        assert off_by_a_cent.verdict is CriterionVerdict.NOT_CROSSED

