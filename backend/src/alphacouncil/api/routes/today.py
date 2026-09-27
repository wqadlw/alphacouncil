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
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from fastapi import APIRouter
from pydantic import BaseModel, Field

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.api.routes.decisions import KillCriterionRead
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.decision import DecisionAction
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage.repositories import decisions as decision_repository

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/today", tags=["today"])


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


@router.get("", summary="What deserves attention today")
def today(connection: DatabaseConnection) -> TodayRead:
    """Scan every recorded decision for predicates whose cutoff has arrived.

    The comparison date is the server's local calendar date — which on this
    product *is* the reader's date, the server being the reader's own desktop.
    """
    today_date = date.today()
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
    return TodayRead(generated_at=utc_millis(), attention=attention)
