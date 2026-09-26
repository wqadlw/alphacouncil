"""The decision journal API — one verb that matters, and no way to take it back.

``POST`` records, ``GET`` lists. There is no ``PUT``, no ``PATCH`` and no
``DELETE``, because the table is append-only: changing your mind is another
decision. Exposing an edit would destroy the only property that makes this
record worth keeping — that it was written before the outcome was known.

**The request model forbids unknown fields, and that is load-bearing.** A
``decisions`` row's primary key is the moment it was written, and the whole
point is that nobody can move that moment. If the request model ignored extra
keys, a client posting ``{"id": "2026-01-01T00:00:00.000Z", ...}`` would be
silently ignored — the row would get the correct server timestamp and the caller
would never learn that their input meant nothing. With ``extra="forbid"`` the
attempt is a ``422`` naming the field. Refusing loudly beats ignoring quietly
when the thing being ignored is the integrity of the evidence.

Nothing here re-checks what the domain checks. The route resolves the
instrument, the domain decides whether the decision could have come from the
user, and the database is the floor under both.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.domain.decision import (
    MAX_TEXT_CHARS,
    ComparisonOperator,
    DecisionAction,
    KillCriterion,
    record,
)
from alphacouncil.domain.instrument import parse_ticker
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import decisions as repository
from alphacouncil.storage.repositories import instruments as instrument_repository

__all__ = ["DecisionRead", "KillCriterionRead", "router", "to_read"]

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])


class KillCriterionRead(BaseModel):
    """One falsifiable condition, in the shape the UI edits.

    A structured object rather than a sentence, because a sentence cannot be
    evaluated — nothing can watch it, so it can never come and find you
    (ADR-0017 #5). Free prose is still allowed, but as the decision's
    ``rationale``, never as the condition.
    """

    metric: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "A metric token, e.g. gross_margin / revenue_yoy / price. The "
            "catalogue belongs to the financial-data layer (D4) and is not "
            "fixed yet, so this is validated for shape, not membership."
        ),
    )
    operator: ComparisonOperator
    threshold: float
    as_of: date = Field(
        description=(
            "Point-in-time cutoff. Only figures announced on or before this date "
            "may be read (constitution rule 20) — using a later publication is "
            "how a review quietly becomes hindsight."
        )
    )


class DecisionCreateRequest(BaseModel):
    """Record a decision. The three fields the product exists for are required."""

    #: `extra="forbid"` is load-bearing, not tidiness. A `decisions` row's
    #: primary key is the moment it was written, and the whole point is that
    #: nobody can move that moment. Ignoring an unknown `id` would be the worst
    #: outcome — the row would get the correct server timestamp and the caller
    #: would never learn their input meant nothing. With this, the attempt is a
    #: 422 naming the field.
    #:
    #: There is deliberately **no** `id` field declared here, not even one that
    #: exists only to be refused. S-06 (`checks/rules/no_client_supplied_id.py`)
    #: flags any request schema that declares a server-assigned field, and its
    #: reasoning is worth keeping: a test that posts an id and asserts the record
    #: round-trips passes while the hole stays open, because the defect is that
    #: the field *exists* — which no execution path reveals. The first draft of
    #: this module declared `id` to give a friendlier error, and the check caught
    #: it. Refusing at the schema is the intended shape.
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, description="600519 / sh600519 / 600519.SH")
    market: Market | None = Field(
        default=None, description="Required when the ticker is ambiguous (000xxx)"
    )
    action: DecisionAction
    rationale: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    counter_evidence: str = Field(
        min_length=1,
        max_length=MAX_TEXT_CHARS,
        description=(
            "The case against your own decision. Required because confirmation "
            "bias is not optional: someone who has decided something will find "
            "reasons for it, and writing the other side down first is the only "
            "known countermeasure."
        ),
    )
    kill_criteria: list[KillCriterionRead] = Field(
        min_length=1,
        description="What would prove this wrong. At least one, and it must be evaluable.",
    )
    thesis_id: str | None = Field(
        default=None,
        description="The thesis this decision serves. Not built yet (J2) — accepted so "
        "records made now do not have to be rewritten later.",
    )


class DecisionRead(BaseModel):
    """One recorded decision, as stored."""

    id: str = Field(
        description=(
            "The moment it was written, in UTC with millisecond precision — the "
            "primary key and the evidence in one value. Server-generated."
        )
    )
    market: Market
    code: str
    display: str
    action: DecisionAction
    rationale: str
    counter_evidence: str
    kill_criteria: list[KillCriterionRead]
    thesis_id: str | None = None


def to_read(row: repository.DecisionRow) -> DecisionRead:
    """Render a stored row for the client.

    Public, and imported by :mod:`alphacouncil.api.routes.instruments`, because a
    decision looks the same wherever it is read from. A second serializer there
    would be a second place for ``display`` to be built by hand, and the whole
    reason ``display`` exists is that the conventional ticker form should have
    exactly one implementation.
    """
    return DecisionRead(
        id=row.id,
        market=row.market,
        code=row.code,
        # Built from Symbol rather than by concatenating here: the conventional
        # form has exactly one implementation, and a second one in this file is
        # a second chance to disagree about the separator.
        display=Symbol(market=row.market, code=row.code).full,
        action=row.action,
        rationale=row.rationale,
        counter_evidence=row.counter_evidence,
        kill_criteria=[
            KillCriterionRead(
                metric=criterion.metric,
                operator=criterion.operator,
                threshold=criterion.threshold,
                as_of=criterion.as_of,
            )
            for criterion in row.kill_criteria
        ],
        thesis_id=row.thesis_id,
    )


@router.get("", summary="The most recent decisions across every instrument")
def list_recent(
    connection: DatabaseConnection,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[DecisionRead]:
    """List decisions newest first.

    One instrument's decisions are **not** fetched here — they arrive with the
    instrument itself (``GET /api/v1/instruments/{market}/{code}``), untruncated.
    Two ways to ask the same question would be two orderings to keep in step,
    and the page that shows a company's history needs all of it, not the last
    fifty.
    """
    return [to_read(row) for row in repository.recent(connection, limit=limit)]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Record a decision")
def create(payload: DecisionCreateRequest, connection: DatabaseConnection) -> DecisionRead:
    """Append a decision, creating the instrument row if it is new.

    Raises:
        TickerInvalidError: The ticker is malformed or contradicts a stated
            market. Surfaces as the standard envelope with a 400.
        DecisionError: A required field was blank, or a predicate could not be
            evaluated. Also the standard envelope, with a 400.
    """
    parsed = parse_ticker(payload.ticker, market=payload.market)
    # Take the stored asset type when the instrument is already on file: the
    # parse default is `stock`, and asserting it against an ETF would raise a
    # conflict the user did not cause.
    symbol = instrument_repository.adopt_stored_type(connection, parsed)
    decision = record(
        symbol,
        payload.action,
        rationale=payload.rationale,
        counter_evidence=payload.counter_evidence,
        kill_criteria=tuple(
            KillCriterion(
                metric=item.metric,
                operator=item.operator,
                threshold=item.threshold,
                as_of=item.as_of,
            )
            for item in payload.kill_criteria
        ),
        thesis_id=payload.thesis_id,
    )
    with transaction(connection):
        return to_read(repository.append(connection, decision))
