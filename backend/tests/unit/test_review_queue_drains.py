"""A reviewed decision must leave the retrospective queue (regression 0007).

The defect, found by probing rather than by reading: the today page's ``due``
line said "1 条决策" **before and after** the review was recorded, and the count
never moved again.

The cause is a difference between the two queues that is easy to miss. A **card**
leaves the K3 queue because FSRS pushes its ``due_at`` forward when it is
reviewed — the date moves, so the row stops matching ``due_at <= as_of``. A
**decision** has no such mechanism: ``due_at`` is set once, when the user states
when they want to come back, and **nothing ever moves it**. So a reviewed
decision kept matching the query for ever.

Why that matters beyond a wrong number:

- the ``due`` count stops meaning "what is outstanding" and becomes a lifetime
  total, and
- the line says the work is waiting after you have done it — which trains the
  reader to ignore the one line on the default page that is sometimes true. That
  is worse than no line at all, and it is the same failure the today page already
  guards against in the other direction ("count zero → render nothing").

The fix is a filter, and the interesting part is what it implies about a second
review, which this file also pins.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import Settings
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.review import Outcome, Review
from alphacouncil.storage import db, migrate
from alphacouncil.storage.repositories import reviews as repository

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
DUE = NOW - timedelta(days=1)
DECISION = "2026-03-12T09:30:00.000Z"


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


@pytest.fixture
def seeded(connection: sqlite3.Connection) -> str:
    # `utc_millis`, not `isoformat()`: the canonical form is what the schema's
    # identity CHECKs compare against, and a fixture that inserts the wrong shape
    # errors in a way that looks like a *result* — the first version of this file
    # "reproduced" the defect with a fixture that had never inserted anything.
    stamp = utc_millis(NOW)
    connection.execute(
        "INSERT INTO instruments (market, code, name, name_source, name_fetched_at, "
        "asset_type, created_at) VALUES ('sh', '600519', '贵州茅台', 'sina', ?, 'stock', ?)",
        (stamp, stamp),
    )
    connection.execute(
        "INSERT INTO decisions (id, market, code, action, rationale, counter_evidence, "
        "kill_criteria) VALUES (?, 'sh', '600519', 'buy', '渠道库存低位', '批价或回落', '[]')",
        (DECISION,),
    )
    repository.schedule(connection, DECISION, due_at=DUE, now=NOW)
    return DECISION


def _review(connection: sqlite3.Connection, decision_id: str) -> None:
    with db.transaction(connection):
        repository.record(
            connection,
            decision_id,
            Review(
                decision_id=decision_id,
                process_score=4,
                outcome=Outcome.GOOD,
                reviewed_at=NOW,
                due_at=DUE,
            ),
            now=NOW,
        )


class TestTheQueueDrains:
    def test_a_reviewed_decision_is_no_longer_due(
        self, connection: sqlite3.Connection, seeded: str
    ) -> None:
        """The regression itself.

        Written against the repository because that is where the filter belongs,
        and because a defect in a query should be pinned at the query.
        """
        assert len(repository.due_reviews(connection, as_of=NOW)) == 1
        _review(connection, seeded)
        assert repository.due_reviews(connection, as_of=NOW) == ()

    def test_a_half_review_stays_in_the_queue(
        self, connection: sqlite3.Connection, seeded: str
    ) -> None:
        """
        A process score alone is not a completed review, so the decision is still
        waiting — and the queue must still say so.

        This is the case that makes the filter easy to get wrong. "Has a review
        row" is not "is reviewed": a half-review is a legitimate state, and
        leaving the queue on it would hide outstanding work behind a row the
        reader already wrote.
        """
        with db.transaction(connection):
            repository.record(
                connection,
                seeded,
                Review(decision_id=seeded, process_score=3),
                now=NOW,
            )
        assert len(repository.due_reviews(connection, as_of=NOW)) == 1
        assert repository.get_review_state(connection, seeded).reviewed_at is None

    def test_the_state_row_survives_the_queue(
        self, connection: sqlite3.Connection, seeded: str
    ) -> None:
        """
        Leaving the queue must not mean losing the record.

        `decision_review_state` is the single source of truth for "has it been
        reviewed" (ADR-0014), and `reviews` is append-only. So a completed review
        is still fully readable — it is just not *waiting* any more. A fix that
        deleted rows to empty the queue would pass the first test and destroy the
        evidence, which is the mistake ADR-0014 exists to prevent.
        """
        _review(connection, seeded)
        assert repository.has_been_reviewed(connection, seeded) is True
        assert repository.count_reviews(connection, seeded) == 1
        assert repository.latest_review(connection, seeded) is not None


class TestTheTodayCountDrains:
    def test_the_today_line_moves_after_a_review(
        self, seeded: str, database_path: Path
    ) -> None:
        """
        The same defect seen from where the reader sees it.

        The probe that found this printed the count before and after a review and
        got the same number both times, which is what made it a defect rather than
        a design choice. This pins it through the API, because the count on the
        default page is the thing that was wrong.
        """
        settings = Settings(database_path=database_path)
        with TestClient(create_app(settings)) as client:
            body = client.get("/api/v1/today").json()
            assert body["due"]["reviews"]["count"] == 1

            recorded = client.post(
                "/api/v1/decision-reviews",
                json={"decision_id": seeded, "process_score": 4, "outcome": "good"},
            )
            assert recorded.status_code == 201, recorded.text

            after = client.get("/api/v1/today").json()
            assert after["due"]["reviews"]["count"] == 0, (
                "a completed review is still being counted as waiting"
            )

    def test_the_queue_page_empties_after_the_last_review(
        self, seeded: str, database_path: Path
    ) -> None:
        """
        The page's own source of truth, not just the count.

        If the count emptied but the queue did not, the today page would stop
        claiming there is work while the queue page still listed it — the two
        would disagree on the same fact, which is the one outcome worse than
        either being wrong alone.
        """
        settings = Settings(database_path=database_path)
        with TestClient(create_app(settings)) as client:
            due = client.get("/api/v1/decision-reviews/due").json()
            assert len(due) == 1
            decision_id = due[0]["decision_id"]
            client.post(
                "/api/v1/decision-reviews",
                json={"decision_id": decision_id, "process_score": 2, "outcome": "bad"},
            )
            assert client.get("/api/v1/decision-reviews/due").json() == []
