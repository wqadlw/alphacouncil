"""Repository for review scheduling: the queue row and the append-only log.

K3 (spec 018). Two rules shape everything here, and both were settled by asking
``fsrs`` what it actually does rather than by guessing (see the spec, §1):

* **A deferral must not damage the memory.** ``fsrs`` has no notion of "not
  now" — ``Scheduler.reschedule_card`` is for recomputing a card after a
  *scheduler configuration* change, and passing it a ``datetime`` raises
  ``TypeError``. So :func:`defer` is ours, and its contract is narrow on purpose:
  it moves ``due_at`` and the queue-facing ``state``, and carries
  ``state_json`` through **byte for byte**. "Not right now" is not a failed
  recall, so it earns no rating, no duration, and no stability change.
* **Every interaction appends a row.** ``card_reviews`` is append-only, and the
  log INSERT and the ``card_schedule`` UPDATE happen in **one transaction** — so
  "the schedule moved but nothing was recorded" and "something was recorded but
  the schedule did not move" are both impossible rather than merely unlikely.

**Why a separate table from ``card_events``** (ADR-0014's precedent, split
rather than merge): lifecycle events are rare and carry a user-written reason;
review facts are frequent and entirely structured. One shape per table.

The FSRS payload is stored as one JSON column rather than seven columns because
``Card.to_dict()`` → ``from_dict()`` round-trips losslessly, so an algorithm
upgrade needs no migration of our schema.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.scheduling import (
    DEFAULT_DEFERRAL_DAYS,
    CardAlreadyScheduledError,
    CardNotScheduledError,
    ReviewOutcome,
    ReviewRating,
    ScheduleSnapshot,
    ScheduleState,
    as_utc_iso,
    decode_payload,
    defer_due,
    parse_due,
    rating_to_fsrs,
    require_utc,
    state_of,
)
from alphacouncil.storage.db import require_open_transaction

__all__ = [
    "ReviewRow",
    "ScheduleRow",
    "defer",
    "due_cards",
    "enroll",
    "get_schedule",
    "list_reviews",
    "record_review",
]


@dataclass(frozen=True, slots=True)
class ScheduleRow:
    """One row of ``card_schedule``."""

    card_id: str
    fsrs_card_id: int
    payload: str
    state: ScheduleState
    due_at: datetime
    enrolled_at: datetime
    updated_at: datetime

    def as_snapshot(self) -> ScheduleSnapshot:
        return ScheduleSnapshot(
            card_id=self.card_id,
            fsrs_card_id=self.fsrs_card_id,
            payload=self.payload,
            state=self.state,
            due_at=self.due_at,
            enrolled_at=self.enrolled_at,
            updated_at=self.updated_at,
        )

    def fsrs_payload(self) -> dict[str, object]:
        """The stored JSON, decoded. Delegates so there is one decoder, not two."""
        return decode_payload(self.payload, card_id=self.card_id)


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """One row of ``card_reviews`` — an interaction, never edited."""

    id: str
    card_id: str
    outcome: ReviewOutcome
    rating: ReviewRating | None
    reviewed_at: datetime
    duration_ms: int | None
    from_due_at: datetime
    to_due_at: datetime
    from_state: ScheduleState
    to_state: ScheduleState


_INSERT_SCHEDULE = (
    "INSERT INTO card_schedule "
    "(card_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)

_INSERT_REVIEW = (
    "INSERT INTO card_reviews "
    "(id, card_id, outcome, rating, reviewed_at, duration_ms, "
    " from_due_at, to_due_at, from_state, to_state) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _new_id(prefix: str) -> str:
    """A millisecond-stamped id, the same scheme the cards table uses.

    Server-generated on purpose: a review is evidence of when the user answered,
    and a client-supplied timestamp would let them move their own evidence
    (the same reasoning as ADR-0011 for decision ids).
    """
    return f"{prefix}_{int(time.time() * 1000)}"


def _fresh_fsrs_card(
    fsrs_card_id: int, *, due: datetime
) -> tuple[int, str, ScheduleState, datetime]:
    """Build a brand-new FSRS card, due at ``due``, and describe it in our terms.

    ``fsrs`` gives a new card a due date of *the wall clock's* now. That is
    right for a library and wrong for us: enrolment takes an injected ``now`` so
    that "is this card due yet?" is a question about a stated instant rather than
    about whenever the test happened to run. So the payload's ``due`` is
    **overwritten** with the caller's moment — a brand-new card is due
    immediately, and the moment you enrolled it is that moment.

    ``fsrs_card_id`` is a **distinct integer per card**. It is never used to look
    anything up (we always rebuild the card from the stored payload), but it
    travels into the review log, and a log full of ``card_id=1`` is a log that
    cannot be read.
    """
    import fsrs

    card = fsrs.Card(card_id=fsrs_card_id)
    payload = dict(card.to_dict())
    payload["card_id"] = fsrs_card_id
    payload["due"] = as_utc_iso(due)
    state = state_of(payload)
    return fsrs_card_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), state, due


def _row_to_schedule(row: sqlite3.Row) -> ScheduleRow:
    return ScheduleRow(
        card_id=row["card_id"],
        fsrs_card_id=int(row["fsrs_card_id"]),
        payload=row["state_json"],
        state=ScheduleState(row["state"]),
        due_at=parse_due(row["due_at"]),
        enrolled_at=parse_due(row["enrolled_at"]),
        updated_at=parse_due(row["updated_at"]),
    )


def _row_to_review(row: sqlite3.Row) -> ReviewRow:
    return ReviewRow(
        id=row["id"],
        card_id=row["card_id"],
        outcome=ReviewOutcome(row["outcome"]),
        rating=ReviewRating(row["rating"]) if row["rating"] else None,
        reviewed_at=parse_due(row["reviewed_at"]),
        duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
        from_due_at=parse_due(row["from_due_at"]),
        to_due_at=parse_due(row["to_due_at"]),
        from_state=ScheduleState(row["from_state"]),
        to_state=ScheduleState(row["to_state"]),
    )


def get_schedule(connection: sqlite3.Connection, card_id: str) -> ScheduleRow:
    """Read one card's schedule, or say it has none."""
    row = connection.execute(
        "SELECT card_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at "
        "FROM card_schedule WHERE card_id = ?",
        (card_id,),
    ).fetchone()
    if row is None:
        raise CardNotScheduledError(f"card {card_id} is not on the review queue")
    return _row_to_schedule(row)


def enroll(
    connection: sqlite3.Connection,
    card_id: str,
    *,
    now: datetime | None = None,
) -> ScheduleRow:
    """Put a card on the review queue. This is "generating a scheduling item".

    Refuses a second enrolment rather than resetting the card: re-enrolling a
    card that has three reviews behind it would hand it a fresh stability and
    make a months-old lesson look like it was learned today, which is the exact
    inversion of what the queue is for.
    """
    moment = require_utc(now or datetime.now(UTC), field="now")
    existing = connection.execute(
        "SELECT 1 FROM card_schedule WHERE card_id = ?", (card_id,)
    ).fetchone()
    if existing is not None:
        raise CardAlreadyScheduledError(
            f"card {card_id} is already scheduled; review it rather than enrolling it again"
        )

    next_id = connection.execute(
        "SELECT COALESCE(MAX(fsrs_card_id), 0) + 1 FROM card_schedule"
    ).fetchone()[0]
    fsrs_id = int(next_id)
    _fsrs_id, payload, state, due = _fresh_fsrs_card(fsrs_id, due=moment)
    stamp = utc_millis(moment)
    connection.execute(
        _INSERT_SCHEDULE,
        (card_id, fsrs_id, payload, state.value, as_utc_iso(due), stamp, stamp),
    )
    return ScheduleRow(
        card_id=card_id,
        fsrs_card_id=fsrs_id,
        payload=payload,
        state=state,
        due_at=due,
        enrolled_at=moment,
        updated_at=moment,
    )


def due_cards(
    connection: sqlite3.Connection,
    *,
    as_of: datetime,
    limit: int = 50,
) -> tuple[ScheduleRow, ...]:
    """The queue, oldest due first.

    Ordering is by ``due_at`` alone. Not by stability, not by priority, and
    certainly not by anything resembling urgency score: those are all ways of
    ranking the user's own backlog, and the product's job is to show it, not to
    grade it. Ties break on ``card_id`` so the order is stable between calls —
    a queue that reshuffles on every open makes "I have handled it" feel futile.
    """
    require_utc(as_of, field="as_of")
    rows = connection.execute(
        "SELECT card_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at "
        "FROM card_schedule WHERE due_at <= ? ORDER BY due_at ASC, card_id ASC LIMIT ?",
        (as_utc_iso(as_of), limit),
    ).fetchall()
    return tuple(_row_to_schedule(row) for row in rows)


def record_review(
    connection: sqlite3.Connection,
    card_id: str,
    rating: ReviewRating,
    *,
    now: datetime | None = None,
    duration_ms: int | None = None,
) -> ReviewRow:
    """Record a real recall and move the schedule. One transaction, both or neither.

    ``duration_ms`` is stored and never compared. Red line 11 says so in as many
    words: knowing how long an answer took is for self-reflection, and the moment
    it becomes a ranking the product has started measuring the user.
    """
    import fsrs

    moment = require_utc(now or datetime.now(UTC), field="now")
    before = get_schedule(connection, card_id)
    if before.state is ScheduleState.DEFERRED:
        raise CardNotScheduledError(
            f"card {card_id} was deferred; it has no recall to record until it is due again"
        )

    require_open_transaction(connection, operation="scheduling.record_review")
    scheduler = fsrs.Scheduler(enable_fuzzing=False)
    # The cast is honest rather than convenient: `state_json` is written only by
    # this module, its CHECK guarantees it is a JSON object, and the round-trip
    # was verified lossless (spec 018 §1, Q3). `fsrs` types the argument as a
    # TypedDict, which a runtime-validated dict cannot be proven to be.
    card = fsrs.Card.from_dict(cast("Any", before.fsrs_payload()))
    reviewed, _log = scheduler.review_card(
        card,
        rating_to_fsrs(rating),
        moment,
        duration_ms,
    )
    payload = dict(reviewed.to_dict())
    after_state = state_of(payload)
    after_due = parse_due(str(payload["due"]))

    row = ReviewRow(
        id=_new_id("review"),
        card_id=card_id,
        outcome=ReviewOutcome.REVIEWED,
        rating=rating,
        reviewed_at=moment,
        duration_ms=duration_ms,
        from_due_at=before.due_at,
        to_due_at=after_due,
        from_state=before.state,
        to_state=after_state,
    )
    connection.execute(
        _INSERT_REVIEW,
        (
            row.id,
            row.card_id,
            row.outcome.value,
            None if row.rating is None else row.rating.value,
            utc_millis(row.reviewed_at),
            row.duration_ms,
            as_utc_iso(row.from_due_at),
            as_utc_iso(row.to_due_at),
            row.from_state.value,
            row.to_state.value,
        ),
    )
    connection.execute(
        "UPDATE card_schedule SET state_json = ?, state = ?, due_at = ?, updated_at = ? "
        "WHERE card_id = ?",
        (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            after_state.value,
            as_utc_iso(after_due),
            utc_millis(moment),
            card_id,
        ),
    )
    return row


def defer(
    connection: sqlite3.Connection,
    card_id: str,
    *,
    now: datetime | None = None,
    days: int = DEFAULT_DEFERRAL_DAYS,
) -> ReviewRow:
    """Postpone a card. One transaction, and the memory is left alone.

    The whole point is what does **not** change: ``state_json`` is written back
    with the identical string it was read as, no rating exists, and no stability
    moves. A mutation check pins that byte-for-byte, because the tempting
    implementation — call ``review_card`` with ``Again`` — would look like
    "deferring" while quietly telling FSRS the user forgot.
    """
    moment = require_utc(now or datetime.now(UTC), field="now")
    before = get_schedule(connection, card_id)
    after_due = defer_due(before.due_at, days=days)
    require_open_transaction(connection, operation="scheduling.defer")

    row = ReviewRow(
        id=_new_id("review"),
        card_id=card_id,
        outcome=ReviewOutcome.DEFERRED,
        rating=None,
        reviewed_at=moment,
        duration_ms=None,
        from_due_at=before.due_at,
        to_due_at=after_due,
        from_state=before.state,
        to_state=ScheduleState.DEFERRED,
    )
    connection.execute(
        _INSERT_REVIEW,
        (
            row.id,
            row.card_id,
            row.outcome.value,
            None,
            utc_millis(row.reviewed_at),
            None,
            as_utc_iso(row.from_due_at),
            as_utc_iso(row.to_due_at),
            row.from_state.value,
            row.to_state.value,
        ),
    )
    connection.execute(
        "UPDATE card_schedule SET state = ?, due_at = ?, updated_at = ? WHERE card_id = ?",
        (ScheduleState.DEFERRED.value, as_utc_iso(after_due), utc_millis(moment), card_id),
    )
    return row


def list_reviews(connection: sqlite3.Connection, card_id: str) -> tuple[ReviewRow, ...]:
    """A card's review history, oldest first."""
    rows = connection.execute(
        "SELECT id, card_id, outcome, rating, reviewed_at, duration_ms, "
        "from_due_at, to_due_at, from_state, to_state "
        "FROM card_reviews WHERE card_id = ? ORDER BY reviewed_at ASC, id ASC",
        (card_id,),
    ).fetchall()
    return tuple(_row_to_review(row) for row in rows)
