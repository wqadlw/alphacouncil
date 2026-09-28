"""Lessons: the API (spec 030 - J5).

Three routes, and the smallness is the design rather than an omission:

* ``POST /api/v1/reviews/{decision_id}/lesson`` - the only way a lesson comes into
  existence. ⭐ **There is no "enrol" verb**, and that absence *is* the feature: a
  lesson's scheduling item is not optional, so exposing a way to create one without
  it would be exposing a way to break red line 7. Every other queue here has an
  explicit enrolment call. This one deliberately does not.
* ``GET /api/v1/lessons/due`` - the queue. A bare array, **no count**, for the
  same reason ``GET /notes/due`` has none.
* ``POST /api/v1/lessons/{lesson_id}/promote`` - sign it as a card, and it will
  refuse without a source.

## Two things in the read models that look like omissions

**The queue row has no title.** The note queue shows one; this does not. A queue
whose rows can be scanned is a to-do list, and 「你欠 N 条」 is the shape this
product's red lines rule out. The row carries ``state`` and ``due_at`` - when this
came back - which is the one fact that makes the visit feel like a re-read rather
than an item to clear. It also carries ``content``, because the reader has to read
something; that is the lesson's own sentence, not a label for it.

**The create response returns the schedule too.** Not for convenience: 「已经在队列
上，刚到期，learning」 is the fact the red line just produced, and a client that
has to ask again cannot tell 「I created it」 from 「I created it *and* scheduled
it」.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.card import ClaimType
from alphacouncil.domain.lesson import (
    MAX_CONTENT_CHARS,
    LessonAlreadyPromotedError,
    LessonContentBlankError,
    LessonNotFoundError,
    LessonPromotionSourceError,
    LessonReviewMissingError,
    LessonTooLongError,
)
from alphacouncil.domain.scheduling import ReviewRating, ScheduleState
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import lesson as repository

router = APIRouter(prefix="/api/v1", tags=["lessons"])


def _now() -> datetime:
    return datetime.now(UTC)


# ── read models ─────────────────────────────────────────────────────────────


class LessonRead(BaseModel):
    """A lesson, as read back.

    ⭐ No ``decision_id``: the table has no such column, because the decision is
    one join away through ``review_id``, and a second copy of a fact that can
    disagree with the first is the hazard this discipline exists to avoid.
    """

    model_config = ConfigDict(frozen=True)

    lesson_id: str
    review_id: str
    content: str
    created_at: datetime


class LessonScheduleRead(BaseModel):
    """One queue row. ⭐ No title, and no count anywhere in this response.

    A queue the reader can scan as a worklist is the shape the product refuses;
    the reasoning is in spec 030 and in ``formatAgo.ts``. ``content`` is here
    because the reader has to read something.
    """

    model_config = ConfigDict(frozen=True)

    lesson_id: str
    state: ScheduleState
    due_at: datetime
    content: str


class LessonCreate(BaseModel):
    """The body for turning a review into a lesson."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(
        min_length=1,
        max_length=MAX_CONTENT_CHARS,
        description="教训正文。没有出处也能记 —— 它的出处是一次复盘。",
    )


class LessonRecordedRead(BaseModel):
    """What a create returns: the lesson **and** the item it forced."""

    model_config = ConfigDict(frozen=True)

    lesson: LessonRead
    state: ScheduleState
    due_at: datetime


class LessonPromote(BaseModel):
    """The body for signing a lesson as a card.

    ⭐ Both source fields are **required**, and that is the product rather than
    the plumbing. A card's provenance is a URL; a lesson has none. So this is
    where the reader says 「这条我现在愿意署名，出处是……」 - and if they cannot,
    they have not got a card, they have got a lesson, which is already saved
    and already queued. Declining costs nothing, which is what makes declining
    a reasonable answer rather than a failure.
    """

    model_config = ConfigDict(extra="forbid")

    source_url: str
    source_title: str
    claim_type: str = Field(
        default="neutral",
        description=(
            "supporting / challenging / neutral。默认 neutral，因为"
            "**教训本身不是方向性主张** ——「下次先看批价」是方法，不是立场。"
        ),
    )


class LessonPromotedRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    lesson_id: str
    card_id: str
    promoted_at: datetime


class LessonReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: ReviewRating
    duration_ms: int | None = Field(default=None, gt=0)


# ── the one way in ──────────────────────────────────────────────────────────


@router.post(
    "/reviews/{decision_id}/lesson",
    status_code=http_status.HTTP_201_CREATED,
    summary="Turn a review into a lesson, and schedule it - one transaction",
)
def record_lesson(
    decision_id: str,
    payload: LessonCreate,
    connection: DatabaseConnection,
) -> LessonRecordedRead:
    """⭐ **Red line 7's endpoint.** The lesson and its schedule are one call.

    There is no separate enrolment verb, and its absence is the guarantee: a
    client cannot create a lesson that is not on the queue, because there is no
    code path that does one without the other.
    """
    try:
        with transaction(connection):
            row, schedule = repository.record_from_review(
                connection, decision_id, payload.content, now=_now()
            )
    except LessonReviewMissingError as cause:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(cause)
        ) from cause
    except (LessonContentBlankError, LessonTooLongError) as cause:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(cause)
        ) from cause
    return LessonRecordedRead(
        lesson=LessonRead(
            lesson_id=row.lesson_id,
            review_id=row.review_id,
            content=row.content,
            created_at=row.created_at,
        ),
        state=schedule.state,
        due_at=schedule.due_at,
    )


@router.get("/lessons", summary="Every lesson, newest first")
def list_lessons(connection: DatabaseConnection) -> list[LessonRead]:
    """All lessons, for a list a reader browses rather than is interrupted by.

    No count, like every other list in this API. A tally of how many lessons you
    have is a number you can start climbing, and red line 11 is explicit that
    these things do not render.
    """
    rows = connection.execute(
        "SELECT lesson_id, review_id, content, created_at FROM lessons "
        "ORDER BY created_at DESC, lesson_id DESC"
    ).fetchall()
    return [
        LessonRead(
            lesson_id=row["lesson_id"],
            review_id=row["review_id"],
            content=row["content"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.get(
    "/lessons/due",
    summary="The lessons that came back on their own",
)
def due_lessons(
    connection: DatabaseConnection,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[LessonScheduleRead]:
    """The queue, oldest due first. A bare array, **no count**, no title per row.

    ``content`` is there because the reader has to read something, and it is the
    lesson's own sentence rather than a label standing in for it.
    """
    pairs = repository.due_lessons(connection, as_of=_now(), limit=limit)
    return [
        LessonScheduleRead(
            lesson_id=schedule.lesson_id,
            state=schedule.state,
            due_at=schedule.due_at,
            content=lesson.content,
        )
        for schedule, lesson in pairs
    ]


# ── promotion ───────────────────────────────────────────────────────────────


@router.post(
    "/lessons/{lesson_id}/promote",
    status_code=http_status.HTTP_201_CREATED,
    summary="Sign a lesson as a card - a source is required",
)
def promote_lesson(
    lesson_id: str,
    payload: LessonPromote,
    connection: DatabaseConnection,
) -> LessonPromotedRead:
    """Write the card and the promotion record. One transaction, both or neither.

    ⭐ **The lesson stays on its own queue.** Red line 7 must have no escape
    hatch, and a branch reading 「转了卡就不用再复习了」 is exactly the kind of clause
    that turns a guarantee back into a suggestion - and it would be invisible,
    because the queue would still *look* right.
    """
    try:
        claim_type = ClaimType(payload.claim_type)
    except ValueError as cause:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                "claim_type 必须是 supporting / challenging / neutral，"
                f"得到「{payload.claim_type}」。"
            ),
        ) from cause

    try:
        with transaction(connection):
            promotion = repository.promote_lesson(
                connection,
                lesson_id,
                payload.source_url,
                payload.source_title,
                now=_now(),
                claim_type=claim_type,
            )
    except LessonPromotionSourceError as cause:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(cause)
        ) from cause
    except LessonAlreadyPromotedError as cause:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(cause)
        ) from cause
    except LessonNotFoundError as cause:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(cause)
        ) from cause
    return LessonPromotedRead(
        lesson_id=promotion.lesson_id,
        card_id=promotion.card_id,
        promoted_at=promotion.promoted_at,
    )


@router.post(
    "/lessons/{lesson_id}/review",
    summary="Record a revisit and move the schedule",
)
def review_lesson(
    lesson_id: str,
    payload: LessonReviewInput,
    connection: DatabaseConnection,
) -> dict[str, Any]:
    """Record how the revisit went.

    ⭐ For a lesson, ``again`` means 「我不同意我学到的东西了」 rather than 「我忘了」.
    A lesson is something the reader *concluded*, so the interesting failure is
    not forgetting it but no longer believing it - and calling that "you forgot"
    would label the most valuable answer this queue collects as a lapse.

    ``duration_ms`` is stored and never compared (red line 11).
    """
    try:
        with transaction(connection):
            row = repository.record_review(
                connection,
                lesson_id,
                payload.rating,
                now=_now(),
                duration_ms=payload.duration_ms,
            )
    except LessonNotFoundError as cause:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(cause)
        ) from cause
    return {
        "lesson_id": row.lesson_id,
        "outcome": row.outcome.value,
        "rating": row.rating.value if row.rating else None,
        "from_due_at": utc_millis(row.from_due_at),
        "to_due_at": utc_millis(row.to_due_at),
        "from_state": row.from_state.value,
        "to_state": row.to_state.value,
    }
