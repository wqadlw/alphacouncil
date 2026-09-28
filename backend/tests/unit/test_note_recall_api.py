"""The note recall queue over HTTP (spec 028).

Two of these are about things that would be **quietly wrong** rather than broken:

* ``test_the_due_route_is_not_captured_by_the_note_id_route`` — FastAPI matches in
  declaration order, so registering ``/due`` after ``/{note_id}`` makes the queue
  answer with a 404 about a note whose id is "due". The feature would look absent
  rather than broken, which is the worst way for it to fail.
* ``test_the_due_route_carries_no_count`` — the product forbids showing how much
  of a queue is left, and a list endpoint has no natural place to put one, so
  nothing pins it. Adding ``{"items": [...], "remaining": 7}`` later would be a
  one-line change and would break nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app

BASE = "/api/v1/notes"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _write(client: TestClient, title: str = "一条笔记", body: str = "正文") -> str:
    response = client.post(BASE, json={"title": title, "body": body})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _enrol(client: TestClient, note_id: str) -> dict[str, Any]:
    response = client.post(f"{BASE}/{note_id}/schedule")
    assert response.status_code == 200, response.text
    parsed: dict[str, Any] = response.json()
    return parsed


# ── the queue ───────────────────────────────────────────────────────────────


class TestTheQueue:
    def test_the_due_route_is_not_captured_by_the_note_id_route(
        self, client: TestClient
    ) -> None:
        """⭐ FastAPI matches in declaration order.

        Registered after `/{note_id}`, this answers 404 with a message about a note
        called "due" — so the whole feature would look *absent* rather than
        broken, and no error would point at the cause.
        """
        response = client.get(f"{BASE}/due")
        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_the_due_route_carries_no_count(self, client: TestClient) -> None:
        """⭐ No count, anywhere in the payload.

        「一句陈述，无推送、无红点、无催促词」 — and a length is the one number a
        reader could start trying to clear. The endpoint returns a bare list, so
        there is no field for one to hide in.
        """
        _enrol(client, _write(client))
        payload = client.get(f"{BASE}/due").json()
        assert isinstance(payload, list)
        assert all(isinstance(item, dict) for item in payload)
        for item in payload:
            assert not any(
                key in item for key in ("remaining", "count", "total", "due_count")
            )

    def test_an_empty_queue_is_an_empty_list(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/due").json() == []

    def test_an_enrolled_note_is_immediately_due(self, client: TestClient) -> None:
        """The reader asked for it now."""
        note_id = _write(client)
        _enrol(client, note_id)
        found = client.get(f"{BASE}/due").json()
        assert [item["note_id"] for item in found] == [note_id]

    def test_a_note_that_was_never_asked_for_is_not_in_the_queue(
        self, client: TestClient
    ) -> None:
        """⭐ Writing a note must not queue it — see the module docstring."""
        _write(client)
        assert client.get(f"{BASE}/due").json() == []

    def test_the_limit_is_bounded(self, client: TestClient) -> None:
        assert client.get(f"{BASE}/due", params={"limit": 0}).status_code == 422
        assert client.get(f"{BASE}/due", params={"limit": 500}).status_code == 422


# ── enrolling ───────────────────────────────────────────────────────────────


class TestEnrolling:
    def test_a_note_can_be_queued(self, client: TestClient) -> None:
        note_id = _write(client)
        schedule = _enrol(client, note_id)
        assert schedule["note_id"] == note_id
        assert schedule["state"] == "learning"

    def test_enrolling_twice_is_refused_with_its_own_code(
        self, client: TestClient
    ) -> None:
        note_id = _write(client)
        _enrol(client, note_id)
        response = client.post(f"{BASE}/{note_id}/schedule")
        assert response.status_code == 400
        assert response.json()["code"] == "NOTE_ALREADY_SCHEDULED"

    def test_a_missing_note_cannot_be_queued(self, client: TestClient) -> None:
        """404, because the note is what is missing.

        ⭐ A mutation that turned this into a 500 left the suite green, and the
        reason is worth keeping: the guard written for it was **dead**. It read
        ``if not repository.get_by_id(...)``, but `get_by_id` *raises* rather than
        returning an empty row, so the domain handler answered 400 and the 404
        branch never ran. A mutation that keeps passing because its target cannot
        execute is a stronger signal than a failing test — it says a guard is
        decorative.
        """
        response = client.post(f"{BASE}/note_9999999999999/schedule")
        assert response.status_code == 404

    def test_the_schedule_of_an_unqueued_note_is_a_404(
        self, client: TestClient
    ) -> None:
        """A 404, and this module's 404s carry `detail`, not the coded envelope.

        The asymmetry is inherited, not chosen: a **400** domain refusal goes
        through the coded envelope so a client can tell which rule broke, while a
        **404** is `HTTPException(detail=...)` — FastAPI's default, and what
        `cards.py` already does. Unifying them is its own piece of work; until then
        the test states which shape it is reading rather than asserting one the
        module does not produce.
        """
        note_id = _write(client)
        response = client.get(f"{BASE}/{note_id}/schedule")
        assert response.status_code == 404
        assert note_id in response.json()["detail"]


# ── reviewing ───────────────────────────────────────────────────────────────


class TestReviewing:
    def test_a_rating_moves_the_schedule(self, client: TestClient) -> None:
        note_id = _write(client)
        before = _enrol(client, note_id)["due_at"]

        response = client.post(f"{BASE}/{note_id}/review", json={"rating": "good"})
        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "reviewed"
        assert response.json()["rating"] == "good"

        # ⭐ The claim is that a rating changes *when the note comes back*, so the
        # date has to move **later**. The first draft compared the new date against
        # the empty string, which is true of any string and asserted nothing.
        after = client.get(f"{BASE}/{note_id}/schedule").json()["due_at"]
        assert after > before, f"the schedule did not move: {before} -> {after}"

    @pytest.mark.parametrize("rating", ["again", "hard", "good", "easy"])
    def test_every_rating_is_accepted(
        self, client: TestClient, rating: str
    ) -> None:
        """`again` is a real answer for a note: 「我的想法已经变了」."""
        note_id = _write(client)
        _enrol(client, note_id)
        response = client.post(f"{BASE}/{note_id}/review", json={"rating": rating})
        assert response.status_code == 200
        assert response.json()["rating"] == rating

    def test_an_unknown_rating_is_refused(self, client: TestClient) -> None:
        note_id = _write(client)
        _enrol(client, note_id)
        response = client.post(f"{BASE}/{note_id}/review", json={"rating": "excellent"})
        assert response.status_code == 422

    def test_a_zero_duration_is_refused(self, client: TestClient) -> None:
        """「未成熟留空，绝不填 0」（红线 6） — 0 is not a duration, it is a default."""
        note_id = _write(client)
        _enrol(client, note_id)
        response = client.post(
            f"{BASE}/{note_id}/review", json={"rating": "good", "duration_ms": 0}
        )
        assert response.status_code == 422

    def test_reviewing_a_note_that_is_not_queued_is_refused(
        self, client: TestClient
    ) -> None:
        note_id = _write(client)
        response = client.post(f"{BASE}/{note_id}/review", json={"rating": "good"})
        assert response.status_code == 400
        assert response.json()["code"] == "NOTE_NOT_SCHEDULED"

    def test_a_deferral_pushes_the_date_and_keeps_the_memory(
        self, client: TestClient
    ) -> None:
        note_id = _write(client)
        _enrol(client, note_id)
        before = client.get(f"{BASE}/{note_id}/schedule").json()

        response = client.post(f"{BASE}/{note_id}/defer", json={"days": 14})
        assert response.status_code == 200
        assert response.json()["outcome"] == "deferred"
        assert response.json()["rating"] is None

        after = client.get(f"{BASE}/{note_id}/schedule").json()
        assert after["due_at"] > before["due_at"]
        assert after["state"] == "deferred"

    def test_a_deferral_beyond_the_ceiling_is_refused(self, client: TestClient) -> None:
        note_id = _write(client)
        _enrol(client, note_id)
        response = client.post(f"{BASE}/{note_id}/defer", json={"days": 365})
        assert response.status_code == 422

    def test_a_deferred_note_cannot_be_reviewed(self, client: TestClient) -> None:
        note_id = _write(client)
        _enrol(client, note_id)
        client.post(f"{BASE}/{note_id}/defer", json={})
        response = client.post(f"{BASE}/{note_id}/review", json={"rating": "good"})
        assert response.status_code == 400


# ── ⭐ the reset, over the wire ─────────────────────────────────────────────


class TestARewriteRestartsTheSchedule:
    def test_a_rewrite_resets_the_schedule_and_the_history(
        self, client: TestClient
    ) -> None:
        """⭐⭐ The whole feature, end to end over HTTP.

        Review it once, rewrite the text, and the note must be due again **now**
        with a `reset` row in its history — because the reader has never reviewed
        the new text, and a scheduler that says otherwise is lying.
        """
        note_id = _write(client, "原来的判断", "原来那段话")
        pushed_out = _enrol(client, note_id)["due_at"]
        client.post(f"{BASE}/{note_id}/review", json={"rating": "easy"})
        assert client.get(f"{BASE}/{note_id}/schedule").json()["due_at"] > pushed_out

        response = client.patch(f"{BASE}/{note_id}", json={"body": "完全不同的另一段话"})
        assert response.status_code == 200

        outcomes = [r["outcome"] for r in client.get(f"{BASE}/{note_id}/reviews").json()]
        assert outcomes == ["reviewed", "reset"], outcomes

    def test_a_rewrite_to_an_unqueued_note_records_nothing(
        self, client: TestClient
    ) -> None:
        note_id = _write(client)
        client.patch(f"{BASE}/{note_id}", json={"body": "改了"})
        assert client.get(f"{BASE}/{note_id}/reviews").json() == []
        assert client.get(f"{BASE}/due").json() == []

    def test_the_history_is_readable_and_ordered(self, client: TestClient) -> None:
        note_id = _write(client)
        _enrol(client, note_id)
        client.post(f"{BASE}/{note_id}/review", json={"rating": "good"})
        client.post(f"{BASE}/{note_id}/defer", json={})
        client.patch(f"{BASE}/{note_id}", json={"body": "改了"})

        history = client.get(f"{BASE}/{note_id}/reviews").json()
        assert [row["outcome"] for row in history] == [
            "reviewed",
            "deferred",
            "reset",
        ]
        assert [row["reviewed_at"] for row in history] == sorted(
            row["reviewed_at"] for row in history
        )

