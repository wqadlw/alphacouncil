"""Value caching for the router.

The cache exists for one reason: when every live source is down, the last known
good value is still the truth about *yesterday*. Showing that value **labelled
stale** is honest; showing an empty page is a lie of omission. The constitution
distinguishes "the source says there is nothing" from "we could not reach the
source" (4.6), and this module is where that distinction survives an outage.

Only ``ok`` results are cached. Caching a failure would turn a five-second
outage into a five-minute one.

Two implementations:

* :class:`MemoryCache` — in-process, ``monotonic`` clock. Lives on as the
  router tests' lightweight double: no filesystem, no schema, deterministic.
* :class:`SqliteCache` — the production cache (spec 006). Same table row
  survives a restart, which is the whole point: "reopen the app with the
  network down and still see yesterday's close" is a stated acceptance
  criterion, and no process-local structure can honour it.

Both take the ``dataset`` explicitly on every call. The cache never guesses it
from the key — parsing key prefixes couples the two modules by convention, and
an explicit argument lets the disk rows be rebuilt into *typed* payloads.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import structlog

from alphacouncil.models.market import DataResult, Quote, RealtimeQuote
from alphacouncil.providers.base import Dataset
from alphacouncil.storage.db import connect, transaction

log = structlog.get_logger(__name__)

__all__ = ["Cache", "MemoryCache", "SqliteCache"]


class Cache(Protocol):
    """The minimal contract the router depends on.

    ``dataset`` names what is being cached, so an implementation can rebuild
    the payload into its real type on read instead of shipping untyped dicts.
    """

    def get(self, key: str, dataset: Dataset) -> DataResult[Any] | None:
        """Return the cached result, or ``None`` when absent or expired."""
        ...

    def put(self, key: str, value: DataResult[Any], *, dataset: Dataset) -> None:
        """Store a successful result under ``key``."""
        ...


class MemoryCache:
    """In-process TTL cache.

    Keeps the router testable without touching a filesystem. The TTL is short on
    purpose: a stale snapshot is useful for minutes, not days. It does **not**
    survive a restart — that case belongs to :class:`SqliteCache`.
    """

    def __init__(
        self,
        ttl_seconds: float = 900.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: dict[str, tuple[float, DataResult[Any]]] = {}

    def get(self, key: str, dataset: Dataset) -> DataResult[Any] | None:
        """Return the cached result if it has not expired."""
        # `dataset` is protocol parity only: an in-memory dict already holds
        # the typed object the disk cache has to rebuild.
        del dataset
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self._clock() >= expires_at:
            del self._items[key]
            return None
        return value

    def put(self, key: str, value: DataResult[Any], *, dataset: Dataset) -> None:
        """Store a result under ``key``."""
        # Same protocol parity as `get` — see the note there.
        del dataset
        self._items[key] = (self._clock() + self._ttl, value)

    def clear(self) -> None:
        """Drop everything. Used by tests and by an explicit user refresh."""
        self._items.clear()


#: How a stored payload is rebuilt, per dataset. A dataset with no entry is a
#: programming error and fails loudly — a fallback here would silently return
#: untyped dicts and move the corruption downstream instead of stopping it.
_PAYLOAD_VALIDATORS: dict[Dataset, type[DataResult[Any]]] = {
    Dataset.REALTIME: DataResult[RealtimeQuote],
    Dataset.DAILY: DataResult[list[Quote]],
}


class SqliteCache:
    """The disk-backed cache: the last known good value outlives the process.

    One row per cache key, in the same SQLite file as the user's records —
    reusing the store the app already opens, migrates, and backs up rather than
    introducing a second persistence mechanism for disposable data. Rows are
    written transactionally and read back typed; a row that arrives damaged is
    deleted and reported as absent, because a cache must never make things
    worse than having no cache.

    Every operation opens its own connection and closes it — the same
    one-connection-at-a-time discipline as the request path. Cache operations
    are rare (a successful fetch writes; only a total outage reads), so the
    connection setup cost is nothing next to the safety of never sharing a
    connection across threads.
    """

    def __init__(
        self,
        database_path: Path | str,
        ttl_seconds: float = 900.0,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = database_path
        self._ttl = ttl_seconds
        self._clock = clock

    def get(self, key: str, dataset: Dataset) -> DataResult[Any] | None:
        """Return the cached result if present, unexpired, and undamaged."""
        validator = _PAYLOAD_VALIDATORS[dataset]
        try:
            connection = connect(self._path)
            try:
                row = connection.execute(
                    "SELECT payload, expires_at FROM market_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            # The same rule as `put`: a cache that cannot be read must degrade
            # to "no cache", not turn the router's last-resort fallback into a
            # second failure.
            log.warning("cache.read_failed", cache_key=key, error=str(exc))
            return None
        if row is None:
            return None
        if self._clock() >= row["expires_at"]:
            return None
        try:
            return validator.model_validate_json(row["payload"])
        except ValueError as exc:
            # A damaged row can never be served again, so keeping it would
            # guarantee the same warning forever. Delete it and report absence
            # — the source retry that follows is the correct behaviour anyway.
            log.warning("cache.row_damaged", cache_key=key, error=str(exc))
            self._delete(key)
            return None

    def put(self, key: str, value: DataResult[Any], *, dataset: Dataset) -> None:
        """Store a result. Never raises: a cache write may not break a fetch.

        The fetch already succeeded; if recording it fails (a locked database,
        a full disk), the consequence must be "no stale fallback next time",
        not an error page for data that is already in hand.
        """
        payload = value.model_dump_json()
        expires_at = self._clock() + self._ttl
        try:
            connection = connect(self._path)
            try:
                with transaction(connection):
                    connection.execute(
                        "INSERT OR REPLACE INTO market_cache "
                        "(cache_key, dataset, payload, expires_at) VALUES (?, ?, ?, ?)",
                        (key, dataset.value, payload, expires_at),
                    )
            finally:
                connection.close()
        except sqlite3.Error as exc:
            log.warning("cache.write_failed", cache_key=key, error=str(exc))

    def _delete(self, key: str) -> None:
        """Remove one row. Failures here are logged and otherwise ignored."""
        try:
            connection = connect(self._path)
            try:
                connection.execute("DELETE FROM market_cache WHERE cache_key = ?", (key,))
            finally:
                connection.close()
        except sqlite3.Error as exc:
            log.warning("cache.delete_failed", cache_key=key, error=str(exc))
