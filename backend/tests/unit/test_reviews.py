"""J3: the four quadrants, and the gate that keeps an outcome from arriving early.

The load-bearing test in this file is
:meth:`TestTheGateSurvivesBypassingTheDomain`. The early-scoring rule is checked
in the domain *and* in the schema, and the second one is the one that matters: a
caller that reaches past :mod:`alphacouncil.domain.review` and writes raw SQL must
still not be able to score an outcome before the review was due. That is
constitution 0.2 — "能移就必须移" — and the test proves the move happened by going
around the layer that was supposed to be enforcing it.
"""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.review import (
    Outcome,
    ProcessBand,
    Quadrant,
    Review,
    ReviewError,
    ReviewNotDueError,
    ReviewNoteBlankError,
    ReviewScoreInvalidError,
    is_due,
    judge,
    outcome_still_blank,
    process_band,
)
from alphacouncil.storage import db, migrate
from alphacouncil.storage.repositories import reviews as repo

NOW = datetime(2026, 9, 28, 1, 0, 0, tzinfo=UTC)
DUE = NOW + timedelta(days=90)
DECISION = "2026-03-12T09:30:00.000Z"


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
            "批价可能因春节压货而短期回落，估值分位已到 20 分位",
            '[{"metric":"revenue_yoy","operator":"<","threshold":0.0,"as_of":"2026-12-31"}]',
        ),
    )
    return DECISION


def _in_tx(connection: sqlite3.Connection) -> AbstractContextManager[sqlite3.Connection]:
    """The project's transaction context manager.

    The convention in this codebase is that the **caller** owns the transaction,
    so a direct repository call must open one too.

    ⚠️ `pytest.raises` must be the **outer** context manager around this one.
    The other way round, pytest swallows the exception, the transaction context
    never sees a failure, and it commits the partial write — so the test asserts
    the opposite of what it appears to assert (regression 0006). `ruff` SIM117
    wants these two merged, which is why every such call site carries a
    `# noqa: SIM117` rather than being "tidied" into `with tx, pytest.raises(...)`.
    """
    return db.transaction(connection)


class TestProcessBand:
    def test_four_and_five_are_good(self) -> None:
        assert process_band(4) is ProcessBand.GOOD
        assert process_band(5) is ProcessBand.GOOD

    def test_three_is_bad_and_that_is_a_judgement_not_a_typo(self) -> None:
        """A 3 means the process was mediocre, and mediocre is what needs changing.

        Pinned because a symmetric rule (">= 3 is good") is the obvious tidy-up,
        and it would move the boundary without anyone noticing.
        """
        assert process_band(3) is ProcessBand.BAD

    def test_one_and_two_are_bad(self) -> None:
        assert process_band(1) is ProcessBand.BAD
        assert process_band(2) is ProcessBand.BAD

    @pytest.mark.parametrize("score", [0, 6, -1, 100])
    def test_out_of_range_is_refused(self, score: int) -> None:
        with pytest.raises(ReviewScoreInvalidError) as caught:
            process_band(score)
        assert caught.value.code is ErrorCode.REVIEW_SCORE_INVALID


class TestTheFourQuadrants:
    """All six combinations, `failed` counted as a bad outcome (ADR-0014)."""

    @pytest.mark.parametrize(
        ("score", "outcome", "expected"),
        [
            (5, Outcome.GOOD, Quadrant.REPEAT),
            (4, Outcome.GOOD, Quadrant.REPEAT),
            (5, Outcome.BAD, Quadrant.ACCEPTABLE),
            (4, Outcome.FAILED, Quadrant.ACCEPTABLE),
            (3, Outcome.GOOD, Quadrant.DANGEROUS),
            (1, Outcome.GOOD, Quadrant.DANGEROUS),
            (2, Outcome.BAD, Quadrant.FIX),
            (1, Outcome.FAILED, Quadrant.FIX),
        ],
    )
    def test_the_cell(
        self, score: int, outcome: Outcome, expected: Quadrant
    ) -> None:
        assert judge(score, outcome).quadrant is expected

    def test_only_good_counts_as_a_good_outcome(self) -> None:
        """`failed` must not be quietly treated as a partial success."""
        assert Outcome.GOOD.is_good is True
        assert Outcome.BAD.is_good is False
        assert Outcome.FAILED.is_good is False

    def test_a_blank_outcome_is_unknown_and_not_guessed(self) -> None:
        """Before the review is due, "how did it turn out" has no answer.

        Returning any real quadrant here would be the system guessing, which is
        what constitution 4.6 calls dressing `unavailable` up as an answer.
        """
        verdict = judge(5, None)
        assert verdict.quadrant is Quadrant.UNKNOWN
        assert "还没" in verdict.guidance()

    def test_every_quadrant_has_a_line_and_none_mentions_a_number(self) -> None:
        """Red line 10: the copy may not carry a result's magnitude.

        There is no magnitude in the data model, so this guards the copy instead
        — the one place a number could creep back in.
        """
        digits = set("0123456789%")
        for quadrant in Quadrant:
            line = judge(4, Outcome.GOOD)
            guidance = line.__class__(quadrant, ProcessBand.GOOD, Outcome.GOOD).guidance()
            assert guidance, f"{quadrant} has no guidance"
            assert not (set(guidance) & digits), f"{quadrant} mentions a number: {guidance}"

    def test_the_dangerous_quadrant_says_the_reason_does_not_hold(self) -> None:
        line = judge(2, Outcome.GOOD).guidance()
        assert "理由" in line
        assert "运气" in line


class TestReviewDomain:
    def test_a_process_score_must_be_present(self) -> None:
        """Red line 15: the system never supplies one. There is no default.

        The type of ``process_score`` is ``int`` with no default, so this is
        partly unreachable from typed code — which is the point. The score is a
        *required* field, so there is no way to construct a review without one,
        and certainly no default the system could quietly fill in.
        """
        with pytest.raises(ReviewScoreInvalidError):
            Review(decision_id=DECISION, process_score=0)

    def test_a_blank_note_is_refused(self) -> None:
        with pytest.raises(ReviewNoteBlankError):
            Review(decision_id=DECISION, process_score=3, note="   ")

    def test_an_over_long_note_is_refused(self) -> None:
        with pytest.raises(ReviewError):
            Review(decision_id=DECISION, process_score=3, note="长" * 1001)

    def test_scoring_before_due_is_refused_by_the_domain(self) -> None:
        with pytest.raises(ReviewNotDueError) as caught:
            Review(
                decision_id=DECISION,
                process_score=2,
                outcome=Outcome.GOOD,
                reviewed_at=NOW,
                due_at=NOW + timedelta(days=1),
            )
        assert caught.value.code is ErrorCode.REVIEW_NOT_DUE
        assert "hindsight" in str(caught.value)

    def test_a_note_may_be_omitted_entirely(self) -> None:
        review = Review(decision_id=DECISION, process_score=3)
        assert review.outcome is None
        assert review.judgement().quadrant is Quadrant.UNKNOWN


class TestDueDate:
    def test_not_due_the_day_before(self) -> None:
        assert not is_due(DUE, as_of=DUE - timedelta(days=1))

    def test_due_on_the_boundary_day(self) -> None:
        """The review is on the reader's desk that morning, not the day after."""
        assert is_due(DUE, as_of=DUE)

    def test_the_outcome_must_stay_blank_until_then(self) -> None:
        assert outcome_still_blank(due_at=DUE, as_of=DUE - timedelta(days=1)) is True
        assert outcome_still_blank(due_at=DUE, as_of=DUE) is False


class TestTheRepository:
    def test_a_scheduled_decision_is_not_reviewed_yet(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=DUE, now=NOW)
        state = repo.get_review_state(connection, decision)
        assert state.reviewed_at is None, "an unreviewed decision must be blank, never 0"
        assert repo.has_been_reviewed(connection, decision) is False

    def test_recording_a_review_stamps_the_state(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=NOW - timedelta(days=1), now=NOW)
        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=2, outcome=Outcome.GOOD),
                now=NOW,
            )
        assert repo.has_been_reviewed(connection, decision) is True
        assert repo.count_reviews(connection, decision) == 1

    def test_a_second_review_does_not_move_the_first_stamp(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        """'When did I first look at this' should not move because I looked again."""
        repo.schedule(connection, decision, due_at=NOW - timedelta(days=2), now=NOW)
        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=2, outcome=Outcome.BAD),
                now=NOW,
            )
        first = repo.get_review_state(connection, decision).reviewed_at
        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=3),
                now=NOW + timedelta(days=5),
            )
        assert repo.get_review_state(connection, decision).reviewed_at == first
        assert repo.count_reviews(connection, decision) == 2

    def test_the_state_is_never_inferred_from_reviews(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        """ADR-0014's hard rule, and the reason the state table exists at all.

        Deleting a review row must not make a reviewed decision look unreviewed.
        ``reviews`` is append-only, so the attempt fails at the trigger — and the
        failure is the point: **you cannot quietly un-record a review**, because
        the database refuses the delete rather than the code remembering to care.
        """
        repo.schedule(connection, decision, due_at=NOW - timedelta(days=1), now=NOW)
        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=4, outcome=Outcome.GOOD),
                now=NOW,
            )
        assert repo.has_been_reviewed(connection, decision) is True

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM reviews WHERE decision_id = ?", (decision,))
        assert repo.has_been_reviewed(connection, decision) is True

    def test_reviews_are_not_updatable(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=NOW - timedelta(days=1), now=NOW)
        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=1, outcome=Outcome.FAILED),
                now=NOW,
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE reviews SET process_score = 5")

    def test_the_repository_refuses_an_early_outcome(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=DUE, now=NOW)
        with pytest.raises(ReviewNotDueError):  # noqa: SIM117
            with _in_tx(connection):
                repo.record(
                    connection,
                    decision,
                    Review(decision_id=decision, process_score=5, outcome=Outcome.GOOD),
                    now=NOW,
                )
        # Nothing half-written: the gate fires before the INSERT, and the state
        # row must not have been stamped either.
        assert repo.count_reviews(connection, decision) == 0
        assert repo.has_been_reviewed(connection, decision) is False

    def test_a_blank_outcome_is_allowed_before_due(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        """The process may be written early; the outcome may not. That asymmetry
        is the gate — a half-finished review is a real state, not a mistake."""
        repo.schedule(connection, decision, due_at=DUE, now=NOW)
        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=3),
                now=NOW,
            )
        assert repo.count_reviews(connection, decision) == 1
        # …and a half-review does **not** make the decision look reviewed, which
        # is what `reviewed_at` means: *completed*, not "somebody wrote something".
        assert repo.get_review_state(connection, decision).reviewed_at is None
        assert repo.has_been_reviewed(connection, decision) is False

    def test_completing_the_review_later_stamps_it_once(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=NOW + timedelta(days=1), now=NOW)
        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=2),
                now=NOW,
            )
        assert repo.has_been_reviewed(connection, decision) is False

        with _in_tx(connection):
            repo.record(
                connection,
                decision,
                Review(decision_id=decision, process_score=2, outcome=Outcome.GOOD),
                now=NOW + timedelta(days=2),
            )
        state = repo.get_review_state(connection, decision)
        assert state.reviewed_at is not None
        assert repo.count_reviews(connection, decision) == 2

    def test_a_due_decision_is_listed_and_an_undue_one_is_not(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=NOW - timedelta(days=1), now=NOW)
        assert repo.due_reviews(connection, as_of=NOW - timedelta(days=2)) == ()
        assert len(repo.due_reviews(connection, as_of=NOW)) == 1

    def test_a_missing_slot_says_so(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        with pytest.raises(repo.ReviewStateMissingError) as caught:
            repo.get_review_state(connection, decision)
        assert caught.value.code is ErrorCode.REVIEW_STATE_MISSING


class TestTheGateSurvivesBypassingTheDomain:
    """The schema is the real enforcement; the domain is the friendly copy."""

    def test_raw_sql_cannot_score_an_outcome_early(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=DUE, now=NOW)
        with pytest.raises(sqlite3.IntegrityError, match="not_scored_early_check"):
            connection.execute(
                "INSERT INTO reviews (id, decision_id, process_score, outcome, reviewed_at, "
                "due_at_snapshot, note, created_at) "
                "VALUES ('review_1', ?, 5, 'good', ?, ?, NULL, ?)",
                (decision, utc_millis(NOW), DUE.isoformat(), utc_millis(NOW)),
            )

    def test_the_same_row_is_fine_once_due(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        """The gate is about the *date*, not about who wrote the row.

        Deliberately a raw INSERT, one string away from the test above: identical
        SQL, identical score, identical outcome — only ``due_at_snapshot`` moved
        back a day. A gate that would also pass after the date moved would not be
        a gate.
        """
        already_due = (NOW - timedelta(days=1)).isoformat()
        repo.schedule(connection, decision, due_at=NOW - timedelta(days=1), now=NOW)
        connection.execute(
            "INSERT INTO reviews (id, decision_id, process_score, outcome, reviewed_at, "
            "due_at_snapshot, note, created_at) "
            "VALUES ('review_1', ?, 5, 'good', ?, ?, NULL, ?)",
            (decision, utc_millis(NOW), already_due, utc_millis(NOW)),
        )
        assert repo.count_reviews(connection, decision) == 1

    def test_the_state_table_refuses_an_early_stamp_too(
        self, connection: sqlite3.Connection, decision: str
    ) -> None:
        repo.schedule(connection, decision, due_at=DUE, now=NOW)
        with pytest.raises(sqlite3.IntegrityError, match="not_reviewed_early_check"):
            connection.execute(
                "UPDATE decision_review_state SET reviewed_at = ? WHERE decision_id = ?",
                (utc_millis(NOW), decision),
            )


class TestTheModelHoldsNoFigure:
    """Red line 10 as a property of the schema rather than of the UI."""

    def test_reviews_has_no_money_or_return_column(self) -> None:
        rows = shipped_columns("reviews")
        forbidden = {
            "return_pct",
            "pnl",
            "profit",
            "gain",
            "outcome_pct",
            "price_change",
            "return_rate",
        }
        assert not (set(rows) & forbidden), (
            "a figure column turns '不显示盈利数字' back into a rendering rule, "
            "and a rendering rule is what the next API field leaks past"
        )

    def test_outcome_accepts_only_the_three_categories(self) -> None:
        """`good` / `bad` / `failed`. Not a number, not a percentage."""
        assert "outcome" in shipped_columns("reviews")
        with pytest.raises(sqlite3.IntegrityError, match="outcome_shape_check"):
            _insert_raw_outcome("+8.2%")


def shipped_columns(table: str) -> set[str]:
    """The column names a shipped table actually has, read from the real schema.

    Built by migrating a throwaway database to the current version rather than by
    parsing the SQL file — a file parse would pass on a migration that is written
    but never applied, which is exactly the class of bug this project keeps
    meeting.
    """
    tmp = Path(tempfile.mkdtemp())
    target = tmp / "schema.db"
    connection = db.connect_for_migration(target)
    try:
        migrate.apply(connection, database_path=target)
        return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def _empty() -> sqlite3.Connection:
    tmp = Path(tempfile.mkdtemp())
    target = tmp / "schema.db"
    boot = db.connect_for_migration(target)
    try:
        migrate.apply(boot, database_path=target)
    finally:
        boot.close()
    return db.connect(target)


def _insert_raw_outcome(value: str) -> None:
    """Write a review straight through SQL, bypassing every layer but the schema."""
    conn = _empty()
    try:
        conn.execute(
            "INSERT INTO instruments (market, code, name, name_source, name_fetched_at, "
            "asset_type, created_at) VALUES ('sh', '600519', 'x', 'sina', ?, 'stock', ?)",
            (utc_millis(NOW), utc_millis(NOW)),
        )
        conn.execute(
            "INSERT INTO decisions (id, market, code, action, rationale, counter_evidence, "
            "kill_criteria) VALUES (?, 'sh', '600519', 'buy', 'r', 'c', '[]')",
            (DECISION,),
        )
        due = (NOW - timedelta(days=1)).isoformat()
        conn.execute(
            "INSERT INTO decision_review_state (decision_id, due_at, reviewed_at, "
            "created_at, updated_at) VALUES (?, ?, NULL, ?, ?)",
            (DECISION, due, utc_millis(NOW), utc_millis(NOW)),
        )
        conn.execute(
            "INSERT INTO reviews (id, decision_id, process_score, outcome, reviewed_at, "
            "due_at_snapshot, note, created_at) VALUES ('review_1', ?, 5, ?, ?, ?, NULL, ?)",
            (DECISION, value, utc_millis(NOW), due, utc_millis(NOW)),
        )
    finally:
        conn.close()
