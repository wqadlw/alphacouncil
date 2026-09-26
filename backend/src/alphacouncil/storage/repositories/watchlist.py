"""Appending to, and reading, the watchlist event log (D1).

The log is append-only, and this module offers no way to break that: there is no
``update`` and no ``delete``, so "changing your mind" has exactly one
implementation, which is appending another event. The database enforces the same
thing with triggers, so the rule survives a caller that reaches past this module
with raw SQL — which is why the triggers exist instead of a comment here.

Reading goes through the ``watchlist_current`` view rather than being re-derived
in Python. Two implementations of "the newest event wins, unless it is a
removal" would be two chances to disagree, and the view is the one the schema
can be tested against.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.watchlist import (
    WatchlistEvent,
    WatchlistEventKind,
    WatchlistState,
)
from alphacouncil.models.market import AssetType, Market, Symbol
from alphacouncil.storage.repositories import instruments

__all__ = [
    "RecordedEvent",
    "WatchlistEntry",
    "append",
    "current",
    "current_event",
    "history",
]

_INSERT = (
    "INSERT INTO watchlist_events (occurred_at, market, code, kind, reason, supersedes_id) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)
_SELECT_CURRENT = (
    "SELECT c.market, c.code, c.reason, c.occurred_at, c.last_event_id, "
    "       i.asset_type, i.name "
    "FROM watchlist_current AS c "
    "JOIN instruments AS i ON i.market = c.market AND i.code = c.code "
    "ORDER BY c.occurred_at DESC, c.last_event_id DESC"
)
_SELECT_LATEST = (
    "SELECT id, kind FROM watchlist_events WHERE market = ? AND code = ? ORDER BY id DESC LIMIT 1"
)
_SELECT_HISTORY = (
    "SELECT id, occurred_at, kind, reason, supersedes_id FROM watchlist_events "
    "WHERE market = ? AND code = ? ORDER BY id ASC"
)


@dataclass(frozen=True, slots=True)
class WatchlistEntry:
    """One instrument currently in the pool, as the view reports it."""

    market: Market
    code: str
    asset_type: AssetType
    name: str | None
    reason: str | None
    since: str
    last_event_id: int


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """The row that was just written — a receipt, not a projection.

    Returned by :func:`append` so the caller does not have to guess the
    timestamp the server chose, and so a client can point at the exact event it
    created without re-reading the log.
    """

    event_id: int
    occurred_at: str
    kind: WatchlistEventKind
    market: Market
    code: str
    reason: str | None
    supersedes_id: int | None


def append(
    connection: sqlite3.Connection,
    event: WatchlistEvent,
    *,
    now: str | None = None,
) -> RecordedEvent:
    """Record one event, creating the instrument first if necessary.

    The instrument is ensured here rather than by the caller so that "the
    instrument exists, then the event refers to it" is one operation. Splitting
    it would leave a foreign-key failure one forgotten call away.

    Must run inside a transaction — this performs two statements.

    Args:
        connection: An open application connection.
        event: A validated event, built by :mod:`alphacouncil.domain.watchlist`.
        now: Timestamp override, for tests.

    Returns:
        The row as written.

    Raises:
        AssetTypeConflictError: The instrument is on file with another type.
    """
    instruments.ensure(connection, event.symbol, now=now)
    stamp = now if now is not None else utc_millis()
    cursor = connection.execute(
        _INSERT,
        (
            stamp,
            event.symbol.market.value,
            event.symbol.code,
            event.kind.value,
            event.reason,
            event.supersedes_id,
        ),
    )
    return RecordedEvent(
        event_id=int(cursor.lastrowid or 0),
        occurred_at=stamp,
        kind=event.kind,
        market=event.symbol.market,
        code=event.symbol.code,
        reason=event.reason,
        supersedes_id=event.supersedes_id,
    )


def current(connection: sqlite3.Connection) -> tuple[WatchlistEntry, ...]:
    """Every instrument currently in the pool, most recently touched first."""
    return tuple(_to_entry(row) for row in connection.execute(_SELECT_CURRENT))


def current_event(connection: sqlite3.Connection, symbol: Symbol) -> WatchlistState | None:
    """The newest event for ``symbol``, or ``None`` when it has never been added.

    Ordered by ``id`` rather than ``occurred_at``: ``id`` is the write order, so
    two events in the same millisecond still have a defined winner.

    Returns a :class:`~alphacouncil.domain.watchlist.WatchlistState` — the domain
    decides what it means; this function only reports what is on disk.
    """
    row = connection.execute(_SELECT_LATEST, (symbol.market.value, symbol.code)).fetchone()
    if row is None:
        return None
    return WatchlistState(event_id=int(row["id"]), kind=WatchlistEventKind(row["kind"]))


def history(connection: sqlite3.Connection, symbol: Symbol) -> tuple[RecordedEvent, ...]:
    """Every event ever recorded for ``symbol``, **oldest first**.

    Ordered by ``id``, not ``occurred_at``: ``id`` is the write order, and the
    whole promise of this log is that the sequence can be read back. Two events
    in the same millisecond are the normal case for a scripted change, and
    sorting them by a millisecond-resolution clock would shuffle the record.

    Ascending rather than descending on purpose. This is not a feed — it is the
    transcript of a relationship, and the interesting thing is how the reason
    *moved*: added → revised → removed → added again. Read newest-first that
    becomes four unrelated rows; read oldest-first it becomes a story, which is
    the only form in which "I have done this before" is visible.

    An instrument that was never followed has no rows, so this returns an empty
    tuple rather than raising. Whether that is an error is the caller's question
    — the domain answers it in
    :func:`alphacouncil.domain.watchlist.require_followed`.
    """
    return tuple(
        RecordedEvent(
            event_id=int(row["id"]),
            occurred_at=row["occurred_at"],
            kind=WatchlistEventKind(row["kind"]),
            market=symbol.market,
            code=symbol.code,
            reason=row["reason"],
            supersedes_id=None if row["supersedes_id"] is None else int(row["supersedes_id"]),
        )
        for row in connection.execute(_SELECT_HISTORY, (symbol.market.value, symbol.code))
    )


def _to_entry(row: sqlite3.Row) -> WatchlistEntry:
    """Decode a view row. Unknown enum values are corruption, not defaults."""
    return WatchlistEntry(
        market=Market(row["market"]),
        code=row["code"],
        asset_type=AssetType(row["asset_type"]),
        name=row["name"],
        reason=row["reason"],
        since=row["occurred_at"],
        last_event_id=int(row["last_event_id"]),
    )
