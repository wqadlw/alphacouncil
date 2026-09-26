"""The watchlist API and the repository under it, exercised through HTTP.

Marked ``unit``: no network. The database is real — a temporary file per test,
supplied by the ``_isolated_database`` fixture — because most of what is worth
asserting here *is* the database: that the triggers refuse an update, that the
view hides a removed instrument, that the append-only log keeps every event.

The distinction matters for what this file can prove. A test that mocked the
repository would confirm that the route calls it, which is the least interesting
property in the module.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import get_settings
from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.storage.db import connect

pytestmark = pytest.mark.unit

ADD = "/api/v1/watchlist"
REASON = "/api/v1/watchlist/reason"
REMOVE = "/api/v1/watchlist/remove"
RESOLVE = "/api/v1/instruments/resolve"

#: `.ai/error-codes.md` §1 fixes the envelope at exactly these keys.
ENVELOPE_KEYS = {"severity", "code", "message", "target", "fix"}


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


def follow(client: TestClient, ticker: str = "600519", **extra: object) -> dict[str, object]:
    """Add an instrument and return the receipt, failing loudly if it did not work."""
    response = client.post(ADD, json={"ticker": ticker, "reason": "估值到了区间", **extra})
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestAddingAnInstrument:
    def test_an_empty_pool_lists_nothing(self, client: TestClient) -> None:
        response = client.get(ADD)

        assert response.status_code == 200
        assert response.json() == []

    def test_adding_returns_a_receipt(self, client: TestClient) -> None:
        body = follow(client)

        assert body["kind"] == "added"
        assert body["market"] == "sh"
        assert body["code"] == "600519"
        assert body["reason"] == "估值到了区间"
        assert body["supersedes_id"] is None
        assert isinstance(body["event_id"], int)

    def test_the_receipt_timestamp_is_the_form_the_schema_accepts(
        self, client: TestClient, database: sqlite3.Connection
    ) -> None:
        """The column has a round-trip CHECK, so this is not a formatting opinion.

        SQLite renders the stored value back and rejects the row unless it comes
        out identical. Asserting the round trip here means a change to
        ``core.time`` fails in a test rather than at a user's first save.
        """
        stamp = str(follow(client)["occurred_at"])
        rendered = database.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', ?)", (stamp,)
        ).fetchone()[0]

        assert rendered == stamp

    def test_the_added_instrument_appears_in_the_list(self, client: TestClient) -> None:
        follow(client)

        entries = client.get(ADD).json()

        assert len(entries) == 1
        assert entries[0]["code"] == "600519"
        assert entries[0]["reason"] == "估值到了区间"
        assert entries[0]["asset_type"] == "stock"

    def test_the_instrument_row_is_created_once(self, client: TestClient) -> None:
        """Adding twice logs two events but does not duplicate the instrument."""
        follow(client)
        follow(client)

        assert len(client.get(ADD).json()) == 1
        assert client.get(ADD).json()[0]["code"] == "600519"


class TestReasonsAreRequired:
    def test_a_blank_reason_is_refused_with_a_code(self, client: TestClient) -> None:
        response = client.post(ADD, json={"ticker": "600519", "reason": "   "})

        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.WATCHLIST_REASON_REQUIRED.value

    def test_an_empty_reason_is_refused_by_the_schema(self, client: TestClient) -> None:
        """Caught before the domain sees it — the outer layer of three."""
        response = client.post(ADD, json={"ticker": "600519", "reason": ""})

        assert response.status_code == 422

    def test_an_over_long_reason_is_refused_by_the_schema(self, client: TestClient) -> None:
        response = client.post(ADD, json={"ticker": "600519", "reason": "x" * 2001})

        assert response.status_code == 422

    def test_a_missing_reason_is_refused_by_the_schema(self, client: TestClient) -> None:
        response = client.post(ADD, json={"ticker": "600519"})

        assert response.status_code == 422


class TestAmbiguityIsAQuestion:
    def test_an_ambiguous_ticker_is_refused_with_its_code(self, client: TestClient) -> None:
        response = client.post(ADD, json={"ticker": "000001", "reason": "跟踪上证指数"})

        assert response.status_code == 400
        assert response.json()["code"] == ErrorCode.DATA_SOURCE_TICKER_AMBIGUOUS.value

    def test_supplying_the_market_resolves_it(self, client: TestClient) -> None:
        body = follow(client, "000001", market="sh", asset_type="index")

        assert body["market"] == "sh"
        assert client.get(ADD).json()[0]["asset_type"] == "index"

    def test_the_two_readings_are_different_instruments(self, client: TestClient) -> None:
        """The whole reason ``(market, code)`` is the key."""
        follow(client, "000001", market="sh", asset_type="index")
        follow(client, "000001", market="sz", asset_type="stock")

        codes = {(entry["market"], entry["code"]) for entry in client.get(ADD).json()}

        assert codes == {("sh", "000001"), ("sz", "000001")}


class TestTheResolveEndpoint:
    def test_an_unambiguous_ticker_resolves(self, client: TestClient) -> None:
        body = client.get(RESOLVE, params={"ticker": "600519"}).json()

        assert body["status"] == "resolved"
        assert body["market"] == "sh"
        assert body["display"] == "600519.SH"
        assert body["candidates"] == []

    def test_an_ambiguous_ticker_returns_the_choices_not_an_error(
        self, client: TestClient
    ) -> None:
        """A 200, because being one answer short of valid is not a failure."""
        response = client.get(RESOLVE, params={"ticker": "000001"})

        assert response.status_code == 200
        assert response.json()["status"] == "ambiguous"
        assert response.json()["candidates"] == ["sh", "sz"]

    def test_a_malformed_ticker_is_an_envelope(self, client: TestClient) -> None:
        response = client.get(RESOLVE, params={"ticker": "sz600519"})

        assert response.status_code == 400
        assert set(response.json()) == ENVELOPE_KEYS
        assert response.json()["code"] == ErrorCode.DATA_SOURCE_TICKER_INVALID.value


class TestRevisingTheReason:
    def test_a_revision_supersedes_the_previous_event(self, client: TestClient) -> None:
        first = follow(client)

        response = client.post(REASON, json={"ticker": "600519", "reason": "营收增速下来了"})

        assert response.status_code == 200
        assert response.json()["kind"] == "reason_revised"
        assert response.json()["supersedes_id"] == first["event_id"]

    def test_the_list_shows_the_new_reason(self, client: TestClient) -> None:
        follow(client)
        client.post(REASON, json={"ticker": "600519", "reason": "营收增速下来了"})

        entries = client.get(ADD).json()

        assert len(entries) == 1
        assert entries[0]["reason"] == "营收增速下来了"

    def test_both_reasons_are_still_on_disk(
        self, client: TestClient, database: sqlite3.Connection
    ) -> None:
        """The point of the log: the earlier wording is not overwritten.

        Without this, "you said this three times" is unanswerable, because the
        first two would have been replaced rather than superseded.
        """
        follow(client)
        client.post(REASON, json={"ticker": "600519", "reason": "营收增速下来了"})

        reasons = [
            row[0]
            for row in database.execute(
                "SELECT reason FROM watchlist_events WHERE code = '600519' ORDER BY id"
            )
        ]

        assert reasons == ["估值到了区间", "营收增速下来了"]

    def test_revising_an_unknown_instrument_is_a_404(self, client: TestClient) -> None:
        response = client.post(REASON, json={"ticker": "600519", "reason": "x"})

        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.WATCHLIST_NOT_FOLLOWED.value


class TestRemoving:
    def test_removing_hides_it_from_the_list(self, client: TestClient) -> None:
        follow(client)

        response = client.post(REMOVE, json={"ticker": "600519", "reason": "论点被证伪"})

        assert response.status_code == 200
        assert response.json()["kind"] == "removed"
        assert client.get(ADD).json() == []

    def test_removing_does_not_delete_anything(
        self, client: TestClient, database: sqlite3.Connection
    ) -> None:
        """The row survives, and so does the instrument."""
        follow(client)
        client.post(REMOVE, json={"ticker": "600519"})

        events = database.execute("SELECT count(*) FROM watchlist_events").fetchone()[0]
        instruments = database.execute("SELECT count(*) FROM instruments").fetchone()[0]

        assert (events, instruments) == (2, 1)

    def test_removing_twice_is_a_conflict(self, client: TestClient) -> None:
        follow(client)
        client.post(REMOVE, json={"ticker": "600519"})

        response = client.post(REMOVE, json={"ticker": "600519"})

        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.WATCHLIST_ALREADY_REMOVED.value

    def test_revising_after_removal_is_a_conflict(self, client: TestClient) -> None:
        follow(client)
        client.post(REMOVE, json={"ticker": "600519"})

        response = client.post(REASON, json={"ticker": "600519", "reason": "x"})

        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.WATCHLIST_ALREADY_REMOVED.value

    def test_re_adding_after_removal_works(self, client: TestClient) -> None:
        follow(client)
        client.post(REMOVE, json={"ticker": "600519"})

        follow(client)

        assert len(client.get(ADD).json()) == 1


class TestThereIsNoDelete:
    def test_the_route_does_not_exist(self, client: TestClient) -> None:
        """Not an oversight: nothing is ever deleted, so no verb should imply it."""
        assert client.delete(ADD).status_code == 405


class TestTheSchemaRefusesWhatTheApiMightMiss:
    """The database is the guarantee; the API is the friendly message."""

    def test_the_log_cannot_be_updated(
        self, client: TestClient, database: sqlite3.Connection
    ) -> None:
        follow(client)

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute("UPDATE watchlist_events SET reason = 'rewritten'")

    def test_the_log_cannot_be_deleted(
        self, client: TestClient, database: sqlite3.Connection
    ) -> None:
        follow(client)

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            database.execute("DELETE FROM watchlist_events")

    def test_a_blank_reason_cannot_be_inserted_directly(
        self, client: TestClient, database: sqlite3.Connection
    ) -> None:
        """Bypassing the domain does not bypass the rule."""
        follow(client)

        with pytest.raises(sqlite3.IntegrityError, match="not_blank"):
            database.execute(
                "INSERT INTO watchlist_events "
                "(occurred_at, market, code, kind, reason) VALUES (?, 'sh', '600519', "
                "'added', '   ')",
                ("2026-09-26T00:00:00.000Z",),
            )


class TestTheEnvelopeIsOneShape:
    def test_every_coded_failure_uses_the_same_five_keys(self, client: TestClient) -> None:
        failures = [
            client.post(ADD, json={"ticker": "000001", "reason": "x"}),
            client.post(ADD, json={"ticker": "600519", "reason": "   "}),
            client.post(REASON, json={"ticker": "600519", "reason": "x"}),
            client.get(RESOLVE, params={"ticker": "not-a-ticker"}),
        ]

        for response in failures:
            assert response.status_code in {400, 404, 409}, response.text
            assert set(response.json()) == ENVELOPE_KEYS, response.text

    def test_an_asset_type_conflict_is_a_409(self, client: TestClient) -> None:
        follow(client)

        response = client.post(
            ADD, json={"ticker": "600519", "asset_type": "etf", "reason": "换个类型"}
        )

        assert response.status_code == 409
        assert response.json()["code"] == ErrorCode.INSTRUMENT_ASSET_TYPE_CONFLICT.value

    def test_a_database_is_never_left_holding_a_half_written_request(
        self, client: TestClient, database: sqlite3.Connection
    ) -> None:
        """A refused write rolls the whole transaction back, instrument included.

        The instrument is inserted before the event, so a failure between the two
        would otherwise leave a followed instrument with no reason — the exact
        state the product forbids.
        """
        response = client.post(ADD, json={"ticker": "600519", "reason": "   "})

        assert response.status_code == 400
        assert database.execute("SELECT count(*) FROM instruments").fetchone()[0] == 0


class TestTheDatabaseFile:
    def test_tests_do_not_touch_the_users_database(self) -> None:
        """A guard on the guard.

        The app factory migrates on startup, so a test that resolved the default
        path would write to the real per-user file. This asserts the fixture is
        doing its job, because the failure is silent — the suite stays green
        while the developer's database is being migrated.
        """
        resolved = Path(get_settings().database_path)

        assert resolved.parent.name != "AlphaCouncil"
        assert "tmp" in str(resolved).lower() or "pytest" in str(resolved).lower()
