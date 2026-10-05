"""Request-scoped dependencies.

Three dependencies do the work. :func:`database_connection` opens a connection for
the duration of a request and closes it afterwards; :func:`app_settings` reads
the settings the *application instance* was built with, so a test that passes
its own settings actually gets them; :func:`market_data` hands out the one
:class:`~alphacouncil.providers.router.MarketDataRouter` the application built
at startup.

A connection per request is not the cheapest arrangement, and it is chosen
deliberately: SQLite connections are not thread-safe, and the alternative — a
pool or a module-level singleton — buys throughput this product does not need
while adding a class of bug (a connection shared across event-loop threads) that
stays invisible until it does not.

⚠️ **That reasoning was right about the hazard and wrong about where it comes
from.** The per-request connection is not shared *between* requests, but it still
crosses threads *within* one: FastAPI runs a sync generator dependency through
``contextmanager_in_threadpool``, and ``__enter__`` / ``__exit__`` are not
guaranteed to land on the same worker. ``GET .../quote`` was therefore returning
500 about half the time from ``connection.close()`` — observed 2026-09-26, and
invisible to ``TestClient``, which runs everything on one thread. The fix is
``check_same_thread=False`` in :func:`alphacouncil.storage.db._open`, where the
full reasoning is written down. **A per-request connection is still the right
design; it just is not the thread-safety guarantee this paragraph once implied.**

The router is a singleton for the opposite reason. Its health state — which
source answered 403 and for how long it is left alone — is only meaningful if it
accumulates across requests. A router rebuilt per request would forget every
refusal it had learned and walk straight back into the rate limit it was
avoiding (constitution 7.8: external calls go through one entry point).

Writes wrap themselves in :func:`alphacouncil.storage.db.transaction`. That is
the route's decision rather than the dependency's, because only the route knows
how many statements one user action covers.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from alphacouncil.core.config import Settings
from alphacouncil.providers.router import MarketDataRouter
from alphacouncil.storage.db import connect


def app_settings(request: Request) -> Settings:
    """The settings the running application was created with."""
    settings: Settings = request.app.state.settings
    return settings


def database_connection(request: Request) -> Iterator[sqlite3.Connection]:
    """Yield an application connection, closing it when the request ends."""
    connection = connect(app_settings(request).database_path)
    try:
        yield connection
    finally:
        connection.close()


def market_data(request: Request) -> MarketDataRouter:
    """The application's market-data router.

    Read off ``app.state`` rather than built here so a test can substitute a
    stub and exercise the four data states without a network — which is the
    only way the ``no_data`` / ``error`` / ``unavailable`` branches get covered
    at all, since no live source will produce them on demand.
    """
    router: MarketDataRouter = request.app.state.market_data
    return router


#: Annotate a route parameter with this to receive a connection.
DatabaseConnection = Annotated[sqlite3.Connection, Depends(database_connection)]

#: Annotate a route parameter with this to receive the market-data router.
MarketData = Annotated[MarketDataRouter, Depends(market_data)]

#: ⭐ Annotate a route parameter with this to receive the settings **this app was built
#: with** — from ``app.state``, not from a second ``get_settings()`` call.
#: ⭐ That distinction is ``F-246``: one fact with two resolvers is a fact that can differ
#: from itself, and the reader would be told which library they are looking at by a lookup
#: that is not the one serving the data. Added for spec 057 (``is_demo``).
Settings_ = Annotated[Settings, Depends(app_settings)]
