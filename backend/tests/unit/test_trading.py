"""The trading-day verdict table (spec 007) — every row, on injected clocks.

Marked ``unit``: no network, no clock. The rule is a pure function of
``now`` and ``last_trading_date``; 2026-09-24 is a Thursday on purpose, and
the cutoff second itself is asserted so the boundary has a named owner.

The two cases the product must never get wrong are the two "certain" rows:
a weekend is never a trading day (adjusted working Saturdays stay closed),
and a bare weekday is never *promoted* to one — Monday can be a holiday, and
an unverified guess dressed as a verdict is what constitution 4.6 forbids.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from alphacouncil.domain.trading import (
    MARKET_OPEN_CERTAINTY,
    TradingDayBasis,
    TradingDayError,
    TradingDayVerdict,
    verdict_for,
)

pytestmark = pytest.mark.unit

THURSDAY = date(2026, 9, 24)
FRIDAY = date(2026, 9, 25)
SATURDAY = date(2026, 9, 26)
SUNDAY = date(2026, 9, 27)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """A local wall-clock moment on ``day``."""
    return datetime(2026, day.month, day.day, hour, minute)


# ---------------------------------------------------------------------------
# the certain rows
# ---------------------------------------------------------------------------


def test_a_saturday_is_never_a_trading_day_even_without_a_probe() -> None:
    """Adjusted working Saturdays stay closed — the verdict needs no probe."""
    verdict, basis = verdict_for(now=at(SATURDAY, 10, 30), last_trading_date=None)

    assert verdict is TradingDayVerdict.NON_TRADING_DAY
    assert basis is TradingDayBasis.WEEKEND


def test_a_sunday_morning_is_non_trading_before_any_probe_answers() -> None:
    verdict, basis = verdict_for(now=at(SUNDAY, 9), last_trading_date=THURSDAY)

    assert verdict is TradingDayVerdict.NON_TRADING_DAY
    assert basis is TradingDayBasis.WEEKEND


# ---------------------------------------------------------------------------
# the probe rows
# ---------------------------------------------------------------------------


def test_a_weekday_with_todays_bar_is_a_trading_day() -> None:
    """Today's bar exists — the market has traded today. Certain."""
    verdict, basis = verdict_for(now=at(THURSDAY, 14, 0), last_trading_date=THURSDAY)

    assert verdict is TradingDayVerdict.TRADING_DAY
    assert basis is TradingDayBasis.PROBE


def test_a_weekday_after_the_cutoff_with_an_older_bar_is_a_holiday() -> None:
    """Thursday 14:00, last bar Wednesday: the market opened 4.5 hours ago and
    produced nothing — today is a holiday."""
    verdict, basis = verdict_for(now=at(THURSDAY, 14, 0), last_trading_date=date(2026, 9, 23))

    assert verdict is TradingDayVerdict.NON_TRADING_DAY
    assert basis is TradingDayBasis.PROBE


def test_a_weekday_before_the_cutoff_with_an_older_bar_is_unknown() -> None:
    """Thursday 09:00, last bar Wednesday: holiday, or simply not open yet."""
    verdict, basis = verdict_for(now=at(THURSDAY, 9, 0), last_trading_date=date(2026, 9, 23))

    assert verdict is TradingDayVerdict.UNKNOWN
    assert basis is TradingDayBasis.NONE


def test_the_cutoff_second_itself_belongs_to_the_decided_side() -> None:
    """10:05:00 exactly is past the certainty point — the boundary has an owner."""
    verdict, _ = verdict_for(now=at(THURSDAY, 10, 5), last_trading_date=date(2026, 9, 23))

    assert verdict is TradingDayVerdict.NON_TRADING_DAY


def test_a_failed_probe_on_a_weekday_is_unknown_not_a_guess() -> None:
    """No evidence means no claim. A bare weekday must never become "trading day"
    — Monday can be a holiday (constitution 4.6)."""
    verdict, basis = verdict_for(now=at(THURSDAY, 14, 0), last_trading_date=None)

    assert verdict is TradingDayVerdict.UNKNOWN
    assert basis is TradingDayBasis.NONE


def test_a_trading_date_from_the_future_is_a_source_fault() -> None:
    """A bar dated tomorrow is corruption, not a verdict — refuse loudly."""
    with pytest.raises(TradingDayError):
        verdict_for(now=at(THURSDAY, 14, 0), last_trading_date=FRIDAY)


def test_the_cutoff_constant_is_documented_in_hours_the_reader_knows() -> None:
    """The constant's reason ("09:30 open + margin") must survive refactors."""
    assert MARKET_OPEN_CERTAINTY.hour == 10
    assert MARKET_OPEN_CERTAINTY.minute == 5
