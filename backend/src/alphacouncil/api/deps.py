"""Request-scoped dependencies.

Two dependencies do the work. :func:`database_connection` opens a connection for
the duration of a request and closes it afterwards; :func:`app_settings` reads
the settings the *application instance* was built with, so a test that passes
its own settings actually gets them.

A connection per request is not the cheapest arrangement, and it is chosen
deliberately: SQLite connections are not thread-safe, and the alternative — a
pool or a module-level singleton — buys throughput this product does not need
while adding a class of bug (a connection shared across event-loop threads) that
stays invisible until it does not.

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


#: Annotate a route parameter with this to receive a connection.
DatabaseConnection = Annotated[sqlite3.Connection, Depends(database_connection)]
