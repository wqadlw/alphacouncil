"""K3 review scheduling: domain rules and the repository's transaction boundary.

The five questions asked of ``fsrs`` (spec 018 §1) are re-asserted here rather
than quoted, because a design that depends on a library's behaviour is only as
durable as that behaviour is pinned. Three of them are load-bearing for a
correctness argument, and two of them (mutation Q3, Q4) exist purely to catch a
future upgrade of ``fsrs`` silently changing the rules this module relies on.

The fourth test in :class:`TestDeferralDoesNotDamageTheMemory` is the one that
matters most: the tempting way to implement "not now" is to call ``review_card``
with ``Again``, which *looks* like postponing while telling FSRS the user forgot.
That implementation is byte-for-byte prevented here.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.domain import scheduling
from alphacouncil.domain.card import (
    CardDraft,
    CardOrigin,
    CardStatus,
    ClaimType,
    build_card_draft,
)
from alphacouncil.domain.scheduling import (
    DEFAULT_DEFERRAL_DAYS,
    MAX_DEFERRAL_DAYS,
    CardAlreadyScheduledError,
    CardNotScheduledError,
    ReviewRating,
    ScheduleState,
    TimestampNotUtcError,
    defer_due,
    require_utc,
    state_from_fsrs,
)
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage import db, migrate
from alphacouncil.storage.repositories import cards as card_repo
from alphacouncil.storage.repositories import scheduling as repo

NOW = datetime(2026, 9, 28, 1, 0, 0, tzinfo=UTC)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """A real database file at the current shipped schema version."""
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


def _in_tx(connection: sqlite3.Connection) -> AbstractContextManager[sqlite3.Connection]:
    """Open a transaction, the way every write route does.

    The project convention is that the **caller** owns the transaction, because a
    repository call often sits inside a larger unit of work. `record_review` and
    `defer` each write two tables, so they *require* an open transaction and say
    so loudly — see `db.require_open_transaction` and regression 0006.

    ⚠️ **Nesting matters when testing a rollback.** `pytest.raises` must be the
    *outer* context manager:

        with pytest.raises(...):      # outer
            with _in_tx(conn):        # inner
                repo.record_review(...)

    Written the other way round (``with _in_tx(conn), pytest.raises(...)``),
    ``pytest.raises`` catches the exception first, the transaction context never
    sees it, and it **commits the partial write** — so the test ends up proving
    the opposite of what it says. It cost an hour to find; the failure is silent
    and looks exactly like a product bug.
    """
    from alphacouncil.storage.db import transaction

    return transaction(connection)


def _expect_rollback(
    connection: sqlite3.Connection, call: Callable[[], object], *, match: str = "blocked"
) -> None:
    """Assert that ``call`` fails and leaves nothing behind.

    The nesting order below is **load-bearing and is the reason this helper
    exists**. ``ruff``'s SIM117 wants these collapsed into a single
    ``with A, B:`` — and doing that is a bug: with ``pytest.raises`` as the
    *inner* manager it catches the exception, the transaction context never sees
    a failure, and it **commits the partial write**. The test then asserts the
    opposite of what it appears to assert, and the failure looks exactly like a
    product bug. Hence the exemption, and hence one helper rather than eight
    copies of the pattern.
    """
    with pytest.raises(sqlite3.IntegrityError, match=match):  # noqa: SIM117
        with _in_tx(connection):
            call()


def _card(connection: sqlite3.Connection, code: str = "600519", *, offset_ms: int = 0) -> str:
    """Create a card.

    ``offset_ms`` exists because the K1 primary key is a millisecond timestamp
    and two cards created in the same millisecond collide — the boundary K1
    recorded and K2 inherited. A test that makes several cards must therefore
    space them out deliberately, rather than discover the collision as a
    confusing UNIQUE violation.
    """
    moment = datetime(2026, 9, 28, 0, 0, 0, tzinfo=UTC) + timedelta(milliseconds=offset_ms)
    draft: CardDraft = build_card_draft(
        content="毛利率连续三年高于 90%，品牌定价权强",
        claim_type=ClaimType.SUPPORTING,
        source_url=f"https://example.com/reports/{code}",
        source_title="白酒渠道深度调研",
        origin=CardOrigin.USER_WRITTEN,
        priority=4,
        status=CardStatus.ACTIVE,
        symbols=(Symbol(market=Market.SH, code=code),),
    )
    return card_repo.create(
        connection,
        draft,
        now=moment.strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{moment.microsecond // 1000:03d}Z",
    ).id


class TestWhatFsrsActuallyDoes:
    """The five probe answers, pinned. A library upgrade that breaks one of these
    should fail here rather than quietly change what a review means."""

    def test_review_card_does_not_mutate_its_input(self) -> None:
        import fsrs

        scheduler = fsrs.Scheduler(enable_fuzzing=False)
        card = fsrs.Card(card_id=1)
        before = dict(card.to_dict())
        reviewed, _log = scheduler.review_card(card, fsrs.Rating.Good, NOW)
        assert card.to_dict() == before, "fsrs mutated the card we passed in"
        assert reviewed is not card

    def test_the_same_input_gives_the_same_due_when_fuzzing_is_off(self) -> None:
        import fsrs

        scheduler = fsrs.Scheduler(enable_fuzzing=False)
        dues = {
            scheduler.review_card(fsrs.Card(card_id=1), fsrs.Rating.Good, NOW)[0]
            .to_dict()["due"]
            for _ in range(4)
        }
        assert len(dues) == 1, f"non-deterministic due dates: {dues}"

    def test_the_payload_round_trips_losslessly(self) -> None:
        import fsrs

        scheduler = fsrs.Scheduler(enable_fuzzing=False)
        reviewed, _log = scheduler.review_card(fsrs.Card(card_id=1), fsrs.Rating.Good, NOW)
        raw = reviewed.to_dict()
        assert fsrs.Card.from_dict(raw).to_dict() == raw

    def test_a_naive_datetime_is_rejected(self) -> None:
        import fsrs

        scheduler = fsrs.Scheduler(enable_fuzzing=False)
        with pytest.raises(ValueError, match="timezone-aware"):
            scheduler.review_card(
                fsrs.Card(card_id=1), fsrs.Rating.Good, datetime(2026, 10, 1, 1, 0, 0)
            )

    def test_fsrs_has_exactly_three_states(self) -> None:
        import fsrs

        assert [s.name for s in fsrs.State] == ["Learning", "Review", "Relearning"]
        assert state_from_fsrs(1) is ScheduleState.LEARNING
        assert state_from_fsrs(2) is ScheduleState.REVIEW
        assert state_from_fsrs(3) is ScheduleState.RELEARNING

    def test_an_unknown_fsrs_state_raises_rather_than_guessing(self) -> None:
        with pytest.raises(scheduling.SchedulingError):
            state_from_fsrs(99)

    def test_defer_is_not_something_fsrs_offers(self) -> None:
        """`reschedule_card` is a scheduler-migration tool, not a postponement.

        It takes a card **and its review logs** and recomputes after the scheduler
        configuration changed. Passing a datetime is a type error — which is how
        this test shows the name is misleading rather than asserting the docs.
        """
        import fsrs

        with pytest.raises(TypeError):
            fsrs.Scheduler(enable_fuzzing=False).reschedule_card(fsrs.Card(card_id=1), NOW)  # type: ignore[arg-type]


class TestScheduleState:
    def test_our_vocabulary_has_the_extra_deferred_state(self) -> None:
        assert {s.value for s in ScheduleState} == {
            "learning",
            "review",
            "relearning",
            "deferred",
        }

    def test_a_payload_can_never_claim_to_be_deferred(self) -> None:
        """Deferral is a queue fact, not a memory fact."""
        with pytest.raises(scheduling.SchedulingError):
            state_from_fsrs(4)

    def test_state_of_refuses_a_payload_without_a_state(self) -> None:
        with pytest.raises(scheduling.SchedulingError):
            scheduling.state_of({"due": "2026-09-28T00:00:00+00:00"})


class TestUtcIsEnforced:
    def test_a_naive_datetime_is_refused_by_us_not_by_the_library(self) -> None:
        with pytest.raises(TimestampNotUtcError) as caught:
            require_utc(datetime(2026, 9, 28, 1, 0, 0), field="now")
        assert "now" in str(caught.value)
        assert caught.value.code is ErrorCode.CARD_TIMESTAMP_NOT_UTC

    def test_an_offset_datetime_is_refused(self) -> None:
        with pytest.raises(TimestampNotUtcError):
            require_utc(
                datetime(2026, 9, 28, 9, 0, 0, tzinfo=timezone(timedelta(hours=8))),
                field="as_of",
            )

    def test_utc_passes_through(self) -> None:
        assert require_utc(NOW, field="now") is NOW


class TestDeferralBounds:
    def test_the_default_is_a_week(self) -> None:
        assert DEFAULT_DEFERRAL_DAYS == 7

    def test_a_deferral_pushes_the_date_out(self) -> None:
        assert defer_due(NOW, days=3) == NOW + timedelta(days=3)

    def test_zero_or_negative_days_is_refused(self) -> None:
        with pytest.raises(scheduling.SchedulingError):
            defer_due(NOW, days=0)

    def test_beyond_the_ceiling_is_refused(self) -> None:
        """A card parked in the far future is a card silently deleted."""
        with pytest.raises(scheduling.SchedulingError):
            defer_due(NOW, days=MAX_DEFERRAL_DAYS + 1)


class TestEnrolment:
    def test_a_new_card_is_immediately_due(self, connection: sqlite3.Connection) -> None:
        row = repo.enroll(connection, _card(connection), now=NOW)
        assert row.state is ScheduleState.LEARNING
        assert repo.due_cards(connection, as_of=NOW) == (row,)

    def test_each_card_gets_its_own_fsrs_handle(
        self, connection: sqlite3.Connection
    ) -> None:
        first = repo.enroll(connection, _card(connection, "600519", offset_ms=0), now=NOW)
        second = repo.enroll(connection, _card(connection, "000001", offset_ms=5), now=NOW)
        assert first.fsrs_card_id != second.fsrs_card_id

    def test_enrolling_twice_is_refused(self, connection: sqlite3.Connection) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with pytest.raises(CardAlreadyScheduledError) as caught:
            repo.enroll(connection, card_id, now=NOW)
        assert caught.value.code is ErrorCode.CARD_ALREADY_SCHEDULED

    def test_reading_a_missing_schedule_says_so(self, connection: sqlite3.Connection) -> None:
        with pytest.raises(CardNotScheduledError) as caught:
            repo.get_schedule(connection, "card_0000000000000")
        assert caught.value.code is ErrorCode.CARD_NOT_SCHEDULED


class TestRecordingAReview:
    def test_a_review_moves_the_due_date_out(self, connection: sqlite3.Connection) -> None:
        card_id = _card(connection)
        before = repo.enroll(connection, card_id, now=NOW)
        with _in_tx(connection):
            row = repo.record_review(connection, card_id, ReviewRating.GOOD, now=NOW)
        after = repo.get_schedule(connection, card_id)
        assert after.due_at > before.due_at
        assert row.outcome.value == "reviewed"
        assert row.rating is ReviewRating.GOOD

    def test_the_log_row_records_the_move_it_caused(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _card(connection)
        before = repo.enroll(connection, card_id, now=NOW)
        with _in_tx(connection):
            row = repo.record_review(connection, card_id, ReviewRating.GOOD, now=NOW)
        assert row.from_due_at == before.due_at
        assert row.to_due_at == repo.get_schedule(connection, card_id).due_at

    def test_duration_is_recorded_but_is_not_comparable(
        self, connection: sqlite3.Connection
    ) -> None:
        """It is stored so the user can look at their own pattern. Nothing sums it."""
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with _in_tx(connection):
            row = repo.record_review(
                connection, card_id, ReviewRating.GOOD, now=NOW, duration_ms=4200
            )
        assert row.duration_ms == 4200
        history = repo.list_reviews(connection, card_id)
        assert [r.duration_ms for r in history] == [4200]

    def test_reviewing_an_unscheduled_card_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        with _in_tx(connection), pytest.raises(CardNotScheduledError):
            repo.record_review(connection, _card(connection), ReviewRating.GOOD, now=NOW)

    def test_a_deferred_card_has_no_recall_to_record(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with _in_tx(connection):
            repo.defer(connection, card_id, now=NOW, days=1)
        with _in_tx(connection), pytest.raises(CardNotScheduledError):
            repo.record_review(connection, card_id, ReviewRating.GOOD, now=NOW)

    def test_recording_a_review_without_a_transaction_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        """Two tables, one caller-opened transaction. No transaction, no write.

        Regression 0006: on an autocommit connection the log INSERT and the
        schedule UPDATE are two independent commits, so a failure between them
        leaves a card whose schedule moved with no record that it did.
        """
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with pytest.raises(RuntimeError, match="transaction"):
            repo.record_review(connection, card_id, ReviewRating.GOOD, now=NOW)
        assert repo.list_reviews(connection, card_id) == ()

    def test_deferring_without_a_transaction_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with pytest.raises(RuntimeError, match="transaction"):
            repo.defer(connection, card_id, now=NOW)
        assert repo.get_schedule(connection, card_id).state is not ScheduleState.DEFERRED


class TestDeferralDoesNotDamageTheMemory:
    def test_the_fsrs_payload_survives_a_deferral_byte_for_byte(
        self, connection: sqlite3.Connection
    ) -> None:
        """The load-bearing assertion of this whole module.

        If a deferral rewrote stability, difficulty, step or state, then saying
        "not now" would be recorded as having forgotten — which is the one thing
        a knowledge system must never do to a user who came back.
        """
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        before = repo.get_schedule(connection, card_id)
        with _in_tx(connection):
            repo.defer(connection, card_id, now=NOW, days=5)
        after = repo.get_schedule(connection, card_id)
        assert after.payload == before.payload
        assert after.fsrs_payload() == before.fsrs_payload()

    def test_a_deferral_produces_no_rating(self, connection: sqlite3.Connection) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with _in_tx(connection):
            row = repo.defer(connection, card_id, now=NOW)
        assert row.outcome.value == "deferred"
        assert row.rating is None
        assert row.duration_ms is None

    def test_a_deferred_card_leaves_the_queue(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        assert len(repo.due_cards(connection, as_of=NOW)) == 1
        with _in_tx(connection):
            repo.defer(connection, card_id, now=NOW, days=7)
        assert repo.due_cards(connection, as_of=NOW + timedelta(days=6)) == ()
        assert len(repo.due_cards(connection, as_of=NOW + timedelta(days=8))) == 1

    def test_a_deferral_marks_the_state_deferred(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with _in_tx(connection):
            repo.defer(connection, card_id, now=NOW)
        assert repo.get_schedule(connection, card_id).state is ScheduleState.DEFERRED


class TestTheQueue:
    def test_only_due_cards_appear(self, connection: sqlite3.Connection) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        assert repo.due_cards(connection, as_of=NOW - timedelta(days=1)) == ()
        assert len(repo.due_cards(connection, as_of=NOW)) == 1

    def test_the_order_is_stable_between_calls(
        self, connection: sqlite3.Connection
    ) -> None:
        """A queue that reshuffles makes "I have handled it" feel futile."""
        for index, code in enumerate(("600519", "000001", "601398")):
            repo.enroll(connection, _card(connection, code, offset_ms=index), now=NOW)
        first = [row.card_id for row in repo.due_cards(connection, as_of=NOW)]
        second = [row.card_id for row in repo.due_cards(connection, as_of=NOW)]
        assert first == second

    def test_the_limit_is_honoured(self, connection: sqlite3.Connection) -> None:
        for index, code in enumerate(("600519", "000001")):
            repo.enroll(connection, _card(connection, code, offset_ms=index), now=NOW)
        assert len(repo.due_cards(connection, as_of=NOW, limit=1)) == 1


class TestTheLogIsAppendOnly:
    def _review_id(self, connection: sqlite3.Connection) -> str:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        with _in_tx(connection):
            return repo.record_review(connection, card_id, ReviewRating.GOOD, now=NOW).id

    def test_update_is_refused(self, connection: sqlite3.Connection) -> None:
        review_id = self._review_id(connection)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE card_reviews SET rating = 'easy' WHERE id = ?", (review_id,))

    def test_delete_is_refused(self, connection: sqlite3.Connection) -> None:
        review_id = self._review_id(connection)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM card_reviews WHERE id = ?", (review_id,))


class TestTheTransactionBoundary:
    def test_a_failed_log_insert_leaves_the_schedule_untouched(
        self, connection: sqlite3.Connection
    ) -> None:
        """Both or neither. Proven by making the INSERT impossible, not by reading code."""
        card_id = _card(connection)
        before = repo.enroll(connection, card_id, now=NOW)

        connection.execute(
            "CREATE TRIGGER block_reviews BEFORE INSERT ON card_reviews "
            "BEGIN SELECT RAISE(ABORT, 'blocked for the test'); END"
        )
        _expect_rollback(
            connection,
            lambda: repo.record_review(connection, card_id, ReviewRating.GOOD, now=NOW),
        )

        after = repo.get_schedule(connection, card_id)
        assert after.payload == before.payload
        assert after.due_at == before.due_at
        assert after.state is before.state
        assert repo.list_reviews(connection, card_id) == ()

    def test_a_failed_schedule_update_leaves_no_orphan_log_row(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        connection.execute(
            "CREATE TRIGGER block_update BEFORE UPDATE ON card_schedule "
            "BEGIN SELECT RAISE(ABORT, 'blocked for the test'); END"
        )
        _expect_rollback(
            connection,
            lambda: repo.record_review(connection, card_id, ReviewRating.GOOD, now=NOW),
        )
        assert repo.list_reviews(connection, card_id) == ()

    def test_a_deferral_is_also_all_or_nothing(
        self, connection: sqlite3.Connection
    ) -> None:
        card_id = _card(connection)
        before = repo.enroll(connection, card_id, now=NOW)
        connection.execute(
            "CREATE TRIGGER block_reviews BEFORE INSERT ON card_reviews "
            "BEGIN SELECT RAISE(ABORT, 'blocked for the test'); END"
        )
        _expect_rollback(connection, lambda: repo.defer(connection, card_id, now=NOW))
        after = repo.get_schedule(connection, card_id)
        assert after.due_at == before.due_at
        assert after.state is before.state


class TestStoredStateIsHonest:
    def test_a_corrupt_payload_is_not_defaulted(self, connection: sqlite3.Connection) -> None:
        """Corruption is not "no data". Raising beats inventing a fresh card.

        The schema CHECK blocks the obvious corruption, so the test suspends it
        with ``PRAGMA ignore_check_constraints`` — which is the realistic
        version of the same situation: a row written by an older build, or a
        library upgrade that changed the payload shape. The decoder must still
        refuse rather than quietly hand back a plausible card.
        """
        card_id = _card(connection)
        repo.enroll(connection, card_id, now=NOW)
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE card_schedule SET state_json = ? WHERE card_id = ?",
            (json.dumps(["not", "an", "object"]), card_id),
        )
        connection.execute("PRAGMA ignore_check_constraints = OFF")
        with pytest.raises(scheduling.SchedulingError):
            repo.get_schedule(connection, card_id).fsrs_payload()

    def test_retrievability_is_never_computed(self) -> None:
        """It is a score. Red line 2 forbids optimising outcomes; 9 forbids showing them.

        Checked on the **AST**, not on the raw text: both modules name the method
        in their docstrings precisely in order to say "we do not use this", and a
        substring scan would fail on that sentence forever.
        """
        import ast

        import fsrs

        assert hasattr(fsrs.Scheduler, "get_card_retrievability"), "upstream renamed it"
        for module in (repo, scheduling):
            assert module.__file__ is not None
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            called = {
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }
            called |= {
                node.func.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            assert "get_card_retrievability" not in called, (
                f"{module.__name__} now asks for retrievability — that is a score, "
                "and red line 9 says do not show it"
            )
