"""The note recall queue — a second, honest copy of the card queue's shape (spec 028).

## What is reused and what is not, and why

`domain/scheduling.py` is **already generic**: `ScheduleState`, `ReviewRating`,
`defer_due`, `rating_to_fsrs`, `state_of`, `parse_due` and `as_utc_iso` contain no
card types. Every one of those is imported and called, not copied. The two card
error classes are *not* reused — they are named for cards, and a note error
arriving as `CARD_NOT_SCHEDULED` would be a message about the wrong thing.

`ScheduleRow` is **not** reused either, and that is the one duplication worth
making. It has a field called ``card_id``. Handing it a note id would put a lie
into a type every downstream reader sees. Twelve duplicated lines buy an honest
name; a copy-paste of the *logic* would buy a second implementation to keep in
step.

## ⭐ Why a separate queue at all, when the shapes match

Because of one asymmetry, and it is not a small one:

* a **card** is immutable — K1 deliberately offers no edit verb, so "the thing I
  reviewed" is stable forever;
* a **note** is working text and has a ``PATCH``.

So a note on the queue can be rewritten, and its FSRS stability would then be
attached to text that no longer exists. A scheduler that claims you remember
something you have never read is a scheduler lying, and this product's entire
premise is that your record is the one thing you can trust.

Hence :data:`NoteReviewOutcome.RESET`, which is **note-specific and could not be
card-specific** — an immutable card never needs it. That asymmetry is the
strongest available evidence that merging the two tables would have been wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.domain.scheduling import (
    ReviewRating,
    ScheduleState,
    TimestampNotUtcError,
)

__all__ = [
    "NoteAlreadyScheduledError",
    "NoteNotScheduledError",
    "NoteRecallError",
    "NoteReviewOutcome",
    "NoteReviewRow",
    "NoteScheduleRow",
    "TimestampNotUtcError",
]


class NoteReviewOutcome(StrEnum):
    """What happened to a note on the recall queue.

    ⭐ Three states, and the third is the reason this module exists.

    ``REVIEWED``
        I re-read it and said whether I still hold it. A rating applies.

    ``DEFERRED``
        Not now — for a note that usually means **the thought is not settled**.
        Nothing about the memory changes: not the stability, not the payload.

    ``RESET``
        The note was **rewritten**, so the schedule restarted.

    A reset is not a kind of review: the reader recalled nothing, so there is no
    rating and no duration. And it is not a kind of deferral either, because the
    two move in **opposite directions** — a deferral pushes a due date out, a
    reset pulls the card back to "learning" and due now. Both leave the memory
    alone; only the reset rebuilds the FSRS card.

    Recording it is not bookkeeping for its own sake. Without a row here,
    「I reviewed this five times, so why did it come back today?」 has no answer,
    and this product's whole argument is that the record of learning attempts *is*
    the product.
    """

    REVIEWED = "reviewed"
    DEFERRED = "deferred"
    RESET = "reset"


class NoteRecallError(ValueError):
    """Base for every refusal from the note recall queue."""

    code: ErrorCode


class NoteNotScheduledError(NoteRecallError):
    """The note is not on the queue, so there is nothing to review or defer."""

    code = ErrorCode.NOTE_NOT_SCHEDULED


class NoteAlreadyScheduledError(NoteRecallError):
    """Enrolling twice would hand the note a fresh stability.

    A note with three reviews behind it would look like it had just been learned
    — the exact inversion of what the queue is for, and the reason cards refuse
    this too.
    """

    code = ErrorCode.NOTE_ALREADY_SCHEDULED


@dataclass(frozen=True, slots=True)
class NoteScheduleRow:
    """One row of ``note_schedule`` — "where this note stands right now".

    The mutable truth. The history of how it got here lives in
    ``note_reviews``, which is append-only, and the two are never merged: deriving
    the current state from the event stream would let a deleted or reordered row
    silently move it (the decisions/reviews split in ADR-0014).
    """

    note_id: str
    fsrs_card_id: int
    payload: str
    state: ScheduleState
    due_at: datetime
    enrolled_at: datetime
    updated_at: datetime

    def fsrs_payload(self) -> dict[str, object]:
        """The stored FSRS state, decoded.

        Written only by this layer and its CHECK guarantees a JSON object, so the
        cast is honest rather than convenient — the same reasoning the card
        repository records for the identical round trip.
        """
        import json
        from typing import Any, cast

        return cast("dict[str, Any]", json.loads(self.payload))


@dataclass(frozen=True, slots=True)
class NoteReviewRow:
    """One row of ``note_reviews`` — one thing that happened, never edited."""

    id: str
    note_id: str
    outcome: NoteReviewOutcome
    rating: ReviewRating | None
    reviewed_at: datetime
    duration_ms: int | None
    from_due_at: datetime
    to_due_at: datetime
    from_state: ScheduleState
    to_state: ScheduleState
