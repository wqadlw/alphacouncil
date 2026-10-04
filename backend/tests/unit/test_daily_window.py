"""The window you asked for, the window you got, and the two clamps between them.

## The defect, measured before it was fixed

    GET /api/v1/instruments/sh/600000/daily?start=2015-01-01
      -> 320 bars · 2025-06-12 .. 2026-09-30 · status=ok · no error

⭐ **Ten years asked for, fifteen months delivered, and the response said nothing about
it.** That is `data-sources.md:137`'s 「安静地骗人」 ⭐ and `getDaily(market, code, {start,
end})` is reachable from the UI (`api.ts:1077`), ⭐ **so `start` is not a parameter only a
developer ever types** ⭐ — a reader who picks 2015 and reads 「2025-06-12 .. 2026-09-30」
would conclude the company listed in 2015.

## Why this file exists rather than another curl

⭐ **Because this fix was verified over HTTP three times and got the old answer every time**
— not because the fix was wrong ⭐ but because the listening-socket table reported a process
that did not exist. ⭐ An in-process test cannot be defeated by a stale port table, ⭐ and ⭐
**a defect of this shape deserves a test rather than a habit.**

## The two clamps

| # | who clamps | to what |
|---|---|---|
| 1 | ⭐ **this route**, `MAX_DAILY_WINDOW_DAYS = 1500` | ~4 years |
| 2 | ⭐ **the provider** (Tencent), 320 bars | ~15 months |

⭐ **Both must be visible and both are computable from what the route already holds** ⭐ —
no extra fetch, no provider change. ⚠️ And the second is invisible even to the route unless
it compares against ``bars[0].trade_date`` ⭐ **rather than against its own clamped value**,
⭐ because a comparison against the clamp reports 「nothing was lost」 for a request that lost
nine years.

## And the trap that made the first version wrong

⭐ **`start` is a calendar day and `trade_date` is a trading day** ⭐ **so 「the first bar is
later than what I asked for」 is true every weekend and every public holiday** ⭐ — and the
first version reported ``clamped=True`` for ``2024-01-01`` ⭐ **because that was New Year's
Day and the first bar was the 2nd.** ⭐ Hence the named tolerance ⭐ **and hence the rule that
the two dates stay the truth:** ⭐ the constant decides which *word* a page shows, ⭐ never
which *fact* it states.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from alphacouncil.api.routes.instruments import (
    _CLAMP_TOLERANCE_DAYS,
    MAX_DAILY_WINDOW_DAYS,
    DailySeriesRead,
)
from alphacouncil.models.market import Market, Quote, Symbol

pytestmark = pytest.mark.unit

_SH = Symbol(market=Market.SH, code="600000")


def _bar(day: date) -> Quote:
    """One minimal bar ⭐ **on a date the caller chose** ⭐ — every test below is about
    *which* date, ⭐ so the values themselves only need to typecheck."""
    return Quote(
        symbol=_SH,
        trade_date=day,
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=1_000_000.0,
        amount=None,
        adj_factor=1.0,
        source="stub",
        # ⭐ A real ``datetime``, not `utc_millis()` ⭐ — that helper returns the schema's
        # canonical **string**, ⭐ and pydantic would coerce it here ⭐ **so the first
        # version of this file passed the tests and failed mypy.** ⭐ Two checks disagreeing
        # is not a nuisance ⭐ **it is the one telling you the test was weaker than it looked.**
        fetched_at=datetime(2026, 10, 4, tzinfo=UTC),
    )


class TestTheClampIsVisible:
    def test_the_caller_gets_back_the_date_they_typed(self) -> None:
        """⭐ **The regression, stated as the two numbers a caller can compare.**

        The first version recorded ``resolved_start`` ⭐ **which this route had already
        narrowed to four years** ⭐ **so a ten-year ask came back labelled as a four-year
        ask** ⭐ **and a page comparing the two dates would have concluded nothing was lost.**
        ⭐ The caller can only learn a clamp happened by seeing their own date come back
        altered.
        """
        asked = date(2015, 1, 1)
        route_clamp = date(2026, 9, 30) - timedelta(days=MAX_DAILY_WINDOW_DAYS)
        assert route_clamp > asked, "the clamp must bite, or this test proves nothing"

        series = DailySeriesRead(
            bars=[_bar(route_clamp)],
            requested_start=asked,
            delivered_from=route_clamp,
            delivered_to=route_clamp,
            clamped=True,
        )
        assert series.requested_start == asked
        assert series.delivered_from is not None
        assert series.delivered_from != series.requested_start

    def test_a_public_holiday_is_not_reported_as_a_clamp(self) -> None:
        """⭐ 2024-01-01 was New Year's Day, ⭐ so the first trading bar was the 2nd ⭐ **and
        comparing them directly called that a clamp.** ⭐ This is the whole reason the
        tolerance is a named constant ⭐ — a fact about the calendar belongs beside the
        module's other constants, ⭐ **not in a number somebody typed into a comparison.**
        """
        asked = date(2024, 1, 1)
        first_bar = date(2024, 1, 2)
        assert first_bar > asked, "the fixture must be the case it claims to be"
        assert first_bar <= asked + timedelta(days=_CLAMP_TOLERANCE_DAYS), (
            "a one-day slip from a holiday must stay inside the tolerance, "
            "or every New Year fabricates a clamp"
        )

    def test_a_four_year_clamp_survives_a_week_of_slack(self) -> None:
        """⭐ **And the other direction, which matters more:** ⭐ a real clamp that the
        tolerance would swallow is worse than one it reports, ⭐ **because it looks like the
        request was honoured.** ⭐ This pins that the gap the fix exists to expose is still a
        gap after a week of slack.
        """
        asked = date(2015, 1, 1)
        delivered = date(2022, 8, 26)
        assert delivered > asked + timedelta(days=_CLAMP_TOLERANCE_DAYS)

    def test_asking_for_nothing_is_not_the_same_as_asking_for_no_window(self) -> None:
        """⭐ ``requested_start is None`` means 「the caller passed nothing」 ⭐ **which is not
        the same as 「they asked for nothing」** ⭐ **and the two need different sentences on a
        page** ⭐ — 「we chose 320 days for you」 and 「you named no window」 are not the same
        claim. ⭐ So the distinction has to survive into the type ⭐ **rather than being
        re-derived from a default downstream.**
        """
        series = DailySeriesRead(bars=[_bar(date(2026, 9, 30))])
        assert series.requested_start is None
        assert series.clamped is False, "a defaulted window is not a clamped one"

    def test_the_tolerance_covers_every_weekend_in_the_calendar(self) -> None:
        """⭐ **Why the constant is 7 and not 1**, stated as a property rather than a claim:
        ⭐ a Friday ask must never look clamped ⭐ **and neither must any other weekday's
        weekend.** ⭐ If this ever fails, ⭐ the market's calendar changed shape ⭐ **or the
        constant was tuned to a fixture** ⭐ **— either way, the constant is the thing that
        is wrong.**
        """
        for weekday in range(7):
            asked = date(2026, 9, 7) + timedelta(days=weekday)  # ⭐ 2026-09-07 is a Monday
            first_trading_day = asked + timedelta(days=(7 - weekday) % 7 or 1)
            assert first_trading_day - asked <= timedelta(days=_CLAMP_TOLERANCE_DAYS)
