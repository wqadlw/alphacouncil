"""Market data contracts (v2).

These models are the **boundary contract** between external data sources and
everything above them. Three rules from the project constitution are encoded
here as types rather than conventions:

1. **Data has four states, not two** (constitution 4.6). ``ok`` / ``no_data`` /
   ``error`` / ``unavailable`` — "the source says there is nothing" and "the
   source is broken" are different facts and must not be collapsed.
2. **Units are explicit** (constitution 4.2). Prices are in CNY, percentages are
   **decimal fractions** (``0.0512`` means 5.12%), dates are trading dates.
   Conversion happens only in :mod:`alphacouncil.providers`.
3. **Every external value carries provenance** (spec FR-7): ``source`` and
   ``fetched_at`` are mandatory on any model that came from outside.

Asset type is stored explicitly rather than inferred from the code prefix —
guessing "this looks like an index" is a bug generator (see the TSP review).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from alphacouncil.core.error_codes import ErrorCode


class _FrozenModel(BaseModel):
    """Immutable, strict, no unexpected fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class Market(StrEnum):
    """Exchange venue."""

    SH = "sh"
    SZ = "sz"
    BJ = "bj"


class AssetType(StrEnum):
    """Asset class. Explicit — never inferred from the code format."""

    STOCK = "stock"
    INDEX = "index"
    ETF = "etf"


class DataStatus(StrEnum):
    """The four states of a data fetch (constitution 4.6).

    ``UNAVAILABLE`` exists for values that are present but cannot be verified
    (e.g. a field whose unit was never declared). Such a value is not ``no_data``
    — it exists — but it must never be presented as fact.
    """

    OK = "ok"
    NO_DATA = "no_data"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class Symbol(_FrozenModel):
    """A normalised instrument identifier.

    ``600519`` on the Shanghai exchange, an index, and an ETF are three
    different things that may share a code shape; ``asset_type`` makes the
    distinction explicit so no downstream code has to guess.
    """

    market: Market
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    asset_type: AssetType = AssetType.STOCK

    @property
    def full(self) -> str:
        """Return the conventional ``600519.SH`` form."""
        return f"{self.code}.{self.market.value.upper()}"


class Quote(_FrozenModel):
    """A single daily OHLCV bar, adjusted-close consistent.

    ``adj_factor`` is stored alongside the prices so that a series can be
    re-derived at any adjustment basis without re-fetching (constitution 4.2:
    adjustment basis is one of the four non-interchangeable units).

    ``amount`` is **optional on purpose**. Tencent's daily endpoint returns
    ``[date, open, close, high, low, volume]`` with no turnover at all — verified
    against a live response on 2026-09-26. Filling in ``close * volume`` would be
    an estimate wearing the costume of a measurement, so the field is ``None``
    and the UI is expected to render "该源不提供" rather than a number.
    """

    symbol: Symbol
    trade_date: date
    open: float = Field(ge=0.0)
    high: float = Field(ge=0.0)
    low: float = Field(ge=0.0)
    close: float = Field(ge=0.0)
    volume: float = Field(ge=0.0, description="Shares.")
    amount: float | None = Field(
        default=None,
        ge=0.0,
        description="Turnover in CNY. None when the source does not publish it.",
    )
    adj_factor: float = Field(default=1.0, gt=0.0)
    source: str = Field(min_length=1)
    fetched_at: datetime

    @model_validator(mode="after")
    def _check_bar_consistency(self) -> Quote:
        """Reject internally inconsistent bars instead of storing them.

        A bar with ``high < low``, or a close outside the high/low range, is a
        source error. Silently persisting it would poison every later
        calculation, which is exactly the failure mode the constitution calls
        out: financial data errors rarely raise, they produce plausible numbers.
        """
        if self.high < self.low:
            msg = f"high ({self.high}) < low ({self.low})"
            raise ValueError(msg)
        if not (self.low <= self.close <= self.high):
            msg = f"close ({self.close}) outside [{self.low}, {self.high}]"
            raise ValueError(msg)
        if not (self.low <= self.open <= self.high):
            msg = f"open ({self.open}) outside [{self.low}, {self.high}]"
            raise ValueError(msg)
        return self


class RealtimeQuote(_FrozenModel):
    """A snapshot quote.

    ``change_pct`` is a **decimal fraction** (``0.0114`` = +1.14%). Sources that
    return percentage points must convert before constructing this model.
    """

    symbol: Symbol
    price: float = Field(ge=0.0, description="Last price in CNY.")
    prev_close: float = Field(gt=0.0, description="Previous close in CNY.")
    open: float = Field(ge=0.0)
    high: float = Field(ge=0.0)
    low: float = Field(ge=0.0)
    volume: float = Field(ge=0.0)
    amount: float = Field(ge=0.0)
    quoted_at: datetime
    source: str = Field(min_length=1)
    fetched_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _drop_serialised_computed(cls, data: object) -> object:
        """Tolerate this model's own serialisation.

        ``change_pct`` is a ``computed_field``, so ``model_dump_json`` writes it
        — and a strict re-validation of that JSON would refuse it as an extra
        input, breaking every dump→validate round trip (the disk cache is one;
        a client echoing a payload back is another). The key is dropped, never
        trusted: the value recomputed from ``price`` / ``prev_close`` is the
        only authoritative one (constitution 4.2 — one implementation of a
        percentage).
        """
        if isinstance(data, dict) and "change_pct" in data:
            del data["change_pct"]
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def change_pct(self) -> float:
        """The change as a decimal fraction, computed not trusted.

        ``computed_field`` rather than a plain ``property`` so the value is
        *serialised*: the alternative is every client re-deriving it from
        ``price`` and ``prev_close``, and a second implementation of a
        percentage is a second chance to disagree about rounding, sign, or
        whether the unit is a fraction or percentage points (constitution 4.2).
        The client formats what it is given; it does not divide.
        """
        return (self.price - self.prev_close) / self.prev_close


class DataResult[T](_FrozenModel):
    """A fetch outcome that can express all four states.

    The validator below is the enforcement point: it makes it impossible to
    build an ``ok`` result with no value, or an ``error`` with no code. That
    turns "handle failure honestly" from a code-review rule into a runtime
    guarantee (constitution 0.2, level ④).
    """

    status: DataStatus
    value: T | None = None
    reason: str | None = Field(default=None, description="Why there is no data.")
    detail: str | None = Field(
        default=None,
        description=(
            "Technical detail behind an error — an exception name, a raw message. "
            "Kept apart from ``reason``, which is the business explanation."
        ),
    )
    error_code: ErrorCode | None = Field(
        default=None,
        description="Machine-readable code. Must come from the managed namespace.",
    )
    source: str | None = None
    fetched_at: datetime | None = None
    stale: bool = Field(
        default=False,
        description=(
            "True when every live source failed and this value is the last "
            "known good one from cache. Stale values keep their original "
            "source and fetched_at, and must be shown to the user as old."
        ),
    )

    @model_validator(mode="after")
    def _check_state_consistency(self) -> DataResult[T]:
        """Each state carries exactly the fields it needs."""
        if self.status is DataStatus.OK:
            if self.value is None:
                msg = "status=ok requires a value"
                raise ValueError(msg)
            if self.source is None or self.fetched_at is None:
                msg = "status=ok requires source and fetched_at (provenance rule)"
                raise ValueError(msg)
        elif self.status is DataStatus.NO_DATA:
            if not self.reason:
                msg = "status=no_data requires a reason"
                raise ValueError(msg)
            if self.value is not None:
                msg = "status=no_data must not carry a value"
                raise ValueError(msg)
        elif self.status is DataStatus.ERROR:
            if not self.error_code:
                msg = "status=error requires an error_code"
                raise ValueError(msg)
            if self.value is not None:
                msg = "status=error must not carry a value"
                raise ValueError(msg)
        elif self.status is DataStatus.UNAVAILABLE and not self.reason:
            msg = "status=unavailable requires a reason (what could not be verified)"
            raise ValueError(msg)
        return self

    @classmethod
    def ok(cls, value: T, *, source: str, fetched_at: datetime) -> DataResult[T]:
        """Build a successful result."""
        return cls(status=DataStatus.OK, value=value, source=source, fetched_at=fetched_at)

    @classmethod
    def no_data(cls, reason: str, *, source: str, fetched_at: datetime) -> DataResult[T]:
        """Build a result for "the source answered, and the answer is: nothing"."""
        return cls(
            status=DataStatus.NO_DATA,
            reason=reason,
            source=source,
            fetched_at=fetched_at,
        )

    @classmethod
    def error(
        cls,
        error_code: ErrorCode,
        *,
        source: str,
        fetched_at: datetime,
        detail: str | None = None,
    ) -> DataResult[T]:
        """Build a result for "the fetch failed".

        ``error_code`` is typed as :class:`ErrorCode`, so an invented or
        misspelled code cannot be constructed — the rule "unregistered codes
        must not appear in code" is enforced by the type checker rather than by
        review.
        """
        return cls(
            status=DataStatus.ERROR,
            error_code=error_code,
            detail=detail,
            source=source,
            fetched_at=fetched_at,
        )

    @classmethod
    def unavailable(cls, reason: str, *, source: str, fetched_at: datetime) -> DataResult[T]:
        """Build a result for "present but unverifiable"."""
        return cls(
            status=DataStatus.UNAVAILABLE,
            reason=reason,
            source=source,
            fetched_at=fetched_at,
        )
