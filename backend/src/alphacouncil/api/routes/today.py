"""The today endpoint — what deserves the reader's attention right now.

The today page is **the one place the product is allowed to come and find the
reader**, and this endpoint carries exactly **two** kinds of thing (spec 023):

1. **a written kill criterion whose cutoff date has arrived** — a fact about the
   reader's own calendar, "the question you scheduled can now be asked", not a
   judgement about the stock. Whether the comparison actually holds cannot be
   said by this system (the metric's value has no data source yet, D4), and the
   route does not pretend otherwise: the client's copy for an attention item is
   "go verify", never "triggered"; and
2. **how many of their own review commitments have come round** — cards (K3) and
   decisions (J3), as **bare counts** (see :func:`_due`).

Both have **the reader as their subject**, and that is the entire boundary: this
endpoint reports *what the reader already promised to look at* and never *what
they might want*. The first is a statement of fact, and the only kind of thing
red line 8 lets a product interrupt with; the second is a recommendation, which
is exactly what that red line exists to forbid.

The scan runs over **every** decision, not a recent window. A predicate
written three years ago is exactly the one that comes due today; a ``LIMIT``
would drop precisely those (see :func:`alphacouncil.storage.repositories.decisions.list_all`).

The endpoint also carries ``market_status`` (spec 007): whether today is an
A-share trading day, probed through the index's own daily bars — the last bar
is the last day the market actually traded, which needs no holiday calendar
and cannot go stale the way a hard-coded table does.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Literal

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
from alphacouncil.storage.repositories import reviews as review_repository
from alphacouncil.storage.repositories import scheduling as scheduling_repository

__all__ = ["DueCount", "DueRead", "TodayRead", "router"]

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


class DueCount(BaseModel):
    """How many things are waiting in one queue, and which queue.

    ⚠️ **The absence of everything else here is the design.** No due date, no
    title, no ordering, no "most overdue", no progress fraction, no link — a link
    would duplicate the frontend's route table, and a due date would let the
    client sort by urgency, which is red line 11 (a ranking the reader can feel)
    wearing a sort order instead of a number.

    ``count`` is a fact about the reader's own commitments. It is **not** a score:
    nothing here is summed, averaged, or compared against a target.
    """

    queue: Literal["cards", "reviews"] = Field(
        description="Which queue, by logical name. The client maps it to its own routes."
    )
    count: int = Field(
        ge=0,
        description=(
            "How many are due now. A ceiling is applied server-side, so a very "
            "large backlog reads as a large number rather than hanging the page."
        ),
    )


class DueRead(BaseModel):
    """The two review queues, as counts.

    Present even when both are zero — the *client* is what decides not to render
    a line, because "0 decisions are due" is still a sentence about the reader,
    and being told you owe yourself nothing is not information worth a line.
    """

    cards: DueCount
    reviews: DueCount


class TodayRead(BaseModel):
    """The today page's server-side blocks.

    Blocks ② (what you follow) and the not-yet-built ③ ④ are deliberately
    absent here: the pool travels through its own endpoints with their own
    failure modes, and a block that does not exist must not look like an empty
    list (the page says so in words instead).
    """

    generated_at: str = Field(description="Server moment, ISO-8601 UTC.")
    attention: list[AttentionRead] = Field(default_factory=list)
    due: DueRead = Field(
        description=(
            "How many of the reader's own commitments have come round. The second "
            "thing this endpoint is allowed to bring — the first is a kill "
            "criterion whose date has arrived — and deliberately no more."
        )
    )
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
        due=_due(connection, now),
        market_status=_market_status(market_data, now),
    )


#: How many rows a count may look at. A ceiling, not a ranking: the point is to
#: answer "are there any", and a page that has to count a million rows to say
#: "yes, some" is a page that will eventually be the slow one.
_COUNT_CEILING = 200


def _due(connection: DatabaseConnection, now: datetime) -> DueRead:
    """How many things the reader promised themselves, and which have come round.

    ⭐ **This block is the product coming to find the reader**, and the line it
    must not cross is narrow. `项目总纲` §2.1⑤ sanctions exactly one shape for it
    — "一句陈述，无推送、无红点、无催促词" — and red line 8 bans anything that
    reads as a push. The difference that keeps both satisfied:

        **a statement about something the reader already committed to**
        versus **a suggestion about something they might want.**

    "Two decisions are due for review" has the reader as its subject and is a
    fact about their own calendar. "Here are three opportunities" has the product
    as its subject and is a judgement about the market — which is what red line 8
    exists to forbid. So the block carries **counts and nothing else**: no due
    dates, no titles, no ordering, no "most urgent", no progress.

    ⭐ **Queue names, not URLs.** The route table is the frontend's single source
    of truth (spec 022), and a URL duplicated here would be a second copy of that
    fact — the kind of second copy that gets edited in one place and then
    disagrees. The client maps ``cards`` / ``reviews`` to its own routes.

    ⭐ **No "three days overdue" threshold.** `项目总纲` ⑤ says "三天未处理 → 一句
    陈述", but three days is not a defined criterion: nothing says what would be
    said differently on day four, or how much louder. Inventing it is the same
    mistake as inventing a 90-day review interval (spec 020 §六), and the failure
    mode is worse — "louder the longer you ignore it" *is* a nagging mechanism,
    which is red line 11. So this reports what is due, and the threshold stays
    undefined until someone argues for it.
    """
    moment = now.astimezone(UTC)
    return DueRead(
        cards=DueCount(
            queue="cards",
            count=len(
                scheduling_repository.due_cards(connection, as_of=moment, limit=_COUNT_CEILING)
            ),
        ),
        reviews=DueCount(
            queue="reviews",
            count=len(
                review_repository.due_reviews(connection, as_of=moment, limit=_COUNT_CEILING)
            ),
        ),
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
