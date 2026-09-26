"""Instrument rows — the table that turns ``(market, code)`` into an identity.

ADR-0017 fixes the primary key, which makes this module the place where "an
instrument exists" is decided. Two properties are easy to lose and are written
down here so a later change has to argue with them:

* **A row is never amended.** :func:`ensure` inserts when the instrument is new
  and *verifies* when it is not. A caller asserting a type that disagrees with
  the stored one has contradicted a fact that has exactly one answer, so it is
  raised rather than settled in either direction: keeping the stored value would
  hide the user's mistake, and taking the new one would rewrite a fact other
  rows may already rest on.
* **The clock is the server's.** ``created_at`` comes from
  :func:`alphacouncil.core.time.utc_millis`; no caller supplies it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.instrument import AssetTypeConflictError
from alphacouncil.models.market import AssetType, Market, Symbol

__all__ = ["InstrumentRow", "ensure", "get"]

_SELECT_ONE = (
    "SELECT market, code, asset_type, name, created_at FROM instruments "
    "WHERE market = ? AND code = ?"
)
_INSERT = "INSERT INTO instruments (market, code, asset_type, created_at) VALUES (?, ?, ?, ?)"


@dataclass(frozen=True, slots=True)
class InstrumentRow:
    """One row of ``instruments``, with the enums already decoded."""

    market: Market
    code: str
    asset_type: AssetType
    name: str | None
    created_at: str


def get(connection: sqlite3.Connection, symbol: Symbol) -> InstrumentRow | None:
    """Read the stored row, or ``None`` when the instrument is unknown."""
    row = connection.execute(_SELECT_ONE, (symbol.market.value, symbol.code)).fetchone()
    return None if row is None else _to_row(row)


def ensure(
    connection: sqlite3.Connection,
    symbol: Symbol,
    *,
    now: str | None = None,
) -> InstrumentRow:
    """Return the stored row for ``symbol``, inserting it when it is new.

    Must run inside a transaction: the read and the possible insert have to be
    atomic, or two callers can both conclude the instrument is missing and one
    of them then fails on the primary key.

    Args:
        connection: An open application connection.
        symbol: The instrument, already validated by
            :func:`alphacouncil.domain.instrument.parse_ticker`.
        now: Creation timestamp override, for tests.

    Returns:
        The row **as stored**. For an instrument that already existed this is
        not the value that was passed in, which is why it is returned rather
        than assumed.

    Raises:
        AssetTypeConflictError: The instrument is on file with another type.
    """
    existing = get(connection, symbol)
    if existing is not None:
        if existing.asset_type is not symbol.asset_type:
            msg = (
                f"{symbol.code}.{symbol.market.value.upper()} is already on file as "
                f"{existing.asset_type.value}, not {symbol.asset_type.value}"
            )
            raise AssetTypeConflictError(msg)
        return existing

    stamp = now if now is not None else utc_millis()
    connection.execute(
        _INSERT,
        (symbol.market.value, symbol.code, symbol.asset_type.value, stamp),
    )
    return InstrumentRow(symbol.market, symbol.code, symbol.asset_type, None, stamp)


def _to_row(row: sqlite3.Row) -> InstrumentRow:
    """Decode a row into enums. An unknown value is a corrupt row, not a default."""
    return InstrumentRow(
        market=Market(row["market"]),
        code=row["code"],
        asset_type=AssetType(row["asset_type"]),
        name=row["name"],
        created_at=row["created_at"],
    )
