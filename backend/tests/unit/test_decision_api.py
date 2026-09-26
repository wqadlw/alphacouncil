"""The decision journal (J1) — the gate, exercised through HTTP.

Marked ``unit``: no network. The database is real (a temporary file per test),
because most of what is worth asserting here *is* the database: that the
append-only triggers refuse an update, that the id is the server's moment and
not the caller's, that the predicate survives the round trip through JSON.

The point of the whole module is that three fields cannot be skipped. So the
tests that matter most are the ones where a caller *tries* to skip them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import get_settings
from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.storage.db import connect

pytestmark = pytest.mark.unit

DECISIONS = "/api/v1/decisions"

#: `.ai/error-codes.md` §1 fixes the envelope at exactly these keys.
ENVELOPE_KEYS = {"severity", "code", "message", "target", "fix"}

CRITERION: dict[str, Any] = {
    "metric": "gross_margin",
    "operator": "<",
    "threshold": 0.55,
    "as_of": "2026-12-31",
}


def body(**overrides: Any) -> dict[str, Any]:
    """A well-formed request, so each test overrides only what it is about."""
    payload: dict[str, Any] = {
        "ticker": "600519",
        "action": "buy",
        "rationale": "毛利率连续三年高于 90%，品牌定价权强",
        "counter_evidence": "白酒需求与宏观强相关，若高端消费收缩，定价权无法对冲量的下滑",
        "kill_criteria": [dict(CRITERION)],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A client over the isolated database, with migrations already applied."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def database() -> Iterator[sqlite3.Connection]:
    """A direct connection, for assertions the API cannot make."""
    connection = connect(get_settings().database_path)
    try:
        yield connection
    finally:
        connection.close()


def record(client: TestClient, **overrides: Any) -> dict[str, Any]:
    """Record a decision, failing loudly if it did not work."""
    response = client.post(DECISIONS, json=body(**overrides))
    assert response.status_code == 201, response.text
    return dict(response.json())


# ---------------------------------------------------------------------------
# The gate: three fields that cannot be skipped
# ---------------------------------------------------------------------------


def test_a_complete_decision_is_recorded_with_the_server_clock_as_its_id(
    client: TestClient,
) -> None:
    """The id is not an identifier, it is the evidence that this came first."""
    recorded = record(client)

    # Exactly the spelling the schema's CHECK accepts, which is also the one
    # core.time.utc_millis produces.
    assert recorded["id"].endswith("Z")
    assert recorded["id"][10] == "T"
    assert recorded["display"] == "600519.SH"
    assert recorded["action"] == "buy"
    assert recorded["counter_evidence"].startswith("白酒需求与宏观强相关")


def test_a_blank_rationale_is_refused_with_its_own_code(client: TestClient) -> None:
    response = client.post(DECISIONS, json=body(rationale="   "))

    assert response.status_code == 400, response.text
    assert response.json()["code"] == ErrorCode.DECISION_RATIONALE_REQUIRED.value
    assert set(response.json()) == ENVELOPE_KEYS


def test_a_blank_counter_evidence_is_refused_with_its_own_code(client: TestClient) -> None:
    """Distinct from the rationale's code on purpose.

    "How often does a user leave the counter-evidence blank" is the question this
    product is built around. It stops being answerable the moment the two
    failures share a name.
    """
    response = client.post(DECISIONS, json=body(counter_evidence="  \n "))

    assert response.status_code == 400, response.text
    assert response.json()["code"] == ErrorCode.DECISION_COUNTER_EVIDENCE_REQUIRED.value
    assert set(response.json()) == ENVELOPE_KEYS


def test_an_empty_rationale_never_reaches_the_domain(client: TestClient) -> None:
    """The request schema is the first floor, and it fails before the domain does."""
    response = client.post(DECISIONS, json=body(rationale=""))

    assert response.status_code == 422, response.text


def test_a_decision_with_no_falsifiable_condition_is_refused(client: TestClient) -> None:
    """The schema cannot catch this one — an empty JSON array is still an array."""
    response = client.post(DECISIONS, json=body(kill_criteria=[]))

    assert response.status_code == 422, response.text


def test_a_client_supplied_id_is_refused_at_the_schema(client: TestClient) -> None:
    """Backdating your own foresight is the one thing the id exists to prevent.

    Refused at the schema rather than by a hand-written check. The difference
    matters: a declared-then-rejected `id` field would be a field that *exists*,
    and no execution path can reveal that — a test posting an id and asserting
    the record round-trips would pass while the hole stayed open (S-06,
    ``checks/rules/no_client_supplied_id.py``). With no field declared and
    ``extra="forbid"``, the refusal is a property of the schema itself.
    """
    response = client.post(
        DECISIONS,
        json=body(id="2020-01-01T00:00:00.000Z"),
    )

    assert response.status_code == 422, response.text
    assert "id" in response.text


def test_an_unknown_field_is_still_refused_by_the_schema(client: TestClient) -> None:
    """Same door as `id`, which is why `id` needs no special case."""
    response = client.post(DECISIONS, json=body(ticker_code="600519"))

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# The predicate: structured, evaluable, and refused when it is neither
# ---------------------------------------------------------------------------


def test_the_predicate_round_trips_unchanged(client: TestClient) -> None:
    recorded = record(client)

    assert recorded["kill_criteria"] == [
        {
            "metric": "gross_margin",
            "operator": "<",
            "threshold": 0.55,
            "as_of": "2026-12-31",
        }
    ]


def test_several_conditions_keep_their_order(client: TestClient) -> None:
    recorded = record(
        client,
        kill_criteria=[
            {"metric": "revenue_yoy", "operator": "<", "threshold": 0.0, "as_of": "2026-12-31"},
            {"metric": "price", "operator": "<=", "threshold": 900.0, "as_of": "2027-03-31"},
        ],
    )

    assert [item["metric"] for item in recorded["kill_criteria"]] == ["revenue_yoy", "price"]
    assert recorded["kill_criteria"][1]["operator"] == "<="


@pytest.mark.parametrize(
    "metric",
    ["gross margin", "毛利率", "Gross_Margin", "3margin", ""],
)
def test_a_metric_name_that_is_not_a_token_is_refused(client: TestClient, metric: str) -> None:
    """Shape, not membership.

    The catalogue belongs to the financial-data layer (D4), which is not built,
    so a closed list here would reject a valid metric the day D4 lands. Shape
    still catches what actually goes wrong.
    """
    response = client.post(
        DECISIONS,
        json=body(kill_criteria=[{**CRITERION, "metric": metric}]),
    )

    assert response.status_code in {400, 422}, response.text
    if response.status_code == 400:
        assert response.json()["code"] == ErrorCode.DECISION_KILL_CRITERIA_REQUIRED.value


def test_an_unknown_operator_is_refused(client: TestClient) -> None:
    response = client.post(
        DECISIONS,
        json=body(kill_criteria=[{**CRITERION, "operator": "approximately"}]),
    )

    assert response.status_code == 422, response.text


def test_a_threshold_that_json_cannot_round_trip_is_refused(client: TestClient) -> None:
    """`1e999` parses to infinity, which Python writes as bare `Infinity`.

    No other JSON parser accepts that, so a stored infinity would corrupt the
    record on the way out. Refused on the way in instead.

    Sent as raw content rather than through ``json=``: Python's own encoder
    rejects ``inf``, so the test client would fail before the request left —
    which is exactly the asymmetry being tested, since a *different* client is
    free to put the literal ``1e999`` on the wire.
    """
    payload = json.dumps(body(kill_criteria=[{**CRITERION, "threshold": 0.0}])).replace(
        '"threshold": 0.0', '"threshold": 1e999'
    )

    response = client.post(
        DECISIONS,
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == ErrorCode.DECISION_KILL_CRITERIA_REQUIRED.value


def test_a_malformed_date_is_refused(client: TestClient) -> None:
    response = client.post(
        DECISIONS,
        json=body(kill_criteria=[{**CRITERION, "as_of": "31/12/2026"}]),
    )

    assert response.status_code == 422, response.text


def test_a_predicate_missing_a_field_is_refused(client: TestClient) -> None:
    response = client.post(
        DECISIONS,
        json=body(kill_criteria=[{"metric": "price", "operator": "<"}]),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# The instrument, and the log
# ---------------------------------------------------------------------------


def test_an_ambiguous_ticker_without_a_market_is_refused(client: TestClient) -> None:
    """000001 is the Shanghai Composite on one exchange and Ping An Bank on the other."""
    response = client.post(DECISIONS, json=body(ticker="000001"))

    assert response.status_code == 400, response.text
    assert response.json()["code"] == ErrorCode.DATA_SOURCE_TICKER_AMBIGUOUS.value


def test_decisions_arrive_with_the_instrument_oldest_first(client: TestClient) -> None:
    record(client, rationale="第一版理由")
    record(client, action="trim", rationale="估值到了上沿，减一半")

    detail = client.get("/api/v1/instruments/sh/600519").json()
    decisions = detail["decisions"]

    assert [item["rationale"] for item in decisions] == ["第一版理由", "估值到了上沿，减一半"]
    assert [item["id"] for item in decisions] == sorted(item["id"] for item in decisions)


def test_an_instrument_with_no_decisions_reports_an_empty_list(client: TestClient) -> None:
    """Not an error, and not a 404 — "nothing yet" is a fact about a page."""
    detail = client.get("/api/v1/instruments/sh/600519").json()

    assert detail["decisions"] == []


def test_recording_a_decision_does_not_require_following_the_instrument(
    client: TestClient,
) -> None:
    """The two are separate on purpose.

    A decision is about a trade. Following is about watching. Someone who bought
    before this system existed has decisions and an empty pool, and demanding a
    watchlist entry first would make the record start a lie.
    """
    record(client)

    detail = client.get("/api/v1/instruments/sh/600519").json()

    assert detail["follow"]["status"] == "never"
    assert len(detail["decisions"]) == 1


def test_a_decision_about_an_etf_does_not_trip_the_asset_type_check(client: TestClient) -> None:
    """The parse default is `stock`; asserting it against a stored ETF is a false conflict."""
    client.post(
        "/api/v1/watchlist",
        json={"ticker": "510300", "asset_type": "etf", "reason": "沪深300 的代理，用于观察大盘"},
    )

    recorded = record(client, ticker="510300")

    assert recorded["market"] == "sh"


def test_the_recent_list_is_newest_first(client: TestClient) -> None:
    """The opposite order to the per-instrument log, and for a different question.

    "What have I been doing lately" wants the latest first; one instrument's log
    is read as a story and only works in order.
    """
    record(client, rationale="先买一点")
    record(client, ticker="600036", rationale="招行，零售护城河")

    listed = client.get(DECISIONS).json()

    assert [item["rationale"] for item in listed] == ["招行，零售护城河", "先买一点"]


# ---------------------------------------------------------------------------
# Append-only, enforced by the database rather than by this module
# ---------------------------------------------------------------------------


def test_the_database_refuses_to_change_a_decision(
    client: TestClient, database: sqlite3.Connection
) -> None:
    """The rule lives in a trigger, so it survives a caller using raw SQL."""
    recorded = record(client)

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        database.execute(
            "UPDATE decisions SET rationale = 'TAMPERED' WHERE id = ?",
            (recorded["id"],),
        )


def test_the_database_refuses_to_delete_a_decision(
    client: TestClient, database: sqlite3.Connection
) -> None:
    recorded = record(client)

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        database.execute("DELETE FROM decisions WHERE id = ?", (recorded["id"],))


def test_the_stored_predicate_is_a_json_array_not_prose(
    client: TestClient, database: sqlite3.Connection
) -> None:
    """Rule 21's mechanical expression: the column holds predicates, not a sentence."""
    recorded = record(client)

    raw = database.execute(
        "SELECT kill_criteria, json_type(kill_criteria) AS kind FROM decisions WHERE id = ?",
        (recorded["id"],),
    ).fetchone()

    assert raw["kind"] == "array"
    assert raw["kill_criteria"].startswith("[{")
