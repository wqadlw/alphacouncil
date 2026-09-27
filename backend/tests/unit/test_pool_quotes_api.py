"""The pool priced as one list (spec 004) — through HTTP, without a network.

Marked ``unit``: the market-data router is a stub keyed by symbol, which is the
only way to arrange ``no_data`` and ``error`` at will — no live source produces
them on demand. The database is real (a temporary file per test), because what
most of these tests assert *is* the database: which instruments are "currently
followed" once one has been removed.

The property under test throughout is that the batch has **no status of its
own**. Ten rows tell ten truths; the endpoint's only job is to carry each one
to the page without flattening, merging, or dropping it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import DataResult, Market, RealtimeQuote, Symbol

pytestmark = pytest.mark.unit

QUOTES = "/api/v1/watchlist/quotes"
ADD = "/api/v1/watchlist"
REMOVE = "/api/v1/watchlist/remove"

STAMP = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

MOUTAI = Symbol(market=Market.SH, code="600519")


class KeyedStub:
    """Answers per symbol from a canned map, recording every question.

    An unmappped symbol raises ``KeyError``, so a test that expects a symbol
    never to be asked fails loudly (500) instead of silently pricing it.
    """

    def __init__(self, results: dict[str, DataResult[RealtimeQuote]]) -> None:
        self.results = results
        self.asked: list[Symbol] = []

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        self.asked.append(symbol)
        return self.results[symbol.full]


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


def ok(symbol: Symbol, price: float) -> DataResult[RealtimeQuote]:
    """A priced snapshot for ``symbol``."""
    return DataResult.ok(
        snapshot(symbol=symbol, price=price, prev_close=price + 10.0),
        source="stub",
        fetched_at=STAMP,
    )


@pytest.fixture
def app() -> FastAPI:
    """A fresh application, so a stub installed by one test cannot leak."""
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client over the isolated database, with migrations already applied."""
    with TestClient(app) as test_client:
        yield test_client


def follow(client: TestClient, ticker: str, market: str | None = None) -> None:
    """Add an instrument, failing loudly if it did not work."""
    response = client.post(
        ADD, json={"ticker": ticker, "reason": "毛利率三年高于 90%", "market": market}
    )
    assert response.status_code == 201, response.text


def install(app: FastAPI, **results: DataResult[RealtimeQuote]) -> KeyedStub:
    """Put a keyed stub on the app, keyed by conventional symbol string."""
    stub = KeyedStub(results)
    app.state.market_data = stub
    return stub


# ---------------------------------------------------------------------------
# the batch has no status of its own
# ---------------------------------------------------------------------------


def test_an_empty_pool_is_priced_by_nobody(client: TestClient, app: FastAPI) -> None:
    """Nothing followed means nothing asked — an empty list, not an error."""
    stub = install(app)

    response = client.get(QUOTES)

    assert response.status_code == 200, response.text
    assert response.json() == []
    assert stub.asked == []


def test_every_followed_instrument_is_priced_under_its_own_composite_key(
    client: TestClient,
    app: FastAPI,
) -> None:
    """A row is a (market, code) pair plus that pair's own outcome.

    The second instrument is Shenzhen on purpose: a bare ``000002`` says
    nothing about its venue, and the row must carry the market the pool stored
    rather than let the client guess it back.
    """
    follow(client, "600519")
    follow(client, "000002", market="sz")
    stub = install(
        app,
        **{
            "600519.SH": ok(MOUTAI, 1237.0),
            "000002.SZ": ok(Symbol(market=Market.SZ, code="000002"), 20.5),
        },
    )

    response = client.get(QUOTES)

    assert response.status_code == 200, response.text
    rows = {(row["market"], row["code"]): row for row in response.json()}
    assert set(rows) == {("sh", "600519"), ("sz", "000002")}
    assert rows[("sh", "600519")]["display"] == "600519.SH"
    assert rows[("sh", "600519")]["quote"]["status"] == "ok"
    assert rows[("sh", "600519")]["quote"]["value"]["price"] == 1237.0
    assert rows[("sz", "000002")]["quote"]["value"]["price"] == 20.5
    # The view's row order is its own business; what the spec fixes is that
    # each followed symbol is asked for exactly once.
    assert sorted(symbol.full for symbol in stub.asked) == ["000002.SZ", "600519.SH"]


def test_one_symbols_failure_does_not_contaminate_the_others(
    client: TestClient,
    app: FastAPI,
) -> None:
    """ok, no_data and error coexist; the response is still one 200 list.

    This is the 连坐 test: a batch endpoint that reported one batch-level
    status would have to pick one truth for three rows, and two of them would
    be lies. Each row keeps its own reason or error code instead.
    """
    follow(client, "600519")
    follow(client, "000002", market="sz")
    follow(client, "600036")
    install(
        app,
        **{
            "600519.SH": ok(MOUTAI, 1237.0),
            "000002.SZ": DataResult.no_data("symbol not present", source="stub", fetched_at=STAMP),
            "600036.SH": DataResult.error(
                ErrorCode.DATA_SOURCE_UNAVAILABLE, source="stub", fetched_at=STAMP
            ),
        },
    )

    response = client.get(QUOTES)

    assert response.status_code == 200, response.text
    rows = {(row["market"], row["code"]): row["quote"] for row in response.json()}
    assert rows[("sh", "600519")]["status"] == "ok"
    assert rows[("sh", "600519")]["value"] is not None
    assert rows[("sz", "000002")]["status"] == "no_data"
    assert rows[("sz", "000002")]["reason"] == "symbol not present"
    assert rows[("sz", "000002")]["value"] is None
    assert rows[("sh", "600036")]["status"] == "error"
    assert rows[("sh", "600036")]["error_code"] == ErrorCode.DATA_SOURCE_UNAVAILABLE.value
    assert rows[("sh", "600036")]["value"] is None


def test_a_removed_instrument_is_not_priced(client: TestClient, app: FastAPI) -> None:
    """ "Currently followed" is the whole pool this endpoint prices.

    The stub raises on an unasked-for symbol anyway; ``asked`` makes the
    negative explicit — the router was never consulted about the departure.
    """
    follow(client, "600519")
    client.post(REMOVE, json={"ticker": "600519"})
    follow(client, "600036")
    stub = install(app, **{"600036.SH": ok(Symbol(market=Market.SH, code="600036"), 41.0)})

    response = client.get(QUOTES)

    assert response.status_code == 200, response.text
    rows = response.json()
    assert [(row["market"], row["code"]) for row in rows] == [("sh", "600036")]
    assert [symbol.full for symbol in stub.asked] == ["600036.SH"]


def test_a_stale_price_arrives_still_labelled_stale(client: TestClient, app: FastAPI) -> None:
    """The one honest way to show yesterday's price is to say so.

    The router relabels a cache fallback as ``stale``; this endpoint's duty is
    to carry the label through untouched, so the page can print 「旧」 instead
    of quietly passing an old number off as today's.
    """
    follow(client, "600519")
    stale = ok(MOUTAI, 1237.0).model_copy(update={"stale": True})
    install(app, **{"600519.SH": stale})

    response = client.get(QUOTES)

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["quote"]["status"] == "ok"
    assert row["quote"]["stale"] is True
    assert row["quote"]["value"]["price"] == 1237.0
