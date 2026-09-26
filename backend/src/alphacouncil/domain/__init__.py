"""Domain layer: the business rules, with nothing to do with HTTP or SQL.

Per constitution 7.5 the layers are separated so that a rule survives a change
of host: ``domain`` holds the decisions, ``storage`` holds the database, ``api``
holds the translation. Nothing here imports FastAPI or SQLAlchemy, which is what
makes this layer the cheapest one to test and therefore the one expected to be
tested hardest — constitution 8.1 sets its coverage floor at 90%.

- :mod:`~alphacouncil.domain.instrument` — text to instrument, refusing to guess
- :mod:`~alphacouncil.domain.watchlist` — what makes a watchlist event legal
"""

from __future__ import annotations

__all__ = ["instrument", "watchlist"]
