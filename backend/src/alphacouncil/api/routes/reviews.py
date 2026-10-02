"""The review queue (K3): enrol a claim, list what is due, record an answer.

Three verbs and nothing else:

* ``POST /api/v1/cards/{id}/schedule`` — put a claim on the queue
* ``GET  /api/v1/review/due`` — what is due at a stated instant
* ``POST /api/v1/review/{card_id}`` — record a recall or a postponement

There is no ``PUT``, no ``PATCH`` and no ``DELETE`` — ``card_reviews`` is
append-only, and rewriting a past recall would let a user edit their own history
(the same reason ``card_events`` is append-only, and the same reason there is no
way to edit a card's content).

**Why the queue has its own prefix rather than living under ``/cards``.**
``cards`` already serves ``GET /{card_id}``, and FastAPI matches in registration
order, so a ``GET /cards/due`` would be swallowed by ``GET /cards/{card_id}`` and
answered as "no card with the id 'due'". The fix for that is registration order —
a hidden coupling that breaks the first time someone reorders two lines in
``app.py``. The queue is a *surface*, not a sub-resource of a card, so it gets a
prefix of its own and the question never arises.

Three decisions in this file are red lines expressed as contract, not as styling.

**No score field exists, anywhere.** ``ScheduleRead`` carries the due date and
the state. Not ``retrievability`` ("the probability you recall this"), not
``stability``, not ``due_in_days``, not ``mastery``. Each is a number *about the
user*; this response describes *when a claim is next due* (red line 9). A field
that does not exist cannot be displayed. ``fsrs`` does offer
``Scheduler.get_card_retrievability`` — nothing here calls it, and
``tests/unit/test_scheduling.py`` pins that with an AST check.

**``duration_ms`` is measured, never submitted.** A client that sends it gets a
``422`` naming it, because a duration a user types in is a duration they
performed. It is stored because self-knowledge needs it (red line 11 — reflection
only, never ranking), and nothing sums it.

**``as_of`` is a parameter, not a call to the clock.** A queue is a question about
a stated instant, and asking the server what time it is makes the question
unanswerable afterwards. The boundary is therefore testable (due on the day, not
the day before), and a replay gets the same answer.

**The caller owns the transaction** — the project convention, and the reason
``db.require_open_transaction`` exists (regression 0006). Each write here opens
one, and the repository refuses to write two rows without it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.domain.card import CardNotFoundError
from alphacouncil.domain.scheduling import (
    DEFAULT_DEFERRAL_DAYS,
    MAX_DEFERRAL_DAYS,
    ReviewOutcome,
    ReviewRating,
    ScheduleState,
)
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import cards as card_repository
from alphacouncil.storage.repositories import scheduling as repository
from alphacouncil.storage.repositories.scheduling import ScheduleRow

__all__ = [
    "ReviewReceipt",
    "ReviewRequest",
    "ScheduleRead",
    "card_router",
    "queue_router",
    "to_schedule_read",
]

card_router = APIRouter(prefix="/api/v1/cards", tags=["cards"])
queue_router = APIRouter(prefix="/api/v1/review", tags=["cards"])


class ScheduleRead(BaseModel):
    """A card's scheduling state.

    ⚠️ **The absence of fields here is the point.** No ``retrievability``, no
    ``stability``, no ``due_in_days``, no ``mastery``. Every one of those is a
    number *about the user*, and this response is a statement about *when a claim
    is next due* (red line 9). If a score is ever wanted here, it needs an ADR
    that argues against red line 9 — not a field addition.
    """

    card_id: str
    state: ScheduleState
    due_at: str = Field(description="ISO datetime, UTC. A fact about time.")


class ReviewRequest(BaseModel):
    """One interaction with a due card: a recall, or a postponement.

    Exactly one of two shapes, and the model says so rather than leaving it to
    each endpoint:

    * ``{"outcome": "reviewed", "rating": "good"}``
    * ``{"outcome": "deferred", "days": 7}``

    ``duration_ms`` is **not** a field. A client that sends it gets a ``422``
    naming it (red line 11: self-knowledge, not a metric).
    """

    model_config = ConfigDict(extra="forbid")

    outcome: ReviewOutcome
    rating: ReviewRating | None = None
    days: int | None = Field(
        default=None,
        ge=1,
        le=MAX_DEFERRAL_DAYS,
        description=(
            "How far to push a postponement. One week by default, "
            f"{MAX_DEFERRAL_DAYS} days at most. Postponing is a feature, not "
            "procrastination (SuperMemo S-05) — and it does not damage the "
            "card's memory."
        ),
    )

    @model_validator(mode="after")
    def _shape_must_match_the_outcome(self) -> ReviewRequest:
        """A recall needs a rating; a postponement must not have one.

        Checked here rather than per-endpoint, so there is exactly one place that
        knows what a review is — and so the domain does not have to defend against
        a nonsensical combination arriving from a future caller.
        """
        if self.outcome is ReviewOutcome.REVIEWED and self.rating is None:
            msg = "a reviewed outcome needs a rating; a deferred one must not have it"
            raise ValueError(msg)
        if self.outcome is ReviewOutcome.DEFERRED and self.rating is not None:
            msg = "a deferred outcome must not carry a rating — nothing was recalled"
            raise ValueError(msg)
        return self


class ReviewReceipt(BaseModel):
    """What one interaction did. A fact, not a verdict.

    No "correct", no "score", no "well done", and no count of how many times the
    user has forgotten this card. The only values here are the dates the system
    changed (red lines 9 and 13 — the product records the interaction and does
    not comment on it).
    """

    card_id: str
    outcome: ReviewOutcome
    next_due_at: str
    state: ScheduleState


def to_schedule_read(row: ScheduleRow) -> ScheduleRead:
    return ScheduleRead(card_id=row.card_id, state=row.state, due_at=row.due_at.isoformat())


@card_router.post(
    "/{card_id}/schedule",
    summary="Put a claim on the review queue",
    status_code=201,
)
def schedule(card_id: str, connection: DatabaseConnection) -> ScheduleRead:
    """Enrol a card for review. This is "generating a scheduling item".

    Refuses a second enrolment rather than resetting the card: re-enrolling a
    claim with three reviews behind it would hand it a fresh stability and make a
    months-old lesson look like it was learned today — the exact inversion of
    what the queue is for.
    """
    if card_repository.get_by_id(connection, card_id) is None:
        raise CardNotFoundError(f"card {card_id!r} not found")
    with transaction(connection):
        row = repository.enroll(connection, card_id, now=datetime.now(UTC))
    return to_schedule_read(row)


@card_router.get(
    "/{card_id}/schedule",
    summary="Whether one card is on the review queue, and when it is next due",
)
def read_schedule(card_id: str, connection: DatabaseConnection) -> ScheduleRead:
    """Read one card's scheduling item. Spec 048.

    ⭐ **This endpoint existed only as a `POST`, and that made the queue unreachable
    from the interface.** Measured on 2026-10-02, against the empty database:

    ```
      POST /api/v1/cards                 -> 201 card_1790916668533
      GET  /api/v1/review/due            -> 0 items      (the server volunteers nothing)
      POST /api/v1/cards/{id}/schedule   -> 201 {"state":"learning", …}
      GET  /api/v1/review/due            -> 1 item
      grep scheduleCard                  -> api.ts:282 defines it, zero callers
    ```

    So a claim could only reach the queue by writing code. **The gap was the missing
    read**, not the missing write: without it the interface cannot tell 「already
    enrolled」 from 「never enrolled」, and **it cannot infer it from
    `GET /review/due` either** — that endpoint returns only what is *due*, so a card
    scheduled for next week is not in it. A button whose result you only learn by
    pressing it is a wager, and this product does not make wagers with a reader's
    records.

    ⚠️ **Not-scheduled answers 409, not 404 — and the reason is already written down,
    elsewhere.** `GET /notes/{note_id}/schedule` answers **404** for the same state,
    and copying it was the first thing this spec did; `api/errors.py` says:

    ```
    # K3. Both are 409 rather than 404 on purpose: the *card* exists, and what
    # conflicts is the request with the card's scheduling state. Answering 404
    # would tell the user their card is gone when it is sitting right there.
    ErrorCode.CARD_NOT_SCHEDULED.value: 409,
    ```

    ⇒ The card's contract is followed, not the note's. ⭐ **And it is the better
    contract for the interface too**: 409 separates 「this claim is not on the queue」
    (an ordinary empty state, the button should be there) from **404 「no such card」**
    (something is wrong that the button must not paper over).
    """
    if card_repository.get_by_id(connection, card_id) is None:
        raise CardNotFoundError(f"card {card_id!r} not found")
    return to_schedule_read(repository.get_schedule(connection, card_id))


@queue_router.get("/due", summary="Claims due at a stated instant")
def due(
    connection: DatabaseConnection,
    as_of: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ScheduleRead]:
    """The queue, oldest due first.

    ``as_of`` defaults to now but is a **parameter**, so the same question can be
    asked again later and get the same answer, and a test can sit exactly on the
    boundary.

    Ordered by due date only, not by priority. SuperMemo S-03 asks for priority
    ordering, but that is about *a list of knowledge*; applying it here would turn
    "how backed up am I" into a ranking the user can feel, which is what red line
    11 objects to. See ADR-0028.
    """
    moment = as_of or datetime.now(UTC)
    rows = repository.due_cards(connection, as_of=moment, limit=limit)
    return [to_schedule_read(row) for row in rows]


@queue_router.post("/{card_id}", summary="Record a recall or a postponement")
def review(
    card_id: str,
    payload: ReviewRequest,
    connection: DatabaseConnection,
) -> ReviewReceipt:
    """Record one interaction with a due card.

    A recall moves the schedule through FSRS. A postponement moves **only** the
    due date — the FSRS payload is carried through byte for byte, because "not
    right now" is not a failed recall (spec 018, and the test that pins it).

    The response is a receipt, not a judgement: no score, no encouragement, no
    count of past failures (red line 13 — the product records and does not
    comment).
    """
    days = payload.days if payload.days is not None else DEFAULT_DEFERRAL_DAYS
    # Existence before state. Without this a missing card answers 409
    # ("not scheduled") when the honest answer is 404 ("no such card") — the two
    # say very different things to a client deciding whether to create one.
    if card_repository.get_by_id(connection, card_id) is None:
        raise CardNotFoundError(f"card {card_id!r} not found")
    with transaction(connection):
        if payload.outcome is ReviewOutcome.DEFERRED:
            row = repository.defer(connection, card_id, now=datetime.now(UTC), days=days)
        else:
            assert payload.rating is not None  # guaranteed by ReviewRequest
            row = repository.record_review(
                connection, card_id, payload.rating, now=datetime.now(UTC)
            )
    after = repository.get_schedule(connection, card_id)
    return ReviewReceipt(
        card_id=card_id,
        outcome=row.outcome,
        next_due_at=after.due_at.isoformat(),
        state=after.state,
    )
