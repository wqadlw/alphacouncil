"""SQLite connections — two profiles, because a query and a migration want
opposite things from the database (ADR-0012).

=================  ================  ===========================================
PRAGMA             application       migration
=================  ================  ===========================================
``journal_mode``   ``WAL``           ``WAL``
``synchronous``    ``NORMAL``        ``FULL``
``temp_store``     (default)         ``FILE``
``foreign_keys``   ``ON``            ``ON``
``busy_timeout``   ``5000``          ``5000``
=================  ================  ===========================================

Two of those are load-bearing rather than tuning:

* ``synchronous=FULL`` while migrating trades throughput for the guarantee that
  what survives a power cut is a complete schema, not half of one.
* ``temp_store=FILE`` is a memory bound, not an optimisation. wealthfolio
  measured a million-row ``UPDATE`` peaking at **2,046 MiB** of allocation with
  ``temp_store=MEMORY`` and **76 MiB** with ``FILE``; a ``VACUUM`` peaked at
  **2,571 MiB**. On a desktop that is the difference between finishing and being
  killed by the OS. ⚠️ ``temp_store=DEFAULT`` also resolves to memory in that
  build, so simply *not* setting it is not a safe default.

``foreign_keys`` is per-connection in SQLite and defaults to **off**. Leaving it
off means the ``REFERENCES`` clauses in the schema would be decorative, which is
exactly the "discipline that lives only in a document" the constitution keeps
warning about — so every connection turns it on.

Connections run in autocommit (``isolation_level=None``) and transactions are
explicit via :func:`transaction`. Python's implicit transaction handling only
begins on DML, so a ``SELECT`` followed by a write is not atomic under it; the
watchlist "ensure the instrument, then append the event" operation needs both
statements in one transaction, and saying so out loud is clearer than relying on
driver behaviour.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

__all__ = [
    "connect",
    "connect_for_migration",
    "transaction",
]

#: How long a writer waits for a lock before giving up. The app is single-user,
#: but a second process (a migration, a test) can hold the write lock briefly.
_BUSY_TIMEOUT_MS = 5000

_RUNTIME_PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}",
)

_MIGRATION_PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = FULL",
    "PRAGMA temp_store = FILE",
    f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}",
)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the application connection.

    Args:
        path: Database file, or ``":memory:"`` for a throwaway one. A ``str`` is
            passed through to SQLite untouched — including ``":memory:"``, which
            must not be turned into a file named ``:memory:``.

    Returns:
        A connection in autocommit mode with rows addressable by column name.
    """
    return _open(path, _RUNTIME_PRAGMAS)


def connect_for_migration(path: Path | str) -> sqlite3.Connection:
    """Open a connection configured for schema changes (ADR-0012 rules 5-6)."""
    return _open(path, _MIGRATION_PRAGMAS)


def _open(path: Path | str, pragmas: tuple[str, ...]) -> sqlite3.Connection:
    """Open a connection and apply a PRAGMA profile.

    ``PRAGMA journal_mode`` and ``PRAGMA foreign_keys`` are no-ops inside a
    transaction, so they are applied before any statement can open one.
    """
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    for statement in pragmas:
        connection.execute(statement)
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block in one transaction, rolling back on any exception.

    Nested use is not supported — SQLite has no true nested transactions and
    savepoints would hide a caller's mistake rather than report it.

    Args:
        connection: An autocommit connection from :func:`connect`.

    Yields:
        The same connection, for use inside the ``with`` block.
    """
    connection.execute("BEGIN")
    try:
        yield connection
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")
