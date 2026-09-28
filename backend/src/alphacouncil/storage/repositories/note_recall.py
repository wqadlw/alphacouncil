"""The note recall queue (spec 028).

## What this reuses, verbatim

Every *function* in :mod:`alphacouncil.domain.scheduling` —
``ScheduleState``, ``ReviewRating``, ``defer_due``, ``rating_to_fsrs``,
``state_of``, ``parse_due``, ``as_utc_iso``, ``require_utc`` — is imported and
called. That module was already generic, so the domain layer of this feature is
**zero new logic**, which is the whole reason it is cheap.

What is *not* reused is ``card_schedule``'s SQL and ``CardAlreadyScheduledError``
/ ``CardNotScheduledError``: the first is a different table, and the second would
report a note's problem under a card's name.

## ⭐ The one thing that is genuinely new: an edit restarts the schedule

A card is immutable, so its schedule can only ever move forward. A note has a
``PATCH``, and that breaks an assumption the card queue never had to make:

    enrol on 09-28, three `good` ratings, FSRS says "due in three months"
    10-02   the note is rewritten from scratch
    12-28   it comes due; the reader is asked to recall text they have
            never reviewed, while the scheduler believes they remember it well

That is the scheduler lying, and this product's premise is that the record is the
one thing the reader can trust. So :func:`reset_on_edit` rebuilds the FSRS card
(``stability`` back to nothing, due now) and appends a
``NoteReviewOutcome.RESET`` row, and the append-only history keeps every earlier
review.

A reset is recorded rather than merely performed because without a row,
「I reviewed this five times, so why did it come back today?」 has no answer —
and the record of learning attempts is, for this product, the product.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any, cast

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.note_recall import (
    NoteAlreadyScheduledError,
    NoteNotScheduledError,
    NoteReviewOutcome,
    NoteReviewRow,
    NoteScheduleRow,
)
from alphacouncil.domain.scheduling import (
    DEFAULT_DEFERRAL_DAYS,
    ReviewRating,
    ScheduleState,
    as_utc_iso,
    defer_due,
    parse_due,
    rating_to_fsrs,
    require_utc,
    state_of,
)
from alphacouncil.storage.db import require_open_transaction

__all__ = [
    "defer",
    "due_notes",
    "enroll",
    "get_schedule",
    "is_scheduled",
    "list_reviews",
    "record_review",
    "reset_on_edit",
]


# ── SQL ─────────────────────────────────────────────────────────────────────

_INSERT_SCHEDULE = """
INSERT INTO note_schedule
    (note_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_SCHEDULE = """
SELECT note_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at
FROM note_schedule WHERE note_id = ?
"""

_SELECT_DUE = """
SELECT note_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at
FROM note_schedule
WHERE due_at <= ?
ORDER BY due_at ASC, note_id ASC
LIMIT ?
"""

_INSERT_REVIEW = """
INSERT INTO note_reviews
    (id, note_id, outcome, rating, reviewed_at, duration_ms,
     from_due_at, to_due_at, from_state, to_state)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_REVIEWS = """
SELECT id, note_id, outcome, rating, reviewed_at, duration_ms,
       from_due_at, to_due_at, from_state, to_state
FROM note_reviews
WHERE note_id = ?
ORDER BY reviewed_at ASC, id ASC
"""

_UPDATE_SCHEDULE_AFTER_REVIEW = """
UPDATE note_schedule SET state_json = ?, state = ?, due_at = ?, updated_at = ?
WHERE note_id = ?
"""

#: ⭐ A **reset** also replaces the FSRS handle, so it needs its own statement.
#:
#: Reusing ``_UPDATE_SCHEDULE_AFTER_REVIEW`` here was right until it was not: that
#: statement is correct for a *review*, which keeps the same FSRS card, and a reset
#: mints a new one. The result was a row whose ``fsrs_card_id`` column said ``1``
#: while the ``state_json`` beside it said ``{"card_id": 2, ...}`` — a disagreement
#: the schema permits, nothing else reads, and only a test comparing both halves
#: would ever surface.
_UPDATE_SCHEDULE_AFTER_RESET = """
UPDATE note_schedule
SET fsrs_card_id = ?, state_json = ?, state = ?, due_at = ?, updated_at = ?
WHERE note_id = ?
"""


# ── helpers ─────────────────────────────────────────────────────────────────


#: How far past the requested millisecond to look for a free id.
#:
#: 1000 is one second. Past that two reviews are not "the same moment" any more,
#: and an id that lies about when it was written would break the reading the whole
#: scheme exists for — a review row is evidence of *when the reader acted*.
_ID_COLLISION_LIMIT = 1_000


def _new_id(connection: sqlite3.Connection, prefix: str) -> str:
    """A millisecond-stamped id that is not already taken.

    Server-generated for the same reason card review ids are: a review is evidence
    of when the reader acted, and a client-supplied timestamp would let them move
    their own evidence (ADR-0011).

    ⭐ **Walks forward until free.** The bare `f"{prefix}_{millis}"` this replaced
    dies with ``UNIQUE constraint failed`` when two reviews land in one
    millisecond, which a test suite does routinely and a fast reader does when
    tapping through a queue.

    This is the same hazard spec 026 found for note ids, and it is **inherited,
    not invented** — ``card_reviews`` still has it, which is why the K1 changelog
    records a same-millisecond boundary for cards. Two rules argued for fixing it
    rather than documenting it: losing a review row loses *evidence*, and the only
    alternative to raising is overwriting one, which is the failure the whole
    append-only discipline exists to prevent.
    """
    base = int(time.time() * 1000)
    for offset in range(_ID_COLLISION_LIMIT):
        candidate = f"{prefix}_{base + offset}"
        taken = connection.execute(
            "SELECT 1 FROM note_reviews WHERE id = ?", (candidate,)
        ).fetchone()
        if taken is None:
            return candidate
    raise NoteNotScheduledError(
        "无法为这次复习生成唯一 id：同一毫秒内已有多达 "
        f"{_ID_COLLISION_LIMIT} 条复习记录。"
    )


def _fresh_fsrs_card(
    fsrs_card_id: int, *, due: datetime
) -> tuple[int, str, ScheduleState, datetime]:
    """A brand-new FSRS card, due at ``due``, described in our terms.

    Copied from the card repository's `_fresh_fsrs_card` rather than imported,
    and that is a real duplication: the card version takes a ``card_id`` and
    returns a ``ScheduleRow``-shaped tuple, and importing it would mean either a
    card-named type in the note path or a second public name for one function.
    The *body* is the same because ``fsrs`` takes an int either way, and the
    inline comment in the card copy explains why ``due`` is overwritten.
    """
    import fsrs

    card = fsrs.Card(card_id=fsrs_card_id)
    payload = dict(card.to_dict())
    payload["card_id"] = fsrs_card_id
    payload["due"] = as_utc_iso(due)
    return (
        fsrs_card_id,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        state_of(payload),
        due,
    )


def _row_to_schedule(row: sqlite3.Row) -> NoteScheduleRow:
    return NoteScheduleRow(
        note_id=row["note_id"],
        fsrs_card_id=int(row["fsrs_card_id"]),
        payload=row["state_json"],
        state=ScheduleState(row["state"]),
        due_at=parse_due(row["due_at"]),
        enrolled_at=parse_due(row["enrolled_at"]),
        updated_at=parse_due(row["updated_at"]),
    )


def _row_to_review(row: sqlite3.Row) -> NoteReviewRow:
    return NoteReviewRow(
        id=row["id"],
        note_id=row["note_id"],
        outcome=NoteReviewOutcome(row["outcome"]),
        rating=ReviewRating(row["rating"]) if row["rating"] else None,
        reviewed_at=parse_due(row["reviewed_at"]),
        duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
        from_due_at=parse_due(row["from_due_at"]),
        to_due_at=parse_due(row["to_due_at"]),
        from_state=ScheduleState(row["from_state"]),
        to_state=ScheduleState(row["to_state"]),
    )


def _write_review(
    connection: sqlite3.Connection,
    *,
    note_id: str,
    outcome: NoteReviewOutcome,
    rating: ReviewRating | None,
    moment: datetime,
    duration_ms: int | None,
    before: NoteScheduleRow,
    after_due: datetime,
    after_state: ScheduleState,
) -> NoteReviewRow:
    row = NoteReviewRow(
        id=_new_id(connection, "note_review"),
        note_id=note_id,
        outcome=outcome,
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
            row.note_id,
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
    return row


# ── public API ──────────────────────────────────────────────────────────────


def get_schedule(connection: sqlite3.Connection, note_id: str) -> NoteScheduleRow:
    """One note's schedule, or say it has none."""
    row = connection.execute(_SELECT_SCHEDULE, (note_id,)).fetchone()
    if row is None:
        raise NoteNotScheduledError(
            f"note {note_id} is not on the recall queue"
        )
    return _row_to_schedule(row)


def is_scheduled(connection: sqlite3.Connection, note_id: str) -> bool:
    """Whether the note is on the queue.

    Separate from :func:`get_schedule` because ``reset_on_edit`` needs the answer
    for **every** note on every edit, and a note that is not on the queue is the
    common case — raising and catching an exception for it would make the ordinary
    path pay for the interesting one.
    """
    return (
        connection.execute(
            "SELECT 1 FROM note_schedule WHERE note_id = ?", (note_id,)
        ).fetchone()
        is not None
    )


def enroll(
    connection: sqlite3.Connection,
    note_id: str,
    *,
    now: datetime | None = None,
) -> NoteScheduleRow:
    """Put a note on the recall queue.

    ⭐ **Always explicit.** Enrolling every note the user ever wrote would build a
    backlog nobody drains, and 「你欠 N 条」 is exactly the feeling the product's
    red lines reject (`项目总纲` §2.1⑤: 一句陈述，无推送、无红点、无催促词).
    So the reader says which things they want to be brought back to.

    A second enrolment is refused rather than reset, for the same reason cards
    refuse it: re-enrolling would hand a note with three reviews behind it a fresh
    stability, making a months-old view look like it had just been formed.
    """
    moment = require_utc(now or datetime.now(UTC), field="now")
    if is_scheduled(connection, note_id):
        raise NoteAlreadyScheduledError(
            f"note {note_id} is already on the recall queue; "
            f"review it rather than enrolling it again"
        )
    require_open_transaction(connection, operation="note_recall.enroll")

    next_id = connection.execute(
        "SELECT COALESCE(MAX(fsrs_card_id), 0) + 1 FROM note_schedule"
    ).fetchone()[0]
    fsrs_id = int(next_id)
    _fsrs_id, payload, state, due = _fresh_fsrs_card(fsrs_id, due=moment)
    stamp = utc_millis(moment)
    connection.execute(
        _INSERT_SCHEDULE,
        (note_id, fsrs_id, payload, state.value, as_utc_iso(due), stamp, stamp),
    )
    return NoteScheduleRow(
        note_id=note_id,
        fsrs_card_id=fsrs_id,
        payload=payload,
        state=state,
        due_at=due,
        enrolled_at=moment,
        updated_at=moment,
    )


def due_notes(
    connection: sqlite3.Connection,
    *,
    as_of: datetime,
    limit: int = 50,
) -> tuple[NoteScheduleRow, ...]:
    """The queue, oldest due first.

    ⭐ **Ordered by ``due_at`` alone** — not by stability, not by a priority the
    user set, and certainly not by an urgency score. Those are all ways of
    ranking the reader's own backlog, and the product's job is to show it, not to
    grade it. Ties break on ``note_id`` so the order is stable between calls: a
    queue that reshuffles on every open makes 「我处理过了」 feel futile.
    """
    require_utc(as_of, field="as_of")
    rows = connection.execute(
        _SELECT_DUE, (as_utc_iso(as_of), limit)
    ).fetchall()
    return tuple(_row_to_schedule(row) for row in rows)


def record_review(
    connection: sqlite3.Connection,
    note_id: str,
    rating: ReviewRating,
    *,
    now: datetime | None = None,
    duration_ms: int | None = None,
) -> NoteReviewRow:
    """Record a re-read and move the schedule. One transaction, both or neither.

    ⭐ For a note, ``again`` does **not** mean 「I could not recall it」 — it means
    「**我的想法已经变了**」. That is the most valuable signal this product can get,
    and calling it "you forgot" in the UI would dress the best feedback it gets as
    a failure.

    ``duration_ms`` is stored and never compared (red line 11): knowing how long a
    re-read took is for self-reflection, and the moment it becomes a ranking the
    product has started measuring the reader.
    """
    import fsrs

    moment = require_utc(now or datetime.now(UTC), field="now")
    before = get_schedule(connection, note_id)
    if before.state is ScheduleState.DEFERRED:
        raise NoteNotScheduledError(
            f"note {note_id} is deferred; there is nothing to recall until it is due again"
        )
    require_open_transaction(connection, operation="note_recall.record_review")

    scheduler = fsrs.Scheduler(enable_fuzzing=False)
    card = fsrs.Card.from_dict(cast("Any", before.fsrs_payload()))
    reviewed, _log = scheduler.review_card(card, rating_to_fsrs(rating), moment, duration_ms)
    payload = dict(reviewed.to_dict())
    after_state = state_of(payload)
    after_due = parse_due(str(payload["due"]))

    row = _write_review(
        connection,
        note_id=note_id,
        outcome=NoteReviewOutcome.REVIEWED,
        rating=rating,
        moment=moment,
        duration_ms=duration_ms,
        before=before,
        after_due=after_due,
        after_state=after_state,
    )
    connection.execute(
        _UPDATE_SCHEDULE_AFTER_REVIEW,
        (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            after_state.value,
            as_utc_iso(after_due),
            utc_millis(moment),
            note_id,
        ),
    )
    return row


def defer(
    connection: sqlite3.Connection,
    note_id: str,
    *,
    now: datetime | None = None,
    days: int = DEFAULT_DEFERRAL_DAYS,
) -> NoteReviewRow:
    """Postpone a note. One transaction, and the memory is left alone.

    ⭐ For a note this is 「**我的想法还没定**」 rather than 「现在不方便」, but the
    mechanics are identical to a card's and the discipline is the strictest thing
    here: ``state_json`` is written back with the identical string it was read as.
    「还没想清楚」 is not a failure and must not touch memory strength — a note
    pushed three times should not come back angrier each time.
    """
    moment = require_utc(now or datetime.now(UTC), field="now")
    before = get_schedule(connection, note_id)
    require_open_transaction(connection, operation="note_recall.defer")

    after_due = defer_due(before.due_at, days=days)
    row = _write_review(
        connection,
        note_id=note_id,
        outcome=NoteReviewOutcome.DEFERRED,
        rating=None,
        moment=moment,
        duration_ms=None,
        before=before,
        after_due=after_due,
        after_state=ScheduleState.DEFERRED,
    )
    connection.execute(
        "UPDATE note_schedule SET state = ?, due_at = ?, updated_at = ? "
        "WHERE note_id = ?",
        (
            ScheduleState.DEFERRED.value,
            as_utc_iso(after_due),
            utc_millis(moment),
            note_id,
        ),
    )
    return row


def reset_on_edit(
    connection: sqlite3.Connection,
    note_id: str,
    *,
    now: datetime | None = None,
) -> NoteReviewRow | None:
    """⭐ Restart the schedule because the note's text was replaced.

    Returns ``None`` when the note is not on the queue — and that is the common
    case, not an error. Most notes will never be enrolled, and an edit to one of
    them has nothing to do to a queue it is not in.

    What it does when the note *is* on the queue:

    1. builds a **new** FSRS card, so stability is nothing again and it is due
       now — because the reader has never reviewed this text;
    2. appends a ``reset`` row recording that this happened, and when.

    Step 2 is the part that is easy to leave out and impossible to add later: a
    reset with no row is invisible, and the reader's question — 「我复习过好几次，
    为什么今天又来?」 — would have no answer. Nothing in ``note_reviews`` is ever
    edited or deleted, so the earlier reviews all survive.
    """
    if not is_scheduled(connection, note_id):
        return None

    moment = require_utc(now or datetime.now(UTC), field="now")
    before = get_schedule(connection, note_id)
    require_open_transaction(connection, operation="note_recall.reset_on_edit")

    # A fresh handle too, so a reset is visible in the FSRS stream as a distinct
    # card rather than a reuse of the old one with a new payload.
    next_id = connection.execute(
        "SELECT COALESCE(MAX(fsrs_card_id), 0) + 1 FROM note_schedule"
    ).fetchone()[0]
    fsrs_id = int(next_id)
    _fsrs_id, payload, state, due = _fresh_fsrs_card(fsrs_id, due=moment)

    row = _write_review(
        connection,
        note_id=note_id,
        outcome=NoteReviewOutcome.RESET,
        rating=None,
        moment=moment,
        duration_ms=None,
        before=before,
        after_due=due,
        after_state=state,
    )
    connection.execute(
        _UPDATE_SCHEDULE_AFTER_RESET,
        (
            fsrs_id,
            # ⚠️ `payload` is **already a JSON string** — `_fresh_fsrs_card`
            # serialises it. Encoding it again stores a JSON *string literal*, and
            # `json_type(...)` of that is `text`, not `object`, so the row fails
            # `note_schedule_state_json_valid_check`.
            #
            # Worth naming because `enroll` passes the same value straight through
            # while `record_review` re-encodes a *dict* it got from
            # `fsrs_payload()`. Three call sites, two types, and only the
            # mismatch is wrong — so the comment is here rather than at the type.
            payload,
            state.value,
            as_utc_iso(due),
            utc_millis(moment),
            note_id,
        ),
    )
    return row


def list_reviews(
    connection: sqlite3.Connection, note_id: str
) -> tuple[NoteReviewRow, ...]:
    """Everything that ever happened to this note's schedule, oldest first.

    The reason a reset is worth a row: this is the function that answers it.
    """
    return tuple(
        _row_to_review(row)
        for row in connection.execute(_SELECT_REVIEWS, (note_id,)).fetchall()
    )
