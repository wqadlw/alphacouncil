"""Repository for decision reviews: the state row and the append-only log (J3).

Three rules shape this file, and all three come from decisions rather than taste.

**"Has it been reviewed?" is state, not a derived quantity** (ADR-0014, hard rule).
It lives in ``decision_review_state`` and is read from there. It is *never*
inferred from whether ``reviews`` has rows, because a derived quantity can be
changed quietly by something as ordinary as deleting a row — and "I reviewed
this" is not a fact anyone should be able to quietly un-record.

That looks inconsistent with the line below it, and is not: ``review_count``
*is* derived from ``reviews``, because ``reviews`` is **append-only**. One is
inferring state from mutable storage (unreliable); the other is counting rows in
immutable storage (reliable). Both sentences are here because the next reader
will assume one of them is a typo and "tidy them into agreement".

**The early-scoring gate is enforced twice** — once in
:mod:`alphacouncil.domain.review`, and once by the schema's
``reviews_not_scored_early_check``. The second one matters more: it fires even
for a caller that went around the domain layer, which is the whole point of
moving a rule out of discipline and into the database (constitution 0.2).

**The caller owns the transaction** (project convention). This module writes two
tables in ``record``, so it calls
:func:`alphacouncil.storage.db.require_open_transaction` — regression 0006 was
a card that retired with no record of why, because the repository's two writes
were not in one transaction and nothing said so.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.review import (
    Outcome,
    QuadrantJudgement,
    Review,
    ReviewError,
    ReviewNotDueError,
    judge,
)
from alphacouncil.storage.db import require_open_transaction

__all__ = [
    "ReviewRow",
    "ReviewStateMissingError",
    "ReviewStateRow",
    "count_reviews",
    "due_reviews",
    "get_review_state",
    "has_been_reviewed",
    "latest_review",
    "record",
    "reviews_for",
    "schedule",
]


class ReviewStateMissingError(ReviewError):
    """The decision has no review slot, so "has it been reviewed" has no answer.

    Its own code because it is a different question from "the score is invalid":
    one is a bad request, the other is a decision that was never scheduled.
    """

    code = ErrorCode.REVIEW_STATE_MISSING


@dataclass(frozen=True, slots=True)
class ReviewStateRow:
    """One row of ``decision_review_state`` — the single source of truth."""

    decision_id: str
    due_at: datetime
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """One row of ``reviews`` — an interaction, never edited."""

    id: str
    decision_id: str
    process_score: int
    outcome: Outcome | None
    reviewed_at: datetime
    due_at_snapshot: datetime
    note: str | None

    def judgement(self) -> QuadrantJudgement:
        return judge(self.process_score, self.outcome)


def _dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _row_to_state(row: sqlite3.Row) -> ReviewStateRow:
    return ReviewStateRow(
        decision_id=row["decision_id"],
        due_at=_dt(row["due_at"]),
        reviewed_at=_dt(row["reviewed_at"]) if row["reviewed_at"] else None,
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _row_to_review(row: sqlite3.Row) -> ReviewRow:
    return ReviewRow(
        id=row["id"],
        decision_id=row["decision_id"],
        process_score=int(row["process_score"]),
        outcome=Outcome(row["outcome"]) if row["outcome"] else None,
        reviewed_at=_dt(row["reviewed_at"]),
        due_at_snapshot=_dt(row["due_at_snapshot"]),
        note=row["note"],
    )


def schedule(
    connection: sqlite3.Connection,
    decision_id: str,
    *,
    due_at: datetime,
    now: datetime | None = None,
) -> ReviewStateRow:
    """Open a review slot for a decision.

    ``due_at`` is given by the caller and **not computed**. ``项目总纲`` suggests
    "bought 90 days ago, time for a first review", and the rule for *that* is
    still undefined — a due date computed from an unstated policy would be a
    policy nobody agreed to. The caller states it, and the system records it.
    """
    moment = now or datetime.now(UTC)
    stamp = utc_millis(moment)
    connection.execute(
        "INSERT INTO decision_review_state "
        "(decision_id, due_at, reviewed_at, created_at, updated_at) "
        "VALUES (?, ?, NULL, ?, ?)",
        (decision_id, due_at.isoformat(), stamp, stamp),
    )
    return ReviewStateRow(
        decision_id=decision_id,
        due_at=due_at,
        reviewed_at=None,
        created_at=moment,
        updated_at=moment,
    )


def get_review_state(connection: sqlite3.Connection, decision_id: str) -> ReviewStateRow:
    """Read the single source of truth for "has this been reviewed"."""
    row = connection.execute(
        "SELECT decision_id, due_at, reviewed_at, created_at, updated_at "
        "FROM decision_review_state WHERE decision_id = ?",
        (decision_id,),
    ).fetchone()
    if row is None:
        raise ReviewStateMissingError(f"decision {decision_id} has no review slot")
    return _row_to_state(row)


def has_been_reviewed(connection: sqlite3.Connection, decision_id: str) -> bool:
    """Whether a review has happened.

    Reads ``decision_review_state`` and nothing else — see the module docstring
    for why deriving this from ``reviews`` is not allowed.
    """
    return get_review_state(connection, decision_id).reviewed_at is not None


def latest_review(connection: sqlite3.Connection, decision_id: str) -> ReviewRow | None:
    """The most recent review of a decision, or ``None`` if it has none.

    Ordered by ``reviewed_at`` then ``id`` so the answer is **total**: two reviews
    written in the same millisecond have distinct ids, and the tie-break makes
    the choice deterministic instead of dependent on the query planner.

    This is the latest *review*, not the reviewed state. They are different
    questions and reading either one for the other is the mistake ADR-0014 warns
    about — see the module docstring.
    """
    row = connection.execute(
        "SELECT id, decision_id, process_score, outcome, reviewed_at, "
        "due_at_snapshot, note FROM reviews "
        "WHERE decision_id = ? ORDER BY reviewed_at DESC, id DESC LIMIT 1",
        (decision_id,),
    ).fetchone()
    return None if row is None else _row_to_review(row)


def reviews_for(connection: sqlite3.Connection, decision_id: str) -> tuple[ReviewRow, ...]:
    """Every review of a decision, oldest first. Append-only, so the order is the record."""
    rows = connection.execute(
        "SELECT id, decision_id, process_score, outcome, reviewed_at, "
        "due_at_snapshot, note FROM reviews "
        "WHERE decision_id = ? ORDER BY reviewed_at ASC, id ASC",
        (decision_id,),
    ).fetchall()
    return tuple(_row_to_review(row) for row in rows)


def count_reviews(connection: sqlite3.Connection, decision_id: str) -> int:
    """How many times a decision has been reviewed.

    Safe to derive, and the reason is worth restating: ``reviews`` is
    **append-only**, enforced by triggers. Counting rows in a table nothing can
    change is not the same as inferring state from one something can.
    """
    row = connection.execute(
        "SELECT COUNT(*) FROM reviews WHERE decision_id = ?", (decision_id,)
    ).fetchone()
    return int(row[0])


def recent_reviews(
    connection: sqlite3.Connection,
    *,
    limit: int = 20,
) -> tuple[ReviewStateRow, ...]:
    """Decisions that **have** been reviewed, most recently first.

    ⭐ This exists because the retrospective page's only other list is the **due**
    one, and a decision leaves that queue the moment its review is written
    (``due_reviews`` filters on ``reviewed_at IS NULL`` — regression 0007's fix). So
    without this, a review you already wrote is **invisible on the page whose entire
    subject is reviews**, and spec 030's lesson composer is unreachable: before the
    review the form is correctly hidden, and after it the decision is gone from the
    only list that could show it.

    Found by opening the app. ⭐ The E2E suite passed throughout, because the fixture
    returned an already-reviewed decision in the *due* queue — a state this
    repository cannot produce. **A fixture describing a state the product cannot be in
    makes the test agree with the fixture rather than with the product.**

    ⭐ **Ordered by ``reviewed_at DESC`` and nothing else.** Sorting a reader's own
    retrospectives by process score or outcome would be grading them, and red line 11
    is about not doing that — in a place nobody was looking. Ties break on
    ``decision_id`` so the order is stable between calls.

    ``limit`` is small on purpose (20): this is a place to go and read, not a history
    to scroll. A decision older than twenty reviews is not something you came back
    for, and a list that grows without bound is a list you stop reading.
    """
    # ⭐ The same five columns `due_reviews` selects, because the same
    # `_row_to_state` reads them. The first version selected two and raised
    # `IndexError: No item with that key` — an error naming the **consumer** of the
    # row rather than the SELECT that under-supplied it, which is the signature of a
    # guessed helper contract. Fourth such guess this session.
    rows = connection.execute(
        "SELECT decision_id, due_at, reviewed_at, created_at, updated_at "
        "FROM decision_review_state "
        "WHERE decision_id IN (SELECT decision_id FROM reviews) "
        # ⭐ Ordered by the ledger's latest `reviewed_at`, **not** by the state row's
        # copy. The state row is stamped when a review is *written*; the ledger holds
        # one row per review. Sorting by the state row would order a decision
        # reviewed twice by its **first** review — the same class of bug as
        # `due_reviews`' missing `reviewed_at IS NULL` filter (regression 0007): a
        # plausible number that is quietly the wrong one.
        "ORDER BY (SELECT MAX(reviewed_at) FROM reviews r "
        "           WHERE r.decision_id = decision_review_state.decision_id) DESC, "
        "         decision_id ASC "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    return tuple(_row_to_state(row) for row in rows)


def due_reviews(
    connection: sqlite3.Connection,
    *,
    as_of: datetime,
    limit: int = 50,
) -> tuple[ReviewStateRow, ...]:
    """Decisions whose review has come round **and has not been done**, oldest first.

    ⭐ **The ``reviewed_at IS NULL`` filter is a defect fix (regression 0007), and
    the reason it was missing is worth keeping.** The card queue needs no such
    filter, because FSRS pushes a reviewed card's ``due_at`` forward — the date
    moves, so the row stops matching. A decision's ``due_at`` is set once, when
    the user says when they want to come back, and **nothing ever moves it**. So
    without this filter a reviewed decision stayed in the queue for ever: the
    count on the today page read "1 条决策" before *and* after the review, and
    would keep saying it for ever after.

    That is worse than a wrong number. A line that still claims there is work after
    the work is done teaches the reader to ignore the one line on the default page
    that is sometimes true — the same failure the today page already guards against
    in the other direction, where a zero count renders nothing.

    **The filter is on the completion stamp, not on "has a review row".** A
    process score alone leaves ``reviewed_at`` NULL, because a half-review is a
    legitimate state and outstanding work must not hide behind a row the reader
    already wrote.

    ⚠️ **Consequence worth stating: a decision is reviewed once.** Nothing
    re-queues it — there is no reschedule for ``decision_review_state``, and
    inventing a second interval would be inventing policy (spec 020 §六, and the
    same reason the "three days overdue" threshold was left undefined in spec 023).
    Looking at a decision again means a *new* decision, or a lesson that becomes a
    card with its own schedule (J5). If a second review is ever wanted, it needs a
    due date that moves, and an ADR.

    ``as_of`` is injected, so the boundary is testable and a replay answers the
    same question. Ordered by due date alone — same reasoning as the K3 queue
    (ADR-0028): ranking the user's own backlog by anything else turns
    "how behind am I" into a score the user can feel (red line 11).
    """
    rows = connection.execute(
        "SELECT decision_id, due_at, reviewed_at, created_at, updated_at "
        "FROM decision_review_state WHERE due_at <= ? AND reviewed_at IS NULL "
        "ORDER BY due_at ASC, decision_id ASC LIMIT ?",
        (as_of.isoformat(), limit),
    ).fetchall()
    return tuple(_row_to_state(row) for row in rows)


def record(
    connection: sqlite3.Connection,
    decision_id: str,
    review: Review,
    *,
    now: datetime | None = None,
) -> ReviewRow:
    """Write a review and stamp the state. One transaction, both or neither.

    The early-scoring gate is checked here *and* by the schema. Here so the
    failure is our error code with our message; there so a caller that bypassed
    this function still cannot write an outcome before the review was due.
    """
    moment = now or datetime.now(UTC)
    state = get_review_state(connection, decision_id)

    if review.outcome is not None and state.due_at > moment:
        msg = (
            f"decision {decision_id} is not due for an outcome until "
            f"{state.due_at.isoformat()}; scoring early is hindsight"
        )
        raise ReviewNotDueError(msg)

    require_open_transaction(connection, operation="reviews.record")

    row = ReviewRow(
        # The id is derived from ``moment`` — the same instant the row records —
        # rather than from the wall clock read again here. Two reviews written in
        # the same millisecond while ``now`` is injected would otherwise collide on
        # the primary key, and the failure would look like "the second review was
        # lost" instead of "the id was read from a different clock than the data".
        id=f"review_{int(moment.timestamp() * 1000)}",
        decision_id=decision_id,
        process_score=review.process_score,
        outcome=review.outcome,
        reviewed_at=review.reviewed_at or moment,
        due_at_snapshot=state.due_at,
        note=review.note.strip() if review.note else None,
    )
    connection.execute(
        "INSERT INTO reviews (id, decision_id, process_score, outcome, reviewed_at, "
        "due_at_snapshot, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            row.id,
            row.decision_id,
            row.process_score,
            None if row.outcome is None else row.outcome.value,
            utc_millis(row.reviewed_at),
            row.due_at_snapshot.isoformat(),
            row.note,
            utc_millis(moment),
        ),
    )
    # `reviewed_at` is stamped **only when an outcome is recorded**, so it means
    # "this review was completed", not "somebody wrote something down here".
    #
    # That distinction is what lets the state table keep its
    # `not_reviewed_early_check`: a process-only note before the due date is a
    # legitimate half-review, and it must not make the decision look reviewed.
    # The two-stage shape is also the point of the gate — you may write down how
    # you reasoned at any time; you may not score how it turned out until then.
    if review.outcome is not None:
        connection.execute(
            "UPDATE decision_review_state SET reviewed_at = COALESCE(reviewed_at, ?), "
            "updated_at = ? WHERE decision_id = ?",
            (utc_millis(row.reviewed_at), utc_millis(moment), decision_id),
        )
    else:
        connection.execute(
            "UPDATE decision_review_state SET updated_at = ? WHERE decision_id = ?",
            (utc_millis(moment), decision_id),
        )
    return row
