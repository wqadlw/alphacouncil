"""The knowledge-card API (K1) — provenance, exercised through HTTP.

Marked ``unit``: no network. The database is real (a temporary file per test),
because most of what is worth asserting here *is* the database: that the card
id and timestamps are the server's and not the caller's, that the provenance
fields survive the round trip, and that the ai_generated upgrade actually
persists.

The point of the whole module is that a claim cannot enter the record without
a source. So the tests that matter most are the ones where a caller *tries* to
smuggle something in — a client-supplied id, a blank claim, a non-http URL.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import get_settings
from alphacouncil.storage.db import connect

pytestmark = pytest.mark.unit

CARDS = "/api/v1/cards"

#: `.ai/error-codes.md` §1 fixes the envelope at exactly these keys.
ENVELOPE_KEYS = {"severity", "code", "message", "target", "fix"}


def body(**overrides: Any) -> dict[str, Any]:
    """A well-formed request, so each test overrides only what it is about."""
    payload: dict[str, Any] = {
        "content": "渠道库存是白酒的先行指标，通常领先报表 1-2 个季度。",
        "claim_type": "supporting",
        "source_url": "https://example.com/reports/liquor-channel-survey.pdf",
        "source_title": "XX证券白酒渠道调研报告",
        "as_of": "2026-06-30",
        "origin": "user_written",
        "priority": 3,
        "symbols": ["sh600519"],
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
    """Record a card, failing loudly if it did not work."""
    response = client.post(CARDS, json=body(**overrides))
    assert response.status_code == 201, response.text
    return dict(response.json())


def assert_envelope(response: Any, code: str, status_code: int) -> None:
    """Assert the standard five-key diagnostic envelope."""
    assert response.status_code == status_code, response.text
    payload = response.json()
    assert set(payload) == ENVELOPE_KEYS
    assert payload["code"] == code


# ---------------------------------------------------------------------------
# Provenance: a claim enters the record only with a source
# ---------------------------------------------------------------------------


def test_a_complete_card_is_recorded_with_server_generated_fields(
    client: TestClient,
) -> None:
    """The id and timestamps are the server's moment, never the caller's."""
    created = record(client)

    assert created["id"].startswith("card_")
    assert created["content"] == "渠道库存是白酒的先行指标，通常领先报表 1-2 个季度。"
    assert created["claim_type"] == "supporting"
    assert created["source_url"] == "https://example.com/reports/liquor-channel-survey.pdf"
    assert created["source_title"] == "XX证券白酒渠道调研报告"
    assert created["as_of"] == "2026-06-30"
    assert created["origin"] == "user_written"
    assert created["priority"] == 3
    assert created["status"] == "active"
    assert created["captured_at"].endswith("Z")
    assert created["created_at"].endswith("Z")
    assert created["symbols"] == [
        {"market": "sh", "code": "600519", "display": "600519.SH"}
    ]


def test_a_card_without_symbols_round_trips(client: TestClient) -> None:
    created = record(client, symbols=[])
    assert created["symbols"] == []


def test_client_supplied_id_is_refused_422(client: TestClient) -> None:
    """S-06: the id column exists only to be refused (extra='forbid')."""
    response = client.post(CARDS, json=body(id="card_1"))
    assert response.status_code == 422, response.text
    assert "id" in response.text


def test_client_supplied_captured_at_is_refused_422(client: TestClient) -> None:
    response = client.post(CARDS, json=body(captured_at="2026-01-01T00:00:00.000Z"))
    assert response.status_code == 422, response.text
    assert "captured_at" in response.text


def test_blank_content_is_refused_with_the_card_code(
    client: TestClient,
) -> None:
    assert_envelope(client.post(CARDS, json=body(content="   ")), "CARD_CONTENT_REQUIRED", 400)


def test_overlong_content_is_refused(client: TestClient) -> None:
    """The request schema enforces the ceiling before the domain has to.

    The schema's ``max_length`` rejects first, so the refusal is a ``422``
    naming the field — the domain's ``CARD_TEXT_TOO_LONG`` guard stays as the
    floor under the schema (its own tests live in test_card.py).
    """
    response = client.post(CARDS, json=body(content="x" * 1001))
    assert response.status_code == 422, response.text
    assert "content" in response.text


def test_non_http_source_url_is_refused(client: TestClient) -> None:
    assert_envelope(
        client.post(CARDS, json=body(source_url="ftp://example.com")),
        "CARD_SOURCE_URL_REQUIRED",
        400,
    )


def test_invalid_ticker_is_refused(client: TestClient) -> None:
    assert_envelope(
        client.post(CARDS, json=body(symbols=["not-a-ticker"])),
        "DATA_SOURCE_TICKER_INVALID",
        400,
    )


def test_out_of_range_priority_is_refused_by_the_schema(
    client: TestClient,
) -> None:
    response = client.post(CARDS, json=body(priority=6))
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Reading: list, filter, single card
# ---------------------------------------------------------------------------


def test_empty_list_is_an_empty_array(client: TestClient) -> None:
    response = client.get(CARDS)
    assert response.status_code == 200
    assert response.json() == []


def test_list_filters_by_claim_type_origin_and_status(client: TestClient) -> None:
    record(client, content="支持的卡片")
    record(
        client,
        content="质疑的卡片",
        claim_type="challenging",
        origin="ai_generated",
    )

    supporting = client.get(CARDS, params={"claim_type": "supporting"})
    assert [c["content"] for c in supporting.json()] == ["支持的卡片"]

    ai = client.get(CARDS, params={"origin": "ai_generated"})
    assert [c["content"] for c in ai.json()] == ["质疑的卡片"]

    active = client.get(CARDS, params={"status": "active"})
    assert len(active.json()) == 2

    both = client.get(
        CARDS,
        params={"claim_type": "challenging", "origin": "ai_generated"},
    )
    assert [c["content"] for c in both.json()] == ["质疑的卡片"]


def test_list_filters_by_instrument(client: TestClient) -> None:
    record(client, content="茅台的卡片")
    record(client, content="平安银行的卡片", symbols=["sz000001"])

    moutai = client.get(CARDS, params={"market": "sh", "code": "600519"})
    assert [c["content"] for c in moutai.json()] == ["茅台的卡片"]

    all_cards = client.get(CARDS)
    assert len(all_cards.json()) == 2


def test_one_sided_instrument_filter_is_refused_422(client: TestClient) -> None:
    response = client.get(CARDS, params={"market": "sh"})
    assert response.status_code == 422, response.text
    assert "market and code must be provided together" in response.text


def test_get_one_card_round_trips(client: TestClient) -> None:
    created = record(client)
    detail = client.get(f"{CARDS}/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert detail.json()["content"] == created["content"]


def test_get_missing_card_is_404(client: TestClient) -> None:
    assert_envelope(client.get(f"{CARDS}/card_999"), "CARD_NOT_FOUND", 404)


# ---------------------------------------------------------------------------
# Verify: the ai_generated isolation (red line 15)
# ---------------------------------------------------------------------------


def test_verify_upgrades_ai_generated_to_user_written(
    client: TestClient,
) -> None:
    created = record(client, origin="ai_generated")
    assert created["origin"] == "ai_generated"

    verified = client.patch(f"{CARDS}/{created['id']}/verify")
    assert verified.status_code == 200, verified.text
    assert verified.json()["origin"] == "user_written"

    # The upgrade persists: a fresh read agrees with the patch response.
    again = client.get(f"{CARDS}/{created['id']}")
    assert again.json()["origin"] == "user_written"


def test_verify_on_a_user_written_card_is_409(client: TestClient) -> None:
    created = record(client, origin="user_written")
    assert_envelope(
        client.patch(f"{CARDS}/{created['id']}/verify"),
        "CARD_ALREADY_VERIFIED",
        409,
    )


def test_verify_on_a_missing_card_is_404(client: TestClient) -> None:
    assert_envelope(client.patch(f"{CARDS}/card_999/verify"), "CARD_NOT_FOUND", 404)


# ---------------------------------------------------------------------------
# Instrument page integration
# ---------------------------------------------------------------------------


def test_instrument_detail_carries_its_cards(client: TestClient) -> None:
    record(client, content="茅台的渠道库存观点", symbols=["sh600519"])
    record(client, content="质疑茅台需求的卡片", claim_type="challenging", symbols=["sh600519"])
    record(client, content="平安银行的卡片", symbols=["sz000001"])

    detail = client.get("/api/v1/instruments/sh/600519")
    assert detail.status_code == 200, detail.text
    cards = detail.json()["cards"]
    contents = [c["content"] for c in cards]
    assert "茅台的渠道库存观点" in contents
    assert "质疑茅台需求的卡片" in contents
    assert "平安银行的卡片" not in contents
    # Newest first: the challenging card was recorded after the supporting one.
    assert contents == ["质疑茅台需求的卡片", "茅台的渠道库存观点"]


def test_instrument_detail_without_cards_has_an_empty_list(
    client: TestClient,
) -> None:
    detail = client.get("/api/v1/instruments/sh/600519")
    assert detail.status_code == 200, detail.text
    assert detail.json()["cards"] == []

# ---------------------------------------------------------------------------
# K2 (spec 013): lifecycle events and the convergence exit
# ---------------------------------------------------------------------------


def test_verify_appends_a_verified_event(client: TestClient) -> None:
    created = record(client, origin="ai_generated")
    verified = client.patch(f"{CARDS}/{created['id']}/verify")
    assert verified.status_code == 200, verified.text

    events = verified.json()["events"]
    assert [e["event_type"] for e in events] == ["verified"]
    assert events[0]["reason"] is None
    # A fresh GET carries the same persisted event.
    again = client.get(f"{CARDS}/{created['id']}")
    assert [e["event_type"] for e in again.json()["events"]] == ["verified"]


def test_converge_retire_active_card_with_a_reason(client: TestClient) -> None:
    created = record(client)
    converged = client.patch(
        f"{CARDS}/{created['id']}/converge",
        json={"reason": "公司改直营，渠道先行关系失效"},
    )
    assert converged.status_code == 200, converged.text
    payload = converged.json()
    assert payload["status"] == "converged"
    events = payload["events"]
    assert [e["event_type"] for e in events] == ["converged"]
    assert events[0]["reason"] == "公司改直营，渠道先行关系失效"

    again = client.get(f"{CARDS}/{created['id']}")
    assert again.json()["status"] == "converged"


def test_converge_on_a_converged_card_is_409(client: TestClient) -> None:
    created = record(client)
    first = client.patch(
        f"{CARDS}/{created['id']}/converge", json={"reason": "第一次收敛"}
    )
    assert first.status_code == 200, first.text
    assert_envelope(
        client.patch(
            f"{CARDS}/{created['id']}/converge", json={"reason": "再试一次"}
        ),
        "CARD_NOT_ACTIVE",
        409,
    )


def test_converge_with_a_blank_reason_is_400(client: TestClient) -> None:
    created = record(client)
    # Whitespace-only passes Pydantic min_length but is refused by the repository.
    assert_envelope(
        client.patch(
            f"{CARDS}/{created['id']}/converge", json={"reason": "   "}
        ),
        "CARD_CONVERGE_REASON_REQUIRED",
        400,
    )


def test_converge_on_a_missing_card_is_404(client: TestClient) -> None:
    assert_envelope(
        client.patch(f"{CARDS}/card_999/converge", json={"reason": "理由"}),
        "CARD_NOT_FOUND",
        404,
    )


def test_verify_then_converge_history_is_complete(client: TestClient) -> None:
    created = record(client, origin="ai_generated")
    client.patch(f"{CARDS}/{created['id']}/verify")
    client.patch(
        f"{CARDS}/{created['id']}/converge", json={"reason": "收敛理由"}
    )

    events = client.get(f"{CARDS}/{created['id']}").json()["events"]
    assert [e["event_type"] for e in events] == ["verified", "converged"]
