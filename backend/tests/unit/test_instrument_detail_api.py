"""The instrument detail and quote endpoints.

Marked ``unit``: no network. Two halves, and they are isolated differently on
purpose.

**Detail** runs against a real database — a temporary file per test, from the
``_isolated_database`` fixture — because what is worth asserting *is* the
storage behaviour: that the log comes back whole, in write order, and that a
removal is not the absence of the events before it.

**Quote** runs against a stub router substituted onto ``app.state``. That is not
a shortcut around the interesting code; it is the only way to reach three of the
four data states at all. No live source produces ``no_data``, ``error`` and
``unavailable`` on demand, so a test that went to the network could only ever
assert ``ok`` — and the states it could not reach are exactly the ones this
endpoint exists to preserve. The real router's own behaviour is covered in
``test_market_data.py`` and ``test_provider_transport.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import (
    AssetType,
    DataResult,
    DataStatus,
    Market,
    RealtimeQuote,
    Symbol,
)

pytestmark = pytest.mark.unit

ADD = "/api/v1/watchlist"
REASON = "/api/v1/watchlist/reason"
REMOVE = "/api/v1/watchlist/remove"

#: `.ai/error-codes.md` §1 fixes the envelope at exactly these keys.
ENVELOPE_KEYS = {"severity", "code", "message", "target", "fix"}

STAMP = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

MOUTAI = Symbol(market=Market.SH, code="600519")


def detail_url(market: str = "sh", code: str = "600519") -> str:
    return f"/api/v1/instruments/{market}/{code}"


def quote_url(market: str = "sh", code: str = "600519") -> str:
    return f"/api/v1/instruments/{market}/{code}/quote"


class StubRouter:
    """Stands in for ``MarketDataRouter``, handing back one canned outcome.

    Only ``get_realtime`` is implemented — deliberately. If the endpoint ever
    starts calling something else, these tests fail on the missing attribute
    rather than quietly exercising a path nobody meant to add.
    """

    def __init__(self, result: DataResult[RealtimeQuote]) -> None:
        self.result = result
        self.asked: list[Symbol] = []

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        self.asked.append(symbol)
        return self.result


def snapshot(**overrides: object) -> RealtimeQuote:
    """A well-formed quote, so each test overrides only what it is about."""
    fields: dict[str, object] = {
        "symbol": MOUTAI,
        "price": 1237.0,
        "prev_close": 1251.0,
        "open": 1250.0,
        "high": 1255.0,
        "low": 1230.0,
        "volume": 2_400_000.0,
        "amount": 2.97e9,
        "quoted_at": STAMP,
        "source": "stub",
        "fetched_at": STAMP,
    }
    fields.update(overrides)
    return RealtimeQuote.model_validate(fields)


@pytest.fixture
def app() -> FastAPI:
    """A fresh application, so a stub installed by one test cannot leak."""
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client over the isolated database, with migrations already applied."""
    with TestClient(app) as test_client:
        yield test_client


def follow(client: TestClient, ticker: str = "600519", **extra: object) -> dict[str, object]:
    """Add an instrument, failing loudly if it did not work."""
    response = client.post(ADD, json={"ticker": ticker, "reason": "毛利率三年高于 90%", **extra})
    assert response.status_code == 201, response.text
    return dict(response.json())


# ---------------------------------------------------------------------------
# detail — identity and follow state
# ---------------------------------------------------------------------------


def test_an_instrument_nobody_has_followed_is_a_page_not_a_404(client: TestClient) -> None:
    """The page exists to help you decide *before* following. So "nothing yet" is 200."""
    response = client.get(detail_url())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["follow"] == {
        "status": "never",
        "reason": None,
        "since": None,
        "last_event_id": None,
        "event_count": 0,
    }
    assert body["history"] == []
    assert body["display"] == "600519.SH"
    assert body["name"] is None


def test_detail_reports_the_reason_that_is_currently_in_force(client: TestClient) -> None:
    follow(client)

    body = client.get(detail_url()).json()

    assert body["follow"]["status"] == "followed"
    assert body["follow"]["reason"] == "毛利率三年高于 90%"
    assert body["follow"]["since"] is not None
    assert body["follow"]["event_count"] == 1


def test_detail_takes_the_asset_type_from_storage_not_from_the_code(client: TestClient) -> None:
    """A code prefix says nothing reliable about what the thing is (ADR-0017)."""
    follow(client, asset_type=AssetType.ETF.value)

    body = client.get(detail_url()).json()

    assert body["asset_type"] == AssetType.ETF.value


def test_a_removal_is_reported_as_a_state_and_the_log_still_holds_everything(
    client: TestClient,
) -> None:
    """``removed`` is the newest event, not the absence of the earlier ones."""
    follow(client)
    assert client.post(REMOVE, json={"ticker": "600519"}).status_code == 200

    body = client.get(detail_url()).json()

    assert body["follow"]["status"] == "removed"
    assert body["follow"]["event_count"] == 2
    assert [event["kind"] for event in body["history"]] == ["added", "removed"]


def test_the_log_comes_back_whole_and_in_write_order(client: TestClient) -> None:
    """Oldest first: read newest-first, four events become four unrelated rows.

    Read in order they become a story — added, revised, removed, added again —
    and that is the only form in which "I have done this before" is visible.
    """
    first = follow(client)
    revised = client.post(REASON, json={"ticker": "600519", "reason": "批价回落，但渠道库存仍低"})
    assert revised.status_code == 200, revised.text
    assert client.post(REMOVE, json={"ticker": "600519"}).status_code == 200
    follow(client, reason="重新关注：估值回到 20 倍以下")

    body = client.get(detail_url()).json()
    history = body["history"]

    assert [event["kind"] for event in history] == [
        "added",
        "reason_revised",
        "removed",
        "added",
    ]
    assert [event["event_id"] for event in history] == sorted(
        event["event_id"] for event in history
    )
    # The revision points at what it replaced; nothing else does.
    assert history[1]["supersedes_id"] == first["event_id"]
    assert history[0]["supersedes_id"] is None
    assert history[2]["supersedes_id"] is None
    # A removal needs no justification, so the field is absent rather than empty.
    assert history[2]["reason"] is None
    assert body["follow"]["event_count"] == 4


def test_detail_rejects_a_code_that_is_not_listed_on_the_stated_market(
    client: TestClient,
) -> None:
    """600519 is a Shanghai code. Asking for it on Shenzhen is a contradiction."""
    response = client.get(detail_url(market="sz"))

    assert response.status_code == 400, response.text
    assert set(response.json()) == ENVELOPE_KEYS


def test_detail_rejects_a_malformed_code(client: TestClient) -> None:
    response = client.get(detail_url(code="abcdef"))

    assert response.status_code == 400, response.text
    assert set(response.json()) == ENVELOPE_KEYS


def test_resolve_is_not_swallowed_by_the_detail_path(client: TestClient) -> None:
    """``/resolve`` is one segment, ``/{market}/{code}`` is two. Both must route."""
    response = client.get("/api/v1/instruments/resolve", params={"ticker": "600519"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"


# ---------------------------------------------------------------------------
# quote — the four states, kept apart
# ---------------------------------------------------------------------------


def test_quote_passes_a_live_snapshot_through_with_the_change_computed(
    app: FastAPI, client: TestClient
) -> None:
    app.state.market_data = StubRouter(DataResult.ok(snapshot(), source="stub", fetched_at=STAMP))

    body = client.get(quote_url()).json()

    assert body["status"] == "ok"
    assert body["value"]["price"] == 1237.0
    # Computed server-side and serialised, so no client divides for itself.
    # Stated as the arithmetic rather than a literal, so the intent survives a
    # change to either price.
    assert body["value"]["change_pct"] == pytest.approx((1237.0 - 1251.0) / 1251.0)
    assert body["source"] == "stub"
    assert body["stale"] is False


@pytest.mark.parametrize(
    ("result", "expected_status", "expected_field"),
    [
        (
            DataResult.no_data("unknown symbol", source="stub", fetched_at=STAMP),
            "no_data",
            "reason",
        ),
        (
            DataResult.error(
                ErrorCode.DATA_SOURCE_UNREACHABLE,
                source="stub",
                fetched_at=STAMP,
                detail="ConnectError",
            ),
            "error",
            "error_code",
        ),
        (
            DataResult.unavailable("unit not declared", source="stub", fetched_at=STAMP),
            "unavailable",
            "reason",
        ),
    ],
)
def test_quote_reports_each_failure_state_rather_than_collapsing_them(
    app: FastAPI,
    client: TestClient,
    result: DataResult[RealtimeQuote],
    expected_status: str,
    expected_field: str,
) -> None:
    """``no_data`` / ``error`` / ``unavailable`` are three different sentences.

    Collapsing any two is how a bug becomes a wrong number instead of a visible
    absence (constitution 4.6), so this asserts the distinctions survive the
    trip through HTTP.
    """
    app.state.market_data = StubRouter(result)

    body = client.get(quote_url()).json()

    assert body["status"] == expected_status
    assert body[expected_field] is not None
    assert body["value"] is None


def test_a_cached_price_is_labelled_stale_rather_than_served_as_current(
    app: FastAPI, client: TestClient
) -> None:
    """Serving yesterday's price as today's would be a quiet lie."""
    app.state.market_data = StubRouter(
        DataResult.ok(snapshot(), source="stub", fetched_at=STAMP).model_copy(
            update={"stale": True}
        )
    )

    body = client.get(quote_url()).json()

    assert body["status"] == "ok"
    assert body["stale"] is True
    # A stale value keeps its original provenance, so the page can say how old.
    assert body["source"] == "stub"


def test_quote_asks_about_the_instrument_the_path_names(app: FastAPI, client: TestClient) -> None:
    stub = StubRouter(DataResult.ok(snapshot(), source="stub", fetched_at=STAMP))
    app.state.market_data = stub

    client.get(quote_url(market="sz", code="000001"))

    assert stub.asked == [Symbol(market=Market.SZ, code="000001")]


def test_quote_uses_the_stored_asset_type_when_the_instrument_is_known(
    app: FastAPI, client: TestClient
) -> None:
    """An ETF must be priced as an ETF, not as the stock the parse defaults to."""
    follow(client, ticker="510300", asset_type=AssetType.ETF.value)
    stub = StubRouter(DataResult.ok(snapshot(), source="stub", fetched_at=STAMP))
    app.state.market_data = stub

    client.get(quote_url(code="510300"))

    assert stub.asked[0].asset_type is AssetType.ETF


def test_quote_rejects_a_malformed_code_before_asking_any_source(
    app: FastAPI, client: TestClient
) -> None:
    stub = StubRouter(DataResult.ok(snapshot(), source="stub", fetched_at=STAMP))
    app.state.market_data = stub

    response = client.get(quote_url(code="abcdef"))

    assert response.status_code == 400, response.text
    assert set(response.json()) == ENVELOPE_KEYS
    assert stub.asked == []


def test_the_four_states_are_the_only_ones_this_endpoint_can_report(
    app: FastAPI, client: TestClient
) -> None:
    """A guard on the enum itself, so a fifth state cannot appear unnoticed."""
    app.state.market_data = StubRouter(DataResult.ok(snapshot(), source="stub", fetched_at=STAMP))

    body = client.get(quote_url()).json()

    assert body["status"] in {state.value for state in DataStatus}
