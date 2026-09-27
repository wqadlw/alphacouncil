"""The disk-backed cache (spec 006) — the last known good value outlives the process.

Marked ``unit``: the database is a temporary file migrated to the real current
schema, and every clock is injected. The test that matters most is the last
one: a **fresh router instance over the same database file** must still serve
the stale value the previous instance cached — that is "restart", simulated
without a process boundary, and it is the single property MemoryCache could
never offer.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import DataResult, Market, Quote, RealtimeQuote, Symbol
from alphacouncil.providers.base import Dataset, ProviderCapabilities
from alphacouncil.providers.cache import SqliteCache
from alphacouncil.providers.router import MarketDataRouter
from alphacouncil.storage import db, migrate

pytestmark = pytest.mark.unit

STAMP = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
MOUTAI = Symbol(market=Market.SH, code="600519")

#: TTL default is 900s; tests that care about expiry use an injected clock
#: instead of sleeping.
TTL = 900.0


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """A real database file at the current shipped schema version."""
    path = tmp_path / "alphacouncil.db"
    connection = db.connect_for_migration(path)
    try:
        migrate.apply(connection, database_path=path)
    finally:
        connection.close()
    return path


def realtime_result(price: float = 1237.0) -> DataResult[RealtimeQuote]:
    """A well-formed ``ok`` snapshot result."""
    return DataResult.ok(
        RealtimeQuote.model_validate(
            {
                "symbol": MOUTAI,
                "price": price,
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
        ),
        source="stub",
        fetched_at=STAMP,
    )


def daily_result() -> DataResult[list[Quote]]:
    """A well-formed ``ok`` daily-bars result — the other cached payload type."""
    bars = [
        Quote(
            symbol=MOUTAI,
            trade_date=datetime(2026, 9, day, tzinfo=UTC).date(),
            open=1500.0,
            high=1520.0,
            low=1490.0,
            close=1510.0,
            volume=1_000_000.0,
            amount=1.51e9,
            source="stub",
            fetched_at=STAMP,
        )
        for day in (24, 25)
    ]
    return DataResult.ok(bars, source="stub", fetched_at=STAMP)


# ---------------------------------------------------------------------------
# round trips
# ---------------------------------------------------------------------------


def test_a_realtime_result_round_trips_through_the_disk(database_path: Path) -> None:
    """What comes back is a typed result equal to what went in, not a dict."""
    cache = SqliteCache(database_path, ttl_seconds=TTL)
    cache.put("realtime:sh600519", realtime_result(), dataset=Dataset.REALTIME)

    restored = cache.get("realtime:sh600519", Dataset.REALTIME)

    assert restored is not None
    assert restored.status.value == "ok"
    assert restored.value == realtime_result().value
    assert restored.source == "stub"
    assert restored.stale is False


def test_daily_bars_round_trip_as_a_typed_list(database_path: Path) -> None:
    """A list payload rebuilds as ``Quote`` models, preserving order."""
    cache = SqliteCache(database_path, ttl_seconds=TTL)
    cache.put("daily:sh600519:-:", daily_result(), dataset=Dataset.DAILY)

    restored = cache.get("daily:sh600519:-:", Dataset.DAILY)

    assert restored is not None
    assert isinstance(restored.value, list)
    assert all(isinstance(bar, Quote) for bar in restored.value)
    assert [bar.trade_date for bar in restored.value] == [
        datetime(2026, 9, 24, tzinfo=UTC).date(),
        datetime(2026, 9, 25, tzinfo=UTC).date(),
    ]


def test_an_absent_key_reads_as_absent(database_path: Path) -> None:
    cache = SqliteCache(database_path, ttl_seconds=TTL)

    assert cache.get("realtime:sh600519", Dataset.REALTIME) is None


# ---------------------------------------------------------------------------
# expiry
# ---------------------------------------------------------------------------


def test_an_expired_row_reads_as_absent(database_path: Path) -> None:
    """TTL is judged on a wall clock, because a monotonic epoch does not
    survive the restart this cache exists for."""
    now = [1_000_000.0]
    cache = SqliteCache(database_path, ttl_seconds=TTL, clock=lambda: now[0])
    cache.put("realtime:sh600519", realtime_result(), dataset=Dataset.REALTIME)

    now[0] += TTL - 1.0
    assert cache.get("realtime:sh600519", Dataset.REALTIME) is not None

    now[0] += 1.0
    assert cache.get("realtime:sh600519", Dataset.REALTIME) is None


# ---------------------------------------------------------------------------
# damage
# ---------------------------------------------------------------------------


def test_syntactically_broken_json_cannot_enter_the_table(database_path: Path) -> None:
    """The `json_valid` CHECK refuses a truncated payload at write time.

    This is the behaviour test behind the ledger's `json` category. Damage of
    the *semantic* kind (valid JSON the model refuses) is what `get` heals.
    """
    cache = SqliteCache(database_path, ttl_seconds=TTL)
    cache.put("realtime:sh600519", realtime_result(), dataset=Dataset.REALTIME)
    connection = sqlite3.connect(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                'UPDATE market_cache SET payload = \'{"status": "ok", \' WHERE cache_key = ?',
                ("realtime:sh600519",),
            )
    finally:
        connection.close()


def test_a_semantically_damaged_row_is_deleted_and_reports_absent(
    database_path: Path,
) -> None:
    """A row no validator can rebuild must not surface, and must not linger.

    The damage is planted as valid JSON that violates the model contract
    (`ok` without a value) — the shape actual bit-level corruption reaches
    after the `json_valid` CHECK has been satisfied.
    """
    cache = SqliteCache(database_path, ttl_seconds=TTL)
    cache.put("realtime:sh600519", realtime_result(), dataset=Dataset.REALTIME)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            'UPDATE market_cache SET payload = \'{"status": "ok"}\' WHERE cache_key = ?',
            ("realtime:sh600519",),
        )
        connection.commit()
    finally:
        connection.close()

    assert cache.get("realtime:sh600519", Dataset.REALTIME) is None

    connection = sqlite3.connect(database_path)
    try:
        remaining = connection.execute(
            "SELECT count(*) FROM market_cache WHERE cache_key = ?",
            ("realtime:sh600519",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert remaining == 0


def test_an_unknown_dataset_cannot_enter_the_table(database_path: Path) -> None:
    """The dataset whitelist is a schema CHECK, not a convention.

    This is the behaviour test behind the ledger's `enum` category: the
    constraint must refuse, not merely be declared.
    """
    connection = sqlite3.connect(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO market_cache (cache_key, dataset, payload, expires_at) "
                "VALUES ('realtime:sh600519', 'financial', '{}', 0)"
            )
    finally:
        connection.close()


def test_a_failed_write_never_breaks_the_caller(tmp_path: Path) -> None:
    """A cache write may not turn a successful fetch into an error.

    The path is a *directory*: SQLite refuses to open it, which is the same
    class of failure as a locked or unreadable database file.
    """
    cache = SqliteCache(tmp_path / "not-a-database", ttl_seconds=TTL)

    cache.put("realtime:sh600519", realtime_result(), dataset=Dataset.REALTIME)

    assert cache.get("realtime:sh600519", Dataset.REALTIME) is None


# ---------------------------------------------------------------------------
# restart survival — the property this module exists for
# ---------------------------------------------------------------------------


class _OnceThenDeadProvider:
    """Answers correctly once, then refuses everything, forever."""

    name = "flaky"
    capabilities = ProviderCapabilities(datasets=frozenset({Dataset.REALTIME}))

    def __init__(self) -> None:
        self.calls = 0

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        self.calls += 1
        if self.calls == 1:
            return realtime_result()
        return DataResult.error(
            ErrorCode.DATA_SOURCE_UNAVAILABLE, source=self.name, fetched_at=STAMP
        )

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: object = None,
        end: object = None,
    ) -> DataResult[list[Quote]]:
        return DataResult.error(
            ErrorCode.DATA_SOURCE_UNAVAILABLE, source=self.name, fetched_at=STAMP
        )


def test_a_fresh_router_over_the_same_database_still_serves_the_stale_value(
    database_path: Path,
) -> None:
    """Restart, simulated: router A caches, every source dies, router B — a new
    instance over the same file — serves yesterday's price **labelled stale**.

    With MemoryCache this test is impossible by construction; that is the gap
    spec 006 closes.
    """
    provider = _OnceThenDeadProvider()

    first = MarketDataRouter([provider], cache=SqliteCache(database_path, ttl_seconds=TTL))
    live = first.get_realtime(MOUTAI)
    assert live.status.value == "ok"
    assert live.stale is False

    # A brand-new router over the same database: the "new process" of a restart.
    second = MarketDataRouter([provider], cache=SqliteCache(database_path, ttl_seconds=TTL))
    stale = second.get_realtime(MOUTAI)

    assert stale.status.value == "ok"
    assert stale.stale is True
    assert stale.value is not None
    assert stale.value.price == 1237.0
