"""The decision-review API: what it exposes, and what it must never expose.

Three of these tests exist to hold absences rather than behaviours, which is
unusual and deliberate:

- :class:`TestTheResponseCarriesNoFigure` enumerates the field names on the wire.
  "We didn't add a profit field" is not a property any test enforces by itself.
- :class:`TestTheTwoQueuesCannotBeConfused` asserts the card queue's paths and the
  decision queue's paths are disjoint. They started out one letter apart, which
  is the kind of near-collision that is invisible in review and expensive at 3am.
- :class:`TestTheGuidanceComesFromTheDomain` pins that the dangerous quadrant's
  sentence is *served*, not retyped. A UI-authored version of that warning is one
  careless PR away from congratulating someone for a decision that lost them money
  the next time.
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

NOW = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
DUE_AT = "2026-12-28T00:00:00.000Z"  # a date the tests can also pretend is past
#: ⭐ A due date in the **past**, for the tests that need a *finished* retrospective.
#: The first version reused `DUE_AT` and got `409 REVIEW_NOT_DUE: scoring early is
#: hindsight` — the gate working as designed. A past due date is not a workaround: a
#: retrospective can only be completed once it is due, so this is the normal shape of a
#: finished one. It also makes the `is_due` mutation detectable with no `as_of`
#: gymnastics, because `now >= due_at` holds by construction.
PAST_DUE_AT = "2026-09-01T00:00:00.000Z"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_path=tmp_path / "alphacouncil.db")
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _due_at(as_of: datetime) -> str:
    """An ``as_of`` query value.

    Passed as a ``params`` mapping rather than interpolated into the path, because
    an aware datetime stringifies with a ``+00:00`` suffix and a bare ``+`` in a
    query string decodes to a **space**. Interpolating it produced a 400 that read
    like a malformed request and was nothing of the kind — the same failure shape
    as the missing ``ReviewError`` registration, and worth naming.
    """
    return as_of.isoformat()


def _decision(
    client: TestClient,
    *,
    review_due_at: str | None = None,
    code: str = "600519",
    index: int = 0,
) -> str:
    """Record a decision through the API and return its id.

    Goes through the real endpoint rather than the repository, because the review
    slot is opened by the **route** in the decision's own transaction — seeding
    the database directly would skip the very thing under test.
    """
    payload: dict[str, Any] = {
        "ticker": code,
        "action": "buy",
        "rationale": "渠道库存处于低位，提价能力可持续",
        "counter_evidence": "批价可能因春节压货而短期回落",
        "kill_criteria": [
            {
                "metric": "revenue_yoy",
                "operator": "<",
                "threshold": 0.0,
                "as_of": "2026-12-31",
            }
        ],
    }
    if review_due_at is not None:
        payload["review_due_at"] = review_due_at
    response = client.post("/api/v1/decisions", json=payload)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


class TestTheReviewCommitment:
    def test_a_review_date_opens_a_slot(self, client: TestClient) -> None:
        """The reachability gap spec 020 left open.

        `schedule()` existed with no caller, so a decision could never come round
        no matter what the mechanism could do. The commitment is now part of the
        decision.
        """
        decision_id = _decision(client, review_due_at=DUE_AT)
        state = client.get(f"/api/v1/decision-reviews/{decision_id}")
        assert state.status_code == 200, state.text
        body = state.json()["state"]
        # Compared as an instant, not a string: the wire form is `isoformat()`
        # (`+00:00`), matching the card queue's `ScheduleRead`. Asserting on the
        # exact text would pin a formatting choice that is not the property under
        # test — the property is "this is the date I asked for".
        assert datetime.fromisoformat(body["due_at"]) == datetime.fromisoformat(DUE_AT)
        assert body["is_due"] is False

    def test_omitting_it_means_not_yet_not_a_default(self, client: TestClient) -> None:
        """No review date → no slot, and a 404 that says which thing is missing.

        A decision that was never given a review date has a perfectly good
        answer to "has it been reviewed" — namely that nobody committed to one.
        The system does not invent a 90-day interval (spec 020 §六).
        """
        decision_id = _decision(client)
        state = client.get(f"/api/v1/decision-reviews/{decision_id}")
        assert state.status_code == 404
        assert state.json()["code"] == "REVIEW_STATE_MISSING"

    def test_a_decision_that_was_never_recorded_is_404_too(
        self, client: TestClient
    ) -> None:
        """Two different 404s, because two different things are absent.

        "No such decision" and "that decision has no review slot" call for
        different replies, and a client that cannot tell them apart will send the
        user to the wrong page.
        """
        response = client.get("/api/v1/decision-reviews/2020-01-01T00:00:00.000Z")
        assert response.status_code == 404
        assert response.json()["code"] == "DECISION_NOT_FOUND"

    def test_the_response_carries_the_words_being_graded(
        self, client: TestClient
    ) -> None:
        """The decision's own text comes back with its review state.

        Not convenience: what gets graded is a passage of text that is still on
        the page and cannot be edited, so a client that could render a review
        *without* the text would be grading from memory — the exact hindsight this
        feature exists to prevent.
        """
        decision_id = _decision(client, review_due_at=DUE_AT)
        body = client.get(f"/api/v1/decision-reviews/{decision_id}").json()
        assert body["decision"]["id"] == decision_id
        assert body["decision"]["rationale"] == "渠道库存处于低位，提价能力可持续"
        assert body["decision"]["counter_evidence"]
        assert body["decision"]["kill_criteria"]
        assert body["latest"] is None, "nothing has been reviewed yet"

    def test_the_slot_is_opened_in_the_decisions_own_transaction(
        self, client: TestClient
    ) -> None:
        """A decision that landed without its commitment is a decision that
        silently never comes round — and nothing downstream would notice, because
        the decision looks complete. So the two writes share a transaction.

        Proved by asking for the slot immediately: if the route committed the
        decision and then failed to open the slot, this would be a 404.
        """
        decision_id = _decision(client, review_due_at=DUE_AT)
        assert client.get(f"/api/v1/decision-reviews/{decision_id}").status_code == 200


class TestTheQueue:
    #: Comfortably past ``DUE_AT`` (2026-12-28). The "is it due yet" tests need a
    #: moment after the commitment; using ``now + 1 day`` looks right and is not,
    #: because December is three months out — a test that "passes" for the wrong
    #: reason is worse than one that fails.
    _PAST = datetime(2027, 1, 1, tzinfo=UTC)
    _NEAR_FUTURE = datetime(2026, 10, 1, tzinfo=UTC)

    def test_nothing_is_due_before_the_date(self, client: TestClient) -> None:
        _decision(client, review_due_at=DUE_AT)
        response = client.get(
            "/api/v1/decision-reviews/due",
            params={"as_of": _due_at(self._NEAR_FUTURE)},
        )
        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_a_due_decision_is_listed(self, client: TestClient) -> None:
        decision_id = _decision(client, review_due_at=DUE_AT)
        response = client.get(
            "/api/v1/decision-reviews/due",
            params={"as_of": _due_at(self._PAST)},
        )
        listed = response.json()
        assert [row["decision_id"] for row in listed] == [decision_id]
        assert listed[0]["is_due"] is True

    def test_a_decision_without_a_commitment_is_never_listed(
        self, client: TestClient
    ) -> None:
        """Only what was promised comes round. The queue is not a sweep."""
        _decision(client)
        response = client.get(
            "/api/v1/decision-reviews/due",
            params={"as_of": _due_at(self._PAST)},
        )
        assert response.json() == []

    def test_the_queue_carries_no_score(self, client: TestClient) -> None:
        _decision(client, review_due_at=DUE_AT)
        response = client.get(
            "/api/v1/decision-reviews/due",
            params={"as_of": _due_at(self._PAST)},
        )
        row = response.json()[0]
        assert set(row) == {
            "decision_id",
            "due_at",
            "reviewed_at",
            "is_due",
            "reviews",
        }, "a score on the queue is a number about the user (red lines 9 and 11)"


class TestRecordingAReview:
    def test_a_process_score_alone_is_accepted(self, client: TestClient) -> None:
        """The asymmetry, end to end: the process can be written at any time."""
        decision_id = _decision(client, review_due_at=DUE_AT)
        response = client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 2},
        )
        assert response.status_code == 201, response.text
        # …and it is *not* a completed review. The quadrant stays unknown
        # because "how did it turn out" genuinely has no answer yet.
        assert response.json()["quadrant"] == "unknown"
        assert response.json()["outcome"] is None

    def test_a_half_review_does_not_mark_the_decision_reviewed(
        self, client: TestClient
    ) -> None:
        decision_id = _decision(client, review_due_at=DUE_AT)
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 4},
        )
        state = client.get(f"/api/v1/decision-reviews/{decision_id}").json()
        assert state["state"]["reviewed_at"] is None
        assert state["state"]["reviews"] == 1

    def test_scoring_an_outcome_before_it_is_due_is_409(self, client: TestClient) -> None:
        """The gate, through the wire. 409 not 400: the request was well-formed,
        it conflicts with a state, and the UI needs to say "not due yet"."""
        decision_id = _decision(
            client, review_due_at=(datetime.now(UTC) + timedelta(days=30)).isoformat()
        )
        response = client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 2, "outcome": "good"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "REVIEW_NOT_DUE"

    def test_a_refused_early_outcome_writes_nothing(self, client: TestClient) -> None:
        decision_id = _decision(
            client, review_due_at=(datetime.now(UTC) + timedelta(days=30)).isoformat()
        )
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 2, "outcome": "good"},
        )
        state = client.get(f"/api/v1/decision-reviews/{decision_id}").json()
        assert state["state"]["reviews"] == 0, "a refused write left a row behind"

    def test_reviewing_a_decision_with_no_slot_is_404(self, client: TestClient) -> None:
        decision_id = _decision(client)
        response = client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 3},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "REVIEW_STATE_MISSING"

    def test_a_score_outside_one_to_five_is_422(self, client: TestClient) -> None:
        decision_id = _decision(client, review_due_at=DUE_AT)
        for score in (0, 6):
            response = client.post(
                "/api/v1/decision-reviews",
                json={"decision_id": decision_id, "process_score": score},
            )
            assert response.status_code == 422, score

    def test_a_client_supplied_figure_is_refused_by_name(self, client: TestClient) -> None:
        """`extra="forbid"` on a red line about numbers.

        Silently ignoring a submitted `outcome_figure` would be the wrong failure
        mode here: the client would believe it had recorded something the product
        is built not to hold.
        """
        decision_id = _decision(client, review_due_at=DUE_AT)
        response = client.post(
            "/api/v1/decision-reviews",
            json={
                "decision_id": decision_id,
                "process_score": 2,
                "outcome_figure": 8.2,
            },
        )
        assert response.status_code == 422
        assert "outcome_figure" in response.text


class TestTheResponseCarriesNoFigure:
    """Red line 10 at the interface, held by enumerating names.

    The absence is in the data model (spec 020), so what is left to prove is that
    the API did not put one back on the wire while serialising.
    """

    #: Substrings that would mean a magnitude is being carried. Matched against
    #: lowercased field names, so `outcomeFigure` and `outcome_figure` both trip.
    _FIGURE_WORDS = (
        "figure",
        "return",
        "profit",
        "pnl",
        "gain",
        "loss",
        "pct",
        "percent",
        "amount",
        "price_change",
        "roi",
    )

    def _assert_no_figure(self, payload: Any) -> None:
        names: list[str] = []
        if isinstance(payload, dict):
            names.extend(payload)
            for value in payload.values():
                names.extend(self._names(value))
        elif isinstance(payload, list):
            for item in payload:
                names.extend(self._names(item))
        offenders = [
            name
            for name in names
            if any(word in name.lower() for word in self._FIGURE_WORDS)
        ]
        assert not offenders, f"the response carries a magnitude: {offenders}"

    def _names(self, payload: Any) -> list[str]:
        return list(payload) if isinstance(payload, dict) else []

    def test_a_review_response_has_no_figure(self, client: TestClient) -> None:
        decision_id = _decision(
            client, review_due_at=(datetime.now(UTC) - timedelta(days=1)).isoformat()
        )
        body = client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 2, "outcome": "good"},
        ).json()
        self._assert_no_figure(body)

    def test_the_state_response_has_no_figure(self, client: TestClient) -> None:
        decision_id = _decision(client, review_due_at=DUE_AT)
        self._assert_no_figure(
            client.get(f"/api/v1/decision-reviews/{decision_id}").json()
        )

    def test_the_quadrant_table_has_no_figure(self, client: TestClient) -> None:
        self._assert_no_figure(client.get("/api/v1/decision-reviews/schema/quadrants").json())


class TestTheGuidanceComesFromTheDomain:
    def test_every_quadrant_is_served_with_its_line(self, client: TestClient) -> None:
        rows = client.get("/api/v1/decision-reviews/schema/quadrants").json()
        assert {row["quadrant"] for row in rows} == {
            "repeat",
            "acceptable",
            "dangerous",
            "fix",
            "unknown",
        }
        for row in rows:
            assert row["guidance"], row["quadrant"]

    def test_the_dangerous_quadrant_warns_about_luck(self, client: TestClient) -> None:
        rows = client.get("/api/v1/decision-reviews/schema/quadrants").json()
        dangerous = next(r for r in rows if r["quadrant"] == "dangerous")
        assert "运气" in dangerous["guidance"]

    def test_no_quadrant_line_contains_a_number(self, client: TestClient) -> None:
        """The copy is the one remaining place a magnitude could reappear."""
        for row in client.get("/api/v1/decision-reviews/schema/quadrants").json():
            digits = set("0123456789%") & set(row["guidance"])
            assert not digits, f"{row['quadrant']} mentions {digits}"


class TestTheTwoQueuesCannotBeConfused:
    """One letter apart is not a distinction. These paths must stay disjoint."""

    def test_the_two_queues_have_different_paths(self, tmp_path: Path) -> None:
        """Read from the OpenAPI document, which is the authoritative route table.

        Builds its own app rather than using the ``client`` fixture: a route table
        is fixed at build time, and ``TestClient.app`` is typed as a bare ASGI
        callable, so asking it for ``openapi()`` needs a cast that would hide the
        very thing being asserted.
        """
        settings = Settings(database_path=tmp_path / "routes.db")
        paths = set(create_app(settings).openapi()["paths"])
        card_queue = {p for p in paths if p.startswith("/api/v1/review")}
        decision_queue = {p for p in paths if p.startswith("/api/v1/decision-reviews")}
        assert card_queue, "the card queue vanished"
        assert decision_queue, "the decision queue vanished"
        assert not (card_queue & decision_queue)
        # The specific near-miss this spec exists to prevent.
        assert "/api/v1/reviews/due" not in paths

    def test_the_near_miss_path_is_a_404_not_the_other_queue(
        self, client: TestClient
    ) -> None:
        """A mistyped ``s`` must fail loudly.

        The dangerous version of the collision is not a wrong URL in a browser —
        it is code that asks for ``/reviews`` and receives a **200** carrying the
        card queue, because the two shapes are both "a list of things to look at".
        """
        _decision(client, review_due_at=DUE_AT)
        response = client.get(
            "/api/v1/reviews/due", params={"as_of": _due_at(TestTheQueue._PAST)}
        )
        assert response.status_code == 404, response.text

    def test_each_queue_only_returns_its_own_kind(self, client: TestClient) -> None:
        """A path answering with the *other* queue's rows would be a 200 carrying
        the wrong data — the failure mode that reads as success."""
        _decision(client, review_due_at=DUE_AT)
        params = {"as_of": _due_at(TestTheQueue._PAST)}
        card_rows = client.get("/api/v1/review/due", params=params).json()
        assert card_rows == [], "no cards were enrolled, so this must be empty"
        decision_rows = client.get("/api/v1/decision-reviews/due", params=params).json()
        assert len(decision_rows) == 1
        assert "card_id" not in decision_rows[0]


class TestTheReviewedListOnTheWire:
    """
    ⭐ Every test here exists because a mutation survived **twice**.

    ``"is_due"`` is set in the **route**, so a repository-level test cannot see it —
    and the E2E could not either, because its fixture hardcoded the very value under
    test. ⭐ **The value a fixture supplies and the value it hides are the same value.**

    Why the field is pinned at all: the page picks its branch from it. A reviewed
    decision reported as due gets five score buttons directly above a line saying the
    score can never change, and the lesson composer — which lives in the same branch
    — was unreachable until ``/recent`` existed.
    """

    def test_a_graded_decision_is_served_as_not_due(self, client: TestClient) -> None:
        decision = _decision(client, review_due_at=PAST_DUE_AT)

        # Complete the review, so the decision leaves the due queue and appears in the
        # reviewed one. An outcome is required: a process score alone is a
        # half-review and deliberately keeps the decision in the queue.
        # ⭐ The create route is at the **prefix root**, with `decision_id` in the
        # body. `POST /api/v1/decision-reviews/{id}` is a 405 — the path I invented
        # because the *read* route looks like that, and the rest of this file already
        # had the right one two screens up.
        scored = client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision, "process_score": 2, "outcome": "bad"},
        )
        assert scored.status_code == 201, scored.text

        # Far enough in the future that `as_of >= due_at` would be **true**, so a
        # computed `is_due` would say True here and the mutation would survive.
        recent = client.get(
            "/api/v1/decision-reviews/recent", params={"limit": 5}
        )
        assert recent.status_code == 200, recent.text
        rows = recent.json()
        assert [row["decision_id"] for row in rows] == [decision]
        assert rows[0]["is_due"] is False, (
            "a decision that has been graded has nothing to grade, and this field "
            "picks the page's branch"
        )
        assert rows[0]["reviewed_at"] is not None

    def test_a_due_decision_is_absent_from_the_reviewed_list(self, client: TestClient) -> None:
        """The two lists are disjoint, and that is what makes the other one reachable."""
        _decision(client, review_due_at=PAST_DUE_AT)
        assert client.get("/api/v1/decision-reviews/recent").json() == []

    def test_the_reviewed_list_renders_no_count(self, client: TestClient) -> None:
        """
        ⭐ A **bare array**, no wrapper — the response *shape* is the guarantee.

        A tally of how many retrospectives you have written is a number you can start
        climbing, and red line 11 is explicit that these things do not render. A
        wrapper object with a ``count`` would be a count, whatever the field is
        called, so the assertion is on the type rather than on a key's absence.
        """
        decision = _decision(client, review_due_at=PAST_DUE_AT)
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision, "process_score": 2, "outcome": "bad"},
        )
        body = client.get("/api/v1/decision-reviews/recent").json()
        assert isinstance(body, list)
        assert body and all(isinstance(row, dict) for row in body)
