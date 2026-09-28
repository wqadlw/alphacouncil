"""Review scheduling — the mechanism that makes a lesson come back (K3).

Red line 7 says a lesson must be able to meet you again, and spells out how:
**every lesson generates one scheduling item.** K1 made cards, K2 gave them a
lifecycle, and neither added anything that brings a card back at the right
moment. This module is that missing mechanism, and nothing else.

**What was asked of ``fsrs`` before any of this was designed** (2026-09-28,
``fsrs`` 6.3.2 — the five questions the previous agent's probe script asked and
never recorded; see `.ai/specs/018-fsrs-review-queue/spec.md` §1):

* ``review_card`` does **not** mutate its input; it returns a new ``Card``.
* With ``enable_fuzzing=False`` the same ``(card, rating, now)`` gives the same
  ``due`` — so a test can assert an exact date instead of an approximation.
* ``Card.to_dict()`` → ``from_dict()`` round-trips losslessly, so the whole
  state can be stored as one JSON blob and survive an algorithm upgrade.
* A naive ``datetime`` is **rejected**: *"datetime must be timezone-aware and
  set to UTC"*. Everything here therefore goes through
  :func:`alphacouncil.core.time.utc_now` and never calls ``datetime.now()``.
* ``fsrs.State`` has **three** values — ``Learning`` / ``Review`` /
  ``Relearning``. There is no "not now", so :class:`ScheduleState` adds one.

### Why there is a fourth state, and why it does not touch the memory

``Scheduler.reschedule_card(card, review_logs)`` exists, and it is not what its
name suggests to a newcomer: it recomputes a card **when the scheduler
configuration changed** (verified 2026-09-28 — passing a ``datetime`` raises
``TypeError``). It is not a way to postpone.

So postponing is ours. And the design decision that matters is this:
**postponing must not damage the memory.** "Not right now" is not a failed
recall, so it must not move stability, must not count as a review, and must not
produce a rating. :func:`defer_due` therefore shifts only the due date and the
queue-facing state; the FSRS payload is carried through **byte for byte**.

That is also why :class:`ScheduleState` is an enum and not
``is_deferred: bool`` — a deferred card is still in ``learning``, ``review`` or
``relearning`` underneath, and two booleans would be needed to say that
(constitution 7.7).

### Two things this module deliberately refuses to do

* **No retrievability.** ``Scheduler.get_card_retrievability`` is right there and
  it is never called. It answers "how well do you remember this" — that is a
  **score**, and red line 2 forbids optimising outcomes while red line 9 forbids
  displaying them. The mechanism exists; using it is a product decision, and the
  decision is no.
* **No comparison of ``duration_ms``.** How long a card took is recorded because
  self-knowledge needs it, and red line 11 says in as many words that it must
  never become a ranking or a check-in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from alphacouncil.core.error_codes import ErrorCode

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fsrs import Rating as FsrsRating

__all__ = [
    "DEFAULT_DEFERRAL_DAYS",
    "MAX_DEFERRAL_DAYS",
    "CardAlreadyScheduledError",
    "CardNotScheduledError",
    "ReviewOutcome",
    "ReviewRating",
    "ScheduleState",
    "SchedulingError",
    "TimestampNotUtcError",
    "defer_due",
    "rating_to_fsrs",
    "state_from_fsrs",
]

#: How far out a single "not now" pushes a card. One week, not one day: a card
#: deferred by a day is a card the user will decline again tomorrow, and the
#: point of the queue is that what is in it deserves an answer.
DEFAULT_DEFERRAL_DAYS = 7

#: A ceiling, so a bug cannot park a card in the year 3000 and make it
#: effectively deleted. Deferring is the one operation that moves a card *away*
#: from being seen, and that is exactly the direction this product must be
#: suspicious of (red line 11: do not encourage activity, but do not let things
#: quietly disappear either).
MAX_DEFERRAL_DAYS = 90


class SchedulingError(ValueError):
    """A scheduling request that could not have come from the user."""

    code: ErrorCode = ErrorCode.CARD_NOT_SCHEDULED


class CardNotScheduledError(SchedulingError):
    """The card has no schedule row, so there is nothing to review or defer."""

    code = ErrorCode.CARD_NOT_SCHEDULED


class CardAlreadyScheduledError(SchedulingError):
    """The card is already on the queue.

    Enrolling twice would silently reset a card's stability to a fresh card's and
    make an old lesson look brand new — the exact opposite of what the queue is
    for.
    """

    code = ErrorCode.CARD_ALREADY_SCHEDULED


class TimestampNotUtcError(SchedulingError):
    """A timestamp that is not timezone-aware UTC.

    Its own code because the underlying failure is a *convention* this project
    enforces everywhere else (``core/time.py``, and a ``strftime`` round-trip
    CHECK on every time column). ``fsrs`` rejects a naive datetime with
    ``ValueError: datetime must be timezone-aware and set to UTC``; surfacing
    that as a 500 would be the library's error leaking into our contract, so
    this names the field instead.
    """

    code = ErrorCode.CARD_TIMESTAMP_NOT_UTC


class ScheduleState(StrEnum):
    """Where a card sits, in **our** vocabulary.

    Three values mirror ``fsrs.State``. The fourth is ours: ``deferred`` means
    "not now", and it is a **queue** state, not a memory state — the FSRS payload
    underneath is untouched and still says ``learning`` / ``review`` /
    ``relearning``.
    """

    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"
    DEFERRED = "deferred"


class ReviewRating(StrEnum):
    """How the recall went, in our vocabulary.

    Four grades, because FSRS v6 has four (``Again`` / ``Hard`` / ``Good`` /
    ``Easy``) — not the five some spaced-repetition literature still describes.
    """

    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class ReviewOutcome(StrEnum):
    """What the user did with a due card."""

    REVIEWED = "reviewed"
    DEFERRED = "deferred"


def rating_to_fsrs(rating: ReviewRating) -> FsrsRating:
    """Map our rating onto ``fsrs.Rating``.

    The import is local so that importing this module does not require ``fsrs``
    to be installed — a reader (and several tests) care about the vocabulary,
    not the scheduler.
    """
    import fsrs

    return {
        ReviewRating.AGAIN: fsrs.Rating.Again,
        ReviewRating.HARD: fsrs.Rating.Hard,
        ReviewRating.GOOD: fsrs.Rating.Good,
        ReviewRating.EASY: fsrs.Rating.Easy,
    }[rating]


def state_from_fsrs(fsrs_state_value: int) -> ScheduleState:
    """Map ``fsrs.State``'s integer onto our enum.

    ``deferred`` is unreachable from here **on purpose**: a deferral does not go
    through ``fsrs`` at all, so a payload can never claim to be deferred. If
    ``fsrs`` ever adds a fourth state, this raises rather than guessing.
    """
    mapping = {1: ScheduleState.LEARNING, 2: ScheduleState.REVIEW, 3: ScheduleState.RELEARNING}
    try:
        return mapping[fsrs_state_value]
    except KeyError as exc:
        msg = f"fsrs reported an unknown state value: {fsrs_state_value!r}"
        raise SchedulingError(msg) from exc


def defer_due(current: datetime, *, days: int = DEFAULT_DEFERRAL_DAYS) -> datetime:
    """Push a due date out, refusing a push beyond :data:`MAX_DEFERRAL_DAYS`.

    Returns the new date; the caller is responsible for carrying the FSRS payload
    through unchanged, which is the part that actually matters and is why this
    function only ever touches a date.
    """
    if days < 1:
        msg = f"a deferral of {days} day(s) is not a deferral"
        raise SchedulingError(msg)
    if days > MAX_DEFERRAL_DAYS:
        msg = f"a deferral of {days} days exceeds the {MAX_DEFERRAL_DAYS}-day ceiling"
        raise SchedulingError(msg)
    return current + timedelta(days=days)


@dataclass(frozen=True, slots=True)
class ScheduleSnapshot:
    """A card's scheduling state, as stored.

    ``payload`` is ``fsrs.Card.to_dict()`` verbatim. It is kept as a string
    because storing it as seven columns would mean a migration every time the
    library adds a field, and the round-trip is lossless (verified).
    """

    card_id: str
    fsrs_card_id: int
    payload: str
    state: ScheduleState
    due_at: datetime
    enrolled_at: datetime
    updated_at: datetime

    def fsrs_payload(self) -> dict[str, object]:
        """The stored JSON, decoded. Raises on corruption — never defaults."""
        return decode_payload(self.payload, card_id=self.card_id)

    def is_due(self, *, as_of: datetime) -> bool:
        """Whether the queue should surface this card at ``as_of``.

        The date is injected rather than read from the clock so the boundary is
        testable — and so the same rule can later be evaluated against a
        *stored* date without pretending that date is today.
        """
        return self.due_at <= as_of


def state_of(payload: dict[str, object]) -> ScheduleState:
    """The queue state implied by an FSRS payload.

    Deliberately never returns ``DEFERRED``: a payload carries memory state only.
    Deferral lives in the row's ``state`` column because it is a fact about *this
    queue*, not about the memory.
    """
    value = payload.get("state")
    if not isinstance(value, int):
        msg = f"fsrs payload has no integer state: {value!r}"
        raise SchedulingError(msg)
    return state_from_fsrs(value)


def is_utc(value: datetime) -> bool:
    """Whether a datetime is timezone-aware and on UTC.

    ``fsrs`` raises ``ValueError: datetime must be timezone-aware and set to UTC``
    for anything else, and a review is not the place to discover that a
    timestamp was local. Checking it here turns a library error into ours, with a
    message that says which field.
    """
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def require_utc(value: datetime, *, field: str) -> datetime:
    """Return ``value`` if it is UTC, else raise with a message naming ``field``."""
    if not is_utc(value):
        msg = f"{field} must be timezone-aware UTC; got {value!r}"
        raise TimestampNotUtcError(msg)
    return value


def decode_payload(raw: str, *, card_id: str) -> dict[str, object]:
    """Decode a stored ``state_json``. Corruption is not "no data".

    Shared by the domain snapshot and the repository row so there is exactly one
    definition of what a malformed payload means — a second copy would be free to
    disagree, and "the repository is more lenient than the domain" is precisely
    the kind of drift that lets a corrupt row through the front door.
    """
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        msg = f"card_schedule.state_json for {card_id} is not an object"
        raise SchedulingError(msg)
    return decoded


def as_utc_iso(value: datetime) -> str:
    """Render a datetime the way ``fsrs`` renders it: ISO with an explicit offset."""
    return value.astimezone(UTC).isoformat()


def parse_due(raw: str) -> datetime:
    """Read a stored ``due_at`` back.

    Accepts both shapes on purpose: the offset form ``fsrs`` produces and the
    ``Z`` form the rest of the schema uses. Rejecting one of them would mean a
    migration to change a serialisation nobody looks at.
    """
    text = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        msg = f"stored due date has no timezone: {raw!r}"
        raise SchedulingError(msg)
    return parsed
