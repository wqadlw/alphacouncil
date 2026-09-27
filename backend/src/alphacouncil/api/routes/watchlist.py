"""The watchlist API — four verbs, and deliberately no DELETE.

``POST`` adds, ``POST /reason`` changes the reason, ``POST /remove`` stops
following, ``GET`` lists — and ``GET /quotes`` prices the pool, each instrument
carrying its own four-state outcome (spec 004). There is no ``DELETE`` because
nothing is ever deleted: the pool is an append-only log, so "remove" is a new
event rather than the absence of an old one. Exposing ``DELETE`` would imply
otherwise and give the frontend a way to erase the record the product's second
highlight is built on ("you said this three times").

Every write goes through :func:`alphacouncil.domain.watchlist`, which is where a
reason is required to be a real sentence. The route does not re-check that — it
would be a second copy of a rule that already lives in the domain, the request
schema, and the database.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from alphacouncil.api.deps import DatabaseConnection, MarketData
from alphacouncil.domain.instrument import parse_ticker
from alphacouncil.domain.watchlist import (
    MAX_REASON_CHARS,
    WatchlistEventKind,
    WatchlistState,
    added,
    reason_revised,
    removed,
    require_followed,
)
from alphacouncil.models.market import AssetType, DataResult, Market, RealtimeQuote, Symbol
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import watchlist as repository

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])

#: The text form of the reason ceiling, quoted in the schema so the request
#: rejects an over-long body before the domain has to build an exception for it.
_REASON = Field(min_length=1, max_length=MAX_REASON_CHARS)


class WatchlistAddRequest(BaseModel):
    """Follow an instrument. The reason is the point of the endpoint."""

    ticker: str = Field(min_length=1, description="600519 / sh600519 / 600519.SH")
    market: Market | None = Field(
        default=None, description="Required when the ticker is ambiguous (000xxx)"
    )
    asset_type: AssetType = AssetType.STOCK
    reason: str = _REASON


class WatchlistReasonRevisionRequest(BaseModel):
    """Replace the reason. Identified by instrument, not by event id.

    The client names the instrument and the server finds the event to supersede.
    Letting the client pass a ``supersedes_id`` would put the log's shape in the
    frontend's hands, and the frontend has no way to know which event is current.
    """

    ticker: str = Field(min_length=1)
    market: Market | None = None
    reason: str = _REASON


class WatchlistRemovalRequest(BaseModel):
    """Stop following. A reason is optional — leaving needs no justification."""

    ticker: str = Field(min_length=1)
    market: Market | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON_CHARS)


class RecordedEventRead(BaseModel):
    """Receipt for a write, so a client can point at the event it created."""

    event_id: int
    occurred_at: str
    kind: WatchlistEventKind
    market: Market
    code: str
    reason: str | None
    supersedes_id: int | None


class WatchlistEntryRead(BaseModel):
    """One instrument currently in the pool, joined to its instrument row."""

    market: Market
    code: str
    asset_type: AssetType
    name: str | None
    reason: str | None
    since: str
    last_event_id: int


def _receipt(recorded: repository.RecordedEvent) -> RecordedEventRead:
    return RecordedEventRead(
        event_id=recorded.event_id,
        occurred_at=recorded.occurred_at,
        kind=recorded.kind,
        market=recorded.market,
        code=recorded.code,
        reason=recorded.reason,
        supersedes_id=recorded.supersedes_id,
    )


def _require_followed(connection: sqlite3.Connection, symbol: Symbol) -> WatchlistState:
    """Read the newest event, then let the domain decide whether acting is allowed."""
    return require_followed(repository.current_event(connection, symbol), symbol)


@router.get("", summary="List every instrument currently followed")
def list_watchlist(connection: DatabaseConnection) -> list[WatchlistEntryRead]:
    """Return the pool as the ``watchlist_current`` view defines it."""
    return [
        WatchlistEntryRead(
            market=entry.market,
            code=entry.code,
            asset_type=entry.asset_type,
            name=entry.name,
            reason=entry.reason,
            since=entry.since,
            last_event_id=entry.last_event_id,
        )
        for entry in repository.current(connection)
    ]


class PoolQuoteRead(BaseModel):
    """One pool instrument paired with its own fetch outcome."""

    market: Market
    code: str
    display: str = Field(description="Conventional form, e.g. 600519.SH.")
    quote: DataResult[RealtimeQuote] = Field(
        description=(
            "This symbol's own four-state outcome. Deliberately not merged with "
            "the neighbours' — see the endpoint's docstring."
        )
    )


@router.get("/quotes", summary="Price every instrument currently followed")
def pool_quotes(
    connection: DatabaseConnection,
    market_data: MarketData,
) -> list[PoolQuoteRead]:
    """Fetch a realtime snapshot for each instrument in the pool.

    **The pool priced here is the pool that ``GET ""`` lists** — both read the
    same ``watchlist_current`` view. Two endpoints holding two ideas of what
    "currently followed" means is how a page starts showing a price for a
    stock the list above it says you left.

    **Every symbol gets its own four-state result, and the states are never
    merged into a batch status.** The truthful sentence about ten followed
    instruments is "seven priced, two not quoted by any source, one refused"
    — any single batch-level status would be a lie about at least one of them
    (spec 004 FR-2). This is also why the loop needs no ``try``: the providers
    map their own transport failures onto the four states, so an exception
    here would be a bug, not a data condition, and it should surface as a 500.

    **The walk is sequential on purpose.** Ten followed instruments fanned out
    concurrently is ten simultaneous upstream requests — the exact behaviour
    that got a source to rate-limit us once already. Until the router grows
    its own throttling, one-at-a-time is the rate discipline, and it costs a
    page a few seconds, not an IP a few hours.

    An empty pool answers ``[]``: there was nothing to price, which is not a
    failure.
    """
    rows: list[PoolQuoteRead] = []
    for entry in repository.current(connection):
        symbol = Symbol(market=entry.market, code=entry.code)
        rows.append(
            PoolQuoteRead(
                market=entry.market,
                code=entry.code,
                display=symbol.full,
                quote=market_data.get_realtime(symbol),
            )
        )
    return rows


@router.post("", status_code=status.HTTP_201_CREATED, summary="Follow an instrument")
def add(payload: WatchlistAddRequest, connection: DatabaseConnection) -> RecordedEventRead:
    """Append an ``added`` event, creating the instrument row if it is new."""
    symbol = parse_ticker(payload.ticker, market=payload.market, asset_type=payload.asset_type)
    event = added(symbol, payload.reason)
    with transaction(connection):
        return _receipt(repository.append(connection, event))


@router.post("/reason", summary="Replace the reason for following an instrument")
def revise_reason(
    payload: WatchlistReasonRevisionRequest,
    connection: DatabaseConnection,
) -> RecordedEventRead:
    """Append a ``reason_revised`` event superseding the current one."""
    symbol = parse_ticker(payload.ticker, market=payload.market)
    with transaction(connection):
        current = _require_followed(connection, symbol)
        event = reason_revised(symbol, payload.reason, supersedes_id=current.event_id)
        return _receipt(repository.append(connection, event))


@router.post("/remove", summary="Stop following an instrument")
def remove(
    payload: WatchlistRemovalRequest,
    connection: DatabaseConnection,
) -> RecordedEventRead:
    """Append a ``removed`` event. Nothing is deleted; the row stays."""
    symbol = parse_ticker(payload.ticker, market=payload.market)
    with transaction(connection):
        _require_followed(connection, symbol)
        event = removed(symbol, reason=payload.reason)
        return _receipt(repository.append(connection, event))
