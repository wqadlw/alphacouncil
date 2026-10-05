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


class TestTheReviewHistory:
    """`GET /decision-reviews/{id}/reviews` — spec 056.

    ⭐⭐ **The second half of B3.** Measured 2026-10-05: `reviews.reviews_for()` existed,
    was exported, had tests, and **no route called it**; `GET /{decision_id}` returns
    `latest` only. ⇒ **a decision can be reviewed repeatedly, so the second and later
    reviews left no trace on screen at all.**

    ⭐ **The test that matters most is `test_a_process_score_only_row_is_in_the_history`**,
    because it is the one that would let someone delete the rows red line 5 is about.
    """

    def test_a_decision_nobody_reviewed_is_an_empty_list(self, client: TestClient) -> None:
        decision_id = _decision(client)
        response = client.get(f"/api/v1/decision-reviews/{decision_id}/reviews")
        assert response.status_code == 200
        assert response.json() == []

    def test_a_missing_decision_is_404_and_not_an_empty_list(self, client: TestClient) -> None:
        """⚠️ 404 for 「no such decision」 and 200 ``[]`` for 「nobody reviewed it」 are
        different facts. This mirrors the card side on purpose; the note side answers
        ``200 []`` for both and a test there holds that inconsistency deliberately, so the
        two endpoints cannot be quietly made to agree."""
        response = client.get("/api/v1/decision-reviews/2020-01-01T00:00:00.000Z/reviews")
        assert response.status_code == 404
        assert response.json()["code"] == "DECISION_NOT_FOUND"

    def test_every_review_is_listed_oldest_first(self, client: TestClient) -> None:
        """⭐ Order is the claim: 「这条判断我前后评了三次」 is a statement about a sequence.

        ⚠️ **``PAST_DUE_AT``, not ``DUE_AT``** — the outcome is gated on the decision being
        due, and ``DUE_AT`` is 2026-12-28. ⭐ The first version of this test used it and
        got **409 REVIEW_NOT_DUE** on the third POST, which is the gate working.
        """
        decision_id = _decision(client, review_due_at=PAST_DUE_AT)
        for score in (2, 4):
            assert (
                client.post(
                    "/api/v1/decision-reviews",
                    json={"decision_id": decision_id, "process_score": score},
                ).status_code
                == 201
            )
        assert (
            client.post(
                "/api/v1/decision-reviews",
                json={
                    "decision_id": decision_id,
                    "process_score": 5,
                    "outcome": "good",
                    "note": "批价确实稳住了",
                },
            ).status_code
            == 201
        )

        rows = client.get(f"/api/v1/decision-reviews/{decision_id}/reviews").json()
        assert len(rows) == 3
        assert [row["process_score"] for row in rows] == [2, 4, 5]
        assert [row["reviewed_at"] for row in rows] == sorted(
            row["reviewed_at"] for row in rows
        )

    def test_a_process_score_only_row_is_in_the_history(self, client: TestClient) -> None:
        """⭐⭐ **Red line 5, as a property of the response.**

        Measured: `reviews.record()` gates only the outcome (`reviews.py:340`), so a
        process score may be written repeatedly while the outcome stays blank. ⭐ **A row
        with a score and no outcome is a normal row, not a broken one** — it is the two
        halves of red line 5 being separate facts.

        ⇒ So it is in the response, with the domain's `unknown` judgement.
        ⭐ **Dropping it would invert the red line** — a history that only shows the rows
        which happened to be completed is a history that teaches the reader the two halves
        are one.
        """
        decision_id = _decision(client, review_due_at=DUE_AT)
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 2},
        )

        rows = client.get(f"/api/v1/decision-reviews/{decision_id}/reviews").json()
        assert len(rows) == 1
        assert rows[0]["outcome"] is None, "the outcome is blank and must be sent as blank"
        assert rows[0]["quadrant"] == "unknown", "and the domain, not the route, says so"
        assert rows[0]["process_score"] == 2
        # ⭐ And it carries the domain's one permitted sentence for `unknown`.
        assert rows[0]["guidance"], "a quadrant always has its sentence (spec 021)"

    def test_the_note_is_carried_and_stays_none_when_absent(self, client: TestClient) -> None:
        """The reader's own words, and an **absence** rather than an empty string.

        ⭐ `null` and `""` both render as nothing, so this is not a rendering preference —
        it is that 「他当时写了什么」 and 「他当时什么都没写」 are different answers, and the
        response should be able to tell them apart.
        """
        decision_id = _decision(client, review_due_at=DUE_AT)
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 2},
        )
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 5, "note": " 当时没留话  "},
        )
        rows = client.get(f"/api/v1/decision-reviews/{decision_id}/reviews").json()
        assert rows[0]["note"] is None
        # ⭐ And it is trimmed: the domain strips, so two readers cannot differ by spaces.
        assert rows[1]["note"] == "当时没留话"

    def test_the_judgement_is_computed_here_and_not_by_the_client(self, client: TestClient) -> None:
        """⭐ The quadrant, its process band and its one sentence all come from the domain.

        A client that re-derived a four-quadrant judgement would be a second implementation
        of `domain/review.py::judge` ⭐ — and spec 049 exists because that class of drift is
        invisible until it is wrong. ⇒ Assert the server sent all three.

        ⚠️ ``PAST_DUE_AT``: an outcome cannot be recorded before the decision is due, and a
        bad process plus a good outcome is the only way to reach ``dangerous``.
        """
        decision_id = _decision(client, review_due_at=PAST_DUE_AT)
        client.post(
            "/api/v1/decision-reviews",
            json={
                "decision_id": decision_id,
                "process_score": 1,
                "outcome": "good",
                "note": "过程差但赚到了",
            },
        )
        row = client.get(f"/api/v1/decision-reviews/{decision_id}/reviews").json()[0]
        # ⭐ 坏过程 + 好结果 = the dangerous quadrant, and it is reported plainly.
        assert row["quadrant"] == "dangerous"
        assert row["process"] == "bad"
        assert row["guidance"]

    def test_no_row_carries_a_figure(self, client: TestClient) -> None:
        """Red line 10 in its strongest available form: **nothing was ever stored**, so a
        history of any length cannot leak a profit number. Same argument as
        ``TestTheResponseCarriesNoFigure`` above, applied to a second endpoint."""
        decision_id = _decision(client, review_due_at=PAST_DUE_AT)
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 1, "outcome": "good"},
        )
        row = client.get(f"/api/v1/decision-reviews/{decision_id}/reviews").json()[0]
        banned = {"profit", "pnl", "return", "gain", "yield", "figure", "price", "change"}
        assert not {k for k in row if k.lower() in banned}
        # ⭐ The judgement sentences are checked for digits too — the retrospective page's
        # own assertion (「no digits at all」) is domain-wide, so a digit leaking into the
        # sentence would break that page and this one.
        assert not any(ch.isdigit() for ch in row["guidance"])

    def test_there_is_no_way_to_rewrite_history(self, client: TestClient) -> None:
        decision_id = _decision(client, review_due_at=DUE_AT)
        client.post(
            "/api/v1/decision-reviews",
            json={"decision_id": decision_id, "process_score": 2},
        )
        for method in ("post", "put", "patch"):
            response = getattr(client, method)(
                f"/api/v1/decision-reviews/{decision_id}/reviews",
                json={"process_score": 5},
            )
            assert response.status_code == 405, (
                f"{method.upper()} answered {response.status_code}; reviews is append-only"
            )
        assert (
            client.delete(f"/api/v1/decision-reviews/{decision_id}/reviews").status_code == 405
        )

    def test_the_route_is_published(self) -> None:
        """⭐ Reads the **published schema**, not the source — the counter-test for `F-247`,
        where walking ``app.routes`` reported zero review routes on an application with
        eleven, because twelve ``_IncludedRouter`` wrappers carry an empty ``path``."""
        paths = create_app(Settings()).openapi()["paths"]
        target = "/api/v1/decision-reviews/{decision_id}/reviews"
        assert target in paths
        assert list(paths[target]) == ["get"]

    def test_the_id_route_still_works_and_is_not_shadowed(self, client: TestClient) -> None:
        """⭐⭐ **The path-ordering trap, held open.**

        ``/recent``, ``/due`` and ``/schema/quadrants`` all sit **above** ``/{decision_id}``
        in this file, because FastAPI matches in declaration order and a single-segment id
        route declared first would answer 「没有这条判断：recent」. ⭐ The new route is
        two-segment and so is unaffected — ⭐ **and this test is what makes that a
        measurement rather than an assumption.**

        It also catches the inverse mistake: putting ``/{decision_id}/reviews`` *above*
        ``/recent`` would not break anything today, but the day a two-segment sibling
        appears it would.

        ⚠️ And the id route answers **404** for a decision with no review slot
        (``REVIEW_STATE_MISSING``) ⭐ — measured, because the first version of this test
        omitted ``review_due_at`` and asserted 200 against a decision that had no slot.
        """
        assert client.get("/api/v1/decision-reviews/recent").status_code == 200
        assert client.get("/api/v1/decision-reviews/due").status_code == 200
        assert client.get("/api/v1/decision-reviews/schema/quadrants").status_code == 200
        decision_id = _decision(client, review_due_at=DUE_AT)
        assert client.get(f"/api/v1/decision-reviews/{decision_id}").status_code == 200


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
