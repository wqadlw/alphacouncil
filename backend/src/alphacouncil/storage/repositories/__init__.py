"""Repositories: the only code that speaks SQL on the application's behalf.

Each module here owns one table (or one table and its view) and exposes plain
Python values — no ``sqlite3.Row`` ever leaves this package, so a change to a
column name stops at the repository instead of reaching the API and the tests.

Two rules hold across all of them:

* **No business rules.** Validation belongs to :mod:`alphacouncil.domain`. A
  repository may only refuse what the schema refuses, plus what would otherwise
  be a silent lie (see :func:`~alphacouncil.storage.repositories.instruments.ensure`).
* **Transactions belong to the caller.** A repository function performs one
  logical operation; when an operation needs two statements to be atomic, it is
  the *caller's* transaction that makes them so, because only the caller knows
  where the operation ends.
"""

from __future__ import annotations

__all__ = ["instruments", "watchlist"]
