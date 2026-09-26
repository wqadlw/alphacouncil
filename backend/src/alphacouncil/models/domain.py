"""Domain models shared across layers.

All models are immutable (``frozen=True``) so that a value, once produced by a
retrieval or data layer, cannot be mutated in place by a downstream agent. This
makes runs reproducible and eliminates a class of hard-to-trace bugs.

Traceability rule: every model that originates from an external source carries
``source`` and ``fetched_at``, per spec 001 FR-7.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _FrozenModel(BaseModel):
    """Base class: immutable, strict, no unexpected fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class StatementType(StrEnum):
    """Financial statement categories."""

    INCOME = "income"
    BALANCE = "balance"
    CASHFLOW = "cashflow"


class RecallRoute(StrEnum):
    """Retrieval routes, as defined in spec 002."""

    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    STRUCTURED = "structured"


class Quote(_FrozenModel):
    """A single daily OHLCV bar."""

    code: str = Field(min_length=1, description="Ticker code, e.g. '600519'.")
    trade_date: date
    open: float = Field(ge=0.0)
    high: float = Field(ge=0.0)
    low: float = Field(ge=0.0)
    close: float = Field(ge=0.0)
    volume: float = Field(ge=0.0)
    amount: float = Field(ge=0.0)
    adj_factor: float = Field(default=1.0, gt=0.0)
    source: str = Field(min_length=1)
    fetched_at: datetime

    @field_validator("high", "low")
    @classmethod
    def _check_high_low_ordering(cls, value: float) -> float:
        """Reject negative prices; ordering is validated at the model level."""
        if value < 0:
            msg = "price must be non-negative"
            raise ValueError(msg)
        return value

    def is_valid_bar(self) -> bool:
        """Return whether the bar is internally consistent.

        A bar where ``high < low`` indicates a data source error and should be
        discarded rather than silently stored.
        """
        return self.high >= self.low


class FinancialItem(_FrozenModel):
    """A single line item from a financial statement."""

    code: str = Field(min_length=1)
    report_date: date
    statement_type: StatementType
    item: str = Field(min_length=1)
    value: float
    source: str = Field(min_length=1)
    fetched_at: datetime


class RetrievedDoc(_FrozenModel):
    """A retrieved document chunk with full traceability.

    Spec 002 FR-12 requires every result to carry its provenance, and FR-13
    requires answers to cite it. ``route_ranks`` records where this document
    placed in each recall route, which is what makes fusion auditable.
    """

    doc_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Origin document, e.g. a filing name.")
    page: int | None = Field(default=None, ge=1)
    score: float = Field(default=0.0, ge=0.0)
    route_ranks: dict[RecallRoute, int] = Field(
        default_factory=dict,
        description="Rank of this document per recall route (1-based).",
    )

    @field_validator("route_ranks")
    @classmethod
    def _check_ranks_positive(cls, value: dict[RecallRoute, int]) -> dict[RecallRoute, int]:
        """Ranks are 1-based; a zero or negative rank signals a fusion bug."""
        for route, rank in value.items():
            if rank < 1:
                msg = f"route_ranks[{route}] must be >= 1, got {rank}"
                raise ValueError(msg)
        return value


class Citation(_FrozenModel):
    """A reference from a generated claim back to its evidence."""

    doc_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    snippet: str = Field(min_length=1, description="Verbatim supporting text.")


class ResearchRequest(_FrozenModel):
    """An inbound research question."""

    query: str = Field(min_length=2, max_length=2000)
    codes: list[str] = Field(default_factory=list, description="Optional ticker filter.")
    max_steps: int | None = Field(default=None, ge=1, le=500)


class ResearchReport(_FrozenModel):
    """A finished research output.

    ``citations`` is not optional by design: spec 002 FR-13 forbids emitting
    unsupported claims, so a report with no citations is a contract violation.
    """

    query: str
    summary: str
    citations: list[Citation] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    critiques: list[str] = Field(default_factory=list)
    step_count: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    generated_at: datetime
