"""The two catalogues, and the grain tag that keeps them apart.

`metrics.py` had **no test file of its own** — its coverage was parasitic inside
`test_criterion_eval.py`. ⭐ With a second catalogue in the tree that stops being acceptable:
the questions below are about `metrics.py` alone, and none of them is a criterion question.

Four things are asserted here, ordered by how quietly each would fail otherwise.

1. ⭐ **The grain rule, as a shape.** `research.md` §8 cites 「different grains must not be
   mixed in one table」, and the concrete form of that here is one field: `period`. A price
   metric's `period` is a bar count and `criterion_sentence.py` subtracts `bars_available` from
   it. So **no financial entry may carry one**, and the price catalogue is asserted to be the
   only place a non-`None` appears.

2. ⭐ **The columns are real.** `FINANCIAL_CATALOGUE` spells each column out because
   `revenue` is `MBRevenue` at the provider, so a reader guessing from the name would work
   today and silently yield `None` the day they diverge. ⭐ This test is what makes that guess
   impossible to write and forget: an unpinned column fails here, not in production as a
   missing number.

3. ⭐ **The two catalogues do not overlap.** They share a shape (`dict[str, ...]`) and
   `catalogue_labels()` merges them with `{**prices, **reported}`, so one name in both would be
   **silently dropped**, the second winning, with no error.

4. ⭐ **`MetricReading`'s fields are a boundary, asserted.** It has **no `__slots__` boundary
   test today** — `MetricFacts` has one and `MetricReading` does not, which is why adding these
   three fields turned nothing red and nothing *forced* the four construction sites to be
   revisited. Deriving the expected set from the dataclass would make it vacuous.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from alphacouncil.metrics import (
    CATALOGUE,
    FINANCIAL_CATALOGUE,
    MetricGrain,
    MetricReading,
    MetricStatus,
    catalogue_labels,
    read_metric,
)
from alphacouncil.models.market import Market, Quote, Symbol

pytestmark = pytest.mark.unit

SYMBOL = Symbol(market=Market.SH, code="600519")
D0 = date(2025, 1, 1)
#: A `datetime`, not the ISO string the JSON carries: `Quote.fetched_at` is typed, and a
#: fixture leaning on pydantic's coercion is one edit from failing for a reason unrelated to
#: the code under test. Copied from `test_criterion_eval.py` rather than reinvented — ⭐ the
#: first version of this helper guessed `Quote`'s shape and pydantic rejected two fields.
STAMP = datetime(2026, 9, 29, tzinfo=UTC)


def bars(count: int) -> list[Quote]:
    """``count`` bars on consecutive calendar days, closing at ``100 + i``."""
    return [
        Quote(
            symbol=SYMBOL,
            trade_date=D0 + timedelta(days=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.0 + index,
            volume=1000.0 + index,
            adj_factor=1.0,
            amount=None,
            source="fixture",
            fetched_at=STAMP,
        )
        for index in range(count)
    ]


class TestTheTwoCataloguesDoNotShareAName:
    """⭐ Because `catalogue_labels` merges them with `{**prices, **reported}`."""

    def test_no_metric_is_in_both(self) -> None:
        assert set(CATALOGUE) & set(FINANCIAL_CATALOGUE) == set()

    def test_the_labels_cover_both_without_losing_one(self) -> None:
        labels = catalogue_labels()
        assert len(labels) == len(CATALOGUE) + len(FINANCIAL_CATALOGUE)
        assert set(labels) == set(CATALOGUE) | set(FINANCIAL_CATALOGUE)


class TestTheGrainRuleIsAShape:
    """⭐ 「different grains must not be mixed in one table」, in the one field it turns on."""

    def test_no_financial_entry_carries_a_bar_count(self) -> None:
        # The entries are `(label, column)`, so there is no `period` slot to be wrong in — and
        # this is what makes that structural rather than a convention someone has to remember.
        assert all(len(entry) == 2 for entry in FINANCIAL_CATALOGUE.values()), (
            "a financial entry gained a period; that field means bars and this is not one"
        )

    def test_the_price_catalogue_is_where_a_period_lives(self) -> None:
        with_period = {name for name, (_, period, _) in CATALOGUE.items() if period is not None}
        assert with_period, "no price metric warms up, which cannot be true of `ma60`"
        assert "ma60" in with_period

    def test_a_price_fact_carries_no_period(self) -> None:
        assert CATALOGUE["close"][1] is None, "a price fact needs one bar and never warms up"

    def test_the_readings_default_to_the_point_grain(self) -> None:
        """⭐ The four existing construction sites pass no grain, and this is why they are right."""
        reading = read_metric("ma20", bars(40))
        assert reading.grain is MetricGrain.POINT
        assert reading.period_end is None
        assert reading.latest_announced_period_end is None

    def test_the_tag_not_the_nulls_is_what_says_the_grain(self) -> None:
        """⭐ The tag, not 「which field is null」 — an inference is how a sentence lies."""
        point = read_metric("close", bars(1))
        assert point.grain is MetricGrain.POINT
        # Every period-shaped field is empty on a POINT row, so ⭐ **the nulls alone
        # cannot tell a POINT row from a PERIOD row that has no data yet** \u2014 the tag is
        # the only thing on the record that can.
        assert (point.period, point.period_end, point.latest_announced_period_end) == (
            None,
            None,
            None,
        )
        # ⭐ And the wire values are pinned, because they are a contract with the
        # frontend — and S-16 reads them out of openapi.json.
        assert {g.value for g in MetricGrain} == {"point", "period"}


class TestEveryFinancialColumnIsPinnedSomewhere:
    """⭐ So a typo cannot become a missing number in production."""

    def test_every_column_is_a_field_on_the_pinned_dataclass(self) -> None:
        from alphacouncil.providers.financial import FinancialPeriod

        pinned = set(FinancialPeriod.__slots__)
        for name, (_, column) in FINANCIAL_CATALOGUE.items():
            assert column in pinned, f"{name} reads a column nobody defined: {column!r}"

    def test_both_catalogues_point_at_a_definition_elsewhere(self) -> None:
        """⭐ The admission rule, checked in the only way a test can: every reader is real."""
        for name, (_, _, reader) in CATALOGUE.items():
            assert callable(reader), f"{name} has a non-callable reader"
        for name, entry in FINANCIAL_CATALOGUE.items():
            assert all(isinstance(part, str) and part for part in entry), name


class TestTheReadingFieldsAreTheBoundary:
    """⭐ Deriving this set from the dataclass would make it say nothing at all."""

    def test_the_fields_are_exactly_these(self) -> None:
        assert set(MetricReading.__slots__) == {
            "status",
            "value",
            "as_of",
            "label",
            "period",
            "grain",
            "period_end",
            "latest_announced_period_end",
        }

    def test_a_read_only_returns_a_declared_status(self) -> None:
        """⭐ Not 「which statuses exist」 — which of them a read can actually return.

        `MetricStatus` is deliberately allowed to declare states this build cannot produce
        (`NOT_ANNOUNCED` until D4 is wired), so this asserts the other direction: nothing
        comes back that is not a member, which is what keeps a mapping table total.
        """
        produced = {
            read_metric("close", bars(1)).status,
            read_metric("ma20", bars(40)).status,
            read_metric("ma20", bars(5)).status,
            read_metric("close", []).status,
            read_metric("revenue_yoy", bars(40)).status,
        }
        assert produced <= set(MetricStatus)
        assert MetricStatus.OK in produced
        assert MetricStatus.UNKNOWN_METRIC in produced

    def test_the_two_warming_shapes_still_differ(self) -> None:
        """⚠️ The old asymmetry, kept deliberately: `UNKNOWN_METRIC` loses the catalogue period.

        `test_criterion_eval.py` pins this one, and it looks like a slip rather than a choice —
        so it is named here as well, in the file that owns `read_metric`.
        """
        unknown = read_metric("revenue_yoy", bars(40))
        warming = read_metric("ma20", bars(5))
        assert unknown.period is None
        assert warming.period == 20
