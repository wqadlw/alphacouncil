"""Decision reviews: the surface where red line 10 has to actually happen.

**The name is not ``reviews.py``, and that is the point.** ``routes/reviews.py``
holds the **card** review queue at ``/api/v1/review``. Calling this module
``reviews.py`` and its prefix ``/api/v1/reviews`` would put two queues one
letter apart::

    GET /api/v1/review/due      # cards   (K3)
    GET /api/v1/reviews/due     # decisions (J3)

For a human that is a trap; for code that mistypes the ``s`` it is worse than a
trap, because the wrong endpoint still answers ``200`` with a plausible list.
So this is ``decision_reviews.py`` under ``/api/v1/decision-reviews`` — a name
that cannot be confused, and that ``grep -i review`` surfaces separately.

**What the responses do not carry is the product.** Red line 10 requires that a
bad decision which happened to pay must not show its profit. Spec 020 settled
that in the data model — ``outcome`` is a classification, so there is no figure
to withhold — and this module's job is to not put one back on the wire.
``TestTheResponseCarriesNoFigure`` enumerates the field names to keep it that
way, because "we didn't add it" is not a property anything enforces.

**The quadrant's sentence comes from the domain, not from here or the frontend.**
:func:`alphacouncil.domain.review.QuadrantJudgement.guidance` is the only text
allowed for a cell, and it is written in the same file as the rule it obeys. A
UI-authored version of the dangerous-quadrant warning is one careless PR away
from "congratulations, good call!"; a domain-authored one is reviewed in the
same diff as the red line it satisfies.

**The caller owns the transaction** — project convention, and the reason
``db.require_open_transaction`` exists (regression 0006). ``record`` writes two
tables, so it opens one transaction here and the repository insists on it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.api.routes.decisions import to_read
from alphacouncil.domain.decision import DecisionNotFoundError
from alphacouncil.domain.review import (
    MAX_NOTE_CHARS,
    MAX_PROCESS_SCORE,
    MIN_PROCESS_SCORE,
    Outcome,
    ProcessBand,
    Quadrant,
    QuadrantJudgement,
    Review,
)
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import decisions as decision_repository
from alphacouncil.storage.repositories import reviews as repository
from alphacouncil.storage.repositories.reviews import ReviewRow, ReviewStateRow

__all__ = [
    "DecisionReviewRead",
    "ReviewRequest",
    "ReviewStateRead",
    "router",
    "to_review_read",
    "to_state_read",
]

router = APIRouter(prefix="/api/v1/decision-reviews", tags=["decisions"])


class ReviewRequest(BaseModel):
    """One review of one decision: a process score, and an outcome once it is due.

    ``outcome`` is optional and **may be absent for as long as the review is not
    due**. That asymmetry is the gate, not an oversight: you may write down how
    you reasoned at any time, and how it turned out only once it has.

    ``extra="forbid"`` for the same reason ``decisions`` has it — a client that
    sends ``outcome_figure`` gets a 422 naming it rather than a silently ignored
    field. On a red line about not showing numbers, silently ignoring a number is
    the wrong failure mode.
    """

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(
        min_length=1,
        description="The decision being reviewed. Its id is the moment it was written.",
    )
    process_score: int = Field(
        ge=MIN_PROCESS_SCORE,
        le=MAX_PROCESS_SCORE,
        description=(
            "How sound the reasoning was, 1 to 5. **Yours to write.** The system "
            "has no estimate and will not offer a default (red line 15: judgement "
            "is the user's to make, not the system's to generate)."
        ),
    )
    outcome: Outcome | None = Field(
        default=None,
        description=(
            "How it turned out — a category, not a number. Null while the review "
            "is not yet due, and refused with 409 if you try to fill it in early "
            "(scoring early is hindsight)."
        ),
    )
    note: str | None = Field(
        default=None,
        max_length=MAX_NOTE_CHARS,
        description=(
            "Optional. A note saying 'failed but…' is yours to write; the field "
            "does not judge phrasing. `failed` exists precisely so a loss need "
            "not be dressed up as a harvest with volatility."
        ),
    )


class ReviewStateRead(BaseModel):
    """Where a decision stands in the review process.

    ⚠️ **There is no score of the user here.** ``process_score`` and ``outcome``
    are the user's own two words about their own reasoning, kept apart because
    red line 5 requires it — but nothing *about the user* is computed, ranked or
    totalled. No "you have reviewed 4 of 7". No completion rate. That would be
    red line 11's "make them move" wearing a progress bar.
    """

    decision_id: str
    due_at: str = Field(description="ISO datetime, UTC. A fact about time.")
    reviewed_at: str | None = Field(
        default=None,
        description=(
            "When the review was **completed**. Null until an outcome is recorded: "
            "writing only a process score does not complete a review, and must not "
            "make a decision look reviewed."
        ),
    )
    is_due: bool = Field(
        description=(
            "Whether an outcome may be recorded now. Computed on the server from "
            "its own clock, so the client and the gate cannot disagree."
        )
    )
    reviews: int = Field(
        ge=0,
        description="How many reviews exist. Counted from an append-only table, so reliable.",
    )


class DecisionReviewRead(BaseModel):
    """A review, with the quadrant it falls in and the one line it is allowed.

    **No figure field exists here, and that is deliberate** (red line 10). The
    dangerous quadrant — a bad decision that happened to pay — has no profit
    number to show, because no profit number was ever stored. Adding one would
    turn "we don't display it" into a promise about this endpoint, and a promise
    about one endpoint is not a red line.
    """

    decision_id: str
    review_id: str
    process_score: int
    outcome: Outcome | None
    process: ProcessBand
    quadrant: Quadrant
    guidance: str = Field(
        description=(
            "The only sentence this quadrant is permitted to print. Served by the "
            "domain so the wording is reviewed alongside the rule that requires it."
        )
    )
    reviewed_at: str


def to_state_read(
    state: ReviewStateRow, *, reviews: int, as_of: datetime
) -> ReviewStateRead:
    return ReviewStateRead(
        decision_id=state.decision_id,
        due_at=state.due_at.isoformat(),
        reviewed_at=None if state.reviewed_at is None else state.reviewed_at.isoformat(),
        is_due=as_of >= state.due_at,
        reviews=reviews,
    )


def to_review_read(row: ReviewRow) -> DecisionReviewRead:
    judgement = row.judgement()
    return DecisionReviewRead(
        decision_id=row.decision_id,
        review_id=row.id,
        process_score=row.process_score,
        outcome=row.outcome,
        process=judgement.process,
        quadrant=judgement.quadrant,
        guidance=judgement.guidance(),
        reviewed_at=row.reviewed_at.isoformat(),
    )


@router.get(
    "/recent",
    summary="Decisions already reviewed, most recent first",
)
def recent(
    connection: DatabaseConnection,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    """⭐ **The reviews you already wrote**, which the due queue cannot show you.

    Found by opening the app (spec 030). The retrospective page's only list was the
    *due* one, and a decision leaves it the moment its review is written — so a
    review you had already done was invisible on the page whose subject is reviews,
    and the lesson composer was unreachable: correctly hidden before the review,
    gone from the only list afterwards.

    ⭐ **No count, and no ordering by how the decision went.** Newest first, ties on
    id. Sorting a reader's own retrospectives by process score would be grading them,
    and red line 11 is about not doing that.
    """
    rows = repository.recent_reviews(connection, limit=limit)
    out: list[dict[str, Any]] = []
    for row in rows:
        # ⭐ Asked for once, into a name. The first draft called
        # `_latest_review(...)` three times in one expression — twice inside a
        # conditional and once as the value — which mypy rejected as `union-attr`
        # because it cannot prove the second call returns the same thing. It
        # probably does; the point is that three calls to ask one question is three
        # chances to be wrong, and the narrow one reads better.
        latest = _latest_review(connection, row.decision_id)
        out.append(
            {
                "decision_id": row.decision_id,
                "due_at": row.due_at,
                "reviewed_at": latest.reviewed_at if latest else None,
                # ⭐ **`is_due` is always False here**, and saying so is the point of
                # this endpoint existing. The due list computes it as
                # `as_of >= due_at`, which is right *there* because that list has
                # already filtered on `reviewed_at IS NULL`. Reusing it made the
                # demo offer a 1-5 score for a decision that had already been
                # graded — the field is not decorative, it picks the page's branch.
                # ⭐ A reviewed decision has nothing to grade; and a decision can be
                # both due *and* graded, which is exactly the case this list exists
                # to show.
                "is_due": False,
                "reviews": repository.count_reviews(connection, row.decision_id),
            }
        )
    return out


@router.get(
    "/due",
    summary="Decisions whose review has come round",
    response_model=list[ReviewStateRead],
)
def due(
    connection: DatabaseConnection,
    as_of: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReviewStateRead]:
    """The retrospective queue, oldest due first.

    ``as_of`` defaults to now but is a **parameter**, so the same question can be
    asked again later and get the same answer, and a test can sit exactly on the
    boundary day.

    Ordered by due date alone, not by any score — same reasoning as the card queue
    (ADR-0028): ranking the user's own backlog by anything else turns "how far
    behind am I" into a number the user can feel, which is what red line 11 is
    about.

    **Not every decision appears.** A decision only reaches this queue if the
    user named a review date when they made it (spec 021 §二). The alternative —
    a default interval — would be a policy nobody agreed to, invented silently.
    """
    moment = as_of or datetime.now(UTC)
    rows = repository.due_reviews(connection, as_of=moment, limit=limit)
    return [
        to_state_read(
            row,
            reviews=repository.count_reviews(connection, row.decision_id),
            as_of=moment,
        )
        for row in rows
    ]


@router.get(
    "/{decision_id}",
    summary="One decision, its review state, and its latest review",
    responses={404: {"description": "The decision does not exist, or has no review slot"}},
)
def read(decision_id: str, connection: DatabaseConnection) -> dict[str, Any]:
    """Everything one retrospective card needs, in one response.

    The **decision's own words** come back with its review state, and that is not
    convenience — it is the mechanism. What gets graded is a passage of text that
    is still on the page and cannot be edited (``decisions`` is append-only), so
    a response that let the client render a review *without* the text would let
    it grade from memory, which is exactly the hindsight this whole feature
    exists to prevent.

    A single response also means the page cannot show a verdict next to a
    decision fetched a moment earlier, from a version that has since changed.

    **The decision is checked first, and that order is deliberate.** A slot's
    foreign key means a decision always exists whenever a slot does, so checking
    the other way round would make the missing-decision branch unreachable — dead
    code that no test can exercise. Checked this way, asking about a decision
    that was never recorded is an ordinary 404, which is a real request someone
    can make.
    """
    row = decision_repository.get_by_id(connection, decision_id)
    if row is None:
        raise DecisionNotFoundError(f"decision {decision_id!r} not found")
    state = repository.get_review_state(connection, decision_id)
    latest = repository.latest_review(connection, decision_id)
    return {
        "state": to_state_read(
            state,
            reviews=repository.count_reviews(connection, decision_id),
            as_of=datetime.now(UTC),
        ),
        "decision": to_read(row),
        "latest": None if latest is None else to_review_read(latest),
    }


def _latest_review(connection: DatabaseConnection, decision_id: str) -> ReviewRow | None:
    return repository.latest_review(connection, decision_id)


@router.post("", status_code=201, summary="Record a review of a decision")
def create(
    payload: ReviewRequest, connection: DatabaseConnection
) -> DecisionReviewRead:
    """Append a review.

    Two writes, one transaction: the review row and the state row's completion
    stamp. A decision whose review row landed without its state update would look
    unreviewed forever, and nothing else would notice (regression 0006 was exactly
    that shape).

    Raises:
        ReviewStateMissingError: The decision has no review slot — 404, because the
            review commitment does not exist rather than conflicting with anything.
        ReviewNotDueError: An outcome arrived before the due date — 409. The
            request was well-formed; it conflicts with a state. The domain refuses
            it, and so does the schema's ``reviews_not_scored_early_check`` for
            anyone who goes around this route (spec 020 §2.3).
    """
    review = Review(
        decision_id=payload.decision_id,
        process_score=payload.process_score,
        outcome=payload.outcome,
        note=payload.note,
    )
    with transaction(connection):
        row = repository.record(
            connection, payload.decision_id, review, now=datetime.now(UTC)
        )
    return to_review_read(row)


@router.get("/schema/quadrants", summary="The four cells and their one permitted line")
def quadrants() -> list[dict[str, str]]:
    """Every quadrant with the sentence it is allowed to print.

    Exposed so the frontend **renders** the wording instead of restating it, and
    so a test can assert on the real copy rather than a copy kept in step by hand.
    Every entry is produced by the domain, so none of them can drift from the rule.

    ⭐ **There is deliberately no ``withholds_outcome_figure`` field here**, even
    though the domain exposes that property. The first draft of this endpoint
    advertised it, and that was wrong twice over: a client that cannot render a
    number it was never given has no use for being *told* there is none, and the
    flag was the only thing in the payload whose name mentioned a figure at all.
    **Absence is the guarantee; a field that advertises absence is just another
    field to leak.** The property stays in the domain, which is where a future
    numeric outcome would have to earn the right to return ``False``.
    """
    return [
        {
            "quadrant": judgement.quadrant.value,
            "guidance": judgement.guidance(),
        }
        for judgement in (
            QuadrantJudgement(
                quadrant=quadrant,
                process=ProcessBand.GOOD,
                outcome=Outcome.GOOD,
            )
            for quadrant in Quadrant
        )
    ]
