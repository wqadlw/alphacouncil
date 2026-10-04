"""Instrument endpoints — resolve, read one, and price one.

Three endpoints, and the split between them is the design:

* ``/resolve`` turns a ticker string into an instrument, or into the question
  "which exchange did you mean". The reasoning behind reporting ambiguity as a
  ``200`` carrying choices rather than as a failure is in the note below, and it
  is worth keeping: `.ai/error-codes.md` §1 fixes the diagnostic envelope at
  exactly five keys, so there is nowhere inside a failure to put two candidate
  markets. An ambiguous ticker is not an error anyway — it is an *input that is
  one answer short*, which is a different thing.
* ``/{market}/{code}`` reads one instrument: its identity, whether it is
  followed and why, and the complete watchlist event log for it.
* ``/{market}/{code}/quote`` prices it, through the router, reporting all four
  data states.

**The record and the price are separate requests, deliberately.** The first is
local and cannot fail; the second crosses the network and frequently will. One
endpoint returning both would couple them, and the failure mode is specific:
a source outage would blank a page whose content — "I followed this in March
because I thought the margin story would hold" — has nothing to do with the
price and is still perfectly true. The user's own words must not be held
hostage by a data vendor.

``/{market}/{code}`` answers ``200`` for an instrument nobody has followed,
with ``follow.status = "never"`` and an empty history. A ``404`` would be the
conventional choice and the wrong one here: the page it feeds exists to show
what you know about a company *before* you decide to follow it, so "nothing
yet" is a valid page, not a missing one.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from alphacouncil.api.deps import DatabaseConnection, MarketData
from alphacouncil.api.routes.cards import CardRead
from alphacouncil.api.routes.cards import to_read as card_to_read
from alphacouncil.api.routes.decisions import DecisionRead
from alphacouncil.api.routes.decisions import to_read as decision_to_read
from alphacouncil.domain.instrument import TickerAmbiguousError, parse_ticker
from alphacouncil.domain.watchlist import WatchlistEventKind
from alphacouncil.indicators import ema, macd, sma
from alphacouncil.models.market import (
    AssetType,
    DataResult,
    DataStatus,
    Market,
    Quote,
    RealtimeQuote,
    Symbol,
)
from alphacouncil.storage.repositories import cards as card_repository
from alphacouncil.storage.repositories import decisions as decision_repository
from alphacouncil.storage.repositories import instruments as instrument_repository
from alphacouncil.storage.repositories import watchlist as watchlist_repository

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


class ResolveStatus(StrEnum):
    """Which of the two answers this is.

    An enum rather than a boolean because the two states carry different data —
    a resolved instrument or a list of choices — and a boolean would leave five
    of the fields meaningless without saying which five.
    """

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


class InstrumentResolveRead(BaseModel):
    """The answer, in one shape for both statuses."""

    status: ResolveStatus
    code: str
    market: Market | None = None
    asset_type: AssetType | None = None
    display: str | None = Field(
        default=None,
        description="Conventional form, e.g. 600519.SH. Absent while ambiguous.",
    )
    candidates: list[Market] = Field(
        default_factory=list,
        description="Markets the code could mean. Empty unless ambiguous.",
    )


@router.get("/resolve", summary="Resolve a ticker, reporting ambiguity instead of failing")
def resolve(
    ticker: Annotated[str, Query(min_length=1, description="600519 / sh600519 / 600519.SH")],
    market: Market | None = None,
    asset_type: AssetType = AssetType.STOCK,
) -> InstrumentResolveRead:
    """Resolve ``ticker``, or list the markets it could mean.

    ``market`` is what the user picks when the response came back ``ambiguous``.
    Passing it up front is also how a caller overrides the derived market — and
    how it gets told when the two disagree.

    Raises:
        TickerInvalidError: The text is not a ticker, or contradicts a stated
            market. Surfaces as the standard diagnostic envelope with a 400.
    """
    try:
        symbol = parse_ticker(ticker, market=market, asset_type=asset_type)
    except TickerAmbiguousError as exc:
        return InstrumentResolveRead(
            status=ResolveStatus.AMBIGUOUS,
            code=exc.ticker,
            candidates=sorted(exc.candidates, key=lambda item: item.value),
        )
    return InstrumentResolveRead(
        status=ResolveStatus.RESOLVED,
        code=symbol.code,
        market=symbol.market,
        asset_type=symbol.asset_type,
        display=symbol.full,
    )


class FollowStatus(StrEnum):
    """Where the instrument stands in the pool, as one of three states.

    Not a boolean, and not a nullable reason. "Never followed" and "followed,
    then removed" both mean the instrument is not in the pool today, but they
    lead to different copy — one offers to add it, the other asks why you left
    — and a boolean would force the UI to recover that difference by
    interpreting an absent reason (constitution 7.7: state is an enum, never a
    boolean plus a nullable field).
    """

    FOLLOWED = "followed"
    REMOVED = "removed"
    NEVER = "never"


class WatchlistEventRead(BaseModel):
    """One line of the append-only log."""

    event_id: int
    occurred_at: str = Field(description="ISO-8601 UTC, server clock (millisecond resolution).")
    kind: WatchlistEventKind
    reason: str | None = Field(
        default=None,
        description="Absent only for a removal the user chose not to explain.",
    )
    supersedes_id: int | None = Field(
        default=None,
        description="The event this one replaced. Set on a revision, null otherwise.",
    )


class FollowStateRead(BaseModel):
    """The relationship between the user and this instrument, right now."""

    status: FollowStatus
    reason: str | None = Field(
        default=None,
        description=(
            "The reason on the newest event, whatever kind it is. When followed "
            "this is why you are holding it under observation; when removed it "
            "is whatever you wrote on the way out. The client labels it per "
            "status rather than this field guessing which one it is."
        ),
    )
    since: str | None = Field(default=None, description="Timestamp of the newest event.")
    last_event_id: int | None = None
    event_count: int = Field(description="Total events ever recorded, including removals.")


class InstrumentDetailRead(BaseModel):
    """Everything the system knows about one instrument."""

    market: Market
    code: str
    display: str = Field(description="Conventional form, e.g. 600519.SH.")
    asset_type: AssetType
    name: str | None = None
    follow: FollowStateRead
    history: list[WatchlistEventRead] = Field(
        default_factory=list,
        description="The full log, oldest first. Never truncated.",
    )
    decisions: list[DecisionRead] = Field(
        default_factory=list,
        description=(
            "Every decision recorded about this instrument, oldest first, never "
            "truncated. Read in order it is the record of a judgement changing; "
            "read newest-first it is a list of unrelated trades."
        ),
    )
    cards: list[CardRead] = Field(
        default_factory=list,
        description=(
            "Every knowledge card tied to this instrument, newest first (K1). "
            "Read with the decisions it is a page that shows what you believed, "
            "why you acted, and where you said it came from."
        ),
    )


def _resolve_path(
    connection: sqlite3.Connection,
    market: Market,
    code: str,
) -> tuple[Symbol, instrument_repository.InstrumentRow | None]:
    """Parse the path into a symbol, plus the stored row when there is one.

    The asset type is never inferred from the code — it is stored explicitly,
    because a code prefix says nothing reliable about what the thing is (see
    :mod:`alphacouncil.models.market`). So for an instrument already on file the
    stored type is the only correct one, and it wins over the parse default.
    Doing this once, here, is why neither endpoint below repeats it.

    Args:
        connection: An open application connection.
        market: The venue from the path.
        code: Six digits from the path.

    Returns:
        The validated symbol, and the stored row or ``None`` when the instrument
        is unknown.

    Raises:
        TickerInvalidError: The code is malformed, or is not listed on the
            stated market. Surfaces as the standard envelope with a 400.
    """
    parsed = parse_ticker(code, market=market)
    row = instrument_repository.get(connection, parsed)
    if row is None:
        return parsed, None
    return parsed.model_copy(update={"asset_type": row.asset_type}), row


@router.get(
    "/{market}/{code}",
    summary="Read one instrument: identity, follow state, and the full event log",
)
def detail(
    market: Market,
    code: str,
    connection: DatabaseConnection,
) -> InstrumentDetailRead:
    """Return everything recorded about ``code`` on ``market``.

    Answers ``200`` even for an instrument that has never been followed: the
    page this feeds is the one where you decide whether to follow it, so
    "nothing yet" is a page, not a ``404``.
    """
    symbol, row = _resolve_path(connection, market, code)
    events = watchlist_repository.history(connection, symbol)
    newest = events[-1] if events else None
    decisions = decision_repository.for_symbol(connection, symbol)
    cards = card_repository.list_for_symbol(connection, symbol)

    if newest is None:
        status = FollowStatus.NEVER
    elif newest.kind is WatchlistEventKind.REMOVED:
        status = FollowStatus.REMOVED
    else:
        status = FollowStatus.FOLLOWED

    return InstrumentDetailRead(
        market=symbol.market,
        code=symbol.code,
        display=symbol.full,
        asset_type=symbol.asset_type,
        name=row.name if row is not None else None,
        follow=FollowStateRead(
            status=status,
            reason=newest.reason if newest is not None else None,
            since=newest.occurred_at if newest is not None else None,
            last_event_id=newest.event_id if newest is not None else None,
            event_count=len(events),
        ),
        history=[
            WatchlistEventRead(
                event_id=event.event_id,
                occurred_at=event.occurred_at,
                kind=event.kind,
                reason=event.reason,
                supersedes_id=event.supersedes_id,
            )
            for event in events
        ],
        decisions=[decision_to_read(recorded) for recorded in decisions],
        cards=[card_to_read(card) for card in cards],
    )


@router.get(
    "/{market}/{code}/quote",
    summary="Price one instrument, reporting all four data states",
)
def quote(
    market: Market,
    code: str,
    connection: DatabaseConnection,
    market_data: MarketData,
) -> DataResult[RealtimeQuote]:
    """Fetch a realtime snapshot through the router.

    The result is passed through **unmodified**, including the states that carry
    no price. Mapping ``no_data`` onto a ``404`` would look tidier and would
    destroy the distinction the UI needs: "this code is not something the source
    quotes" and "every source we know refused us" are different sentences to put
    on a page, and only one of them is worth retrying.

    ``stale`` is likewise preserved rather than smoothed over — a cached price
    served as today's would be a quiet lie, and the flag is how the client can
    say "this number is old" instead.
    """
    symbol, _ = _resolve_path(connection, market, code)
    return market_data.get_realtime(symbol)

#: Bars served when the caller states no window.
#:
#: ⭐ A history endpoint can be asked for an unbounded range by accident and a provider will
#: try to satisfy it. The cap lives here, not in the source, so the contract is one line to
#: read rather than a behaviour to discover.
DEFAULT_DAILY_WINDOW_DAYS = 320

#: The hard ceiling, whatever the caller asks for.
MAX_DAILY_WINDOW_DAYS = 1500

#: ⭐ **Why 7.** A caller's `start` is a calendar day and a bar's `trade_date` is a trading
#: day, so 「the first bar is later than I asked」 is true every weekend and every holiday.
_CLAMP_TOLERANCE_DAYS = 7


def _default_end() -> date:
    """Today, in UTC.

    ⭐ For A shares this is the previous day between 00:00 and 08:00 Beijing time. That is
    benign for this endpoint: no bar for that session exists yet either, so the series is
    not wrong — it is one session behind at an hour when there is nothing to show. A comment
    that says why is cheaper than a market-calendar dependency, and easier to check.
    """
    return datetime.now(UTC).date()


class IndicatorRead(BaseModel):
    """One indicator series, aligned to ``bars`` and ``None`` where it does not exist yet.

    ⭐ The alignment is the point. A separate, shorter list of only the mature values would
    force the client to infer which bars they belong to, and **every** such inference is a
    place to be off by one — which on a chart looks like a signal shifting in time.
    """

    name: str = Field(description="Stable id, e.g. `ma20`.")
    label: str = Field(description="Human label, e.g. `MA20`.")
    values: list[float | None] = Field(description="One entry per bar, oldest first.")


class DailySeriesRead(BaseModel):
    """Bars and the indicators derived from them, as one value.

    ⭐⭐ **Plus the window that was asked for and the window that arrived**, because as of
    2026-10-04 they could differ by four years **and nothing said so.**

    ⚠️⚠️ **Measured, not anticipated.** ``?start=2015-01-01`` returned **320 bars starting
    2025-06-12**, with ``status="ok"`` and no error. ⭐ Two clamps produce that and neither
    was visible:

    - ⭐ **this route** (``MAX_DAILY_WINDOW_DAYS = 1500``, ~4 years) rewrites
      ``resolved_start`` in place ⭐ **and the rewritten value is what gets fetched** ⭐ so
      the response cannot tell you an ask ever happened.
    - ⭐ **the provider** caps at 320 bars, which turns those four years into fifteen
      months.

    ⇒ ⭐ **Both are computable here** ⭐ from the caller's ``start`` and ``bars[0]``,
    ⭐ **so this costs no extra fetch and no provider change.**
    """

    bars: list[Quote]
    indicators: list[IndicatorRead] = Field(
        default_factory=list,
        description=(
            "Empty when the window is shorter than every indicator's period "
            "which is a fact about the data, not a failure."
        ),
    )
    #: ⭐ **Null when the caller passed no window at all** ⭐ — which is **not** the same as
    #: 「they asked for nothing」 ⭐ it is 「we chose 320 days for them」, ⭐ and a page needs
    #: two different sentences for those.
    requested_start: date | None = Field(
        default=None, description="The `start` the caller passed, or null."
    )
    requested_end: date | None = Field(
        default=None, description="The `end` the caller passed, or null."
    )
    delivered_from: date | None = Field(
        default=None, description="First delivered bar's trade_date; null when there are none."
    )
    delivered_to: date | None = Field(
        default=None, description="Last delivered bar's trade_date; null when there are none."
    )
    #: ⭐⭐ **The field a page branches on.** ⭐ True when the delivered window is narrower
    #: than the one asked for — by this route's clamp, by the provider's row cap, or both.
    #: ⚠️ **It is deliberately a boolean and not a message** ⭐ because `api.ts:731-736`
    #: says the client's job is not to reword what the server says ⭐ **and a boolean cannot
    #: be reworded, misread, or translated into a claim the product did not make.**
    #:
    #: ⭐ **And it is not the truth — the two dates are.** ⭐ `delivered_from` is a *trading*
    #: day and `requested_start` is a *calendar* one, ⭐ so this carries
    #: `_CLAMP_TOLERANCE_DAYS` of slack ⭐ **and the slack is a judgement, not a measurement.**
    #: ⭐ A page that shows both dates is right even when this boolean is wrong; ⭐ a page that
    #: shows only this boolean is right only when the judgement was.
    clamped: bool = Field(
        default=False,
        description=(
            "True when delivered_from is more than _CLAMP_TOLERANCE_DAYS after "
            "requested_start. Compare the dates rather than trusting this."
        ),
    )


def _indicators(bars: list[Quote]) -> list[IndicatorRead]:
    """Compute the panel's indicators from bars already in hand.

    ⭐ Deliberately a **fixed small set** rather than everything ``indicators.py`` offers.
    A panel that draws six lines teaches nothing and hides the three that matter; the rest
    are one request away. Which ones earn their place is a product question, and
    ``spec 037`` §7 already ruled out pattern judgements like 「均线多头」 as strategy
    language.
    """
    closes = [bar.close for bar in bars]
    if len(closes) < 2:
        return []

    macd_line = macd(closes)
    moving = sma(closes, 20)
    spread = ema(closes, 12)

    def series(name: str, label: str, values: list[float | None]) -> IndicatorRead | None:
        if all(value is None for value in values):
            # ⭐ An all-empty series is not a series. Returning it would put a line on a
            # chart that has nothing to draw, and a legend entry that cannot be hovered.
            return None
        return IndicatorRead(name=name, label=label, values=values)

    candidates = [
        series("ma20", "MA20", moving),
        series("ema12", "EMA12", spread),
        series("dif", "DIF", macd_line.dif),
        series("dea", "DEA", macd_line.dea),
        series("histogram", "MACD 柱", macd_line.histogram),
    ]
    return [item for item in candidates if item is not None]


@router.get(
    "/{market}/{code}/daily",
    summary="Daily bars for one instrument, reporting all four data states",
)
def daily(
    market: Market,
    code: str,
    connection: DatabaseConnection,
    market_data: MarketData,
    start: date | None = None,
    end: date | None = None,
) -> DataResult[DailySeriesRead]:
    """Fetch daily bars through the router, oldest first.

    The result is passed back **unmodified**, for the reasons ``/quote`` gives and does not
    repeat: ``no_data`` and ``error`` are different sentences and only one is worth
    retrying, and ``stale`` is how the client can say 「这个数是旧的」 instead of serving a
    cached price as today's.

    Args:
        market: The venue from the path.
        code: Six digits from the path.
        start: First trading day wanted. Defaults to ``DEFAULT_DAILY_WINDOW_DAYS`` back.
        end: Last trading day wanted. Defaults to today.
    """
    symbol, _ = _resolve_path(connection, market, code)

    resolved_end = end if end is not None else _default_end()
    resolved_start = (
        start
        if start is not None
        else resolved_end - timedelta(days=DEFAULT_DAILY_WINDOW_DAYS)
    )
    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"start={resolved_start.isoformat()} is after "
                f"end={resolved_end.isoformat()}"
            ),
        )
    if (resolved_end - resolved_start).days > MAX_DAILY_WINDOW_DAYS:
        resolved_start = resolved_end - timedelta(days=MAX_DAILY_WINDOW_DAYS)

    result = market_data.get_daily(symbol, start=resolved_start, end=resolved_end)
    # ⭐ `status is OK`, not `error_code is None`. The validator guarantees ok carries a
    # value, so this test cannot pass a `no_data` result off as an empty series — which is
    # the one misreading that would render 「这只票没有历史」 when the truth is 「所有源都
    # 拒绝了」.
    series: DailySeriesRead | None = None
    if result.status is DataStatus.OK and result.value is not None:
        bars = sorted(result.value, key=lambda quote: quote.trade_date)
        # ⭐ Ascending is the contract, not a coincidence: the router merges sources and
        # each returns its own order.
        # ⭐⭐ Both clamps, named. `resolved_start` has already been narrowed by
        # `MAX_DAILY_WINDOW_DAYS` above ⭐ **and the provider may have narrowed it further**
        # ⭐ so the comparison is against the *bars*, not against the clamp ⭐ — comparing
        # against the clamp would report 「nothing was lost」 ⭐ **for a request that lost
        # nine years**, ⭐ which is the exact defect.
        delivered_from = bars[0].trade_date if bars else None
        delivered_to = bars[-1].trade_date if bars else None
        series = DailySeriesRead(
            bars=bars,
            indicators=_indicators(bars),
            # ⭐⭐ **The caller's own `start`, verbatim — not `resolved_start`.** ⭐ The first
            # version of this line passed `resolved_start` ⭐ **with a comment arguing that
            # was the point** ⭐ **and it is the opposite:** measured 2026-10-04, a
            # `?start=2015-01-01` came back labelled `requested=2022-08-26`, ⭐ **so the four
            # years the clamp above threw away were invisible** ⭐ **and a caller comparing
            # the two dates would conclude nothing was lost.** ⭐ The caller can only learn a
            # clamp happened by seeing their own date come back altered.
            requested_start=start,
            requested_end=end,
            delivered_from=delivered_from,
            delivered_to=delivered_to,
            # ⭐ **A declared tolerance, because `start` is a calendar day and `trade_date`
            # is a trading day ⭐ **and comparing them directly made `?start=2024-01-01`
            # come back `clamped=True`** ⭐ — that day was New Year's, ⭐ **so the first bar
            # was the 2nd and the clamp was fiction.** ⭐ A week covers every weekend plus
            # this market's two-to-three-day holiday clusters ⭐ **and anything wider is a
            # real clamp.** ⭐ And the two dates remain the truth ⭐ — this constant only
            # decides which *word* appears, never which *fact*.
            clamped=bool(
                delivered_from is not None
                and start is not None
                and delivered_from > start + timedelta(days=_CLAMP_TOLERANCE_DAYS)
            ),
        )

    # ⭐ **One return, both states.** Rebuilding rather than returning `result` unchanged is
    # what keeps the *other* four fields — `stale`, `source`, `fetched_at`, `error_code` —
    # exactly as the router produced them. Passing them through by hand is the price of
    # changing the value's type, and skipping one of them is how a stale series would come
    # back unlabelled.
    return DataResult[DailySeriesRead](
        status=result.status,
        value=series,
        reason=result.reason,
        detail=result.detail,
        error_code=result.error_code,
        source=result.source,
        fetched_at=result.fetched_at,
        stale=result.stale,
    )
