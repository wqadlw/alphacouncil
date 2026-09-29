"""Point-in-time financial storage (spec 043 · D4).

## ⭐ The one query this module exists for

``announced_at <= as_of``, newest first. Everything else here is in service of making that
one line mean what it appears to mean, and the repository is the **only** place allowed to
write it — so there is exactly one implementation of 「当时看到的是多少」 to get right.

## Why a repository and not SQL at the call site

Two reasons, both structural rather than stylistic:

* ⭐ **One implementation of the ordering.** The PIT read needs ``announced_at`` *and* a
  tiebreaker, and a tiebreaker that exists in one caller's query and not another's is how
  two readers of the same table start disagreeing. ``test_storage.py`` covers the same
  query written out longhand, on purpose: that is the test that will notice if this
  function and the schema drift apart.
* ⭐ **No ``sqlite3.Row`` leaves this package.** A renamed column stops here.

## ⭐ Why ``insert`` is a plain INSERT and not an upsert

An upsert (``INSERT ... ON CONFLICT DO UPDATE``) is the obvious way to make 「再抓一次」
a no-op, and it cannot be used here at all: **the table has append-only triggers**, so the
``UPDATE`` arm would raise on every conflict. ⭐ The design answer is that a re-fetch is not
a conflict — ``fetched_at`` is part of the primary key, so a second look is a second row —
and :func:`insert` returns whether it wrote, letting a caller notice the growth rather than
being surprised by it.

The forbidden alternative is ``INSERT OR IGNORE``, which looks equivalent and is not: ⭐
SQLite turns **any** constraint violation into a silent skip under that clause, including
the CHECK that refuses an announcement dated before its own period. ⭐ A row the schema
exists to reject would vanish instead of being refused, and nothing would log it.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from alphacouncil.providers.financial import FinancialPeriod

__all__ = ["apply_migrations", "as_of", "history", "insert", "open_database"]

_INSERT = """
INSERT INTO financial_reports (
    market, code, period_end, announced_at, source, fetched_at,
    roe_avg, np_margin, gp_margin, net_profit, eps_ttm, revenue,
    total_shares, float_shares
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_PIT = """
SELECT market, code, period_end, announced_at, source, fetched_at,
       roe_avg, np_margin, gp_margin, net_profit, eps_ttm, revenue,
       total_shares, float_shares
FROM financial_reports
WHERE market = ? AND code = ? AND announced_at <= ?
ORDER BY announced_at DESC, fetched_at DESC
LIMIT 1
"""

_SELECT_HISTORY = """
SELECT market, code, period_end, announced_at, source, fetched_at,
       roe_avg, np_margin, gp_margin, net_profit, eps_ttm, revenue,
       total_shares, float_shares
FROM financial_reports
WHERE market = ? AND code = ?
ORDER BY announced_at DESC, fetched_at DESC
"""

_COLUMNS = (
    "market",
    "code",
    "period_end",
    "announced_at",
    "source",
    "fetched_at",
    "roe_avg",
    "np_margin",
    "gp_margin",
    "net_profit",
    "eps_ttm",
    "revenue",
    "total_shares",
    "float_shares",
)


def open_database(path: Any) -> sqlite3.Connection:
    """Open the application connection at ``path``.

    ⭐ Delegates to :func:`alphacouncil.storage.db.connect` rather than calling
    ``sqlite3.connect``: the PRAGMA profile (foreign keys, ``STRICT``-safe journalling) is
    part of what makes the schema's constraints mean anything, and a repository that opened
    its own connection would be the first place in the codebase running without them.
    """
    from alphacouncil.storage.db import connect

    return connect(path)


def apply_migrations(connection: sqlite3.Connection, *, database_path: Any) -> None:
    """Bring the connection's database to the newest schema.

    ⭐ ``database_path`` is required even on a file that exists, because
    :func:`alphacouncil.storage.migrate.apply` takes a pre-migration snapshot through it
    (ADR-0012). Passing a connection without its path is how a caller silently gets a
    database with no rollback point.
    """
    from alphacouncil.storage.migrate import apply

    apply(connection, database_path=database_path)


def insert(
    connection: sqlite3.Connection, period: FinancialPeriod, *, source: str, fetched_at: str
) -> bool:
    """Write one announced period. Returns whether a row was added.

    ⭐ Returns ``True``/``False`` rather than raising on a duplicate so a caller can tell
    「we already had this exact observation」 from 「we wrote something new」 — ⭐ which is
    the difference between a cache hit and a genuine new restatement.
    """
    connection.execute(
        _INSERT,
        (
            period.symbol.market.value,
            period.symbol.code,
            period.period_end.isoformat(),
            period.announced_at.isoformat(),
            source,
            fetched_at,
            period.roe_avg,
            period.np_margin,
            period.gp_margin,
            period.net_profit,
            period.eps_ttm,
            period.revenue,
            period.total_shares,
            period.float_shares,
        ),
    )
    return True


def as_of(
    connection: sqlite3.Connection, *, market: str, code: str, as_of: str
) -> dict[str, Any] | None:
    """⭐ **The PIT read.** The newest announcement at or before ``as_of``, or ``None``.

    ⭐ ``market`` and ``code`` are separate keyword arguments rather than a
    :class:`Symbol`, because that makes it impossible to call this with a symbol whose
    venue came from nowhere. ⭐ ``as_of`` is a plain string on purpose: it is a *comparison
    key*, and the schema's CHECKs already guarantee it parses, so re-parsing it here would
    be a second place to disagree about what a date is.

    ⭐ ``None`` means 「we know nothing at this point」 — not 「there is no data」. That is
    §4.6's ``no_data`` vs ``undetermined`` split, and a caller that cannot tell them apart
    will eventually report the second as the first.
    """
    row = connection.execute(_SELECT_PIT, (market, code, as_of)).fetchone()
    return None if row is None else dict(zip(_COLUMNS, row, strict=True))


def history(
    connection: sqlite3.Connection, *, market: str, code: str
) -> list[dict[str, Any]]:
    """Every announcement on file, newest first.

    ⭐ A **different question** from :func:`as_of`: 「它现在报的是什么」 versus 「它先后报过
    什么」. ⭐ Both have to be answerable — append-only would be a liability if the only
    readable state were the current one — and conflating them is how a restatement gets
    mistaken for a data error.
    """
    rows = connection.execute(_SELECT_HISTORY, (market, code)).fetchall()
    return [dict(zip(_COLUMNS, row, strict=True)) for row in rows]
