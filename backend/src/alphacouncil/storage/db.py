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

    ``check_same_thread=False`` is load-bearing and needs its reason written
    down, because it disables a tripwire. The failure it prevents was observed
    in real use on 2026-09-26: ``GET /instruments/{market}/{code}/quote``
    returned **500 about half the time**, with

        sqlite3.ProgrammingError: SQLite objects created in a thread can only
        be used in that same thread.

    raised from ``connection.close()`` in ``api/deps.py``. The cause is not a
    shared connection — it is the opposite. FastAPI runs sync dependencies
    through a threadpool via ``contextmanager_in_threadpool``, and a generator
    dependency's ``__enter__`` and ``__exit__`` **are not guaranteed to land on
    the same worker**: the connection was created on one thread and closed on
    another. ``TestClient`` runs everything on one thread, so no test could see
    it, and it is intermittent by nature — which is the worst shape a defect can
    have.

    Turning the check off is safe *here* for three reasons, and only because of
    all three:

    1. **No connection is shared between requests.** ``api/deps.py`` opens one
       per request; there is no pool and no module-level singleton.
    2. **The threads that touch one connection are sequential, not concurrent.**
       Create, use, close — never two at once.
    3. **SQLite is compiled in serialized threading mode by default**, so even
       concurrent use from several threads is safe at the C level.

    What this flag gives up: if a future change introduces a genuinely shared
    connection, the driver will no longer say so. The constraint therefore lives
    in this docstring and in ``api/deps.py`` rather than in the driver, and
    ``tests/unit/test_storage.py`` pins the cross-thread behaviour so removing
    the flag fails the build instead of failing a user's click.
    """
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
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


def require_open_transaction(connection: sqlite3.Connection, *, operation: str) -> None:
    """Refuse a multi-statement write that was not wrapped by the caller.

    The project convention is that **the caller owns the transaction**: every
    write route in ``api/routes/`` opens one with :func:`transaction`, because a
    repository call may need to sit inside a larger unit of work (a read, then a
    write, then a read).

    That convention has a cost, and this function is the cost being paid out
    loud: a repository method that mutates two tables **cannot be atomic on its
    own**, and nothing about ``connection.execute(a); connection.execute(b)`` on
    an autocommit connection says so. Called outside a transaction, the two
    statements are two independent commits — the card ends up ``converged`` with
    no record of why, and ``card_events`` is append-only, so that record can never
    be written afterwards (regression ``0006``).

    So the repository does not open a transaction (that would nest, and
    :func:`transaction` deliberately refuses to) and does not silently proceed
    either. It checks.

    Args:
        connection: The connection the write is about to use.
        operation: What the caller was doing, for the error message.

    Raises:
        RuntimeError: No transaction is open on this connection.
    """
    if not connection.in_transaction:
        msg = (
            f"{operation} writes more than one row and must run inside "
            "`alphacouncil.storage.db.transaction(...)`; the connection is in "
            "autocommit, so the writes would each commit on their own"
        )
        raise RuntimeError(msg)
