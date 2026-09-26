"""AlphaCouncil — a practical stock-market knowledge management system.

The package is organised in layers, and the imports only point one way:

- ``core``       configuration, logging, the managed error-code namespace
- ``models``     contracts shared across layers (market data, domain models)
- ``providers``  the only way out to a data source — rate limits, fallback, cache
- ``storage``    the SQLite database and its migrations
- ``domain``     the business rules; no FastAPI, no SQL
- ``api``        the FastAPI application — thin routes over the two above

``core`` imports nothing above it. ``domain`` imports ``core`` and ``models``
but never ``api``, which is what lets the rules be tested without a server and
is why constitution 8.1 asks for 90% coverage there specifically.

The list above is what exists, not what is planned: a layer added to this
docstring before it has a module is a promise the file cannot keep.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
