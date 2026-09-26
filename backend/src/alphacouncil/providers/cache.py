"""Value caching for the router.

The cache exists for one reason: when every live source is down, the last known
good value is still the truth about *yesterday*. Showing that value **labelled
stale** is honest; showing an empty page is a lie of omission. The constitution
distinguishes "the source says there is nothing" from "we could not reach the
source" (4.6), and this module is where that distinction survives an outage.

Only ``ok`` results are cached. Caching a failure would turn a five-second
outage into a five-minute one.

⚠️ ``MemoryCache`` does **not** survive a restart, so it cannot honour the
"show yesterday's close after reopening the app" case. That needs the disk-backed
store, which belongs to the persistence layer (S1) where it can be transactional.
Until then the limitation is real and is stated here rather than hidden.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

from alphacouncil.models.market import DataResult


class Cache(Protocol):
    """The minimal contract the router depends on."""

    def get(self, key: str) -> DataResult[Any] | None:
        """Return the cached result, or ``None`` when absent or expired."""
        ...

    def put(self, key: str, value: DataResult[Any]) -> None:
        """Store a successful result under ``key``."""
        ...


class MemoryCache:
    """In-process TTL cache.

    Keeps the router testable without touching a filesystem. The TTL is short on
    purpose: a stale snapshot is useful for minutes, not days.
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

    def get(self, key: str) -> DataResult[Any] | None:
        """Return the cached result if it has not expired."""
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self._clock() >= expires_at:
            del self._items[key]
            return None
        return value

    def put(self, key: str, value: DataResult[Any]) -> None:
        """Store a result under ``key``."""
        self._items[key] = (self._clock() + self._ttl, value)

    def clear(self) -> None:
        """Drop everything. Used by tests and by an explicit user refresh."""
        self._items.clear()
