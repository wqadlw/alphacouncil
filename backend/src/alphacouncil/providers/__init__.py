"""Market data providers and the router that chooses between them.

Public surface of the data boundary. Everything above this package talks to
:class:`MarketDataRouter` and the models in :mod:`alphacouncil.models.market`;
it never imports a concrete provider, so swapping a source is a local change.
"""

from alphacouncil.core.trace import TraceHook
from alphacouncil.providers.base import (
    BatchSemantics,
    Dataset,
    MarketDataProvider,
    ProviderBlockedError,
    ProviderCapabilities,
    ProviderEmptyError,
    ProviderError,
    ProviderIpBlockedError,
    ProviderProtocolError,
    ProviderRateLimitedError,
    ProviderUnreachableError,
)
from alphacouncil.providers.cache import Cache, MemoryCache, SqliteCache
from alphacouncil.providers.financial import (
    BaostockFinancial,
    FinancialDataProvider,
    FinancialPeriod,
)
from alphacouncil.providers.router import MarketDataRouter
from alphacouncil.providers.sources import (
    EastmoneyProvider,
    SinaProvider,
    TencentProvider,
)

__all__ = [
    "BaostockFinancial",
    "BatchSemantics",
    "Cache",
    "Dataset",
    "EastmoneyProvider",
    "FinancialDataProvider",
    "FinancialPeriod",
    "MarketDataProvider",
    "MarketDataRouter",
    "MemoryCache",
    "ProviderBlockedError",
    "ProviderCapabilities",
    "ProviderEmptyError",
    "ProviderError",
    "ProviderIpBlockedError",
    "ProviderProtocolError",
    "ProviderRateLimitedError",
    "ProviderUnreachableError",
    "SinaProvider",
    "SqliteCache",
    "TencentProvider",
    "default_router",
]


def default_router(
    *, cache: Cache | None = None, tracer: TraceHook | None = None
) -> MarketDataRouter:
    """Build the production router.

    The order looks odd — the fragile source first — until you remember that
    selection is capability-driven. Eastmoney is skipped entirely for snapshots
    (it declares no ``REALTIME``), so snapshots resolve to Tencent then Sina;
    history resolves to Eastmoney first because it is the only source that also
    publishes turnover, with Tencent as the fallback that at least has prices.

    One global ordering, two different effective priorities. That is the whole
    point of declaring capabilities instead of hard-coding names.
    """
    return MarketDataRouter(
        [EastmoneyProvider(), TencentProvider(), SinaProvider()],
        cache=cache if cache is not None else MemoryCache(),
        tracer=tracer,
    )
