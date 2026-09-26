"""Storage layer: SQLite connection management and schema migrations.

The layer owns the database file and its schema. Per constitution 7.5 it does
**not** own business rules — those live in :mod:`alphacouncil.domain`, and the
API routes only translate between HTTP and the two.
"""

from __future__ import annotations

__all__ = ["db", "migrate"]
