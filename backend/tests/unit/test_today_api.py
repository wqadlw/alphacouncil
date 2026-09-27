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
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.domain.decision import (
    ComparisonOperator,
    DecisionAction,
    KillCriterion,
)
from alphacouncil.domain.trading import verdict_for
from alphacouncil.models.market import (
    AssetType,
    DataResult,
    Market,
    Quote,
    RealtimeQuote,
    Symbol,
)
from alphacouncil.providers.base import Dataset, ProviderCapabilities
from alphacouncil.storage.db import connect
from alphacouncil.storage.repositories import decisions as decision_repository

pytestmark = pytest.mark.unit

TODAY = "/api/v1/today"
DECISIONS = "/api/v1/decisions"

STAMP = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
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
    """A client whose probe never touches the network.

    The today route now consults the market-data router for the trading-day
    probe; left on the default router, every one of these unit tests would
    make a live request (conftest's network rule exists to prevent exactly
    that). The stub refuses everything, which lands the verdict on the
    ``unknown``/weekend path the domain tests cover independently.
    """
    app = create_app()
    app.state.market_data = _SilentProbe()
    with TestClient(app) as test_client:
        yield test_client


class _SilentProbe:
    """Refuses every fetch, so the probe degrades to ``unknown`` — no network."""

    name = "silent"
    capabilities = ProviderCapabilities(datasets=frozenset({Dataset.DAILY, Dataset.REALTIME}))

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        return DataResult.error(
            ErrorCode.DATA_SOURCE_UNAVAILABLE, source=self.name, fetched_at=STAMP
        )

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        return DataResult.error(
            ErrorCode.DATA_SOURCE_UNAVAILABLE, source=self.name, fetched_at=STAMP
        )


class _FixedBars:
    """Answers the probe with a fixed newest bar (or with a failure for ``None``)."""

    name = "fixed"
    capabilities = ProviderCapabilities(datasets=frozenset({Dataset.DAILY}))

    def __init__(self, last_bar: date | None) -> None:
        self._last_bar = last_bar

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        if self._last_bar is None:
            return DataResult.error(
                ErrorCode.DATA_SOURCE_UNAVAILABLE, source=self.name, fetched_at=STAMP
            )
        bar = Quote(
            symbol=Symbol(market=Market.SH, code="000001", asset_type=AssetType.INDEX),
            trade_date=self._last_bar,
            open=3888.0,
            high=3900.0,
            low=3880.0,
            close=3888.37,
            volume=1.0,
            amount=1.0,
            source=self.name,
            fetched_at=STAMP,
        )
        return DataResult.ok([bar], source=self.name, fetched_at=STAMP)

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        return DataResult.error(
            ErrorCode.DATA_SOURCE_UNAVAILABLE, source=self.name, fetched_at=STAMP
        )


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


# ---------------------------------------------------------------------------
# the trading-day probe (spec 007)
# ---------------------------------------------------------------------------


def make_client(probe: object) -> TestClient:
    """A client whose market-data router is the given probe stub."""
    app = create_app()
    app.state.market_data = probe
    return TestClient(app)


def test_the_market_status_carries_the_verdict_with_its_basis() -> None:
    """The route composes probe → domain rule; the oracle is the rule itself,
    whose rows are pinned with dead expectations by test_trading.py."""
    probe = _FixedBars(date.today())
    with make_client(probe) as test_client:
        response = test_client.get(TODAY)

    assert response.status_code == 200, response.text
    status = response.json()["market_status"]
    expected_verdict, expected_basis = verdict_for(
        now=datetime.now().astimezone(), last_trading_date=date.today()
    )
    assert status["verdict"] == expected_verdict.value
    assert status["basis"] == expected_basis.value
    assert status["last_trading_date"] == date.today().isoformat()
    assert status["checked_at"].endswith("Z")


def test_a_failed_probe_reads_as_unknown_without_breaking_the_page() -> None:
    """One source's bad morning may not take the today page with it."""
    with make_client(_SilentProbe()) as test_client:
        response = test_client.get(TODAY)

    assert response.status_code == 200, response.text
    status = response.json()["market_status"]
    expected_verdict, expected_basis = verdict_for(
        now=datetime.now().astimezone(), last_trading_date=None
    )
    assert status["verdict"] == expected_verdict.value
    assert status["basis"] == expected_basis.value
    assert status["last_trading_date"] is None


def test_the_attention_blocks_keep_working_when_the_probe_refuses(
    client: TestClient,
) -> None:
    """The probe rides along in the same response; a refusal must not blank
    the attention block, the way any other failure must not blank its page."""
    recorded = client.post(DECISIONS, json=body(kill_criteria=[criterion(YESTERDAY)]))
    assert recorded.status_code == 201, recorded.text

    response = client.get(TODAY)

    assert response.status_code == 200, response.text
    body_json = response.json()
    assert len(body_json["attention"]) == 1
    assert body_json["attention"][0]["item"]["decision_id"] == recorded.json()["id"]
