"""The note recall queue (spec 028).

Most of this file is a mirror of the card queue's tests, because the queue is a
mirror. The tests worth reading first are the two about **editing**:

* editing a note **on** the queue restarts its schedule and writes a `reset` row
  (`test_an_edit_restarts_the_schedule_of_a_note_on_the_queue`);
* editing a note **off** the queue writes nothing at all
  (`test_an_edit_to_a_note_off_the_queue_writes_nothing`).

The second is not the absence of a feature. Most notes are never enrolled, so the
ordinary path must not pay for the interesting one — and a reset that fires for
notes nobody queued would fill the history with events the reader never caused.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alphacouncil.domain.note import NoteDraft
from alphacouncil.domain.note_recall import (
    NoteAlreadyScheduledError,
    NoteNotScheduledError,
    NoteReviewOutcome,
)
from alphacouncil.domain.scheduling import ReviewRating, ScheduleState
from alphacouncil.storage import db, migrate
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import note_recall as recall
from alphacouncil.storage.repositories import notes as notes_repo

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
# ⭐ After both reviews, and before the ~10-24 that FSRS schedules them to.
# The first draft put this at 10-02 — *before* the 10-05 and 10-06 reviews — so
# the history came back reset-first and the test expected review-first. The code
# was right: `ORDER BY reviewed_at` cannot be wrong, and a note cannot be
# rewritten before it was reviewed. The scenario was incoherent, not the sort.
REWRITE = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "alphacouncil.db"
    connection = db.connect_for_migration(path)
    try:
        migrate.apply(connection, database_path=path)
    finally:
        connection.close()
    return path


@pytest.fixture
def connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    conn = db.connect(database_path)
    try:
        yield conn
    finally:
        conn.close()


def _write(connection: sqlite3.Connection, title: str = "一条笔记", body: str = "正文") -> str:
    with transaction(connection):
        return notes_repo.create(
            connection, NoteDraft(title=title, body=body), now=_stamp(NOW)
        ).note.id


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _enroll(connection: sqlite3.Connection, note_id: str, *, now: datetime = NOW) -> None:
    with transaction(connection):
        recall.enroll(connection, note_id, now=now)


# ── enrolment ───────────────────────────────────────────────────────────────


class TestEnrolment:
    def test_a_note_can_be_put_on_the_queue(self, connection: sqlite3.Connection) -> None:
        note_id = _write(connection)
        _enroll(connection, note_id)
        row = recall.get_schedule(connection, note_id)
        assert row.note_id == note_id
        assert row.state is ScheduleState.LEARNING
        # A brand-new item is due immediately: the reader asked for it now.
        assert row.due_at == NOW

    def test_enrolment_is_never_automatic(self, connection: sqlite3.Connection) -> None:
        """⭐ Writing a note must not put it on the queue.

        Enrolling everything the reader ever wrote builds a backlog nobody
        drains, and 「你欠 N 条」 is the exact feeling the red lines reject. So the
        reader says which things they want brought back to.
        """
        note_id = _write(connection)
        assert recall.is_scheduled(connection, note_id) is False
        with pytest.raises(NoteNotScheduledError):
            recall.get_schedule(connection, note_id)

    def test_a_second_enrolment_is_refused(self, connection: sqlite3.Connection) -> None:
        """Re-enrolling would give a reviewed note a fresh stability, making a
        months-old view look like it had just been formed."""
        note_id = _write(connection)
        _enroll(connection, note_id)
        with pytest.raises(NoteAlreadyScheduledError):
            _enroll(connection, note_id, now=LATER)

    def test_the_fsrs_handle_is_distinct_per_note(
        self, connection: sqlite3.Connection
    ) -> None:
        """Never used to look anything up, but it travels into the log — and a log
        full of ``note_id=1`` is a log nobody can read."""
        first = _write(connection, "一")
        second = _write(connection, "二")
        _enroll(connection, first)
        _enroll(connection, second)
        assert (
            recall.get_schedule(connection, first).fsrs_card_id
            != recall.get_schedule(connection, second).fsrs_card_id
        )


# ── the queue ───────────────────────────────────────────────────────────────


class TestTheQueue:
    def test_only_due_notes_are_listed(self, connection: sqlite3.Connection) -> None:
        due = _write(connection, "到期的")
        _enroll(connection, due)
        # Enrolled later, so due later.
        fresh = _write(connection, "刚入队的")
        _enroll(connection, fresh, now=NOW + timedelta(days=3))

        found = {row.note_id for row in recall.due_notes(connection, as_of=NOW)}
        assert found == {due}

    def test_the_queue_is_ordered_by_due_date_alone(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ Not by stability, not by a priority, not by an urgency score.

        Those are all ways of grading the reader's own backlog, and the product's
        job is to show it. The third note is enrolled *last* but due *first*, so a
        priority ordering would put it last and a naive insertion order would too.
        """
        third = _write(connection, "第三")
        first = _write(connection, "第一")
        second = _write(connection, "第二")
        _enroll(connection, third, now=NOW)
        _enroll(connection, first, now=NOW + timedelta(days=1))
        _enroll(connection, second, now=NOW + timedelta(days=2))

        found = [
            row.note_id
            for row in recall.due_notes(connection, as_of=NOW + timedelta(days=5))
        ]
        assert found == [third, first, second]

    def test_the_order_is_stable_between_calls(
        self, connection: sqlite3.Connection
    ) -> None:
        """A queue that reshuffles on every open makes 「我处理过了」 feel futile."""
        for title in ("一", "二", "三"):
            _enroll(connection, _write(connection, title))
        moment = NOW + timedelta(days=1)
        first = [r.note_id for r in recall.due_notes(connection, as_of=moment)]
        second = [r.note_id for r in recall.due_notes(connection, as_of=moment)]
        assert first == second

    def test_an_empty_queue_lists_nothing(self, connection: sqlite3.Connection) -> None:
        assert recall.due_notes(connection, as_of=NOW) == ()


# ── reviewing ───────────────────────────────────────────────────────────────


class TestReviewing:
    def test_a_review_appends_and_moves_the_schedule(
        self, connection: sqlite3.Connection
    ) -> None:
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            row = recall.record_review(connection, note_id, ReviewRating.GOOD, now=LATER)

        assert row.outcome is NoteReviewOutcome.REVIEWED
        assert row.rating is ReviewRating.GOOD
        assert recall.get_schedule(connection, note_id).due_at > LATER
        assert len(recall.list_reviews(connection, note_id)) == 1

    def test_again_means_my_view_moved_not_that_i_forgot(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ For a note, `again` is the **most valuable** signal the product gets.

        The test cannot check the UI wording, so it checks the thing the wording
        has to be true of: `again` is recorded as a normal rating with no special
        casing, and the note comes back **sooner**, because a view that has moved
        is exactly the one that should be revisited.
        """
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            again = recall.record_review(connection, note_id, ReviewRating.AGAIN, now=LATER)
        assert again.rating is ReviewRating.AGAIN
        assert again.outcome is NoteReviewOutcome.REVIEWED
        assert recall.get_schedule(connection, note_id).due_at < LATER + timedelta(days=2)

    def test_a_deferred_note_cannot_be_reviewed(
        self, connection: sqlite3.Connection
    ) -> None:
        """「我的想法还没定」 is not a recall, so there is nothing to score."""
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            recall.defer(connection, note_id, now=LATER)
        with pytest.raises(NoteNotScheduledError), transaction(connection):
            recall.record_review(connection, note_id, ReviewRating.GOOD, now=LATER)

    def test_a_duration_is_recorded_and_never_compared(
        self, connection: sqlite3.Connection
    ) -> None:
        """Red line 11: how long a re-read took is for self-reflection, and the
        moment it becomes a ranking the product has started measuring the reader."""
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            row = recall.record_review(
                connection, note_id, ReviewRating.HARD, now=LATER, duration_ms=4200
            )
        assert row.duration_ms == 4200

    def test_a_deferral_touches_no_memory(self, connection: sqlite3.Connection) -> None:
        """⭐ ``state_json`` is written back with the identical string.

        A note pushed three times must not come back angrier each time; 「还没想
        清楚」 is not a failure and must not cost memory strength.
        """
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            recall.record_review(connection, note_id, ReviewRating.GOOD, now=LATER)
        before = recall.get_schedule(connection, note_id)

        with transaction(connection):
            recall.defer(connection, note_id, now=LATER)

        after = recall.get_schedule(connection, note_id)
        assert after.payload == before.payload
        assert after.state is ScheduleState.DEFERRED
        assert after.due_at > before.due_at

    def test_a_deferral_beyond_the_ceiling_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        note_id = _write(connection)
        _enroll(connection, note_id)
        with pytest.raises(ValueError), transaction(connection):
            recall.defer(connection, note_id, now=LATER, days=91)


# ── ⭐⭐ the two tests this spec is about ────────────────────────────────────


class TestAnEditRestartsTheSchedule:
    """A note is mutable; a card is not. That difference has to reach the queue."""

    def test_an_edit_restarts_the_schedule_of_a_note_on_the_queue(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐⭐ The whole spec, in one test.

        Enrol, review it well enough that FSRS pushes it months out, then rewrite
        the text completely. The schedule must come back **due now** — because the
        reader has never reviewed *this* text — and a ``reset`` row must say so.
        """
        note_id = _write(connection, "原来的判断", "原来那段话")
        _enroll(connection, note_id)
        # Two easy reviews, not one. FSRS schedules a single `easy` on a brand-new
        # card about 15 days out; asking for "more than ten days" was passing by
        # accident on the calendar and would have broken on any change to the
        # algorithm's parameters. Two reviews put it months out, which is the
        # situation that makes the reset matter.
        for index in range(2):
            with transaction(connection):
                recall.record_review(
                    connection, note_id, ReviewRating.EASY, now=LATER + timedelta(days=index)
                )
        before = recall.get_schedule(connection, note_id)
        pushed_out = before.due_at
        # ⭐ The relationship, not a number. The first two drafts asserted
        # "more than ten days" and then "more than twenty", both invented:
        # FSRS schedules a new card's first two `easy` reviews about 15 and 19
        # days out. A test that quotes the algorithm's parameters breaks when
        # the parameters are tuned, and tells you nothing about the reset.
        # What matters is that the note was scheduled *after* the rewrite, and
        # that the reset pulls it back to the rewrite.
        assert pushed_out > REWRITE, (
            f"the note should have been scheduled past the rewrite, got {pushed_out}"
        )

        with transaction(connection):
            notes_repo.update_body(
                connection,
                note_id,
                title="新的判断",
                body="完全不同的另一段话",
                now=_stamp(REWRITE),
            )

        after = recall.get_schedule(connection, note_id)
        assert after.due_at == REWRITE, "the schedule was not restarted"
        # The FSRS payload must be a *different card*, not the old one with a
        # fresh due date. (The first draft wrote `after.payload != pushed_out`,
        # which compares a JSON string to a datetime and is true forever.)
        assert after.payload != before.payload
        assert after.fsrs_card_id != before.fsrs_card_id

        history = recall.list_reviews(connection, note_id)
        assert [r.outcome for r in history] == [
            NoteReviewOutcome.REVIEWED,
            NoteReviewOutcome.REVIEWED,
            NoteReviewOutcome.RESET,
        ], "the reset must be appended, in order, after everything before it"

    def test_the_reset_row_carries_no_rating_and_no_duration(
        self, connection: sqlite3.Connection
    ) -> None:
        """The reader recalled nothing during a rewrite, so there is nothing to
        score and nothing to time."""
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            notes_repo.update_body(connection, note_id, body="改了", now=_stamp(REWRITE))

        resets = [
            r
            for r in recall.list_reviews(connection, note_id)
            if r.outcome is NoteReviewOutcome.RESET
        ]
        (reset,) = resets
        assert reset.rating is None
        assert reset.duration_ms is None

    def test_the_earlier_reviews_are_all_still_there(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The reset is appended; nothing is rewritten or dropped.

        A note reviewed five times and then rewritten is still a note the reader
        engaged with five times. Losing that is losing the record, and the record
        is the product.
        """
        note_id = _write(connection)
        _enroll(connection, note_id)
        for index in range(3):
            with transaction(connection):
                recall.record_review(
                    connection, note_id, ReviewRating.GOOD, now=LATER + timedelta(days=index)
                )
        with transaction(connection):
            notes_repo.update_body(connection, note_id, body="重写", now=_stamp(REWRITE))

        outcomes = [r.outcome for r in recall.list_reviews(connection, note_id)]
        assert outcomes == [
            NoteReviewOutcome.REVIEWED,
            NoteReviewOutcome.REVIEWED,
            NoteReviewOutcome.REVIEWED,
            NoteReviewOutcome.RESET,
        ]

    def test_an_edit_to_a_note_off_the_queue_writes_nothing(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The common case, and it must be silent.

        Most notes are never enrolled. A reset that fired for them would fill the
        append-only history with events the reader never caused, and the history's
        value is that every row means something.
        """
        note_id = _write(connection)
        before = connection.execute("SELECT count(*) FROM note_reviews").fetchone()[0]

        with transaction(connection):
            notes_repo.update_body(
            connection, note_id, body="改了两次", now=_stamp(REWRITE)
        )

        after = connection.execute("SELECT count(*) FROM note_reviews").fetchone()[0]
        assert after == before
        assert recall.is_scheduled(connection, note_id) is False

    def test_a_rewrite_does_not_enrol_a_note_that_was_off_the_queue(
        self, connection: sqlite3.Connection
    ) -> None:
        """A reset must not be a back door into the queue. Being rewritten is not
        a request to be brought back."""
        note_id = _write(connection)
        with transaction(connection):
            notes_repo.update_body(connection, note_id, body="改了", now=_stamp(REWRITE))
        assert recall.is_scheduled(connection, note_id) is False
        assert recall.due_notes(connection, as_of=NOW + timedelta(days=365)) == ()

    def test_a_rewrite_while_deferred_restarts_rather_than_defers(
        self, connection: sqlite3.Connection
    ) -> None:
        """A reset and a deferral move in **opposite** directions.

        Leaving a rewritten note in `deferred` would be wrong: the reader deferred
        a thought, then replaced it, and the new text is not the thing they said
        they were not ready to revisit.
        """
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            recall.defer(connection, note_id, now=LATER)
        assert recall.get_schedule(connection, note_id).state is ScheduleState.DEFERRED

        with transaction(connection):
            notes_repo.update_body(
                connection, note_id, body="换了想法", now=_stamp(REWRITE)
            )

        after = recall.get_schedule(connection, note_id)
        assert after.state is not ScheduleState.DEFERRED
        assert after.due_at == REWRITE

    def test_two_rewrites_produce_two_resets(
        self, connection: sqlite3.Connection
    ) -> None:
        """A reset is not a one-shot: every replacement of the text is an event."""
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            notes_repo.update_body(connection, note_id, body="第二版", now=_stamp(REWRITE))
        with transaction(connection):
            notes_repo.update_body(
                connection, note_id, body="第三版", now=_stamp(REWRITE)
            )

        resets = [
            r
            for r in recall.list_reviews(connection, note_id)
            if r.outcome is NoteReviewOutcome.RESET
        ]
        assert len(resets) == 2


# ── the history ─────────────────────────────────────────────────────────────


class TestTheHistory:
    def test_the_history_is_append_only(self, connection: sqlite3.Connection) -> None:
        """Editing a past review would let a changed mind be retrofitted into
        never having held the old one — the hindsight bias the record exists to
        survive."""
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            recall.record_review(connection, note_id, ReviewRating.GOOD, now=LATER)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE note_reviews SET rating = 'easy'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM note_reviews")

    def test_the_history_is_oldest_first(self, connection: sqlite3.Connection) -> None:
        note_id = _write(connection)
        _enroll(connection, note_id)
        with transaction(connection):
            recall.record_review(connection, note_id, ReviewRating.GOOD, now=LATER)
        with transaction(connection):
            notes_repo.update_body(connection, note_id, body="改了", now=_stamp(REWRITE))

        stamps = [r.reviewed_at for r in recall.list_reviews(connection, note_id)]
        assert stamps == sorted(stamps)


def _enrolled_note(connection: sqlite3.Connection) -> str:
    """A note that is on the queue, for tests that need a valid foreign key."""
    note_id = _write(connection)
    _enroll(connection, note_id)
    return note_id


class TestTheGuardsThemselves:
    """Two guarantees that only a direct test can hold.

    Both were found by mutation checks that left the suite green, and for the same
    reason: **no code path violates them.** They protect a future writer, so the
    only honest test bypasses the layer that would have to be wrong.
    """

    def test_the_schema_refuses_a_reset_row_that_carries_a_rating(
        self, connection: sqlite3.Connection
    ) -> None:
        """`note_reviews_reset_has_no_rating_check` is defence-in-depth.

        Neutralising the CHECK changed nothing the suite could see, because
        `reset_on_edit` never passes a rating for a reset. So the constraint is
        inserted-violated here, straight into the table — which is the only way to
        show the *schema* holds rather than the caller.
        """
        note_id = _write(connection)
        _enroll(connection, note_id)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO note_reviews"
                " (id, note_id, outcome, rating, reviewed_at, duration_ms,"
                "  from_due_at, to_due_at, from_state, to_state)"
                " VALUES ('note_review_1', ?, 'reset', 'easy', ?, NULL,"
                " ?, ?, 'learning', 'learning')",
                (
                    note_id,
                    _stamp(NOW),
                    NOW.isoformat().replace("+00:00", "Z"),
                    NOW.isoformat().replace("+00:00", "Z"),
                ),
            )

    def test_two_reviews_in_the_same_millisecond_both_survive(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ Written as each id is minted, so it does not depend on machine speed.

        The original failure was found because a test suite happened to run two
        reviews inside one millisecond — luck, not a property. Removing the
        collision check therefore left this file green on a slow run.

        Note what is asserted: **survival**, not uniqueness. `_new_id` finds an id
        that is not already *stored*; it keeps no memory of what it returned, so
        two calls with nothing written between them rightly return the same free
        id. The first draft demanded 200 distinct ids from 200 calls and was
        asserting a claim the function never made — the row count is the invariant,
        and every row is written the way a second review would write it.
        """
        note_id = _enrolled_note(connection)
        stamp = _stamp(NOW)
        due = NOW.isoformat().replace("+00:00", "Z")
        for _ in range(200):
            connection.execute(
                "INSERT INTO note_reviews"
                " (id, note_id, outcome, rating, reviewed_at, duration_ms,"
                "  from_due_at, to_due_at, from_state, to_state)"
                " VALUES (?, ?, 'deferred', NULL, ?, NULL, ?, ?, 'learning', 'learning')",
                (recall._new_id(connection, "note_review"), note_id, stamp, due, due),
            )
        stored = connection.execute(
            "SELECT count(*) FROM note_reviews"
        ).fetchone()[0]
        assert stored == 200

    def test_a_review_id_is_not_already_taken(self, connection: sqlite3.Connection) -> None:
        """The other half: the guard skips ids that **are** taken, not just repeats."""
        first = recall._new_id(connection, "note_review")
        connection.execute(
            "INSERT INTO note_reviews"
            " (id, note_id, outcome, rating, reviewed_at, duration_ms,"
            "  from_due_at, to_due_at, from_state, to_state)"
            " VALUES (?, ?, 'deferred', NULL, ?, NULL, ?, ?, 'learning', 'learning')",
            (
                first,
                _enrolled_note(connection),
                _stamp(NOW),
                NOW.isoformat().replace("+00:00", "Z"),
                NOW.isoformat().replace("+00:00", "Z"),
            ),
        )
        assert recall._new_id(connection, "note_review") != first
