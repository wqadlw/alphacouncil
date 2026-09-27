"""Capability-based routing across the key-less sources.

The router owns three decisions that must not leak into callers:

1. **Which provider to ask.** Selection is driven by
   :class:`~alphacouncil.providers.base.ProviderCapabilities` — declared datasets
   and declared venues — never by a hard-coded provider name. Adding a fourth
   source is a registration, not a new ``if``.
2. **What to do when one fails.** Try the next declared source; if all of them
   fail, fall back to the last known good value **labelled stale**. Never
   silently empty the page.
3. **When to stop asking.** A source that answered 403/429 is put in cooldown.
   Retrying a refusal is how an IP gets banned.

Degradation order is explicit and deliberate:

    ``ok`` > ``no_data`` > ``stale`` > ``error``

A source saying "there is nothing" outranks our own cache saying "here is what
it was yesterday", because the first is a statement about *now*. Stale data only
wins when no live source managed to answer at all.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, TypeVar

import structlog

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import (
    DataResult,
    DataStatus,
    Quote,
    RealtimeQuote,
    Symbol,
)
from alphacouncil.providers.base import Dataset, MarketDataProvider, now
from alphacouncil.providers.cache import Cache

log = structlog.get_logger(__name__)

T = TypeVar("T")

# A source that refuses us (403/429) is left alone for a long while.
_BLOCKED_COOLDOWN_S = 300.0
# Transport failures are cheap to hit and cheap to recover from, so the fuse is
# shorter — but it still exists, so a dead source stops costing us latency.
_FAILURE_THRESHOLD = 3
_FAILURE_COOLDOWN_S = 60.0


@dataclass
class _Health:
    """Runtime health of one provider.

    This is *state*, not *capability*: capabilities live on the provider and
    never change, health changes constantly and therefore lives here.
    """

    failures: int = 0
    cooling_until: float = 0.0


class MarketDataRouter:
    """Routes dataset requests across providers, with fallback and caching."""

    def __init__(
        self,
        providers: list[MarketDataProvider],
        *,
        cache: Cache | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """``providers`` is in priority order: first is the preferred source."""
        self._providers = list(providers)
        self._cache = cache
        self._clock = clock
        self._health: dict[str, _Health] = {}

    # -- public API --------------------------------------------------------

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        """Fetch a snapshot, trying each capable source in priority order.

        Snapshots deliberately do **not** accept a cache hit as the answer: a
        cached price is a *past* price, and serving it as the current one would
        be a quiet lie. The cache is still consulted when every source fails —
        but then the result is labelled ``stale``.
        """
        return self._route(
            Dataset.REALTIME,
            symbol,
            cache_key=f"realtime:{symbol.full}",
            call=lambda provider: provider.get_realtime(symbol),
            allow_cached_answer=False,
        )

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        """Fetch daily bars, trying each capable source in priority order.

        History is immutable, so an identical window is served from cache
        without touching the network.
        """
        window = f"{start.isoformat() if start else '-'}:{end.isoformat() if end else '-'}"
        return self._route(
            Dataset.DAILY,
            symbol,
            cache_key=f"daily:{symbol.full}:{window}",
            call=lambda provider: provider.get_daily(symbol, start=start, end=end),
            allow_cached_answer=True,
        )

    def usable_datasets(self, symbol: Symbol) -> frozenset[Dataset]:
        """Datasets at least one *currently awake* provider declares.

        This is the gate the UI asks before rendering a panel. A page must not
        promise a chart it cannot fill (constitution: honest empty states).
        """
        return frozenset(dataset for dataset in Dataset if self._candidates(dataset, symbol))

    # -- internals ---------------------------------------------------------

    def _route(
        self,
        dataset: Dataset,
        symbol: Symbol,
        *,
        cache_key: str,
        call: Callable[[MarketDataProvider], DataResult[T]],
        allow_cached_answer: bool,
    ) -> DataResult[T]:
        """Try capable providers in order and degrade explicitly."""
        if allow_cached_answer and self._cache is not None:
            cached = self._cache.get(cache_key, dataset)
            if cached is not None:
                log.info("router.cache_hit", dataset=dataset.value, symbol=symbol.full)
                return cached

        first_no_data: DataResult[T] | None = None
        first_failure: DataResult[T] | None = None
        attempted: list[str] = []

        for provider in self._candidates(dataset, symbol):
            attempted.append(provider.name)
            result = call(provider)
            self._record(provider.name, result)

            if result.status is DataStatus.OK:
                self._remember(cache_key, result, dataset=dataset)
                return result
            if result.status is DataStatus.NO_DATA:
                if first_no_data is None:
                    first_no_data = result
                continue
            if first_failure is None:
                first_failure = result

        # No live source answered with data. A stale value beats an empty page,
        # but only when nothing authoritative said "there is nothing".
        if first_no_data is None:
            stale: DataResult[T] | None = self._recall(cache_key, dataset)
            if stale is not None:
                log.warning(
                    "router.serving_stale",
                    dataset=dataset.value,
                    symbol=symbol.full,
                    attempted=attempted,
                )
                return stale

        fallback = first_no_data if first_no_data is not None else first_failure
        if fallback is not None:
            log.warning(
                "router.degraded",
                dataset=dataset.value,
                symbol=symbol.full,
                attempted=attempted,
                status=fallback.status.value,
            )
            return fallback

        log.warning(
            "router.no_provider",
            dataset=dataset.value,
            symbol=symbol.full,
            attempted=attempted,
        )
        return DataResult.error(
            ErrorCode.DATA_SOURCE_UNAVAILABLE, source="router", fetched_at=now()
        )

    def _candidates(self, dataset: Dataset, symbol: Symbol) -> list[MarketDataProvider]:
        """Providers that declare the dataset, can serve the venue, and are awake."""
        return [
            provider
            for provider in self._providers
            if dataset in provider.capabilities.datasets
            and symbol.market in provider.capabilities.markets
            and not self._cooling(provider.name)
        ]

    def _cooling(self, name: str) -> bool:
        """Whether a provider is inside a cooldown window."""
        health = self._health.get(name)
        return health is not None and self._clock() < health.cooling_until

    def _record(self, name: str, result: DataResult[Any]) -> None:
        """Update one provider's health from its latest outcome."""
        health = self._health.setdefault(name, _Health())

        if result.status is DataStatus.OK:
            health.failures = 0
            health.cooling_until = 0.0
            return

        if result.error_code is ErrorCode.DATA_SOURCE_FORBIDDEN:
            health.failures += 1
            health.cooling_until = self._clock() + _BLOCKED_COOLDOWN_S
            log.warning(
                "router.provider_blocked",
                provider=name,
                cooldown_s=_BLOCKED_COOLDOWN_S,
            )
            return

        if result.status is DataStatus.ERROR:
            health.failures += 1
            if health.failures >= _FAILURE_THRESHOLD:
                health.cooling_until = self._clock() + _FAILURE_COOLDOWN_S
                log.warning(
                    "router.provider_fused",
                    provider=name,
                    failures=health.failures,
                    cooldown_s=_FAILURE_COOLDOWN_S,
                )

    def _remember(self, key: str, result: DataResult[T], *, dataset: Dataset) -> None:
        """Cache a successful result."""
        if self._cache is not None:
            self._cache.put(key, result, dataset=dataset)

    def _recall(self, key: str, dataset: Dataset) -> DataResult[T] | None:
        """Return the cached value relabelled as stale, or ``None``."""
        if self._cache is None:
            return None
        cached = self._cache.get(key, dataset)
        if cached is None:
            return None
        return cached.model_copy(update={"stale": True})
