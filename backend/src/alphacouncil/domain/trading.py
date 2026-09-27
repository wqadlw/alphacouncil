"""Trading-day determination — a probe, not a calendar (spec 007).

Whether the A-share market opens today decides how every price on the screen
should be read: "the same number as an hour ago" means one thing on a trading
day and another on a holiday. This module answers it with an explicit verdict
and, just as importantly, the **basis** the verdict rests on — because the
three answers are not equally certain.

Deliberate departures from the TSP reference (T-08), recorded here because
they are the point:

* No embedded holiday calendar. A table written from memory or copied without
  a verifiable source goes stale silently, and a wrong holiday table produces
  "plausible wrong results" — the exact failure this discipline exists to
  prevent. The probe needs no holiday knowledge at all.
* A bare weekday never yields ``trading_day``. A Monday can be a holiday; the
  TSP fallback ("weekday → trading day") would dress an unverified guess as an
  answer, which constitution 4.6 forbids. The weekend direction *is* kept: the
  A-share market never opens on a Saturday or Sunday, even when the state
  calendar swaps a working day onto them.
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum

__all__ = [
    "MARKET_OPEN_CERTAINTY",
    "TradingDayBasis",
    "TradingDayVerdict",
    "verdict_for",
]

#: 09:30 open + 35 minutes. On a genuine trading day the session has produced
#: today's bar by then; before it, "yesterday's bar" cannot be told apart from
#: "today is a holiday". The assumption that an intraday series already holds
#: today's bar is declared in status.md §五 and must be verified on the next
#: trading morning.
MARKET_OPEN_CERTAINTY = time(10, 5)


class TradingDayVerdict(StrEnum):
    """Whether the market opens today — or that we cannot tell."""

    TRADING_DAY = "trading_day"
    NON_TRADING_DAY = "non_trading_day"
    UNKNOWN = "unknown"


class TradingDayBasis(StrEnum):
    """What the verdict rests on. ``none`` accompanies ``unknown`` only."""

    PROBE = "probe"
    WEEKEND = "weekend"
    NONE = "none"


class TradingDayError(ValueError):
    """The probe returned a date from the future — a source fault, not an answer."""


def verdict_for(
    *,
    now: datetime,
    last_trading_date: date | None,
) -> tuple[TradingDayVerdict, TradingDayBasis]:
    """Judge ``now`` from the last date the market actually traded.

    The rules as data — an ordered table, each row a condition and the answer
    it licenses. Weekend first: it is the most certain and costs nothing.

    Args:
        now: The reader's local wall clock (server == reader on this product).
        last_trading_date: The newest date with a daily bar, or ``None`` when
            the probe could not answer.

    Returns:
        ``(verdict, basis)`` — never one without the other.

    Raises:
        TradingDayError: The probe reports a trading date in the future, which
            is a data-source fault rather than a verdict.
    """
    today = now.date()

    if last_trading_date is not None and last_trading_date > today:
        raise TradingDayError(
            f"probe returned a future trading date: {last_trading_date} > {today}"
        )

    if now.weekday() >= 5:
        # Certain even without a probe: adjusted working Saturdays stay closed.
        return (TradingDayVerdict.NON_TRADING_DAY, TradingDayBasis.WEEKEND)

    if last_trading_date is None:
        return (TradingDayVerdict.UNKNOWN, TradingDayBasis.NONE)

    if last_trading_date == today:
        return (TradingDayVerdict.TRADING_DAY, TradingDayBasis.PROBE)

    # last_trading_date < today on a weekday: holiday or not-open-yet, decided
    # by the certainty cutoff alone.
    if now.time() >= MARKET_OPEN_CERTAINTY:
        return (TradingDayVerdict.NON_TRADING_DAY, TradingDayBasis.PROBE)
    return (TradingDayVerdict.UNKNOWN, TradingDayBasis.NONE)
