"""The watchlist API — four verbs, and deliberately no DELETE.

``POST`` adds, ``POST /reason`` changes the reason, ``POST /remove`` stops
following, ``GET`` lists. There is no ``DELETE`` because nothing is ever
deleted: the pool is an append-only log, so "remove" is a new event rather than
the absence of an old one. Exposing ``DELETE`` would imply otherwise and give
the frontend a way to erase the record the product's second highlight is built
on ("you said this three times").

Every write goes through :func:`alphacouncil.domain.watchlist`, which is where a
reason is required to be a real sentence. The route does not re-check that — it
would be a second copy of a rule that already lives in the domain, the request
schema, and the database.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from alphacouncil.api.deps import DatabaseConnection
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
from alphacouncil.models.market import AssetType, Market, Symbol
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
