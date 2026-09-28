"""The today page's ``due`` block — the product coming to find the reader.

Red line 10 sat at ``partial`` for one reason: `项目总纲` §2.1 says the product must
go and find the reader at the moments they will not come, and nothing did. This
block is the answer, so the interesting tests are the ones about **what it is
allowed to contain**.

The boundary, stated once so the tests can cite it:

    a statement about something the reader already committed to
    versus a suggestion about something they might want.

The first is a fact and the only kind of interruption red line 8 permits. The
second is a recommendation, which is what that red line forbids. So ``due`` may
carry counts — and must carry **nothing that could be sorted, ranked, clicked
through, or read as urgency**.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar, TypedDict

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import Settings
from alphacouncil.storage import db

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


class DueCount(TypedDict):
    """The only two fields an entry is allowed to have."""

    queue: str
    count: int


class Due(TypedDict):
    cards: DueCount
    reviews: DueCount


@dataclass(frozen=True, slots=True)
class Env:
    """A running app and the database file behind it.

    Both together because several tests move a due date in the database and then
    ask the API about it. Reading the path off ``client.app.state`` looks like the
    shorter route and does not typecheck — ``TestClient.app`` is declared as a bare
    ASGI callable — which is a hint that reaching through the client to the app to
    the settings is one hop too many.
    """

    client: TestClient
    database: Path

    def set_due_at(self, table: str, key_column: str, key: str, when: datetime) -> None:
        """Move one row's due date, so a queue can be arranged as due or not.

        Through the database rather than the API on purpose: neither queue accepts
        a due date on the way in — the card's comes from FSRS, the decision's from
        the user at decision time — so no endpoint could set this.
        """
        connection = db.connect(self.database)
        try:
            connection.execute(
                f"UPDATE {table} SET due_at = ? WHERE {key_column} = ?",  # noqa: S608
                (when.isoformat(), key),
            )
        finally:
            connection.close()


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    database = tmp_path / "alphacouncil.db"
    with TestClient(create_app(Settings(database_path=database))) as client:
        yield Env(client=client, database=database)


def _card(env: Env, index: int) -> str:
    response = env.client.post(
        "/api/v1/cards",
        json={
            "content": f"渠道库存是白酒的先行指标（第 {index} 条）",
            "claim_type": "supporting",
            "source_url": f"https://example.com/report/{index}",
            "source_title": "白酒渠道深度调研",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _enrolled_card(env: Env, index: int = 0) -> str:
    """A card on the review queue, with its due date already past."""
    card_id = _card(env, index)
    assert env.client.post(f"/api/v1/cards/{card_id}/schedule").status_code == 201
    env.set_due_at("card_schedule", "card_id", card_id, NOW - timedelta(days=1))
    return card_id


def _decision_with_due_review(env: Env) -> str:
    response = env.client.post(
        "/api/v1/decisions",
        json={
            "ticker": "600519",
            "action": "buy",
            "rationale": "渠道库存处于低位",
            "counter_evidence": "批价可能短期回落",
            "kill_criteria": [
                {
                    "metric": "revenue_yoy",
                    "operator": "<",
                    "threshold": 0.0,
                    "as_of": "2026-12-31",
                }
            ],
            "review_due_at": (NOW - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _due(env: Env) -> Due:
    body = env.client.get("/api/v1/today").json()
    due: Due = body["due"]
    return due


class TestTheBlockIsThere:
    def test_an_empty_book_reports_zero_and_zero(self, env: Env) -> None:
        """
        Present even when empty.

        The *client* is what decides not to render a line — "0 decisions are due"
        is still a sentence about the reader, and being told you owe yourself
        nothing is not worth a line of screen. The server's job is to answer
        honestly either way, so a missing block is never a valid answer.
        """
        assert _due(env) == {
            "cards": {"queue": "cards", "count": 0},
            "reviews": {"queue": "reviews", "count": 0},
        }

    def test_a_due_card_is_counted(self, env: Env) -> None:
        _enrolled_card(env)
        assert _due(env)["cards"] == {"queue": "cards", "count": 1}

    def test_two_due_cards_are_counted_as_two(self, env: Env) -> None:
        _enrolled_card(env, 0)
        _enrolled_card(env, 1)
        assert _due(env)["cards"]["count"] == 2

    def test_a_due_decision_review_is_counted(self, env: Env) -> None:
        _decision_with_due_review(env)
        assert _due(env)["reviews"] == {"queue": "reviews", "count": 1}

    def test_a_card_that_is_not_due_yet_is_not_counted(self, env: Env) -> None:
        """
        A queue is not a scoreboard: only what has actually come round counts.

        Note the arrangement. A **freshly enrolled** card *is* due immediately —
        FSRS enrols a new claim as due now, which `test_reviews_api.py` already
        pins — so "not due" has to be produced by moving the date forward.
        Asserting the opposite here would have contradicted that deliberate
        behaviour rather than found a bug in this block.
        """
        card_id = _card(env, 0)
        assert env.client.post(f"/api/v1/cards/{card_id}/schedule").status_code == 201
        assert _due(env)["cards"]["count"] == 1

        env.set_due_at("card_schedule", "card_id", card_id, NOW + timedelta(days=30))
        assert _due(env)["cards"]["count"] == 0

    def test_an_unenrolled_card_is_not_counted(self, env: Env) -> None:
        """Only a promise counts. A card nobody put on the queue is not a debt."""
        _card(env, 0)
        assert _due(env)["cards"]["count"] == 0


class TestTheBlockCarriesNothingElse:
    """
    ⭐ The absence assertions.

    Each of these would be invisible in a code review — a due date here, an
    ordering key there, a link — and each is a step toward a ranking the reader
    can feel (red line 11) or a second copy of the route table (spec 022).
    """

    #: A count and a queue name. Two fields. Anything more is scope nobody agreed to.
    _EXPECTED_FIELDS: ClassVar[set[str]] = {"queue", "count"}

    def test_each_entry_is_a_count_and_a_queue_name(self, env: Env) -> None:
        _enrolled_card(env)
        due = _due(env)
        assert set(due) == {"cards", "reviews"}
        # Named rather than `.values()`: mypy widens a heterogeneous TypedDict's
        # value view to `object`, which turns the assertion below into a type
        # error and, worse, would let a `set(entry)` of something unhashable slip
        # past for the wrong reason.
        for entry in (due["cards"], due["reviews"]):
            assert set(entry) == self._EXPECTED_FIELDS, entry

    def test_no_entry_carries_a_due_date(self, env: Env) -> None:
        """
        A due date would let the client sort by urgency.

        "Most overdue first" is a ranking, and a ranking the reader can feel is
        what red line 11 objects to — the same objection ADR-0028 recorded for the
        card queue, which is ordered by due date *because nothing else is allowed
        to order it*. A count must not quietly import that ordering.
        """
        _enrolled_card(env)
        text = str(_due(env))
        assert "due_at" not in text
        assert "2026-" not in text, "a date reached the today page"

    def test_no_entry_carries_a_title_or_an_id(self, env: Env) -> None:
        """
        The detail belongs to the queue page.

        Listing what is due here would make the today page a second, competing
        view of the same rows — and the one that is easier to skim, which is
        exactly the "clear the backlog as a gameable number" failure.
        """
        _enrolled_card(env)
        text = str(_due(env))
        assert "card_" not in text
        assert "content" not in text

    def test_no_entry_carries_a_url(self, env: Env) -> None:
        """
        A link here would be a second copy of the frontend's route table.

        Spec 022 made `ROUTES` the single source of truth precisely so there is one
        place a route is written down. A URL in an API response is that place
        again, and the two would eventually disagree — the classic "works in dev,
        404 in prod" that nobody can explain.
        """
        _enrolled_card(env)
        text = str(_due(env))
        assert "/api/v1" not in text
        assert "#/" not in text

    def test_the_queue_is_named_not_linked(self, env: Env) -> None:
        """The queue field is a **logical name**, which is what makes the above hold."""
        due = _due(env)
        assert due["cards"]["queue"] == "cards"
        assert due["reviews"]["queue"] == "reviews"


class TestNoUrgencyIsImplied:
    def test_counts_are_not_sums_or_ratios(self, env: Env) -> None:
        """
        Nothing to divide by, nothing to add up.

        A backlog counter invites exactly one follow-up question — "out of how
        many?" — and answering it puts a completion fraction on the default page,
        which is red line 11's progress bar by another route. ADR-0028 lists that
        as one of the things the card page deliberately does not do.
        """
        _enrolled_card(env, 0)
        _enrolled_card(env, 1)
        entry = _due(env)["cards"]
        assert set(entry) == {"queue", "count"}
        for banned in ("total", "of", "pct", "percent", "streak", "consecutive"):
            assert banned not in entry

    def test_a_large_backlog_is_still_just_a_number(self, env: Env) -> None:
        """
        Eleven items is not "a lot" in a sentence, and must not become a level.

        The temptation with a counter is to escalate past a threshold — 10+, 50+,
        "a lot". That is a nudge wearing a number's clothes, and it is the
        mechanism `项目总纲` §2.1⑤ rules out: 一句陈述, no 催促词.
        """
        for index in range(11):
            _enrolled_card(env, index)
        assert _due(env)["cards"]["count"] == 11
        body = env.client.get("/api/v1/today").text.lower()
        for escalated in ("urgent", "overdue", "warning", "alert", "很多", "逾期", "堆积"):
            assert escalated not in body
