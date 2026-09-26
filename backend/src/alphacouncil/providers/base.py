"""Data provider protocol and capability declarations.

Design borrowed from the TSP review (see ``references/deep-dives/12``):

* **A capability is a dataset, not a feature.** Providers declare which
  *datasets* they can serve, so "can this page work?" becomes a mechanical
  question instead of a guess.
* **Capabilities are booleans, state is an enum.** "Does this provider support
  daily bars" is a fact about the provider. "Is the provider healthy right now"
  is runtime state and belongs in the router, not here.
* **Batch failure semantics must be declared.** Some sources fail a whole batch
  when one symbol is bad (collateral failure); others fail per symbol. The
  router needs to know which, otherwise one bad code silently kills a page.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import DataResult, Market, Quote, RealtimeQuote, Symbol


class _FrozenModel(BaseModel):
    """Immutable, strict model."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Dataset(StrEnum):
    """A standardised dataset a provider may or may not be able to serve."""

    DAILY = "daily"
    REALTIME = "realtime"
    ADJ_FACTOR = "adj_factor"
    FINANCIAL = "financial"
    INSTRUMENTS = "instruments"


class BatchSemantics(StrEnum):
    """How a provider behaves when one symbol in a batch is unsupported.

    ``COLLATERAL`` means the whole request fails — observed in the wild on
    index-snapshot endpoints. The router must pre-filter unsupported codes
    before calling such a provider, or a single bad code blanks the page.
    """

    INDEPENDENT = "independent"
    COLLATERAL = "collateral"


class ProviderCapabilities(_FrozenModel):
    """What a provider can serve, and how it behaves."""

    datasets: frozenset[Dataset] = Field(default_factory=frozenset)
    markets: frozenset[Market] = Field(
        default_factory=lambda: frozenset(Market),
        description=(
            "Venues this provider can actually serve. The router pre-filters on "
            "this instead of sending a request the source will answer with null — "
            "an unverified venue is a claim we must not make."
        ),
    )
    batch_semantics: BatchSemantics = BatchSemantics.INDEPENDENT
    supports_batch: bool = False
    notes: str | None = Field(
        default=None,
        description="Must state how this provider differs from the primary one.",
    )


class ProviderError(Exception):
    """Base class for provider failures.

    ``code`` is drawn from the same :class:`ErrorCode` enum the data results
    use. Keeping one namespace matters: a second, private set of strings is how
    the same failure ends up reported two different ways depending on which
    layer noticed it first.
    """

    code: ErrorCode = ErrorCode.DATA_FETCH_ERROR


class ProviderUnreachableError(ProviderError):
    """Network-level failure: timeout, DNS, connection reset."""

    code = ErrorCode.DATA_SOURCE_UNREACHABLE


class ProviderBlockedError(ProviderError):
    """The provider refused us (403 / rate limit).

    The router treats this as non-retryable: hammering a source that already
    said no is how an IP gets banned.
    """

    code = ErrorCode.DATA_SOURCE_FORBIDDEN


class ProviderProtocolError(ProviderError):
    """The provider answered, but not in the shape we expect."""

    code = ErrorCode.DATA_UNVERIFIABLE


class ProviderEmptyError(ProviderError):
    """The provider answered successfully and there is genuinely no data."""

    code = ErrorCode.DATA_NO_DATA


@runtime_checkable
class MarketDataProvider(Protocol):
    """A source of market data.

    Implementations must:

    * convert units, dates and code formats at this boundary — callers only
      ever see the internal standard format;
    * return :class:`DataResult` rather than raising for *expected* absences
      ("this symbol has no data") — raising is reserved for genuine faults;
    * never return an empty list to mean failure. Empty means empty.
    """

    @property
    def name(self) -> str:
        """Short identifier used in logs and provenance fields."""
        ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Declared datasets and batch behaviour."""
        ...

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        """Fetch daily bars for one symbol.

        ``start``/``end`` are real :class:`datetime.date` values, not the string
        format any particular source happens to want. Converting ``2026-09-18``
        into ``20260918`` for Eastmoney and keeping the dashes for Tencent is the
        provider's job — callers must never see a source-specific date format.
        """
        ...

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        """Fetch a realtime snapshot for one symbol."""
        ...


def now() -> datetime:
    """Return the current local timestamp.

    Wrapped so tests can freeze time without patching the stdlib globally.
    """
    return datetime.now()
