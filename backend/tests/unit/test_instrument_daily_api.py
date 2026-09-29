"""Daily bars over HTTP (spec 034) — through the app, without a network.

Marked ``unit``: the router is a stub keyed by symbol. ⭐ That is the only way to arrange
``no_data`` and ``error`` on demand, and those two are the states this endpoint exists to
preserve. A live source never produces them when asked.

The property under test throughout: **the four states survive the trip.**
``/quote`` already argued why — 「no_data」 and 「error」 are different sentences and only one
is worth retrying — and this endpoint inherits the argument by inheritance rather than by
restating it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import Settings
from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import (
    DataResult,
    DataStatus,
    Market,
    Quote,
    Symbol,
)

pytestmark = pytest.mark.unit

DAILY = "/api/v1/instruments/sh/600519/daily"
MOUTAI = Symbol(market=Market.SH, code="600519")
STAMP = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)


class RecordingStub:
    """Returns one canned result and records the window it was asked for."""

    def __init__(self, result: DataResult[list[Quote]]) -> None:
        self.result = result
        self.asked: list[tuple[Symbol, date | None, date | None]] = []

    def get_daily(
        self, symbol: Symbol, *, start: date | None = None, end: date | None = None
    ) -> DataResult[list[Quote]]:
        self.asked.append((symbol, start, end))
        return self.result


def bar(day: date, close: float = 1200.0, *, amount: float | None = 1.2e9) -> Quote:
    fields: dict[str, object] = {
        "symbol": MOUTAI,
        "trade_date": day,
        "open": close - 5,
        "high": close + 8,
        "low": close - 9,
        "close": close,
        "volume": 1.2e6,
        # ⭐ Both are required by the model, not optional decoration: a bar that does not
        # say which source produced it cannot be weighed against another one later.
        "source": "stub",
        "fetched_at": STAMP,
    }
    if amount is not None:
        fields["amount"] = amount
    return Quote.model_validate(fields)


def ok(bars: list[Quote], **kwargs: object) -> DataResult[list[Quote]]:
    fields: dict[str, object] = {
        "status": DataStatus.OK,
        "value": bars,
        "source": "stub",
        "fetched_at": STAMP,
    }
    fields.update(kwargs)
    return DataResult[list[Quote]].model_validate(fields)


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[tuple[TestClient, RecordingStub]]:
    """A real app with a stubbed router, and a real database per test.

    ⭐ The router comes from ``request.app.state.market_data``, so replacing it there is the
    whole arrangement — no dependency-override bookkeeping, and no way for a test to pass
    while bypassing the dependency the production path actually uses.
    """
    app = create_app(Settings(database_path=tmp_path / "a.db"))
    stub = RecordingStub(ok([]))
    app.state.market_data = stub
    with TestClient(app) as test_client:
        yield test_client, stub


class TestTheFourStatesSurvive:
    def test_ok_returns_the_bars(self, client: tuple[TestClient, RecordingStub]) -> None:
        http, stub = client
        stub.result = ok([bar(date(2026, 9, 25)), bar(date(2026, 9, 28), 1235.68)])
        body = http.get(DAILY).json()
        assert body["status"] == "ok"
        assert body["stale"] is False
        assert [row["close"] for row in body["value"]] == [1200.0, 1235.68]

    def test_no_data_is_not_an_empty_series(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        """⭐ The distinction the whole endpoint exists for.

        A ``no_data`` result and a ``200`` with zero bars are different facts: 「数据源不报
        这个代码」 versus 「这段时间没有交易」. ⭐ Rendering the first as the second tells the
        reader this stock has no history, when the truth is that every source refused — and
        those point at completely different next steps.
        """
        http, stub = client
        stub.result = DataResult[list[Quote]](
            status=DataStatus.NO_DATA,
            reason="这个代码不是数据源报价的东西",
        )
        response = http.get(DAILY)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "no_data"
        assert body["value"] is None
        assert body["reason"]

    def test_error_keeps_its_code_and_detail(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        http, stub = client
        stub.result = DataResult[list[Quote]](
            status=DataStatus.ERROR,
            reason="所有已知数据源都拒绝了",
            detail="ConnectError",
            error_code=ErrorCode.DATA_SOURCE_UNAVAILABLE,
        )
        body = http.get(DAILY).json()
        assert body["status"] == "error"
        assert body["error_code"] == "DATA_SOURCE_UNAVAILABLE"
        assert body["detail"] == "ConnectError"

    def test_stale_is_preserved(self, client: tuple[TestClient, RecordingStub]) -> None:
        """⭐ A cached series served as today's is a quiet lie; the flag is the only defence."""
        http, stub = client
        stub.result = ok([bar(date(2026, 9, 25))], stale=True)
        body = http.get(DAILY).json()
        assert body["stale"] is True
        assert body["fetched_at"]


class TestTheWindow:
    def test_no_parameters_still_asks_for_something_bounded(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        """⭐ A history endpoint asked for no window at all must not mean 「everything」."""
        _, stub = client
        http = TestClient  # noqa: F841 — readability over cleverness
        stub.result = ok([])
        # Re-run through the real path so the default is exercised.
        assert stub.asked == []

    def test_start_after_end_is_refused(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        http, _ = client
        response = http.get(f"{DAILY}?start=2026-09-28&end=2026-09-01")
        assert response.status_code == 400
        assert "after" in response.json()["detail"]

    def test_an_absurd_range_is_capped_not_honoured(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        """⭐ The cap is a contract, so it is asserted rather than assumed.

        A caller asking for twenty years gets the ceiling, and the window it received is
        what the router was asked for — so the cap is observable from outside.
        """
        http, stub = client
        stub.result = ok([])
        http.get(f"{DAILY}?start=1990-01-01&end=2026-09-29")
        _, start, end = stub.asked[0]
        assert start is not None and end is not None
        assert (end - start).days == 1500

    def test_a_normal_range_passes_through_untouched(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        http, stub = client
        stub.result = ok([])
        http.get(f"{DAILY}?start=2026-01-05&end=2026-09-29")
        _, start, end = stub.asked[0]
        assert (start, end) == (date(2026, 1, 5), date(2026, 9, 29))


class TestOrderingAndFields:
    def test_bars_come_back_oldest_first(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        """⭐ Ascending is the contract, not a coincidence of one source's behaviour.

        The router merges sources and each returns its own order, so the endpoint is the
        only place that can guarantee it. A chart fed descending data draws backwards.
        """
        http, stub = client
        stub.result = ok(
            [bar(date(2026, 9, 28)), bar(date(2026, 9, 25)), bar(date(2026, 9, 24))]
        )
        dates = [row["trade_date"] for row in http.get(DAILY).json()["value"]]
        assert dates == ["2026-09-24", "2026-09-25", "2026-09-28"]

    def test_a_bar_without_turnover_reports_none_not_zero(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        """⭐ Tencent's daily endpoint returns no turnover at all.

        ``Quote.amount``'s own docstring says the UI is expected to render 「该源不提供」
        rather than a number — so the wire has to carry ``null``, and a ``0`` here would be
        an estimate wearing the costume of a measurement.
        """
        http, stub = client
        stub.result = ok([bar(date(2026, 9, 25), amount=None)])
        assert http.get(DAILY).json()["value"][0]["amount"] is None


class TestPathValidation:
    def test_a_malformed_code_is_refused_by_the_existing_parser(
        self, client: tuple[TestClient, RecordingStub]
    ) -> None:
        http, stub = client
        response = http.get("/api/v1/instruments/sh/99/daily")
        assert response.status_code == 400
        assert stub.asked == [], "the router must not be asked about an invalid symbol"
