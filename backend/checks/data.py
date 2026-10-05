"""Opening the reader's own database, read-only.

# Why this module exists

`.ai/checks/data/README.md` draws the line the static side never had to cross:

| | `data/` | `static/` |
|---|---|---|
| what it looks at | **数据内容** | 源码 |
| when it can find a defect | after the data is written | before the code is |

⭐ **That difference is the whole reason `data/` is a second kind of check** ⭐ — and it is
# also why this module's first job is to refuse to write.

# Read-only is a connection string, not a promise

Every rule here opens ``file:...?mode=ro``. ⭐ The README's rule 4（「`AUTO` 修复必须可逆」）
implies that some checks may repair, ⭐ **and the first batch has none** ⭐ — ⭐ so the batch
must not be able to, ⭐ whatever a future edit to a rule's SQL might intend.

# Which database

⭐ **The configured one, not a temporary one.** ⭐ `S-16` and `S-17` build a throwaway
# database, ⭐ and that is right for them ⭐ — ⭐ they read a *schema*, which pydantic
# regenerates. ⭐ A data check that ran against a fresh database would report zero for all
# twenty-four, ⭐ and the README's rule 1 requires an empty database to pass ⭐ — ⭐ **so a
# temporary one would make every check vacuous.**

⇒ ⭐ **and that is the reason `dev.py check` now reads the reader's rows.** ⭐ It is read-only,
⭐ and the gate says so in the README, ⭐ because a gate that silently opens your database is
# worse than one that is absent.

# Why an absent database is a skip

`dev.py:288-292` ⭐ — 「a skipped gate is not a passing gate」 ⭐ — ⭐ so a reader who has not
installed the product gets `skipped`, ⭐ which `--strict` turns into exit 1, ⭐ rather than a
green run that means nothing.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

NO_DATABASE = (
    "no configured database to read — a data check that cannot see the reader's rows has "
    "nothing to say, and saying nothing is not passing (dev.py:288-292)"
)


def configured_path() -> Path | None:
    """Where the product reads its data from, or ``None`` when there is none.

    ⭐ Resolved through ``Settings`` ⭐ rather than by guessing at the platform's app-data
    directory, ⭐ because a second copy of that path is the two-homes failure this repository
    already has three entries about ⭐ — ⭐ and `api/errors.py:731` is not the place to look
    for the truth, ⭐ the settings object is.
    """
    # ⭐⭐ **Through `get_settings()`, not a fresh `Settings()`.** ⭐ ⭐ Measured 2026-10-05:
    # ⭐⭐ `get_settings()` is `lru_cache(maxsize=1)` ⭐ ⭐ so the *first* call in a process wins
    # ⭐⭐ and a fresh `Settings()` reads the environment ⭐ ⭐ ⇒ **the two can name different
    # ⭐⭐ files.** ⭐ `tests/conftest.py:65` clears the cache ⭐ ⭐ which is the only reason a
    # ⭐⭐ test could move the variable ⭐ ⭐ ⭐ and a first draft of this function built its own
    # ⭐⭐ `Settings()` ⭐⭐ so it read the *new* value while the application read the old one.
    # ⭐⭐ ⭐ That is not a theoretical split: ⭐⭐ it put a criterion out of the reader's own
    # ⭐⭐ database inside a unit-test assertion. ⭐⭐ `F-233`'s shape ⭐⭐ ⭐ with real rows on
    # ⭐⭐ the other end.  ⇒ **One resolver, the application's.**
    try:
        from alphacouncil.core.config import get_settings
    except ImportError:
        return None
    path = Path(get_settings().database_path)
    return path if path.is_file() else None


@contextmanager
def readonly() -> Iterator[tuple[sqlite3.Connection | None, str | None]]:
    """Yield ``(connection, skip_reason)`` ⭐ — exactly one of the two is not ``None``.

    ⭐ The pair rather than an exception ⭐ because a missing database is **not a defect**
    ⭐ and reporting it as one would train the reader to ignore this gate. ⭐ It is the gate
    # having nothing to look at, ⭐ and the framework has a word for that: ``skipped``.
    # """
    path = configured_path()
    if path is None:
        yield None, NO_DATABASE
        return
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        # ⭐⭐ **Opening is not a fact.** ⭐ SQLite defers reading the header ⭐ ⭐ so a file
        # that is not a database connects happily ⭐ ⭐ and raises on the first query ⭐ ⭐
        # ⭐ which would be *outside* the `except` below ⭐ ⭐ and outside the rule's own
        # ⭐ `except` ⭐ ⭐ landing in `crashed` ⭐ ⭐ a different line of the summary from
        # ⭐ `findings`. ⭐ One statement makes "it opened" mean "it answered".
        con.execute("select 1").fetchone()
    except sqlite3.Error as exc:  # a path that exists but will not open is a fact to report
        # ⭐⭐ **And the handle has to go.** ⭐ The `finally` that closes it is *below* this
        # `except` ⭐ ⭐ so returning from here leaked the connection ⭐ ⭐ and `pytest` said so
        # ⭐ ⭐ in a `PytestUnraisableExceptionWarning` printed **below the summary line** ⭐ ⭐
        # ⭐ after 「37 passed」 ⭐ ⭐ where nobody looks ⭐ ⭐ while the exit code said 1. ⭐
        # ⭐ The exit code is the only reason this was found ⭐ ⭐ and that is the argument for
        # ⭐ `make check` being the definition of done ⭐ ⭐ wearing a bug.
        con.close()
        yield None, f"the configured database at {path} would not open: {exc}"
        return
    try:
        yield con, None
    finally:
        con.close()


def has_table(con: sqlite3.Connection, table: str) -> bool:
    """Whether ``table`` exists ⭐ — asked as a query rather than assumed, ⭐ because eleven
    of the twenty-four declared checks name a table or column that does not exist, ⭐ and a
    rule that crashed on that would be indistinguishable from a rule that passed."""
    row = con.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?", (table,)
    ).fetchone()
    return row is not None


def count(con: sqlite3.Connection, sql: str) -> int:
    """Run a counting query ⭐ — the only shape a data check needs, ⭐ so the rule bodies stay
    one line of SQL each and the interesting part stays in the docstrings."""
    return int(con.execute(sql).fetchone()[0])
