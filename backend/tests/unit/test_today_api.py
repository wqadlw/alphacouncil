"""The today endpoint (spec 005) — predicates whose cutoff has arrived.

Marked ``unit``: no network, temporary database per test. The rule under test
is one line of arithmetic on a calendar date, which is exactly why it gets
disproportionate testing: "due" must never drift into "triggered" (the metric
value is not in this system), and the boundary day itself must belong to the
due side — "as of 2026-12-31" lands on the reader's desk that morning.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.domain.decision import ComparisonOperator, DecisionAction, KillCriterion
from alphacouncil.storage.db import connect
from alphacouncil.storage.repositories import decisions as decision_repository

pytestmark = pytest.mark.unit

TODAY = "/api/v1/today"
DECISIONS = "/api/v1/decisions"

YESTERDAY = date.today() - timedelta(days=1)
TOMORROW = date.today() + timedelta(days=1)


def criterion(as_of: date, metric: str = "revenue_yoy") -> dict[str, Any]:
    """One well-formed predicate body, so tests override only the date."""
    return {"metric": metric, "operator": "<", "threshold": 0.55, "as_of": as_of.isoformat()}


def body(**overrides: Any) -> dict[str, Any]:
    """A well-formed decision request, so each test overrides only what it is about."""
    payload: dict[str, Any] = {
        "ticker": "600519",
        "action": "buy",
        "rationale": "毛利率连续三年高于 90%，品牌定价权强",
        "counter_evidence": "白酒需求与宏观强相关，若高端消费收缩，定价权无法对冲量的下滑",
        "kill_criteria": [criterion(TOMORROW)],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A client over the isolated database, with migrations already applied."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def database(client: TestClient) -> Iterator[sqlite3.Connection]:
    """A direct connection, for repository-level assertions.

    Depends on ``client`` (not the app): the TestClient's startup is what runs
    the schema migration, so connecting first would find no tables.
    """
    connection = connect(create_settings_database_path())
    try:
        yield connection
    finally:
        connection.close()


def create_settings_database_path() -> str:
    """The isolated database path, read the same way the app factory does."""
    from alphacouncil.core.config import get_settings

    return str(get_settings().database_path)


# ---------------------------------------------------------------------------
# the domain rule: due, never "triggered"
# ---------------------------------------------------------------------------


def test_a_criterion_is_due_on_its_own_day() -> None:
    """The boundary belongs to due: "as of 2026-12-31" is on the desk that morning."""
    subject = KillCriterion(
        metric="revenue_yoy",
        operator=ComparisonOperator.LT,
        threshold=0.55,
        as_of=date(2026, 12, 31),
    )

    assert subject.due(as_of=date(2026, 12, 31)) is True


def test_a_criterion_stays_due_after_its_day() -> None:
    subject = KillCriterion(
        metric="revenue_yoy",
        operator=ComparisonOperator.LT,
        threshold=0.55,
        as_of=date(2026, 12, 31),
    )

    assert subject.due(as_of=date(2027, 1, 2)) is True


def test_a_criterion_is_not_due_before_its_day() -> None:
    subject = KillCriterion(
        metric="revenue_yoy",
        operator=ComparisonOperator.LT,
        threshold=0.55,
        as_of=date(2026, 12, 31),
    )

    assert subject.due(as_of=date(2026, 12, 30)) is False


# ---------------------------------------------------------------------------
# the endpoint
# ---------------------------------------------------------------------------


def test_an_empty_book_reports_no_attention(client: TestClient) -> None:
    """Nothing recorded means nothing due — an empty list, not an error."""
    response = client.get(TODAY)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["attention"] == []
    assert body["generated_at"].endswith("Z")


def test_a_past_cutoff_arrives_in_attention(client: TestClient) -> None:
    """A due predicate carries where it came from, and the way back to it."""
    recorded = client.post(DECISIONS, json=body(kill_criteria=[criterion(YESTERDAY)]))
    assert recorded.status_code == 201, recorded.text

    response = client.get(TODAY)

    assert response.status_code == 200, response.text
    items = response.json()["attention"]
    assert len(items) == 1
    item = items[0]["item"]
    assert items[0]["kind"] == "kill_criterion_due"
    assert item["decision_id"] == recorded.json()["id"]
    assert item["market"] == "sh"
    assert item["code"] == "600519"
    assert item["display"] == "600519.SH"
    assert item["action"] == "buy"
    assert item["criterion"]["as_of"] == YESTERDAY.isoformat()
    assert item["criterion"]["metric"] == "revenue_yoy"


def test_a_future_cutoff_does_not_arrive_in_attention(client: TestClient) -> None:
    client.post(DECISIONS, json=body(kill_criteria=[criterion(TOMORROW)]))

    response = client.get(TODAY)

    assert response.status_code == 200, response.text
    assert response.json()["attention"] == []


def test_only_the_due_criteria_of_one_decision_are_listed(client: TestClient) -> None:
    """Flattening is per criterion, not per decision: one due, one not."""
    client.post(
        DECISIONS,
        json=body(
            kill_criteria=[
                criterion(YESTERDAY, metric="revenue_yoy"),
                criterion(TOMORROW, metric="gross_margin"),
            ]
        ),
    )

    response = client.get(TODAY)

    assert response.status_code == 200, response.text
    items = response.json()["attention"]
    assert [item["item"]["criterion"]["metric"] for item in items] == ["revenue_yoy"]


# ---------------------------------------------------------------------------
# the untruncated scan
# ---------------------------------------------------------------------------


def test_list_all_returns_every_row_beyond_any_recent_window(database: sqlite3.Connection) -> None:
    """A rule that scans for "due today" cannot afford a LIMIT.

    Fifty-one decisions are recorded directly through the repository (with
    server-style stamps); ``recent`` keeps its window of 50, ``list_all``
    returns all 51 in write order — the 51st is exactly the kind of old row
    whose predicate comes due one day.
    """
    from alphacouncil.domain.decision import Decision
    from alphacouncil.models.market import Market, Symbol

    symbol = Symbol(market=Market.SH, code="600519")
    for index in range(51):
        decision = Decision(
            symbol=symbol,
            action=DecisionAction.BUY,
            rationale="毛利率连续三年高于 90%，品牌定价权强",
            counter_evidence="白酒需求与宏观强相关",
            kill_criteria=(criterion_domain(TOMORROW),),
            thesis_id=None,
        )
        decision_repository.append(
            database,
            decision,
            now=f"2026-09-{1 + index // 10:02d}T0{index % 10}:00:00.000Z",
        )

    assert len(decision_repository.recent(database, limit=50)) == 50
    every = decision_repository.list_all(database)
    assert len(every) == 51
    assert [row.id for row in every] == sorted(row.id for row in every)


def criterion_domain(as_of: date, metric: str = "revenue_yoy") -> KillCriterion:
    """The domain-typed counterpart of :func:`criterion`."""
    return KillCriterion(
        metric=metric,
        operator=ComparisonOperator.LT,
        threshold=0.55,
        as_of=as_of,
    )
