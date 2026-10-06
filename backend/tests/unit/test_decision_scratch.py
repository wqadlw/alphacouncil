"""「这条是试验记录」 -- the reader's own mark, and the two places it changes.

Spec 060. The mark exists because of a measured harm: on 2026-10-06 `GET /today`
returned four attention items, all four from test records, and none from the one
decision the reader actually wrote. One of them announced a kill criterion as
crossed. Nothing was wrong with the rule; the rule was reading a record the
reader has since said was a trial.

What these tests hold fixed:

* The mark is an append. Un-marking writes a second row; it never edits or
  removes the first, so "I pressed it and then changed my mind" stays readable.
* State is the last row. Mark, unmark, mark is marked again.
* The mark changes conclusions, not records. The today attention list and the
  retrospective list drop it; the decision list, the instrument page and the
  review history reached by explicit id do not.
* Nothing guesses. The route refuses a decision it cannot find and otherwise
  writes whatever was asked for. It has no opinion about which decisions are
  trials -- that is the reader's to have (red line 15).
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
from alphacouncil.storage import db

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
DUE = (NOW - timedelta(days=1)).isoformat()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database = tmp_path / "alphacouncil.db"
    with TestClient(create_app(Settings(database_path=database))) as c:
        yield c
    del database


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "alphacouncil.db"


def _decision(client: TestClient, code: str = "600519") -> str:
    """A decision with one kill criterion whose as_of has already passed.

    The criterion is what puts the decision on the today page at all, so a test
    that wants to see the exclusion has to give it something due. `as_of` in the
    past rather than the future is the whole difference: on 2026-10-06 the
    reader's one real decision carried `as_of 2026-12-31`, so it was correctly
    absent, and the four attention items on that page all came from test
    records.
    """
    response = client.post(
        "/api/v1/decisions",
        json={
            "ticker": code,
            "action": "buy",
            "rationale": "渠道库存是先行指标",
            "counter_evidence": "动销可能来自投放",
            "kill_criteria": [
                {
                    "metric": "revenue_yoy",
                    "operator": "<",
                    "threshold": 0.0,
                    "as_of": "2026-09-01",
                }
            ],
            "review_due_at": DUE,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _review(client: TestClient, decision_id: str) -> None:
    """A completed review in the quadrant this feature matters most for.

    ``process_score`` 0 with ``outcome`` good is 「the process was wrong and it
    paid out anyway」 -- the quadrant where a test record is most misleading,
    because it looks like the clearest possible evidence about the owner.
    """
    response = client.post(
        "/api/v1/decision-reviews",
        json={"decision_id": decision_id, "process_score": 1, "outcome": "good"},
    )
    assert response.status_code == 201, response.text


def _mark(client: TestClient, decision_id: str, marked: bool) -> dict[str, object]:
    response = client.post(
        f"/api/v1/decisions/{decision_id}/scratch", json={"marked": marked}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _events(database: Path, decision_id: str) -> list[tuple[int, str]]:
    connection = db.connect(database)
    try:
        return [
            (int(r["id"]), str(r["verb"]))
            for r in connection.execute(
                "SELECT id, verb FROM decision_scratch_events "
                "WHERE decision_id = ? ORDER BY id",
                (decision_id,),
            )
        ]
    finally:
        connection.close()


def _attention_ids(client: TestClient) -> set[str]:
    """The decision ids the today page is interrupting the reader about."""
    body = client.get("/api/v1/today").json()
    return {str(item["item"]["decision_id"]) for item in body["attention"]}


class TestTheMarkIsAppendOnly:
    def test_marking_writes_one_row(self, client: TestClient, database: Path) -> None:
        decision_id = _decision(client)
        _mark(client, decision_id, True)
        assert _events(database, decision_id) == [(1, "marked")]

    def test_unmarking_writes_a_second_row_rather_than_removing_the_first(
        self, client: TestClient, database: Path
    ) -> None:
        """The failure this shape exists to prevent: 「I marked it, then changed
        my mind」 turning into 「there is no record that I ever marked it」.

        Overwriting the verb would make the state unreadable and deleting the row
        would erase the act. Both are quieter than an append and both lose the
        thing the log is for.
        """
        decision_id = _decision(client)
        _mark(client, decision_id, True)
        _mark(client, decision_id, False)
        assert _events(database, decision_id) == [(1, "marked"), (2, "unmarked")]

    def test_the_database_refuses_an_edit_of_the_verb(
        self, client: TestClient, database: Path
    ) -> None:
        """The repository appends; the trigger is what actually forbids the rest.

        Without this the rule would be a convention, and conventions about the
        reader's own record have already cost this repo once.
        """
        decision_id = _decision(client)
        _mark(client, decision_id, True)
        connection = db.connect(database)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE decision_scratch_events SET verb = 'unmarked'"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM decision_scratch_events")
        finally:
            connection.rollback()
            connection.close()


class TestTheStateIsTheLastRow:
    def test_a_decision_is_not_scratch_until_it_is_marked(
        self, client: TestClient
    ) -> None:
        decision_id = _decision(client)
        listed = client.get("/api/v1/decisions").json()
        row = next(r for r in listed if r["id"] == decision_id)
        assert row["scratch"] is False

    def test_marking_twice_is_idempotent_in_the_state(
        self, client: TestClient, database: Path
    ) -> None:
        decision_id = _decision(client)
        _mark(client, decision_id, True)
        _mark(client, decision_id, True)
        listed = client.get("/api/v1/decisions").json()
        row = next(r for r in listed if r["id"] == decision_id)
        assert row["scratch"] is True
        # Additive in the record, idempotent in the outcome. Both are deliberate.
        assert len(_events(database, decision_id)) == 2

    def test_mark_then_unmark_then_mark_ends_marked(
        self, client: TestClient, database: Path
    ) -> None:
        decision_id = _decision(client)
        for marked in (True, False, True):
            _mark(client, decision_id, marked)
        assert _events(database, decision_id)[-1][1] == "marked"
        listed = client.get("/api/v1/decisions").json()
        row = next(r for r in listed if r["id"] == decision_id)
        assert row["scratch"] is True

    def test_unmarking_puts_the_decision_back(
        self, client: TestClient
    ) -> None:
        """Latest wins, tested in both directions -- the second half of the
        toggle is the half most likely to be wired one-way.
        """
        decision_id = _decision(client)
        _mark(client, decision_id, True)
        body = _mark(client, decision_id, False)
        assert body["scratch"] is False


class TestTheMarkMovesConclusionsNotRecords:
    def test_a_marked_decision_leaves_the_today_attention_list(
        self, client: TestClient
    ) -> None:
        """Exclusion point one, and the measured harm.

        `GET /today` is the one page the reader opens without choosing to, so a
        test record's kill criterion announced there is an interruption they
        cannot trace back to something they wrote.
        """
        decision_id = _decision(client)
        assert decision_id in _attention_ids(client)
        _mark(client, decision_id, True)
        assert decision_id not in _attention_ids(client)

    def test_an_unmarked_decision_returns_to_the_attention_list(
        self, client: TestClient
    ) -> None:
        decision_id = _decision(client)
        _mark(client, decision_id, True)
        _mark(client, decision_id, False)
        assert decision_id in _attention_ids(client)

    def test_a_marked_decision_stays_in_the_decision_list(
        self, client: TestClient
    ) -> None:
        """Skipped is not hidden. The record is the reader's and stays readable;
        only the conclusions derived from it change.
        """
        decision_id = _decision(client)
        _mark(client, decision_id, True)
        listed = client.get("/api/v1/decisions").json()
        row = next(r for r in listed if r["id"] == decision_id)
        assert row["rationale"] == "渠道库存是先行指标"
        assert row["scratch"] is True

    def test_a_marked_decision_leaves_the_retrospective_list(
        self, client: TestClient
    ) -> None:
        """Exclusion point two. A quadrant is a conclusion about their judgement,
        and the quadrant that matters most here is 「looks wrong but paid out」:
        a test record that happened to gain would otherwise sit there looking
        like the product's clearest evidence that its owner cannot be trusted.
        """
        decision_id = _decision(client)
        _review(client, decision_id)
        recent = client.get("/api/v1/decision-reviews/recent").json()
        assert decision_id in {row["decision_id"] for row in recent}
        _mark(client, decision_id, True)
        recent = client.get("/api/v1/decision-reviews/recent").json()
        assert decision_id not in {row["decision_id"] for row in recent}

    def test_the_review_history_reached_by_id_is_not_filtered(
        self, client: TestClient
    ) -> None:
        """The boundary of the boundary. `reviews_for` keeps answering.

        Filtering it would mean that marking a decision as a trial silently
        removes the reviews they wrote about it -- which is deleting their
        record, and the one thing this mark must never do.
        """
        decision_id = _decision(client)
        _review(client, decision_id)
        _mark(client, decision_id, True)
        history = client.get(f"/api/v1/decision-reviews/{decision_id}/reviews")
        assert history.status_code == 200, history.text
        assert len(history.json()) == 1


class TestTheRouteDoesNotGuess:
    def test_an_unknown_decision_is_a_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/decisions/2026-01-01T00:00:00.000Z/scratch",
            json={"marked": True},
        )
        assert response.status_code == 404, response.text

    def test_the_request_carries_nothing_but_the_mark(
        self, client: TestClient
    ) -> None:
        """`extra="forbid"` on the request.

        The temptation on an endpoint like this is to accept a `reason`, or a
        `tag`, or a `confidence`. Each of those is a way for the product to end
        up grading the reader's own records, which red line 11 refuses, and the
        cheapest place to stop it is the shape of the request.
        """
        decision_id = _decision(client)
        response = client.post(
            f"/api/v1/decisions/{decision_id}/scratch",
            json={"marked": True, "reason": "评测用"},
        )
        assert response.status_code == 422, response.text
