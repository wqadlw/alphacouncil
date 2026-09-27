"""The today endpoint — what deserves the reader's attention right now.

The today page's first block ("需要你处理的") is the one place the product is
allowed to come and find the reader, and this endpoint is deliberately the
*only* thing it can find so far: a written kill criterion whose cutoff date
has arrived. That is a fact about the reader's own calendar — "the question
you scheduled can now be asked" — not a judgement about the stock. Whether the
comparison actually holds cannot be said by this system (the metric's value
has no data source yet, D4), and the route does not pretend otherwise: the
client's copy for an attention item is "go verify", never "triggered".

The scan runs over **every** decision, not a recent window. A predicate
written three years ago is exactly the one that comes due today; a ``LIMIT``
would drop precisely those (see :func:`alphacouncil.storage.repositories.decisions.list_all`).

The endpoint also carries ``market_status`` (spec 007): whether today is an
A-share trading day, probed through the index's own daily bars — the last bar
is the last day the market actually traded, which needs no holiday calendar
and cannot go stale the way a hard-coded table does.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from alphacouncil.api.deps import DatabaseConnection, MarketData
from alphacouncil.api.routes.decisions import KillCriterionRead
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.decision import DecisionAction
from alphacouncil.domain.trading import (
    TradingDayBasis,
    TradingDayError,
    TradingDayVerdict,
    verdict_for,
)
from alphacouncil.models.market import AssetType, DataStatus, Market, Symbol
from alphacouncil.storage.repositories import decisions as decision_repository

__all__ = ["router"]

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/today", tags=["today"])

#: The probe reads the SSE Composite: the deepest liquidity, never delisted,
#: and its daily series is the market's own record of which days it traded.
#: Constructed directly — a bare ``000001`` is ambiguous precisely because it
#: is also Ping An Bank, and a probe may not guess (ADR-0017 rule 16).
_PROBE_SYMBOL = Symbol(market=Market.SH, code="000001", asset_type=AssetType.INDEX)

#: Longest A-share closure is the Spring Festival week (~8 days); a fortnight
#: guarantees the probe window always contains at least one real trading bar,
#: even on the first trading morning after the longest holiday.
_PROBE_WINDOW_DAYS = 14


class DueCriterionRead(BaseModel):
    """One predicate whose cutoff has arrived, with where it came from.

    The decision's id is the write moment, so carrying it doubles as carrying
    "when you wrote this" — no separate timestamp field to disagree with it.
    """

    decision_id: str = Field(description="The decision it belongs to (the write moment, UTC).")
    market: Market
    code: str
    display: str = Field(description="Conventional form, e.g. 600519.SH.")
    action: DecisionAction
    criterion: KillCriterionRead


class AttentionKind(StrEnum):
    """Why an item is on the list. One value today; more arrive with J3/J4."""

    KILL_CRITERION_DUE = "kill_criterion_due"


class AttentionRead(BaseModel):
    """One line of "需要你处理" — a fact, with a way out (the instrument page)."""

    kind: AttentionKind = AttentionKind.KILL_CRITERION_DUE
    item: DueCriterionRead


class TodayRead(BaseModel):
    """The today page's server-side blocks.

    Blocks ② (what you follow) and the not-yet-built ③ ④ are deliberately
    absent here: the pool travels through its own endpoints with their own
    failure modes, and a block that does not exist must not look like an empty
    list (the page says so in words instead).
    """

    generated_at: str = Field(description="Server moment, ISO-8601 UTC.")
    attention: list[AttentionRead] = Field(default_factory=list)
    market_status: MarketStatusRead = Field(
        description="Whether today is an A-share trading day, and on what evidence."
    )


class MarketStatusRead(BaseModel):
    """The trading-day verdict, with its basis.

    The verdict and its basis travel together because they are not equally
    certain: "non-trading day (weekend)" is certain, "non-trading day (probe)"
    rests on the intraday-bar assumption, and ``unknown`` means no claim at
    all. The client renders the basis implicitly — a badge only for 休市, with
    the last trading date as the fact behind it.
    """

    verdict: TradingDayVerdict
    basis: TradingDayBasis
    last_trading_date: date | None = Field(
        default=None,
        description="The newest date with a daily bar. Absent when the probe failed.",
    )
    checked_at: str = Field(description="When the probe ran, ISO-8601 UTC with Z suffix.")


@router.get("", summary="What deserves attention today")
def today(connection: DatabaseConnection, market_data: MarketData) -> TodayRead:
    """Scan every recorded decision for predicates whose cutoff has arrived.

    The comparison date is the server's local calendar date — which on this
    product *is* the reader's date, the server being the reader's own desktop.
    """
    now = datetime.now().astimezone()
    today_date = now.date()
    attention: list[AttentionRead] = []
    for row in decision_repository.list_all(connection):
        for criterion in row.kill_criteria:
            if criterion.due(as_of=today_date):
                attention.append(
                    AttentionRead(
                        item=DueCriterionRead(
                            decision_id=row.id,
                            market=row.market,
                            code=row.code,
                            display=Symbol(market=row.market, code=row.code).full,
                            action=row.action,
                            criterion=KillCriterionRead(
                                metric=criterion.metric,
                                operator=criterion.operator,
                                threshold=criterion.threshold,
                                as_of=criterion.as_of,
                            ),
                        )
                    )
                )
    return TodayRead(
        generated_at=utc_millis(),
        attention=attention,
        market_status=_market_status(market_data, now),
    )


def _market_status(market_data: MarketData, now: datetime) -> MarketStatusRead:
    """Probe the index's daily bars and judge today. Never raises.

    A probe failure — transport, empty window, a source sending a date from
    the future — degrades to ``unknown``: the today page's other blocks must
    not pay for one source's bad morning.
    """
    result = market_data.get_daily(
        _PROBE_SYMBOL,
        start=now.date() - timedelta(days=_PROBE_WINDOW_DAYS),
        end=now.date(),
    )
    last = (
        result.value[-1].trade_date
        if result.status is DataStatus.OK and result.value is not None
        else None
    )
    try:
        verdict, basis = verdict_for(now=now, last_trading_date=last)
    except TradingDayError as exc:
        log.warning("today.probe_inconsistent", error=str(exc))
        return MarketStatusRead(
            verdict=TradingDayVerdict.UNKNOWN,
            basis=TradingDayBasis.NONE,
            last_trading_date=None,
            checked_at=utc_millis(),
        )
    return MarketStatusRead(
        verdict=verdict,
        basis=basis,
        last_trading_date=last,
        checked_at=utc_millis(),
    )
