"""API tests for the review queue (K3, spec 019).

The test that matters most is
:class:`TestTheResponseCarriesNoScore`. It enumerates the response model's
fields and fails if any of them names a grade the user is given — which is how
red line 9 stops being a sentence in a design document and becomes a property of
the contract. A comment saying "no scores here" is a promise; a field list is a
check.

``test_a_client_supplied_duration_is_rejected`` is the matching one for red line
11: a duration the user types in is a duration they performed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import Settings
from alphacouncil.storage import db

NOW = "2026-09-28T00:00:00.000Z"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_path=tmp_path / "alphacouncil.db")
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _card(client: TestClient, *, code: str = "600519", index: int = 0) -> str:
    """Create a card through the API and return its id."""
    response = client.post(
        "/api/v1/cards",
        json={
            "content": f"渠道库存是白酒的先行指标（第 {index} 条）",
            "claim_type": "supporting",
            "source_url": f"https://example.com/report/{code}/{index}",
            "source_title": "白酒渠道深度调研",
            "symbols": [code],
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _enrolled(client: TestClient, **kwargs: Any) -> str:
    card_id = _card(client, **kwargs)
    response = client.post(f"/api/v1/cards/{card_id}/schedule")
    assert response.status_code == 201, response.text
    return card_id


class TestEnrolment:
    def test_a_new_card_is_immediately_due(self, client: TestClient) -> None:
        card_id = _card(client)
        created = client.post(f"/api/v1/cards/{card_id}/schedule")
        assert created.status_code == 201
        due = client.get("/api/v1/review/due")
        assert [row["card_id"] for row in due.json()] == [card_id]

    def test_enrolling_twice_is_409(self, client: TestClient) -> None:
        card_id = _card(client)
        client.post(f"/api/v1/cards/{card_id}/schedule")
        again = client.post(f"/api/v1/cards/{card_id}/schedule")
        assert again.status_code == 409
        assert again.json()["code"] == "CARD_ALREADY_SCHEDULED"

    def test_enrolling_a_missing_card_is_404(self, client: TestClient) -> None:
        response = client.post("/api/v1/cards/card_9999999999999/schedule")
        assert response.status_code == 404


class TestReadingASchedule:
    """`GET /cards/{id}/schedule` — spec 048.

    ⭐ **This endpoint is why the queue was reachable at all.** Measured on
    2026-10-02: `POST` existed with **zero callers**, and the interface could not
    tell 「already enrolled」 from 「never enrolled」 — nor infer it from
    `GET /review/due`, which returns only what is *due*, so a card scheduled for
    next week is absent from it.

    ⚠️ **The not-scheduled case is 409, and the assertion below is the reason the
    number is worth pinning.** `GET /notes/{id}/schedule` answers **404** for the
    same state; copying the note's contract was this spec's first move, and
    `api/errors.py` already decided the card's:

        # K3. Both are 409 rather than 404 on purpose: the *card* exists, and what
        # conflicts is the request with the card's scheduling state. Answering 404
        # would tell the user their card is gone when it is sitting right there.
    """

    def test_not_enrolled_is_409_and_says_which_code(self, client: TestClient) -> None:
        card_id = _card(client)
        response = client.get(f"/api/v1/cards/{card_id}/schedule")
        assert response.status_code == 409
        assert response.json()["code"] == "CARD_NOT_SCHEDULED"

    def test_enrolled_reads_back_the_same_shape_the_post_returned(self, client: TestClient) -> None:
        card_id = _card(client)
        created = client.post(f"/api/v1/cards/{card_id}/schedule")
        assert created.status_code == 201

        read = client.get(f"/api/v1/cards/{card_id}/schedule")
        assert read.status_code == 200
        # ⭐ **The read must equal the write, byte for byte on the fields the client
        # renders.** A read that reshapes the answer would mean the interface has two
        # shapes to reconcile, and the second one would be discovered by a screenshot.
        assert read.json() == created.json()

    def test_a_missing_card_is_404_which_is_a_different_problem_from_409(
        self, client: TestClient
    ) -> None:
        # ⭐ **409 and 404 must stay apart**, and this is the test that says why:
        # 409 is an ordinary empty state (the button should be offered), 404 means
        # the thing the reader is looking at does not exist. Collapsing them would let
        # a broken link show a working 「加入复习」 button.
        response = client.get("/api/v1/cards/card_9999999999999/schedule")
        assert response.status_code == 404
        assert response.json()["code"] == "CARD_NOT_FOUND"

    def test_reading_does_not_enqueue_anything(self, client: TestClient) -> None:
        # ⭐ **A read with a side effect would be the worst kind of bug here**, because
        # the interface calls it on every card it renders — so every card would
        # enrol itself and the queue would fill with things nobody asked for.
        _card(client)
        assert client.get("/api/v1/review/due").json() == []
        before = client.get("/api/v1/cards").json()
        _card(client, index=1)
        client.get("/api/v1/review/due")
        assert client.get("/api/v1/cards").json() != before  # sanity: two cards now
        assert client.get("/api/v1/review/due").json() == []

    def test_the_due_route_is_not_shadowed_by_the_card_route(
        self, client: TestClient
    ) -> None:
        """`/api/v1/cards/{card_id}` would otherwise answer "no card called due"."""
        response = client.get("/api/v1/review/due")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestTheQueue:
    def test_an_unscheduled_card_is_absent(self, client: TestClient) -> None:
        _card(client)
        assert client.get("/api/v1/review/due").json() == []

    def test_as_of_is_a_parameter_not_a_clock_reading(self, client: TestClient) -> None:
        """The same question asked twice gets the same answer."""
        _enrolled(client)
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        assert len(client.get("/api/v1/review/due", params={"as_of": future}).json()) == 1
        assert client.get("/api/v1/review/due", params={"as_of": past}).json() == []

    def test_the_limit_is_honoured(self, client: TestClient) -> None:
        for index in range(3):
            _enrolled(client, index=index)
        assert len(client.get("/api/v1/review/due", params={"limit": 2}).json()) == 2

    def test_a_nonsense_limit_is_422(self, client: TestClient) -> None:
        assert client.get("/api/v1/review/due", params={"limit": 0}).status_code == 422


class TestTheResponseCarriesNoScore:
    """Red line 9 as a property of the contract, not of the styling."""

    def test_schedule_read_names_no_grade(self) -> None:
        from alphacouncil.api.routes.reviews import ScheduleRead

        fields = set(ScheduleRead.model_fields)
        assert fields == {"card_id", "state", "due_at"}
        forbidden = {"retrievability", "stability", "mastery", "score", "accuracy"}
        assert not fields & forbidden

    def test_the_receipt_names_no_grade(self) -> None:
        from alphacouncil.api.routes.reviews import ReviewReceipt

        fields = set(ReviewReceipt.model_fields)
        assert fields == {"card_id", "outcome", "next_due_at", "state"}
        forbidden = {"retrievability", "stability", "mastery", "score", "streak"}
        assert not fields & forbidden

    def test_a_receipt_after_answering_carries_only_the_new_date(
        self, client: TestClient
    ) -> None:
        card_id = _enrolled(client)
        response = client.post(
            f"/api/v1/review/{card_id}", json={"outcome": "reviewed", "rating": "again"}
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"card_id", "outcome", "next_due_at", "state"}
        # Red line 13: the receipt does not comment on how the user did.
        assert body["outcome"] == "reviewed"


class TestRecordingAReview:
    def test_a_recall_moves_the_card_out_of_the_queue(self, client: TestClient) -> None:
        card_id = _enrolled(client)
        response = client.post(
            f"/api/v1/review/{card_id}", json={"outcome": "reviewed", "rating": "good"}
        )
        assert response.status_code == 200
        assert client.get("/api/v1/review/due").json() == []

    def test_a_recall_without_a_rating_is_422(self, client: TestClient) -> None:
        card_id = _enrolled(client)
        response = client.post(f"/api/v1/review/{card_id}", json={"outcome": "reviewed"})
        assert response.status_code == 422

    def test_a_postponement_with_a_rating_is_422(self, client: TestClient) -> None:
        card_id = _enrolled(client)
        response = client.post(
            f"/api/v1/review/{card_id}",
            json={"outcome": "deferred", "rating": "good"},
        )
        assert response.status_code == 422

    def test_a_postponement_takes_the_card_out_of_the_queue(
        self, client: TestClient
    ) -> None:
        card_id = _enrolled(client)
        response = client.post(f"/api/v1/review/{card_id}", json={"outcome": "deferred"})
        assert response.status_code == 200
        assert response.json()["outcome"] == "deferred"
        assert client.get("/api/v1/review/due").json() == []

    def test_a_postponement_beyond_the_ceiling_is_422(self, client: TestClient) -> None:
        card_id = _enrolled(client)
        response = client.post(
            f"/api/v1/review/{card_id}", json={"outcome": "deferred", "days": 400}
        )
        assert response.status_code == 422

    def test_reviewing_an_unscheduled_card_is_409(self, client: TestClient) -> None:
        """409, not 404: the card exists; the conflict is with its queue state.

        Answering "not found" would tell the user their card is gone when it is
        sitting on the page.
        """
        card_id = _card(client)
        response = client.post(
            f"/api/v1/review/{card_id}", json={"outcome": "reviewed", "rating": "good"}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "CARD_NOT_SCHEDULED"

    def test_reviewing_a_missing_card_is_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/review/card_9999999999999",
            json={"outcome": "reviewed", "rating": "good"},
        )
        assert response.status_code == 404

    def test_an_unknown_field_is_rejected(self, client: TestClient) -> None:
        """S-06's `extra="forbid"`, for the same reason as everywhere else."""
        card_id = _enrolled(client)
        response = client.post(
            f"/api/v1/review/{card_id}",
            json={"outcome": "reviewed", "rating": "good", "mood": "great"},
        )
        assert response.status_code == 422

    def test_a_client_supplied_duration_is_rejected(self, client: TestClient) -> None:
        """Red line 11: a duration you type in is a duration you performed."""
        card_id = _enrolled(client)
        response = client.post(
            f"/api/v1/review/{card_id}",
            json={"outcome": "reviewed", "rating": "good", "duration_ms": 4200},
        )
        assert response.status_code == 422
        assert "duration_ms" in response.text

    def test_there_is_no_way_to_edit_or_delete_a_review(self, client: TestClient) -> None:
        card_id = _enrolled(client)
        for method in ("put", "patch"):
            response = getattr(client, method)(
                f"/api/v1/review/{card_id}", json={"outcome": "reviewed"}
            )
            assert response.status_code == 405, (
                f"{method.upper()} answered {response.status_code}; card_reviews is "
                "append-only, so there must be no verb that can rewrite a past recall"
            )
        # ⭐ Restored 2026-10-05. Inserting the new class split this method in two and
        # orphaned its last line, which is why `client.delete` ended up executing inside a
        # test that takes no `client`. Recorded as `F-251`: **an insertion whose `oldString`
        # ends mid-method will not fail loudly** — the file still parses, and the damage
        # shows up as a confusing error in an unrelated test.
        assert client.delete(f"/api/v1/review/{card_id}").status_code == 405


class TestReadingAReviewHistory:
    """`GET /cards/{id}/reviews` — spec 055.

    ⭐⭐ **The endpoint spec 028 asked for, and spec 055 measured as missing.** Measured on
    2026-10-05 against the **published** OpenAPI table (45 paths): `/api/v1/cards/` carried
    exactly four — the card, `/converge`, `/schedule`, `/verify` — and no history, while
    `GET /api/v1/notes/{note_id}/reviews` existed. ⭐ `scheduling.list_reviews()` had been
    implemented, exported, documented and tested the whole time.

    ⇒ **what was missing was the boundary, not the data.** So the reader could answer
    「我复习过 5 次」 about a note and **could not answer it about a card**.

    ⚠️ Two of the tests below exist to hold a **deliberate divergence** from the note route,
    because "I copied the neighbouring implementation" is the likeliest way this regresses.
    """

    def test_a_card_with_no_history_is_an_empty_list(self, client: TestClient) -> None:
        card_id = _card(client)
        response = client.get(f"/api/v1/cards/{card_id}/reviews")
        assert response.status_code == 200
        assert response.json() == []

    def test_an_enrolled_card_that_was_never_answered_is_still_empty(
        self, client: TestClient
    ) -> None:
        """⭐ **Measured, not assumed** (spec 055 §1.5).

        Enrolment inserts a `card_schedule` row and nothing else, so 「已加入复习」 does not
        imply a history. The interface therefore renders nothing for an empty list rather
        than an empty timeline — and it can only do that if this stays true.
        """
        card_id = _enrolled(client)
        assert client.get(f"/api/v1/cards/{card_id}/reviews").json() == []

    def test_every_interaction_is_listed_oldest_first(self, client: TestClient) -> None:
        """⭐ Order is the whole point: 「我复习过 5 次」 is a claim about a sequence."""
        card_id = _enrolled(client)
        client.post(f"/api/v1/review/{card_id}", json={"outcome": "reviewed", "rating": "hard"})
        client.post(f"/api/v1/review/{card_id}", json={"outcome": "deferred", "days": 7})

        rows = client.get(f"/api/v1/cards/{card_id}/reviews").json()
        assert [row["outcome"] for row in rows] == ["reviewed", "deferred"]
        assert rows[0]["rating"] == "hard"
        assert rows[1]["rating"] is None, "a postponement recalls nothing, so it has no grade"
        assert [row["reviewed_at"] for row in rows] == sorted(row["reviewed_at"] for row in rows)

    def test_a_missing_card_is_404_and_not_an_empty_list(self, client: TestClient) -> None:
        """⚠️⚠️ **The divergence, pinned.**

        `GET /notes/{id}/reviews` does **no existence check** (`routes/notes.py:540`), so a
        note that does not exist answers `200 []`. Copying that here would make
        「no such card」 and 「this card has not been reviewed yet」 the same answer, and the
        interface treats them differently — one is something wrong, the other is an ordinary
        empty state.

        ⇒ The card's contract, not the note's. `GET /cards/{id}/schedule` above already
        answers **409** for the neighbouring state and argues the same distinction.
        """
        response = client.get("/api/v1/cards/card_9999999999999/reviews")
        assert response.status_code == 404, (
            f"answered {response.status_code} with {response.text!r}; a missing card must not "
            "be indistinguishable from a card that simply has no reviews yet"
        )
        assert response.json()["code"] == "CARD_NOT_FOUND"

    def test_the_note_route_really_does_answer_200_for_a_missing_note(
        self, client: TestClient
    ) -> None:
        """⭐ **The control for the test above, and it is why that test is trustworthy.**

        A claim that two endpoints behave differently is worth nothing unless both
        behaviours have been observed. If this test ever goes red because the note route
        was fixed, ⭐ **the note route's docstring and this spec's both have to be updated**
        — the divergence is a decision, and decisions go stale loudly.
        """
        response = client.get("/api/v1/notes/note_9999999999999/reviews")
        assert response.status_code == 200, (
            "the note route no longer answers 200 [] for a missing note; spec 055 §2.2 and "
            "`routes/reviews.py` both record that it does, and one of them is now wrong"
        )
        assert response.json() == []

    def test_the_response_is_published(self, client: TestClient) -> None:
        """⭐ **Reads the schema, not the source — the direct counter-test for §1.2.**

        The measurement that opened this spec walked `app.routes` and reported **zero**
        review routes on an application with eleven, because `app.routes` holds twelve
        `_IncludedRouter` wrappers whose `.path` is the empty string and `getattr(r, "path",
        "")` turns every one into a skip (spec 050's root cause, `F-213`).

        ⇒ A test that asserts on source text would repeat the mistake; only the published
        schema cannot have it.
        """
        from alphacouncil.api.app import create_app

        paths = create_app(Settings()).openapi()["paths"]
        assert "/api/v1/cards/{card_id}/reviews" in paths
        assert list(paths["/api/v1/cards/{card_id}/reviews"]) == ["get"]

    def test_there_is_no_way_to_rewrite_history(self, client: TestClient) -> None:
        """append-only, same as every other review surface in the product."""
        card_id = _enrolled(client)
        client.post(f"/api/v1/review/{card_id}", json={"outcome": "reviewed", "rating": "good"})
        for method in ("post", "put", "patch"):
            response = getattr(client, method)(
                f"/api/v1/cards/{card_id}/reviews", json={"rating": "easy"}
            )
            assert response.status_code == 405, (
                f"{method.upper()} answered {response.status_code}; card_reviews is append-only"
            )
        # ⭐ `delete` takes no `json` kwarg on this httpx build — the same reason the
        # neighbouring test calls it bare. Kept identical rather than "improved", because
        # a rewrite of a working line is a chance to lose it.
        assert client.delete(f"/api/v1/cards/{card_id}/reviews").status_code == 405


class TestTheHistoryCarriesNoScore:
    """Red lines 9 and 13, as properties of the contract rather than of the styling."""

    def test_the_row_names_no_grade(self) -> None:
        from alphacouncil.api.routes.reviews import CardReviewRead

        fields = set(CardReviewRead.model_fields)
        assert fields == {
            "card_id",
            "id",
            "outcome",
            "rating",
            "reviewed_at",
            "duration_ms",
            "from_due_at",
            "to_due_at",
            "from_state",
            "to_state",
        }
        forbidden = {"retrievability", "stability", "mastery", "score", "accuracy", "streak"}
        assert not fields & forbidden

    def test_the_row_carries_no_count_of_past_failures(self, client: TestClient) -> None:
        """⭐ Red line 11: the number of past reviews is a number the reader could climb.

        `GET /review/due` already returns a bare list with a test asserting no count
        (`routes/notes.py:286-288` argues it for notes). A history is the same question.
        """
        card_id = _enrolled(client)
        client.post(f"/api/v1/review/{card_id}", json={"outcome": "reviewed", "rating": "again"})
        row = client.get(f"/api/v1/cards/{card_id}/reviews").json()[0]
        assert not any(
            token in key.lower() for key in row for token in ("count", "total", "times", "streak")
        ), f"a count about the reader appeared in the row: {sorted(row)}"

    def test_duration_is_a_stored_fact_that_this_layer_does_not_render(self) -> None:
        """⭐⚠️ **The first version of this test tried to assert the value end to end and
        could not, and the reason is the design rather than a missing fixture.**

        `POST /review/{id}` answers **422** for a client-supplied `duration_ms` (see
        `test_a_client_supplied_duration_is_rejected` above) — ⭐ so **no row with a
        duration can be created over HTTP at all.** Reaching one would mean reaching past
        the boundary this test is about.

        ⇒ So the honest division of labour is:
          - **the value flows** — proven where it is produced, at the repository
            (`test_scheduling.py::…::test_duration_is_recorded_but_is_not_comparable`,
            which asserts `list_reviews` returns it);
          - **the field exists on the contract** — asserted here;
          - **nobody may submit one** — asserted above.

        ⚠️ I wrote this test three ways before accepting the third. The first two reached
        into `app.state.services`, which does not exist. ⭐ **A test that cannot be written
        the honest way is usually telling you the boundary is in the wrong place** — and
        here the boundary is right, the assertion was not.
        """
        from alphacouncil.api.routes.reviews import CardReviewRead

        assert "duration_ms" in CardReviewRead.model_fields
        annotation = CardReviewRead.model_fields["duration_ms"].annotation
        # `int | None`: a postponement recalls nothing and therefore has no duration
        # (`card_reviews_deferred_has_no_duration_check` in migration 0005).
        assert annotation == int | None


class TestTheLogSurvives:
    def test_the_review_is_in_the_database_afterwards(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        card_id = _enrolled(client)
        client.post(f"/api/v1/review/{card_id}", json={"outcome": "deferred"})
        connection = db.connect(tmp_path / "alphacouncil.db")
        try:
            rows = connection.execute(
                "SELECT outcome, rating FROM card_reviews WHERE card_id = ?", (card_id,)
            ).fetchall()
        finally:
            connection.close()
        assert [(r["outcome"], r["rating"]) for r in rows] == [("deferred", None)]
