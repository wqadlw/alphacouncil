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
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from alphacouncil.api.deps import DatabaseConnection, MarketData
from alphacouncil.domain.instrument import TickerAmbiguousError, parse_ticker
from alphacouncil.domain.watchlist import WatchlistEventKind
from alphacouncil.models.market import (
    AssetType,
    DataResult,
    Market,
    RealtimeQuote,
    Symbol,
)
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
