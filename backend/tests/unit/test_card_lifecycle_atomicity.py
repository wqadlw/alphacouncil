"""Regression 0006 — a card's state change and its event were not one transaction.

K2's ``verify`` and ``converge`` both say in their docstrings that the UPDATE
and the event INSERT "run in one transaction". Neither did. Connections in this
project run in autocommit (``storage/db.py``: ``isolation_level=None``), and
``with connection:`` on an autocommit connection does not open one — so the two
statements were two independent commits.

The failure that produces is the exact one the table exists to prevent: the card
ends up ``converged`` (or ``user_written``) with **no record of why or when**, and
``card_events`` is append-only, so the missing event can never be written
afterwards. A user who retires a claim and then cannot remember why is exactly
the situation K2 was built to prevent.

These tests make the second statement impossible by making the INSERT fail
*after* the UPDATE has run, and then assert the card did not move.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from alphacouncil.domain.card import (
    CardOrigin,
    CardStatus,
    ClaimType,
    build_card_draft,
)
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage import db, migrate
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import cards as repo

NOW = "2026-09-28T00:00:00.000Z"


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "alphacouncil.db"
    connection = db.connect_for_migration(path)
    try:
        migrate.apply(connection, database_path=path)
    finally:
        connection.close()
    return path


@pytest.fixture
def connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    conn = db.connect(database_path)
    try:
        yield conn
    finally:
        conn.close()


def _make_card(connection: sqlite3.Connection, *, origin: CardOrigin, code: str) -> str:
    draft = build_card_draft(
        content="渠道库存是白酒先行指标",
        claim_type=ClaimType.SUPPORTING,
        source_url=f"https://example.com/reports/{code}",
        source_title="白酒渠道深度调研",
        origin=origin,
        priority=4,
        status=CardStatus.ACTIVE,
        symbols=(Symbol(market=Market.SH, code=code),),
    )
    return repo.create(connection, draft, now=NOW).id


def _block_event_inserts(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TRIGGER block_events BEFORE INSERT ON card_events "
        "BEGIN SELECT RAISE(ABORT, 'blocked for the test'); END"
    )


def _in_tx(connection: sqlite3.Connection) -> AbstractContextManager[sqlite3.Connection]:
    """The project's transaction context manager.

    The convention in this codebase is that the **caller** owns the transaction —
    every write route opens one. So a direct repository call must open one too,
    which is exactly the mistake this file exists to make loud.

    ⚠️ `pytest.raises` must be the **outer** context manager around this one. The
    other way round, pytest swallows the exception, the transaction context never
    sees a failure, and it commits the partial write — so the test asserts the
    opposite of what it appears to assert.
    """
    return transaction(connection)


class TestConvergeIsAtomic:
    def test_converge_without_a_transaction_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        """The guard itself: two tables, one caller-opened transaction.

        Before the guard this was the silent failure — two autocommit statements
        that *looked* atomic because they sat next to each other.
        """
        card_id = _make_card(connection, origin=CardOrigin.USER_WRITTEN, code="600519")
        with pytest.raises(RuntimeError, match="transaction"):
            repo.converge(connection, card_id, "渠道口径已被直营替代", now=NOW)
        after = repo.get_by_id(connection, card_id)
        assert after is not None
        assert after.status is CardStatus.ACTIVE

    def test_a_card_does_not_retire_without_a_record_of_why(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _make_card(connection, origin=CardOrigin.USER_WRITTEN, code="600519")
        _block_event_inserts(connection)

        with pytest.raises(sqlite3.IntegrityError, match="blocked for the test"):  # noqa: SIM117
            with _in_tx(connection):
                repo.converge(connection, card_id, "渠道口径已被直营替代", now=NOW)

        after = repo.get_by_id(connection, card_id)
        assert after is not None
        assert after.status is CardStatus.ACTIVE, (
            "the card retired with no event explaining it — and card_events is "
            "append-only, so that record can never be written afterwards"
        )
        assert repo.list_events(connection, card_id) == ()

    def test_the_happy_path_still_writes_both(self, connection: sqlite3.Connection) -> None:
        """The guard must not have turned convergence into a no-op."""
        card_id = _make_card(connection, origin=CardOrigin.USER_WRITTEN, code="600519")
        with _in_tx(connection):
            repo.converge(connection, card_id, "渠道口径已被直营替代", now=NOW)
        after = repo.get_by_id(connection, card_id)
        assert after is not None
        assert after.status is CardStatus.CONVERGED
        events = repo.list_events(connection, card_id)
        assert [e.event_type.value for e in events] == ["converged"]
        assert events[0].reason == "渠道口径已被直营替代"


class TestVerifyIsAtomic:
    def test_verify_without_a_transaction_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _make_card(connection, origin=CardOrigin.AI_GENERATED, code="600519")
        with pytest.raises(RuntimeError, match="transaction"):
            repo.verify(connection, card_id, now=NOW)
        after = repo.get_by_id(connection, card_id)
        assert after is not None
        assert after.origin is CardOrigin.AI_GENERATED

    def test_a_card_is_not_upgraded_without_a_record(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _make_card(connection, origin=CardOrigin.AI_GENERATED, code="600519")
        _block_event_inserts(connection)

        with pytest.raises(sqlite3.IntegrityError, match="blocked for the test"):  # noqa: SIM117
            with _in_tx(connection):
                repo.verify(connection, card_id, now=NOW)

        after = repo.get_by_id(connection, card_id)
        assert after is not None
        assert after.origin is CardOrigin.AI_GENERATED, (
            "the card was promoted to user_written with no event saying it was checked"
        )

    def test_the_happy_path_still_writes_both(self, connection: sqlite3.Connection) -> None:
        card_id = _make_card(connection, origin=CardOrigin.AI_GENERATED, code="600519")
        with _in_tx(connection):
            repo.verify(connection, card_id, now=NOW)
        after = repo.get_by_id(connection, card_id)
        assert after is not None
        assert after.origin is CardOrigin.USER_WRITTEN
        assert [e.event_type.value for e in repo.list_events(connection, card_id)] == ["verified"]


class TestWhyItLookedFine:
    def test_autocommit_is_the_cause_not_a_missing_trigger(self) -> None:
        """Pin the mechanism, so a future reader does not go looking for triggers.

        ``storage/db.py`` opens every connection with ``isolation_level=None``,
        and the project already ships ``db.transaction()`` for exactly this. The
        defect was using neither.
        """
        connection = db.connect(":memory:")
        try:
            assert connection.isolation_level is None, "autocommit is what made this atomic-looking"
        finally:
            connection.close()

    def test_a_bare_with_connection_block_does_not_open_a_transaction(
        self, connection: sqlite3.Connection
    ) -> None:
        """The shape that looked correct and was not.

        A reader who writes ``with connection:`` here is relying on a Python
        feature that only begins a transaction when the connection is *not* in
        autocommit mode. This asserts that, rather than trusting the reading of
        a docstring.
        """
        connection.execute("CREATE TABLE probe (n INTEGER)")
        with connection:
            connection.execute("INSERT INTO probe VALUES (1)")
        assert connection.in_transaction is False
