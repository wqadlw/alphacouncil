"""Tests for the indicator layer (spec 037).

## What is asserted, and what deliberately is not

Every value below is **hand-computed**, not copied from a platform. ⭐ Asserting an
indicator against another library's output would be asserting that somebody else's
caliber is right, which is the very thing this module exists to pin down: EMA's
recursion, RSI's Wilder smoothing, KDJ's per-bar denominator and Bollinger's SMA middle
are each a fork where two defensible implementations disagree.

So the tests state the fork and check the arithmetic:

* ``ema`` is checked against a worked example where every step is visible;
* ``rma`` is checked against ``period = 2`` where the two smoothing rules diverge;
* ⭐ **the same input under ``ema`` and ``rma`` must give different numbers**, because a
  module that silently used one for the other would pass every individual test above;
* warm-up lengths are asserted explicitly, because 「how many bars before this exists」 is
  the part a UI gets wrong — and S-08 (红线 6) requires it to render blank.

## The maturity assertions are the constitution, not tidiness

``None`` for an immature window is 红线 6. A test that only checks 「the last value is a
number」 passes for an implementation that fills the warm-up with zeros, and the difference
is a chart that draws a descending line through the present before any data exists.
"""

from __future__ import annotations

import math

import pytest

from alphacouncil.indicators import (
    TRADING_DAYS_PER_YEAR,
    annualised_volatility,
    atr,
    bollinger,
    ema,
    kdj,
    macd,
    rma,
    rsi,
    sma,
    true_range,
)


class TestSma:
    def test_warmup_is_none_then_the_window_mean(self) -> None:
        assert sma([1.0, 2.0, 3.0, 4.0], 3) == [
            None,
            None,
            pytest.approx(2.0),
            pytest.approx(3.0),
        ]

    def test_length_always_matches_the_input(self) -> None:
        for period in (2, 5, 20):
            assert len(sma(list(range(30)), period)) == 30

    def test_a_long_series_keeps_only_the_window(self) -> None:
        """⭐ Regression against the running-sum bug: an off-by-one in the subtraction
        would drift, and only a value far from the start would show it."""
        values = [float(index) for index in range(1, 31)]
        result = sma(values, 5)
        assert result[29] == pytest.approx(sum(values[25:30]) / 5)
        assert result[-1] != pytest.approx(sum(values) / len(values))

    def test_period_must_be_positive(self) -> None:
        for bad in (0, -1):
            with pytest.raises(ValueError):
                sma([1.0, 2.0], bad)


class TestEma:
    def test_the_first_value_is_the_seed_average_not_the_first_price(self) -> None:
        """⭐ EMA does not start at ``prices[0]``; it starts at the SMA of the window.

        This is the check that distinguishes recursive EMA from ``adjust=True`` semantics,
        and it is why ``pipeline.py`` in the upstream project writes ``adjust=False``
        fourteen times.
        """
        result = ema([10.0, 20.0, 30.0], 3)
        assert result[0] is None and result[1] is None
        assert result[2] == pytest.approx(20.0)

    def test_each_step_is_alpha_weighted(self) -> None:
        values = [10.0, 20.0, 30.0, 40.0]
        result = ema(values, 3)
        alpha = 2.0 / 4.0
        expected = 20.0 + alpha * (40.0 - 20.0)
        assert result[3] == pytest.approx(expected)

    def test_it_differs_from_rma(self) -> None:
        """⭐ The fork, asserted directly.

        With ``period = 4`` the alpha values are 0.4 and 0.25, so after the seed the two
        smoothing rules diverge. ⭐ A module that used one for the other would pass every
        per-function test and fail only here.
        """
        values = [10.0, 12.0, 11.0, 14.0, 13.0, 16.0, 15.0]
        assert ema(values, 4)[-1] != pytest.approx(rma(values, 4)[-1])


class TestRma:
    def test_wilder_smoothing_uses_alpha_of_one_over_n(self) -> None:
        values = [0.0, 2.0, 4.0]
        result = rma(values, 2)
        assert result[0] is None
        assert result[1] == pytest.approx(1.0)  # seed = mean(0, 2)
        assert result[2] == pytest.approx(1.0 + 0.5 * (4.0 - 1.0))


class TestMacd:
    def test_dif_appears_only_once_both_legs_exist(self) -> None:
        closes = [float(index) for index in range(1, 40)]
        result = macd(closes)
        # The slow leg needs 26 bars, so nothing exists before index 25.
        assert result.dif[:25] == [None] * 25
        assert result.dif[25] is not None

    def test_histogram_is_dif_minus_dea(self) -> None:
        closes = [10.0, 11.0, 10.5, 12.0, 11.5, 13.0, 12.5, 14.0, 13.5, 15.0] * 5
        result = macd(closes)
        for index, (dif, dea, bar) in enumerate(
            zip(result.dif, result.dea, result.histogram, strict=True)
        ):
            if dif is None or dea is None:
                assert bar is None, f"histogram exists at index {index} with no inputs"
            else:
                assert bar == pytest.approx(dif - dea)

    def test_a_flat_series_has_a_zero_dif(self) -> None:
        result = macd([100.0] * 60)
        assert result.dif[-1] == pytest.approx(0.0)
        assert result.histogram[-1] == pytest.approx(0.0)


class TestRsi:
    def test_a_monotonic_rise_is_the_ceiling(self) -> None:
        """⭐ 「Nothing fell」 is exactly what 100 means — not a division by zero."""
        result = rsi([float(index) for index in range(1, 40)]).rsi
        assert result[-1] == pytest.approx(100.0)

    def test_a_monotonic_fall_is_zero(self) -> None:
        result = rsi([float(index) for index in range(40, 1, -1)]).rsi
        assert result[-1] == pytest.approx(0.0)

    def test_warmup_leaves_a_gap_before_the_first_bar_with_a_change(self) -> None:
        closes = [10.0, 11.0, 10.5, 12.0, 11.5, 13.0, 12.5, 14.0, 13.5, 15.0] * 3
        result = rsi(closes, period=5).rsi
        # period changes need `period` bars, and the first bar has no change at all.
        assert result[:5] == [None] * 5
        assert result[5] is not None

    def test_the_index_stays_in_range(self) -> None:
        closes = [10.0, 12.0, 9.0, 15.0, 8.0, 20.0, 7.0, 11.0] * 6
        for value in rsi(closes, period=14).rsi:
            if value is not None:
                assert 0.0 <= value <= 100.0


class TestKdj:
    def test_a_flat_window_is_none_rather_than_infinite(self) -> None:
        """⭐ RSV divides by ``window_high - window_low``, which is ``0`` on a flat series.

        Dividing would produce ``inf``, and a chart draws ``inf`` as a spike off the top of
        the screen. ⭐ A definition that cannot be reached must be absent.
        """
        closes = [100.0] * 30
        result = kdj(closes, closes, closes, period=9)
        assert all(value is None for value in result.k)
        assert all(value is None for value in result.d)
        assert all(value is None for value in result.j)

    def test_j_is_three_k_minus_two_d(self) -> None:
        highs = [float(index + 1) for index in range(40)]
        lows = [float(index) for index in range(40)]
        closes = [float(index) + 0.5 for index in range(40)]
        result = kdj(highs, lows, closes, period=9)
        for k, d, j in zip(result.k, result.d, result.j, strict=True):
            if k is None or d is None:
                assert j is None
            else:
                assert j == pytest.approx(3 * k - 2 * d)

    def test_k_stays_within_zero_and_a_hundred(self) -> None:
        highs = [10.0, 12.0, 11.0, 15.0, 13.0, 18.0, 12.0, 20.0] * 6
        lows = [9.0, 10.0, 8.0, 13.0, 11.0, 16.0, 9.0, 18.0] * 6
        closes = [9.5, 11.0, 10.0, 14.0, 12.0, 17.0, 11.0, 19.0] * 6
        for value in kdj(highs, lows, closes, period=9).k:
            if value is not None:
                assert 0.0 <= value <= 100.0


class TestBollinger:
    def test_a_flat_series_has_zero_width_bands(self) -> None:
        closes = [50.0] * 30
        result = bollinger(closes, period=20)
        assert result.middle[-1] == pytest.approx(50.0)
        assert result.upper[-1] == pytest.approx(50.0)
        assert result.lower[-1] == pytest.approx(50.0)

    def test_the_middle_is_an_sma_not_an_ema(self) -> None:
        closes = [float(index) for index in range(1, 41)]
        result = bollinger(closes, period=20)
        assert result.middle == sma(closes, 20)

    def test_bandwidth_is_the_relative_width(self) -> None:
        closes = [float(index % 7) + 10 for index in range(40)]
        result = bollinger(closes, period=20)
        up, mid, low, band = (
            result.upper[-1],
            result.middle[-1],
            result.lower[-1],
            result.bandwidth[-1],
        )
        assert up is not None and mid is not None and low is not None
        assert band == pytest.approx((up - low) / mid)


class TestTrueRangeAndAtr:
    def test_the_first_bar_has_no_true_range(self) -> None:
        """⭐ It needs the previous close, which does not exist for bar zero."""
        highs = [10.0, 11.0]
        lows = [9.0, 10.0]
        closes = [9.5, 10.5]
        assert true_range(highs, lows, closes)[0] is None

    def test_true_range_accounts_for_gaps(self) -> None:
        """A gap makes the range larger than ``high - low``; that is the whole point."""
        highs = [10.0, 20.0]
        lows = [9.0, 19.0]
        closes = [9.5, 19.5]
        assert true_range(highs, lows, closes)[1] == pytest.approx(10.5)

    def test_atr_is_wilder_smoothed(self) -> None:
        highs = [10.0, 11.0, 12.0, 13.0] * 5
        lows = [9.0, 10.0, 11.0, 12.0] * 5
        closes = [9.5, 10.5, 11.5, 12.5] * 5
        result = atr(highs, lows, closes, period=4)
        assert result[0] is None
        assert result[-1] is not None


class TestAnnualisedVolatility:
    def test_a_series_with_known_daily_volatility_reproduces_it(self) -> None:
        """⭐ Verified against the closed form, so the ``sqrt(252)`` is checked and not
        assumed.

        The first version of this test used a **constant** 1% daily rate and expected
        ``0.01 * sqrt(252)``. The code returned ``0.0`` and **the code was right**:
        volatility measures the *variation* of returns, and a perfectly constant rate has
        none. ⭐ A test that asserts a plausible-looking number without checking that the
        number means what it says is how a wrong expectation survives review.

        So the series is built with alternating returns, whose standard deviation is
        exactly ``0.01`` by construction.
        """
        daily = 0.01
        closes = [100.0]
        for index in range(80):
            step = daily if index % 2 == 0 else -daily
            closes.append(closes[-1] * math.exp(step))
        result = annualised_volatility(closes, period=20)
        assert result[-1] == pytest.approx(daily * math.sqrt(TRADING_DAYS_PER_YEAR))

    def test_a_constant_rate_series_has_no_volatility(self) -> None:
        """⭐ The case the first version got wrong, kept as its own test.

        「涨得一模一样」 and 「忽涨忽跌但平均一样」 are different things, and only one of
        them is volatile. A reader who sees a constant climb must not be shown a volatility
        figure that implies the climb was risky.
        """
        closes = [100.0]
        for _ in range(60):
            closes.append(closes[-1] * 1.01)
        assert annualised_volatility(closes, period=20)[-1] == pytest.approx(0.0)

    def test_a_constant_price_has_no_volatility(self) -> None:
        result = annualised_volatility([100.0] * 40, period=20)
        assert result[-1] == pytest.approx(0.0)

    def test_a_zero_close_makes_the_window_undefined_rather_than_flat(self) -> None:
        """⭐ The `0.0` that was there before, and why it was wrong.

        ``Quote.close`` is ``ge=0.0``, so a zero base is a state the schema permits and
        real data never reaches. ⭐ A log return over a zero base is an **undefined
        ratio**, so the volatility over any window containing it is undefined too — and
        ``0.0`` claimed the price had not moved. The zero here is the *base*, and a
        volatility of zero means 「nothing changed」, which is a different sentence.
        """
        closes = [100.0] * 35
        closes[10] = 0.0  # ⭐ schema-legal, and it breaks two returns
        result = annualised_volatility(closes, period=20)

        assert len(result) == len(closes)
        assert result[9] is None, "before the zero, the window is still warming up"
        # ⭐ **Two** returns are undefined, not one: the fall *into* zero is -inf and the
        # rise *out of* it has no base. Either end of the ratio being zero makes the
        # return undefined, and both of them are here.
        assert result[10] is None
        assert result[11] is None
        # ⭐ A return at position ``pos`` sits in the trailing window for bars
        # ``pos … pos + period - 1``, so the last undefined one (``pos = 11``) masks
        # through bar 30 and recovery is at 31. ⭐ Both ends asserted because the two
        # off-by-ones that actually happened in this function were **one bar** wide, and
        # the symptom was a series masked to the end rather than anything that raised.
        assert result[11 + 20 - 1] is None
        assert result[11 + 20] is not None
        assert result[-1] is not None

    def test_the_output_stays_one_entry_per_bar(self) -> None:
        """⭐ Alignment is the property everything else rests on (spec 037 §1)."""
        for closes in ([100.0] * 40, [0.0] + [100.0 + i for i in range(39)]):
            assert len(annualised_volatility(closes, period=20)) == len(closes)


class TestMaturityIsTheConstitution:
    """⭐ 红线 6: an immature result is blank, never a number."""

    @pytest.mark.parametrize(
        ("call", "warmup"),
        [
            (lambda values: sma(values, 20), 19),
            (lambda values: ema(values, 20), 19),
            (lambda values: rma(values, 20), 19),
            (lambda values: macd(values).dif, 25),
            # ⭐ `dea` was **missing from this list** while `macd`'s docstring claimed a
            # `signal - 1` extra warm-up. Nothing failed, because nothing asserted it: the
            # docstring and the code disagreed and 34 tests were happy either way. It
            # surfaced in `spec 038` by counting non-nulls in a live response. The lesson
            # is not "add a row" — it is that a docstring claiming a number is a claim
            # somebody has to check, and the cheapest way to check it is to assert it.
            (lambda values: macd(values).dea, 25 + 8),
            (lambda values: rsi(values, 14).rsi, 14),
            (lambda values: bollinger(values, period=20).middle, 19),
            (lambda values: annualised_volatility(values, period=20), 20),
        ],
    )
    def test_the_warmup_is_exactly_none(self, call: object, warmup: int) -> None:
        values = [float(index + 1) for index in range(60)]
        result = call(values)  # type: ignore[operator]
        assert len(result) == 60, "a series shorter than its input shifts everything"
        assert result[:warmup] == [None] * warmup, (
            f"expected {warmup} empty warm-up bars, got "
            f"{sum(1 for v in result[:warmup] if v is not None)} filled"
        )
        assert result[warmup] is not None

    def test_no_indicator_ever_invents_a_zero(self) -> None:
        """⭐ The specific substitution that红线 6 forbids.

        Zero would be a plausible-looking value in a warm-up — a price-average of zero is
        wrong but not obviously so — so it is worth a test rather than a convention.
        """
        values = [float(index + 1) for index in range(60)]
        warmups = [
            sma(values, 20),
            ema(values, 20),
            rma(values, 20),
            macd(values).dif,
            macd(values).dea,
            rsi(values, 14).rsi,
            bollinger(values, period=20).middle,
            # ⭐ Added in spec 042, and the omission was the bug: `annualised_volatility`
            # filled a zero log return whenever the previous close was 0, so a
            # schema-legal zero base produced 0.0 where there is no ratio at all. ⭐ The
            # list above was written by reading the function names off the module and
            # **this one was not on it** — so the rule 「a warm-up bar is never 0.0」
            # was never applied to it. Found by reading TSP's `scoring.py::_ratio`,
            # which handles the same shape with `None`.
            annualised_volatility(values, period=20),
            true_range(
                [value + 1.0 for value in values],
                [value - 1.0 for value in values],
                values,
            ),
        ]
        for series in warmups:
            assert 0.0 not in series, "a warm-up bar is 0.0 rather than absent"
