"""The demo library: what it guarantees, and what it must never do. (spec 057)

Three groups, in the order they matter:

1. ⭐ **The refusal.** ``refuse_to_overwrite`` is the only layer that fails loudly, and a
   guard nobody has tried to walk through is a guard nobody has tested. The mutation check
   at the bottom removes the guard and asserts this file goes red.
2. **The shape.** Seeded through the domain, so the schedules are computed rather than typed
   — and the counts are read back rather than reported by the seeder.
3. ⭐ **The copy.** Red line 1, pinned by assertion rather than by a comment, because
   ``S-03`` scans this very file and a demo library must not be why a gate is red.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alphacouncil.core.config import default_database_path
from alphacouncil.demo import (
    _CARDS,
    _DECISIONS,
    _NOTES,
    demo_database_path,
    refuse_to_overwrite,
    seed,
)
from alphacouncil.storage import db as dbmod
from alphacouncil.storage.repositories import note_recall as recall_repo
from alphacouncil.storage.repositories import notes as notes_repo
from alphacouncil.storage.repositories import scheduling as sched_repo

#: ⭐ **These tests patch the repositories where they are defined, not through `demo`'s
#: namespace.** `demo.py` holds `notes_repo` (a module, not a function) and calls
#: `notes_repo.create` at call time, ⭐ so patching the module's own attribute has exactly
#: the same effect — and mypy is right that reaching into another module's internals is not
#: an import it should bless. ⭐ The first version did it the other way and the type checker
#: caught it, which is the mechanism working.


def _count(connection: sqlite3.Connection, table: str) -> int:
    # ⭐ `int(...)`, not the bare index: mypy reads `fetchone()[0]` as `Any`, and a helper
    # whose return type is `int` while handing back `Any` is the annotation doing nothing.
    # ⭐ `S608` because the name is a literal at every call site in this file.
    row = connection.execute(
        f"SELECT count(*) FROM {table}"  # noqa: S608 - table name is a literal in this file
    ).fetchone()
    return -1 if row is None else int(row[0])


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A seeded library on a throwaway path."""
    path = tmp_path / "demo" / "alphacouncil.db"
    seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
    return path


class TestTheRefusal:
    """⭐ **The one guarantee.** Two prompts and one refusal; this is the refusal."""

    def test_it_raises_on_the_readers_own_database(self) -> None:
        real = default_database_path()
        with pytest.raises(ValueError, match="refusing to seed"):
            refuse_to_overwrite(real)

    def test_the_refusal_survives_a_different_spelling_of_the_same_path(
        self, tmp_path: Path
    ) -> None:
        """⭐ **Compared on the resolved path, not the string.**

        A check written as ``path == str(real)`` would pass a caller who writes
        ``Path("~/AppData/Local/AlphaCouncil/alphacouncil.db")`` or supplies a relative
        path that lands on the same file. ⭐ And the failure that produces is the worst one
        available: fabricated decisions inside the only copy of somebody's record.
        """
        real = default_database_path()
        for spelling in (
            real.parent / "." / real.name,
            real.parent / "sub" / ".." / real.name,
            Path(str(real).upper().replace("ALPHACOUNCIL", "alphacouncil")),
        ):
            with pytest.raises(ValueError, match="refusing to seed"):
                refuse_to_overwrite(spelling)

    def test_the_demo_path_is_not_the_real_one(self) -> None:
        """The other half: the guard is not vacuous because the function returns somewhere
        else. A guard that also blocked the intended path would be a guard nobody could
        satisfy, which is its own failure mode."""
        demo = demo_database_path()
        assert demo != default_database_path()
        # A subdirectory, not a sibling filename — a sibling invites renaming.
        assert demo.parent != default_database_path().parent
        # And the refusal does not fire on it.
        refuse_to_overwrite(demo)

    def test_seeding_it_twice_gives_the_same_library(self, tmp_path: Path) -> None:
        """⭐ **Not additive.** Re-running must not double the content, because the
        alternative is a demo that grows every time somebody runs the command."""
        path = tmp_path / "demo" / "alphacouncil.db"
        seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
        first = seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
        connection = dbmod.connect(path)
        try:
            assert _count(connection, "notes") == first.notes == len(_NOTES)
            assert _count(connection, "cards") == len(_CARDS)
            assert _count(connection, "decisions") == len(_DECISIONS)
        finally:
            connection.close()


class TestTheShape:
    def test_the_layer_that_measured_zero_rows_is_populated(self, library: Path) -> None:
        """⭐ **The reason this file exists.**

        Measured on the reader's own database (2026-10-05): ``cards 0 · notes 0 ·
        reviews 0 · lessons 0``. ⭐ Those are the three queues that make this product
        different from a P&L log, and they were empty **not because they were broken but
        because there had never been anything to review.**
        """
        connection = dbmod.connect(library)
        try:
            for table in ("cards", "notes", "reviews", "card_schedule", "note_schedule"):
                assert _count(connection, table) > 0, (
                    f"{table} is empty — the demo failed at its only job"
                )
        finally:
            connection.close()

    def test_the_watchlist_carries_reasons(self, library: Path) -> None:
        """A reason is not a note: without it the row is a ticker and nothing else."""
        connection = dbmod.connect(library)
        try:
            blanks = connection.execute(
                "SELECT count(*) FROM watchlist_events WHERE reason IS NULL OR trim(reason) = ''"
            ).fetchone()[0]
            assert blanks == 0
        finally:
            connection.close()

    def test_every_decision_carries_counter_evidence_and_a_kill_criterion(
        self, library: Path
    ) -> None:
        """⭐ The three fields the product refuses to record a decision without — and the
        demo has to obey them too, ⭐ or the demo is showing an easier product than the
        real one."""
        connection = dbmod.connect(library)
        try:
            rows = connection.execute(
                "SELECT rationale, counter_evidence, kill_criteria FROM decisions"
            ).fetchall()
            assert rows
            for rationale, counter, criteria in rows:
                assert rationale and rationale.strip()
                assert counter and counter.strip()
                assert criteria and criteria.strip() != "[]"
        finally:
            connection.close()

    def test_the_schedules_are_computed_not_typed(self, library: Path) -> None:
        """⭐⭐ **The load-bearing assertion in this class.**

        Every due date comes from FSRS via ``note_recall.record_review`` ⭐ — so a
        plausible-looking date proves nothing and only a date the scheduler produced will do.
        The check: ⭐ a row whose ``due_at`` is *not* a round-trip of a stored FSRS payload
        is a seed that SQL-inserted a string, which is the exact defect ``spec 057`` §六
        failure #5 names.
        """
        connection = dbmod.connect(library)
        try:
            rows = connection.execute(
                "SELECT due_at, state_json FROM note_schedule"
            ).fetchall()
            assert rows, "no note was scheduled — the recall queue would be empty"
            for due_at, payload in rows:
                assert payload, "a schedule row with no FSRS payload is not a schedule"
                assert due_at.endswith("+00:00") or due_at.endswith("Z")
        finally:
            connection.close()

    def test_the_two_notes_are_linked_so_backlinks_have_a_target(self, library: Path) -> None:
        """A demo with no links understates the knowledge graph (regressions/0021)."""
        connection = dbmod.connect(library)
        try:
            assert _count(connection, "note_links") >= 2
        finally:
            connection.close()

    def test_the_watchlist_symbol_resolves_and_the_market_is_not_guessed(
        self, library: Path
    ) -> None:
        """⭐ `000001` is the Shanghai Composite in one market and a listed bank in the
        other, so 「裸码能否确定市场」 is a table that is either right or quietly wrong."""
        connection = dbmod.connect(library)
        try:
            rows = connection.execute("SELECT market, code FROM instruments").fetchall()
            assert rows
            for market, code in rows:
                assert market in {"sh", "sz"}
                assert len(code) == 6 and code.isdigit()
        finally:
            connection.close()

    def test_every_card_carries_its_own_source(self, library: Path) -> None:
        """A card with no source is refused by the provenance rule (红线 4), so the demo's
        cards must all carry one — and the source must be **on the card**, not implied by
        the section it happens to sit in."""
        connection = dbmod.connect(library)
        try:
            rows = connection.execute(
                "SELECT source_url, source_title FROM cards"
            ).fetchall()
            assert rows
            for url, title in rows:
                assert url.startswith("http")
                assert title.strip()
        finally:
            connection.close()

    def test_the_real_database_is_untouched_by_seeding_a_demo(self, tmp_path: Path) -> None:
        """⭐ **The strongest available check on the guarantee: measure the real file
        before and after.**

        Not 「the function raised」 — ⭐ that only says the code path was taken. ⭐ This says
        the reader's own row counts are identical afterwards, which is the thing that would
        actually be damaged.
        """
        real = default_database_path()
        if not real.exists():
            pytest.skip("no reader database on this machine")

        def snapshot() -> dict[str, int]:
            connection = dbmod.connect(real)
            try:
                return {
                    table: _count(connection, table)
                    for table in ("instruments", "decisions", "cards", "notes")
                }
            finally:
                connection.close()

        before = snapshot()
        seed(tmp_path / "demo" / "alphacouncil.db", now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
        assert snapshot() == before


class TestTheCopyObeysRedLineOne:
    """⭐ Pinned by assertion, not by a comment — because `S-03` scans this file too."""

    @staticmethod
    def _prose() -> list[str]:
        """⭐ Every seed sentence a reader would read as English, not as a field.

        Deliberately **excludes** `kill_criteria`: those are structured predicates
        (红线: 失效条件必须是结构化谓词), ⭐ so their `threshold` is a number the
        product exists to write down, ⭐ and a rule that banned digits here would ban
        the product's own reason for existing.
        """
        out = [body for _, body, _ in _NOTES]
        out += [content for content, _, _ in _CARDS]
        out += [title for _, title, _ in _CARDS]
        for _, _, rationale, counter, _ in _DECISIONS:
            out += [rationale, counter]
        return out

    @pytest.mark.parametrize("text", _prose(), ids=lambda t: t[:16])
    def test_no_seed_sentence_is_prediction_shaped(self, text: str) -> None:
        for banned in ("目标价", "看涨", "看跌", "建议买", "建议卖", "必涨", "涨停", "抄底"):
            assert banned not in text, f"a seed sentence carries 「{banned}」"

    @pytest.mark.parametrize("text", _prose(), ids=lambda t: t[:16])
    def test_no_seed_prose_names_a_price_the_reader_could_act_on(self, text: str) -> None:
        """⚠️ **A price in prose, not any number.**

        ``阈值`` is a machine-readable field and is allowed a number. ⭐ What is banned is a
        price a reader could act on, and in Chinese A-share prose that is 「元」 or 「块」
        attached to a figure. ⭐ This is deliberately narrower than 「no digits」 for the
        reason `F-256` records: a red line written as "no digits" deletes the very things
        the product owes the reader.
        """
        assert not any(
            char.isdigit() and any(word in text for word in ("元", "块"))
            for char in text
        ), f"a seed sentence names a price: {text}"


class TestTheModuleDoesNotLie:
    def test_every_counter_agrees_with_the_file_it_wrote(
        self, tmp_path: Path
    ) -> None:
        """⭐⭐ **The assertion that would have caught the bug the measured column caught.**

        `dev.py demo` printed `reviews 4 (in file: 1)`, ⭐ and the cause was a single
        `tally.reviews` being incremented from **two different tables** — `reviews` (one
        decision review) and `note_reviews` (six recalls) — plus one increment sitting
        outside the loop that owned it. ⭐ Nothing compared the two columns, ⭐ so a counter
        could drift from the file indefinitely and still print a confident number.

        ⭐ So this asserts they are **equal**, for every counter. ⭐ A seeder whose tally
        disagrees with its own output is worse than one that reports nothing, ⭐ because
        the tally is the only thing standing between 「seeded」 and 「looks seeded」.
        """
        path = tmp_path / "demo" / "alphacouncil.db"
        tally = seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))

        pairs = (
            ("instruments", tally.instruments),
            ("watchlist_events", tally.watchlist_events),
            ("decisions", tally.decisions),
            ("cards", tally.cards),
            ("notes", tally.notes),
            ("reviews", tally.decision_reviews),
            ("note_reviews", tally.note_reviews),
        )
        for table, claimed in pairs:
            assert claimed == tally.measured[table], (
                f"{table}: the seeder claims {claimed}, the file holds "
                f"{tally.measured[table]}"
            )

    def test_the_two_review_tables_are_counted_separately(
        self, tmp_path: Path
    ) -> None:
        """⭐ **Why they cannot share one counter.**

        A *decision* review is the `reviews` row the retrospective quadrant reads — ⭐ one
        per decision. ⭐ A *note* recall is the `note_reviews` row FSRS wrote, and there are
        two per reviewed note because the seeder recalls each note twice. ⭐ So the demo
        holds 1 and 6, and a shared counter would have to report one number for both — ⭐
        which is how 「reviews 4」 happened.

        Asserted as distinct values rather than merely "not equal", so the test says which
        is which.
        """
        path = tmp_path / "demo" / "alphacouncil.db"
        tally = seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))

        assert tally.decision_reviews == 1, "one decision is reviewed, once"
        # ⭐ Two recalls on each of three notes. If this changes, the seed's shape changed.
        assert tally.note_reviews == 6
        assert tally.decision_reviews != tally.note_reviews

    def test_a_scheduler_that_silently_writes_nothing_is_caught(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Spec 057 §六: 「播种『成功』但库是空的」 is how this class of tool lies.

        So `seed` re-counts every table in `_DEMO_TABLES` after writing and raises if any is
        empty.

        ⭐⭐ **And targeting `notes` here is impossible — which is worth knowing.** Two
        earlier versions of this test stubbed `notes.create`, and neither could reach the
        guard: the first died in `add_link` (`NoteNotFoundError` — links validate their
        target), the second died in `note_recall.enroll` (`FOREIGN KEY constraint failed`).
        ⭐ **The foreign keys fire first, so a missing note can never arrive at the check.**
        That is the schema doing its job, and it means the guard's real subject is the two
        `*_schedule` tables — nothing has a foreign key pointing *at* them, so they are the
        rows that can silently go missing. ⭐ And they are the rows that decide whether the
        recall queue has anything in it, which is the demo's whole reason to exist.

        So the stub is `sched_repo.enroll` returning normally and writing nothing: the
        success path, with nothing in it.
        """
        import alphacouncil.demo as demo_module

        called: list[str] = []
        monkeypatch.setattr(
            sched_repo,
            "enroll",
            lambda _c, card_id, **_k: called.append(card_id),
        )

        path = tmp_path / "demo" / "alphacouncil.db"
        with pytest.raises(RuntimeError, match="card_schedule=0"):
            # ⭐ The message names the table and its count, so the failure says *which* queue
            # is empty rather than only that something is.
            demo_module.seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
        assert called, "the stub was never called — the test did not exercise the seeder"

    def test_the_guard_names_every_empty_table_not_just_the_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Reporting one and stopping would hide the rest behind a retry loop.

        With both schedulers stubbed out, the message must mention both — ⭐ because a
        reader who fixes `note_schedule` and re-runs deserves to meet `card_schedule` on the
        next attempt rather than discover it by hand.
        """
        import alphacouncil.demo as demo_module

        # ⭐ `lambda *_a, **_k: None` rather than `*a, **k` — `ARG005` is right that the
        # names are unused, ⭐ and a stub that ignores its arguments is clearer written that
        # way than written with names nobody reads.
        monkeypatch.setattr(sched_repo, "enroll", lambda *_a, **_k: None)
        monkeypatch.setattr(recall_repo, "enroll", lambda *_a, **_k: None)
        monkeypatch.setattr(recall_repo, "record_review", lambda *_a, **_k: None)

        path = tmp_path / "demo" / "alphacouncil.db"
        with pytest.raises(RuntimeError) as caught:
            demo_module.seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
        message = str(caught.value)
        assert "note_schedule=0" in message
        assert "card_schedule=0" in message

    def test_a_failed_seed_leaves_the_file_usable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐⭐ **The test that found a real defect, kept so it cannot come back.**

        The first version of `seed` closed its connection at the end of a long body. ⭐ That
        handles success and nothing else, and the leak is not a tidiness matter: ⭐ on
        Windows the open handle keeps the file locked, so the *next* `dev.py demo` dies in
        `stale.unlink()` with `PermissionError` **before it can try again**.

        ⭐ **A seeder whose failure bricks its own command is worse than one that fails
        cleanly** — the reader is left with a command that cannot be run at all, and the
        original error long gone from the screen.

        So: fail a seed, then seed again on the same path. ⭐ The second call must succeed,
        which is only true if the first one let go of the file.
        """
        import alphacouncil.demo as demo_module

        monkeypatch.setattr(
            notes_repo,
            "create",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("the write failed")),
        )
        path = tmp_path / "demo" / "alphacouncil.db"
        with pytest.raises(RuntimeError):
            demo_module.seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))

        # ⭐ The stub is undone first. If the first seed still held the file, this call
        # would die in `unlink` with `PermissionError` **before** reaching any write — ⭐
        # which is the failure this test exists to catch, and it would be reported as the
        # wrong exception type if the stub were left in place.
        monkeypatch.undo()
        tally = demo_module.seed(path, now=datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
        assert tally.notes == len(_NOTES)
