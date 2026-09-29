"""Lessons (spec 030 · J5) — including the test that red line 7 actually needs.

## The two tests worth reading first

**`test_blocking_the_schedule_insert_rolls_the_lesson_back`** is the one. Red line
7 says 「每条教训必须生成一条调度项」, and a positive test would ask *is the schedule
row there?* — which passes just as happily if a future refactor moves the insert
into its own transaction, or wraps it in a branch, or drops it and hard-codes the
answer into the fixture. This test blocks the insert with a trigger and asks the
stronger question: **is it possible for a lesson to exist without one?** No. That is
what the red line claims, and it is the only formulation of the claim that cannot be
satisfied by a code path which happens to work today.

⚠️ And it is the test that regression 0006 exists for. `pytest.raises` must be the
**outer** context manager: the other way round, pytest swallows the exception, the
transaction context never sees a failure, and it **commits the partial write** — so
the test would assert the opposite of what it appears to assert, and pass.

**`test_lesson_reviews_has_no_reset_outcome`** pins an *absence*. Spec 028 found
that notes needed a third outcome (`reset`) because they are mutable, and that cards
do not need one because they are not. Lessons are the same kind of thing as cards, so
they must not grow one either — and an absence is exactly the kind of thing a later
copy-paste from `note_reviews` removes without anyone noticing. So it is asserted
twice: the enum has no such member, and the database's `CHECK` rejects the string.

## What is deliberately not tested

Nothing here checks that a lesson "works" in the product sense. This is a storage and
domain layer, and the claims worth pinning are the ones the red line is made of: the
atomicity, the immutability, the absence of `reset`, the derived demand for a source
on promotion, and the fact that promoting does not quietly discharge the guarantee.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.card import CardOrigin
from alphacouncil.domain.lesson import (
    MAX_CONTENT_CHARS,
    Lesson,
    LessonAlreadyPromotedError,
    LessonContentBlankError,
    LessonNotFoundError,
    LessonPromotionSourceError,
    LessonRecordOutcome,
    LessonReviewMissingError,
    LessonScheduleRow,
    LessonTooLongError,
)
from alphacouncil.domain.review import Review
from alphacouncil.domain.scheduling import ReviewRating, ScheduleState
from alphacouncil.storage import db, migrate

# The module is `lesson.py`; aliased to the plural because the test talks about
# lessons as a collection throughout, and an unaliased `lesson` in a file that
# also imports the `Lesson` row type is a name that means two things.
from alphacouncil.storage.repositories import cards, reviews
from alphacouncil.storage.repositories import lesson as lessons

NOW = datetime(2026, 9, 28, 1, 0, 0, tzinfo=UTC)
DECISION = "2026-09-20T02:15:00.000Z"
LATER = datetime(2026, 10, 20, 1, 0, 0, tzinfo=UTC)


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


@pytest.fixture
def decision(connection: sqlite3.Connection) -> str:
    """A recorded decision. The id *is* the moment it was written (red line 4)."""
    connection.execute(
        "INSERT INTO instruments (market, code, name, name_source, name_fetched_at, "
        "asset_type, created_at) "
        "VALUES ('sh', '600519', '贵州茅台', 'sina', '2026-03-12T09:30:00.000Z', "
        "'stock', '2026-03-12T09:30:00.000Z')"
    )
    connection.execute(
        "INSERT INTO decisions (id, market, code, action, rationale, counter_evidence, "
        "kill_criteria, thesis_id) VALUES (?, 'sh', '600519', 'buy', ?, ?, ?, NULL)",
        (
            DECISION,
            "高端酒提价能力可持续，渠道库存处于低位",
            "批价可能因春节压货而短期回落",
            '[{"metric":"revenue_yoy","operator":"<","threshold":0.0}]',
        ),
    )
    return DECISION


def _in_tx(connection: sqlite3.Connection) -> AbstractContextManager[sqlite3.Connection]:
    """The project's transaction context manager.

    The convention is that the **caller** owns the transaction, so a direct
    repository call must open one too.

    ⚠️ `pytest.raises` must be the **outer** context manager around this one
    (regression 0006). The other way round, pytest swallows the exception, the
    transaction never sees a failure, and it commits the partial write — so the
    test asserts the opposite of what it appears to assert.
    """
    return db.transaction(connection)


def _write_review(connection: sqlite3.Connection, decision_id: str, *, due: bool = True) -> str:
    """Schedule and then write the review, so a lesson has something to attach to.

    Returns the ``reviews.id``.
    """
    with db.transaction(connection):
        reviews.schedule(connection, decision_id, due_at=NOW, now=NOW)
    if not due:
        return ""
    with db.transaction(connection):
        row = reviews.record(
            connection,
            decision_id,
            Review(
                decision_id=decision_id,
                process_score=2,
                outcome=None,
                reviewed_at=NOW,
                due_at=NOW,
                note="批价当时已经回落，我没看。",
            ),
            now=NOW,
        )
    return row.id


def _record(
    connection: sqlite3.Connection,
    decision_id: str,
    content: str = "先看批价再动手",
) -> tuple[Lesson, LessonScheduleRow]:
    with db.transaction(connection):
        return lessons.record_from_review(connection, decision_id, content, now=NOW)


# ── the whole point: the lesson and its schedule arrive together ─────────────


class TestRedLineSeven:
    def test_recording_writes_the_lesson_the_schedule_and_the_ledger_row(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Acceptance 1: three rows, one call, no verb the reader has to remember."""
        _write_review(connection, decision)
        lesson, schedule = _record(connection, decision)

        assert connection.execute("SELECT count(*) FROM lessons").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM lesson_schedule").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM lesson_reviews").fetchone()[0] == 1
        assert lesson.content == "先看批价再动手"
        assert schedule.lesson_id == lesson.lesson_id

    def test_blocking_the_schedule_insert_rolls_the_lesson_back(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """⭐⭐ Acceptance 2: **is it possible** for a lesson to exist unscheduled?

        A positive assertion — "the schedule row is there" — is satisfied by any code
        path that happens to work today. This asks the question the red line actually
        poses: block the scheduling insert at the database, and the lesson write must
        fail **with nothing left behind**.

        ⚠️ `pytest.raises` is the outer context manager on purpose (regression 0006).
        The other way round pytest swallows the exception, the transaction context
        never sees a failure, commits the partial write, and this test would pass
        while asserting the opposite of what it says.
        """
        _write_review(connection, decision)
        connection.execute(
            "CREATE TRIGGER block_lesson_schedule BEFORE INSERT ON lesson_schedule "
            "BEGIN SELECT RAISE(ABORT, 'blocked by the test'); END;"
        )

        with pytest.raises(sqlite3.IntegrityError):  # noqa: SIM117 - regression 0006
            with _in_tx(connection):
                lessons.record_from_review(connection, decision, "先看批价再动手", now=NOW)

        # ⭐ Not "the schedule is missing" — "the *lesson* is missing". The
        # guarantee is about the database, so this is the shape that tests it.
        assert connection.execute("SELECT count(*) FROM lessons").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM lesson_reviews").fetchone()[0] == 0

    def test_the_enrolment_row_carries_no_grade(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Acceptance 4: the reader has not recalled anything yet.

        A grade written on their behalf would dress a forced enrolment as a
        remembered fact, and FSRS would then start from a stability nobody earned.
        """
        _write_review(connection, decision)
        _record(connection, decision)

        row = connection.execute(
            "SELECT outcome, rating, duration_ms FROM lesson_reviews"
        ).fetchone()
        assert row["outcome"] == "enrolled"
        assert row["rating"] is None
        assert row["duration_ms"] is None

    def test_a_lesson_is_due_immediately(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Acceptance 5: due now, and in ``learning``.

        A product judgement, not a default: a lesson is something the reader has
        already been wrong about once, so it is the one thing here that has earned an
        immediate revisit. A card typed a minute ago has not.
        """
        _write_review(connection, decision)
        _lesson, schedule = _record(connection, decision)

        assert schedule.state is ScheduleState.LEARNING
        assert schedule.due_at == NOW
        assert schedule.fsrs_card_id >= 1

    def test_a_lesson_does_not_touch_an_existing_schedule_row(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """The check-then-insert shape would make the guarantee conditional.

        A second lesson for the same review gets its **own** ``fsrs_card_id`` — the
        handle is what FSRS uses to tell two memories apart, and sharing one would
        make the second lesson's first review act on the first lesson's stability.
        """
        _write_review(connection, decision)
        first, _ = _record(connection, decision, "先看批价")
        second, schedule = _record(connection, decision, "先看渠道库存")

        assert first.lesson_id != second.lesson_id
        assert connection.execute("SELECT count(*) FROM lesson_schedule").fetchone()[0] == 2
        assert schedule.fsrs_card_id == 2

    def test_one_review_can_hold_several_lessons(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Acceptance 6: one mistake usually teaches more than one thing."""
        _write_review(connection, decision)
        _record(connection, decision, "先看批价")
        _record(connection, decision, "仓位别一次打满")

        review_id = connection.execute("SELECT id FROM reviews").fetchone()["id"]
        assert len(lessons.list_lessons_for_review(connection, review_id)) == 2


# ── what a lesson is, and what it deliberately is not ───────────────────────


class TestTheLessonItself:
    def test_a_blank_lesson_is_refused(self, connection: sqlite3.Connection, decision: str) -> None:
        """A scheduled item the reader is asked to read, with nothing in it.

        Red line 7 would then be satisfied in form and empty in substance, which is
        the one shape a red line must not have. A spaces-only body counts as blank.
        """
        _write_review(connection, decision)
        with pytest.raises(LessonContentBlankError) as caught:  # noqa: SIM117
            with _in_tx(connection):
                lessons.record_from_review(connection, decision, "   \n  ", now=NOW)
        assert caught.value.code is ErrorCode.LESSON_CONTENT_BLANK
        assert connection.execute("SELECT count(*) FROM lessons").fetchone()[0] == 0

    def test_the_body_is_verbatim(self, connection: sqlite3.Connection, decision: str) -> None:
        """Trimmed for the blank check, stored as typed — like a note body.

        The lesson is the reader's own sentence and the schedule hangs off it, so the
        stored text and the text the memory is about must be the same bytes.
        """
        _write_review(connection, decision)
        body = "  先看批价\n\n  再看渠道库存  "
        lesson, _ = _record(connection, decision, body)
        assert lesson.content == body

    def test_an_over_long_lesson_is_refused(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        _write_review(connection, decision)
        with pytest.raises(LessonTooLongError) as caught:  # noqa: SIM117
            with _in_tx(connection):
                lessons.record_from_review(
                    connection, decision, "啊" * (MAX_CONTENT_CHARS + 1), now=NOW
                )
        assert caught.value.code is ErrorCode.LESSON_TEXT_TOO_LONG

    def test_a_lesson_needs_a_review_that_was_written(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Acceptance 7, and the distinction the error name is about.

        A *scheduled* review is not a written one. ``decision_review_state`` says when
        a review will be due; ``reviews`` has a row only once the reader has written
        it. Attaching a lesson to the former would date it to a moment that has not
        happened.
        """
        _write_review(connection, decision, due=False)
        with pytest.raises(LessonReviewMissingError) as caught:  # noqa: SIM117
            with _in_tx(connection):
                lessons.record_from_review(connection, decision, "先看批价", now=NOW)
        assert caught.value.code is ErrorCode.LESSON_REVIEW_MISSING
        assert "复盘" in str(caught.value)

    def test_a_lesson_for_an_unknown_decision_is_refused(
self,
connection: sqlite3.Connection,
    ) -> None:
        with pytest.raises(LessonReviewMissingError):  # noqa: SIM117
            with _in_tx(connection):
                lessons.record_from_review(
                    connection, "2026-01-01T00:00:00.000Z", "先看批价", now=NOW
                )

    def test_lessons_are_immutable(self, connection: sqlite3.Connection, decision: str) -> None:
        """Acceptance 8, enforced by the database rather than by convention.

        Spec 030's whole ``no reset`` argument rests on this. An update would leave
        FSRS's memory strength attached to text that no longer exists — the exact
        failure spec 028 fixed for notes by adding a third outcome. The right answer
        here is to forbid the edit instead, and a reader who disagrees writes another
        lesson.
        """
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):  # noqa: SIM117
            with _in_tx(connection):
                connection.execute(
                    "UPDATE lessons SET content = '改了' WHERE lesson_id = ?",
                    (lesson.lesson_id,),
                )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):  # noqa: SIM117
            with _in_tx(connection):
                connection.execute("DELETE FROM lessons WHERE lesson_id = ?", (lesson.lesson_id,))

    def test_an_unknown_lesson_says_so(self, connection: sqlite3.Connection) -> None:
        with pytest.raises(LessonNotFoundError) as caught:
            lessons.get_lesson(connection, "lesson_1700000000000")
        assert caught.value.code is ErrorCode.LESSON_NOT_FOUND

    def test_the_review_ledger_is_append_only(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Evidence of *when the reader acted* must not be re-writable.

        A past revisit edited into a better past revisit is hindsight, and
        hindsight is the one thing this whole record exists to survive.
        """
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        for statement in (
            "UPDATE lesson_reviews SET rating = 'easy' WHERE lesson_id = ?",
            "DELETE FROM lesson_reviews WHERE lesson_id = ?",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):  # noqa: SIM117
                with _in_tx(connection):
                    connection.execute(statement, (lesson.lesson_id,))


# ── ⭐ the absence, pinned twice ────────────────────────────────────────────


class TestWhyThereIsNoReset:
    def test_lesson_reviews_has_no_reset_outcome(self) -> None:
        """Acceptance 9, half one: the vocabulary has no third interaction.

        ``note_reviews`` needs ``reset`` because a note in the queue can be rewritten
        and the memory would then hang off text that no longer exists. Lessons are
        immutable — pinned by ``test_lessons_are_immutable`` — so the condition cannot
        arise, and an outcome for it would be a fiction.
        """
        members = {member.value for member in LessonRecordOutcome}
        assert members == {"enrolled", "reviewed", "deferred"}
        assert "reset" not in members

    def test_the_database_refuses_a_reset_row(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Acceptance 9, half two — and the half that actually holds the line.

        Asserting the enum lacks a member only pins *this module*. A future migration
        widening the ``CHECK``, or a raw insert from a script, would pass the enum
        test. The ``CHECK`` is where a value that should not exist stops existing.
        """
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        with pytest.raises(sqlite3.IntegrityError, match="outcome"):  # noqa: SIM117
            with _in_tx(connection):
                connection.execute(
                    "INSERT INTO lesson_reviews (id, lesson_id, outcome, rating, reviewed_at, "
                    "duration_ms, from_due_at, to_due_at, from_state, to_state) "
                    "VALUES ('lesson_review_1700000000999', ?, 'reset', NULL, ?, NULL, ?, ?, "
                    "'learning', 'learning')",
                    (lesson.lesson_id, utc_millis(NOW), utc_millis(NOW), utc_millis(NOW)),
                )

    def test_a_deferral_cannot_carry_a_rating(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        """
        ⭐ **This test exists because a mutation survived.**

        Widening ``lesson_reviews_deferred_has_no_rating_check`` to a tautology left
        all 32 tests green, because nothing asserted it. Acceptance item 4 covers
        ``enrolled``; ``deferred`` was copied from ``note_reviews`` and never given
        its own test.

        ⭐ **A constraint copied from a sibling table is a constraint nobody is
        holding** — the copy is not the coverage. And the mutation is how you find
        out, which is the whole reason the check runs.

        A deferral means 「not now, I have not thought it through」, and a grade means
        「here is how well I recalled it」. There is no recall in a deferral, so a row
        carrying both is asserting something about the reader that did not happen.
        """
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):  # noqa: SIM117
            with _in_tx(connection):
                connection.execute(
                    "INSERT INTO lesson_reviews (id, lesson_id, outcome, rating, reviewed_at, "
                    "duration_ms, from_due_at, to_due_at, from_state, to_state) "
                    "VALUES ('lesson_review_1700000000998', ?, 'deferred', 'good', ?, NULL, "
                    "?, ?, 'learning', 'learning')",
                    (
                        lesson.lesson_id,
                        utc_millis(NOW),
                        utc_millis(NOW),
                        utc_millis(NOW),
                    ),
                )

    def test_a_deferral_cannot_carry_a_duration(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        """The same shape, one column over — and it was equally untested."""
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):  # noqa: SIM117
            with _in_tx(connection):
                connection.execute(
                    "INSERT INTO lesson_reviews (id, lesson_id, outcome, rating, reviewed_at, "
                    "duration_ms, from_due_at, to_due_at, from_state, to_state) "
                    "VALUES ('lesson_review_1700000000997', ?, 'deferred', NULL, ?, 4200, "
                    "?, ?, 'learning', 'learning')",
                    (
                        lesson.lesson_id,
                        utc_millis(NOW),
                        utc_millis(NOW),
                        utc_millis(NOW),
                    ),
                )

    def test_notes_still_have_their_reset(self, connection: sqlite3.Connection) -> None:
        """⭐ The contrast, so the absence above is a distinction and not a gap.

        If ``note_reviews`` lost ``reset`` in the same commit that ``lesson_reviews``
        was born, the two tests above would still pass while the notes queue quietly
        went back to lying about a rewritten note. Two absences are only meaningful
        next to the presence they are being distinguished from.
        """
        from alphacouncil.domain.note_recall import NoteReviewOutcome

        assert "reset" in {member.value for member in NoteReviewOutcome}


# ── promotion: the derived demand for a source ──────────────────────────────


class TestPromotion:
    def test_promoting_without_a_source_is_refused(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """⭐⭐ The most important behaviour in the spec.

        A card's provenance is a URL and a lesson has none, so 「我拿不出出处」 means
        this is a lesson and not yet a card. And **nothing is lost by declining** — it
        is already saved and already queued — which is what makes declining a
        reasonable answer rather than a failure.
        """
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        for url, title in ((None, "标题"), ("https://example.com/a", None), ("", "标题")):
            with pytest.raises(LessonPromotionSourceError) as caught:  # noqa: SIM117
                with _in_tx(connection):
                    lessons.promote_lesson(connection, lesson.lesson_id, url, title, now=NOW)
            assert caught.value.code is ErrorCode.LESSON_PROMOTION_SOURCE_REQUIRED
        assert connection.execute("SELECT count(*) FROM cards").fetchone()[0] == 0

    def test_a_non_http_source_is_refused(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        with pytest.raises(LessonPromotionSourceError, match="http"):  # noqa: SIM117
            with _in_tx(connection):
                lessons.promote_lesson(
                    connection, lesson.lesson_id, "file:///C:/notes.md", "本地笔记", now=NOW
                )

    def test_promoting_writes_a_card_the_reader_signed(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        with db.transaction(connection):
            promotion = lessons.promote_lesson(
                connection,
                lesson.lesson_id,
                "https://research.example.com/maotai-price",
                "白酒批价跟踪",
                now=NOW,
            )

        row = cards.get_by_id(connection, promotion.card_id)
        assert row is not None
        assert row.content == lesson.content
        assert row.source_url == "https://research.example.com/maotai-price"
        assert row.source_title == "白酒批价跟踪"
        # ⭐ Never `ai_generated`: the text is the reader's own sentence about their
        # own mistake, and the link is only where they found support. This would be
        # the one unforced misattribution in the whole knowledge layer.
        assert row.origin is CardOrigin.USER_WRITTEN

    def test_a_lesson_cannot_be_promoted_twice(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """One promise per lesson, and it is the table's key rather than a check.

        Two cards both claiming the same provenance is a question the reader cannot
        answer, so ``lesson_promotions.lesson_id`` being the PRIMARY KEY is what makes
        the second attempt impossible instead of merely refused.
        """
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        with db.transaction(connection):
            lessons.promote_lesson(
                connection, lesson.lesson_id, "https://a.example/1", "一", now=NOW
            )

        with pytest.raises(LessonAlreadyPromotedError) as caught:  # noqa: SIM117
            with _in_tx(connection):
                lessons.promote_lesson(
                    connection, lesson.lesson_id, "https://a.example/2", "二", now=NOW
                )
        assert caught.value.code is ErrorCode.LESSON_ALREADY_PROMOTED
        assert connection.execute("SELECT count(*) FROM cards").fetchone()[0] == 1

    def test_one_card_cannot_come_from_two_lessons(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """The other UNIQUE: ``card_id`` — a card has exactly one origin."""
        _write_review(connection, decision)
        first, _ = _record(connection, decision, "第一条")
        second, _ = _record(connection, decision, "第二条")
        with db.transaction(connection):
            promotion = lessons.promote_lesson(
                connection, first.lesson_id, "https://a.example/1", "一", now=NOW
            )
        # ⚠️ A **separate** transaction, not a nested one. SQLite has no nested
        # transactions and `db.transaction` says so rather than pretending, so the
        # first draft of this test — promotion and the forged row inside one
        # transaction — failed with 「cannot start a transaction within a
        # transaction」 and would have kept failing there while looking like a
        # constraint problem.
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):  # noqa: SIM117
            with _in_tx(connection):
                connection.execute(
                    "INSERT INTO lesson_promotions (lesson_id, card_id, promoted_at) "
                    "VALUES (?, ?, ?)",
                    (second.lesson_id, promotion.card_id, utc_millis(NOW)),
                )

    def test_the_promotion_record_is_append_only(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """It is a promise the reader made, and a promise cannot be re-pointed.

        The UNIQUE constraints already freeze the content; what append-only adds is
        that the row cannot be **removed** either. Un-promoting would leave a card
        whose declared origin no longer exists — the same dangling provenance reached
        from the other direction.
        """
        _write_review(connection, decision)
        lesson, _ = _record(connection, decision)
        with db.transaction(connection):
            lessons.promote_lesson(
                connection, lesson.lesson_id, "https://a.example/1", "一", now=NOW
            )
        for statement in (
            "UPDATE lesson_promotions SET card_id = 'card_1' WHERE lesson_id = ?",
            "DELETE FROM lesson_promotions WHERE lesson_id = ?",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):  # noqa: SIM117
                with _in_tx(connection):
                    connection.execute(statement, (lesson.lesson_id,))

    def test_promoting_does_not_discharge_the_guarantee(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """⭐ Acceptance 11: the lesson **stays on its own queue**.

        Red line 7 must have no escape hatch. A branch reading 「转了卡就不用再复习了」
        is exactly the kind of clause that turns a guarantee back into a suggestion —
        and it would be invisible, because the queue would still *look* right.
        """
        _write_review(connection, decision)
        lesson, schedule = _record(connection, decision)
        with db.transaction(connection):
            lessons.promote_lesson(
                connection, lesson.lesson_id, "https://a.example/1", "一", now=NOW
            )

        still = connection.execute(
            "SELECT state, due_at FROM lesson_schedule WHERE lesson_id = ?", (lesson.lesson_id,)
        ).fetchone()
        assert still is not None
        assert still["state"] == schedule.state.value
        assert still["due_at"] == schedule.due_at.isoformat()
        # And the card did **not** get silently enrolled: the card queue is the
        # reader's own choice, and inheriting an enrolment across two aggregates
        # would be a second, invisible guarantee nobody asked for.
        assert connection.execute(
            "SELECT count(*) FROM card_schedule WHERE card_id IN "
            "(SELECT card_id FROM lesson_promotions WHERE lesson_id = ?)",
            (lesson.lesson_id,),
        ).fetchone()[0] == 0


# ── ⭐ the red line itself was not relaxed to make this work ────────────────


class TestProvenanceWasNotTouched:
    def test_a_blank_source_url_is_still_refused(self, connection: sqlite3.Connection) -> None:
        """Acceptance 3, stated as behaviour rather than as a schema reading.

        The first draft of this spec put lessons **in** ``cards`` and relaxed
        ``source_url`` to nullable so provenance could be 「URL 或复盘」. That is the
        change this whole migration exists to avoid, and the cheapest way to notice
        somebody making it later is to try it: a card with no source is still refused.
        """

        with pytest.raises(sqlite3.IntegrityError, match="CHECK"), _in_tx(connection):
            connection.execute(
                "INSERT INTO cards (id, content, claim_type, source_url, source_title, "
                "captured_at, origin, priority, status, created_at, as_of) "
                "VALUES ('card_1', '一条判断', 'neutral', '', '标题', ?, 'user_written', "
                "0, 'active', ?, NULL)",
                (utc_millis(NOW), utc_millis(NOW)),
            )

    def test_cards_carry_no_review_id(self, connection: sqlite3.Connection) -> None:
        """The column the first draft wanted does not exist, which is the point.

        Adding ``review_id`` to ``cards`` is the change this spec reversed. Asserting
        the column's absence makes the reversal executable rather than a matter of
        somebody's memory of an ADR.
        """
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(cards)")}
        assert "review_id" not in columns

    def test_the_two_provenance_checks_are_still_named_the_same(
self,
connection: sqlite3.Connection,
    ) -> None:
        """And with the same meaning — a rename would hide a rewrite."""
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
        ).fetchone()["sql"]
        assert "cards_source_url_required_check" in sql
        assert "cards_source_title_required_check" in sql
        assert "source_url   TEXT    NOT NULL" in sql or "source_url TEXT NOT NULL" in sql


# ── the queue ───────────────────────────────────────────────────────────────


class TestTheQueue:
    def test_the_queue_is_ordered_by_due_and_nothing_else(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """Oldest first, ties on id — never by stability or a priority the reader set.

        Ranking the reader's own backlog is the thing the product's red lines
        refuse, and a queue that reshuffles on every open makes 「我处理过了」 feel
        futile, so the tie-break is fixed rather than left to SQLite.
        """
        _write_review(connection, decision)
        first, _ = _record(connection, decision, "第一条")
        second, _ = _record(connection, decision, "第二条")

        due = lessons.due_lessons(connection, as_of=LATER)
        assert [lesson.lesson_id for _schedule, lesson in due] == [
            first.lesson_id,
            second.lesson_id,
        ]

    def test_nothing_is_due_before_its_date(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        _write_review(connection, decision)
        _record(connection, decision)
        assert lessons.due_lessons(connection, as_of=datetime(2026, 9, 1, tzinfo=UTC)) == ()

    def test_reviewing_moves_the_schedule_and_leaves_a_row(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        _write_review(connection, decision)
        lesson, before = _record(connection, decision)
        with db.transaction(connection):
            after_row = lessons.record_review(
                connection, lesson.lesson_id, ReviewRating.GOOD, now=LATER, duration_ms=4200
            )

        assert after_row.from_due_at == before.due_at
        assert after_row.to_due_at > before.due_at
        assert connection.execute("SELECT count(*) FROM lesson_reviews").fetchone()[0] == 2
        assert connection.execute(
            "SELECT rating FROM lesson_reviews WHERE outcome = 'reviewed'"
        ).fetchone()["rating"] == "good"

    def test_reviewing_an_unscheduled_lesson_is_refused(
self,
connection: sqlite3.Connection,
    ) -> None:
        with pytest.raises(LessonNotFoundError), _in_tx(connection):
            lessons.record_review(connection, "lesson_1700000000000", ReviewRating.GOOD, now=NOW)

    def test_the_write_needs_an_open_transaction(
self,
connection: sqlite3.Connection,
decision: str,
    ) -> None:
        """A lesson outside a transaction would enrol without recording why.

        The repository refuses rather than opening one itself, because the project
        convention is that the **caller** owns it and a nested transaction is not a
        thing SQLite has.
        """
        _write_review(connection, decision)
        with pytest.raises(RuntimeError, match="transaction"):
            lessons.record_from_review(connection, decision, "先看批价", now=NOW)
