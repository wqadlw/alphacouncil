"""Notes: the half of the knowledge layer that was missing (spec 026).

The tests are grouped by the decision each one pins, and several of them exist
because the first draft of the code got that decision **wrong** — in which case
the test is the record of the mistake, not a restatement of the code.

Four of them are about things that must *not* happen, which is where the real
risk is in a knowledge store:

* the body is never rewritten (``test_the_body_is_stored_verbatim``)
* a tag never matches a longer tag (``test_a_tag_does_not_match_a_longer_one``)
* a note needs no source and no instrument (``test_a_note_needs_neither_*``)
* a link cannot point at nothing (``test_a_link_to_a_missing_target_is_refused``)
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from alphacouncil.domain.card import (
    CardDraft,
    CardOrigin,
    CardStatus,
    ClaimType,
)
from alphacouncil.domain.note import (
    Link,
    LinkKind,
    NoteBodyBlankError,
    NoteDraft,
    NoteLinkSelfError,
    NoteLinkTargetUnknownError,
    NoteNotFoundError,
    NoteTagInvalidError,
    NoteTitleRequiredError,
    validate_draft,
    validate_tag,
)
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage import db, migrate
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import cards as cards_repo
from alphacouncil.storage.repositories import notes as repo

NOW = "2026-09-28T00:00:00.000Z"


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


def _write(connection: sqlite3.Connection, **overrides: object) -> str:
    """Create a note inside a transaction and return its id."""
    draft = NoteDraft(
        title=str(overrides.get("title", "流动性与周期股")),
        body=str(overrides.get("body", "流动性收紧时周期股先跌，成长股后跌。")),
        tags=tuple(overrides.get("tags", ())),  # type: ignore[arg-type]
        links=tuple(overrides.get("links", ())),  # type: ignore[arg-type]
        symbols=tuple(overrides.get("symbols", ())),  # type: ignore[arg-type]
        as_of=overrides.get("as_of"),  # type: ignore[arg-type]
    )
    with transaction(connection):
        # `NoteRow` wraps a `Note` — the relationship fields live beside it, so
        # the id is `row.note.id`. Reading `row.id` was my first draft and it
        # failed 16 tests at once, which is the cheapest possible way to find
        # out.
        return repo.create(connection, draft, now=NOW).note.id


# ── the whole point: a note needs neither a source nor an instrument ─────────


class TestAFileIsAFact:
    def test_a_note_needs_no_source(self, connection: sqlite3.Connection) -> None:
        """A macro view has no citation, and refusing it is what made the vault
        impossible to build in the first place.

        The contrast with ``cards`` is the point, so it is asserted against the
        card side too: the same repository session, a card without a source is
        refused. That is not a bug to fix later — it is the provenance rule.
        """
        note_id = _write(connection, title="流动性收紧时周期股先跌")
        row = repo.get_by_id(connection, note_id)
        assert row.note.title == "流动性收紧时周期股先跌"
        assert row.symbols == ()
        assert row.links == ()

    def test_a_card_still_may_not_be_written_without_a_source(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The provenance rule is untouched.

        If this ever starts failing, the feature was implemented the wrong way:
        by loosening cards instead of adding notes. A note with no source is
        fine; a *claim* with no source is a claim the reader cannot check.
        """
        with (
            pytest.raises(Exception),  # noqa: B017 - any card-domain refusal
            transaction(connection),
        ):
            cards_repo.create(
                connection,
                CardDraft(
                    content="高端白酒提价能力持续",
                    claim_type=ClaimType.SUPPORTING,
                    source_url="",  # <- the thing cards may not do
                    source_title="",
                    origin=CardOrigin.USER_WRITTEN,
                    priority=3,
                    status=CardStatus.ACTIVE,
                ),
            )

    def test_a_note_needs_no_instrument(self, connection: sqlite3.Connection) -> None:
        """A method or a framework has no ticker. `cards` cannot express that;
        this is the row that proves the two tables are not the same thing."""
        _write(connection, title="我的估值框架", body="先看现金流，再看增长。")
        assert len(repo.list_all(connection)) == 1

    def test_a_note_may_also_carry_instruments(self, connection: sqlite3.Connection) -> None:
        """Optional, not forbidden — a note *about* a stock is a normal note."""
        sym = Symbol(market=Market.SH, code="600519")
        note_id = _write(
            connection,
            title="茅台的提价能力",
            body="看批价，不看出厂价。",
            symbols=(sym,),
        )
        row = repo.get_by_id(connection, note_id)
        assert [s.code for s in row.symbols] == ["600519"]

    def test_a_note_keeps_a_data_cutoff_date(self, connection: sqlite3.Connection) -> None:
        """PIT discipline on a note too, and it must survive the round trip.

        ⭐ The first draft of ``_to_note_row`` hard-coded ``as_of=None`` while the
        dataclass had the field. This test is why that was caught: without it the
        field would have quietly answered "no cutoff date" forever.
        """
        note_id = _write(connection, as_of=date(2026, 8, 31))
        assert repo.get_by_id(connection, note_id).as_of == date(2026, 8, 31)


# ── the body is the user's own words ─────────────────────────────────────────


class TestTheBodyIsVerbatim:
    def test_the_body_is_stored_verbatim(self, connection: sqlite3.Connection) -> None:
        """Whitespace, newlines and Markdown punctuation all survive.

        A "tidy the input" step would rewrite the reader's own writing, and for a
        product whose premise is that your record is trustworthy that is the one
        change that would not look like a bug.
        """
        body = "# 标题\n\n- 第一条\n- 第二条\n\n  缩进两格\n\n结尾没有换行"
        note_id = _write(connection, body=body)
        assert repo.get_by_id(connection, note_id).note.body == body

    def test_a_body_of_only_whitespace_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        with pytest.raises(NoteBodyBlankError):
            _write(connection, body="   \n\t  \n")

    def test_editing_replaces_the_body_and_moves_only_updated_at(
        self, connection: sqlite3.Connection
    ) -> None:
        """A note is mutable, and ``created_at`` never moves.

        ⭐ Cards are append-only because a claim you later retract must leave a
        trace — that is the anti-hindsight mechanism. A note is working text; an
        event per keystroke would bury it. So no event stream here, but the
        creation moment stays answerable.
        """
        note_id = _write(connection)
        with transaction(connection):
            updated = repo.update_body(
                connection, note_id, body="改过的正文", now="2026-09-29T00:00:00.000Z"
            )
        assert updated.note.body == "改过的正文"
        assert updated.note.created_at == NOW
        assert updated.note.updated_at == "2026-09-29T00:00:00.000Z"

    def test_an_edit_cannot_blank_the_body(self, connection: sqlite3.Connection) -> None:
        """Otherwise the page could be emptied by a stray save."""
        note_id = _write(connection)
        with pytest.raises(NoteBodyBlankError), transaction(connection):
            repo.update_body(connection, note_id, body="  ")


# ── tags are rows, not a joined string ──────────────────────────────────────


class TestTags:
    def test_a_tag_does_not_match_a_longer_one(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The test the comma-string design would fail.

        ``LIKE '%宏观%'`` returns 宏观债 too, and the user's filtered list
        silently omits a note they can see in the unfiltered one. There is no way
        for them to work out why.
        """
        broad = _write(connection, title="宏观", body="关于宏观", tags=("宏观",))
        _write(connection, title="宏观债", body="关于宏观债", tags=("宏观债",))

        found = repo.list_by_tag(connection, "宏观")
        assert [r.note.id for r in found] == [broad]

    def test_a_tag_is_trimmed_so_the_set_has_no_ghosts(
        self, connection: sqlite3.Connection
    ) -> None:
        note_id = _write(connection, tags=("  宏观  ", "估值"))
        assert repo.get_by_id(connection, note_id).tags == ("估值", "宏观")

    def test_a_comma_in_a_tag_is_refused(self) -> None:
        """Because the joined shape is the failure mode this table exists to avoid."""
        with pytest.raises(NoteTagInvalidError):
            validate_tag("宏观,估值")

    def test_a_blank_tag_is_refused(self) -> None:
        with pytest.raises(NoteTagInvalidError):
            validate_tag("   ")

    def test_tags_can_be_added_and_removed(self, connection: sqlite3.Connection) -> None:
        note_id = _write(connection, tags=("宏观",))
        with transaction(connection):
            repo.add_tag(connection, note_id, "估值")
        assert set(repo.get_by_id(connection, note_id).tags) == {"宏观", "估值"}
        with transaction(connection):
            repo.remove_tag(connection, note_id, "宏观")
        assert repo.get_by_id(connection, note_id).tags == ("估值",)

    def test_a_filter_value_containing_a_wildcard_matches_nothing_extra(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ Added because a mutation check found the test above was too weak.

        Turning ``WHERE t.tag = ?`` into ``LIKE ?`` **left the previous test
        green** — SQLite's ``LIKE`` without a wildcard in the pattern is an exact
        match, so 宏观 still did not pull in 宏观债 and the assertion passed.

        The mutation only bites when the *value* carries a wildcard, and nothing
        tested that. So a reader who typed ``%`` into the tag filter would get
        **every note in the vault** and no error, because ``LIKE '%'`` is true for
        every string.

        That is the general shape of the hole: the first test proved the *common*
        case, the mutation proved the *reach* was untested. A filter that accepts
        a user string has to say what happens when the string is a pattern.
        """
        _write(connection, title="宏观", body="b1", tags=("宏观",))
        _write(connection, title="估值", body="b2", tags=("估值",))

        assert repo.list_by_tag(connection, "%") == []
        assert repo.list_by_tag(connection, "_") == []

    def test_all_tags_lists_every_tag_in_use(self, connection: sqlite3.Connection) -> None:
        _write(connection, tags=("宏观",))
        _write(connection, tags=("估值", "宏观"))
        assert repo.all_tags(connection) == ["估值", "宏观"]


# ── links: the skeleton, and the one check the schema cannot do ──────────────


class TestLinks:
    def test_a_note_can_link_to_a_card(self, connection: sqlite3.Connection) -> None:
        with transaction(connection):
            card_id = cards_repo.create(
                connection,
                CardDraft(
                    content="渠道库存是白酒先行指标",
                    claim_type=ClaimType.SUPPORTING,
                    source_url="https://example.com/r",
                    source_title="白酒渠道调研",
                    origin=CardOrigin.USER_WRITTEN,
                    priority=3,
                    status=CardStatus.ACTIVE,
                ),
                now=NOW,
            ).id
        note_id = _write(
            connection,
            title="先行指标怎么用",
            links=(Link(to_kind=LinkKind.CARD, to_id=card_id),),
        )
        assert repo.get_by_id(connection, note_id).links == (
            Link(to_kind=LinkKind.CARD, to_id=card_id),
        )

    def test_a_link_to_a_missing_target_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The constraint SQLite cannot express.

        ``note_links.to_id`` points into five different tables and there is no
        polymorphic foreign key, so without this check the table would happily
        hold a dead reference that only shows up as a blank space months later.
        """
        with pytest.raises(NoteLinkTargetUnknownError):
            _write(
                connection,
                links=(Link(to_kind=LinkKind.CARD, to_id="card_9999999999999"),),
            )

    def test_a_link_to_a_missing_target_is_refused_on_the_add_path_too(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ `add_link` repeats the existence check, so it needs its own test.

        A mutation check found this: removing the guard from `add_link` while
        leaving it in `create` left the suite **green**, because every test that
        exercised a bad link went through `create`.

        That is the specific hazard of a guard that exists in two places — the
        second copy is untested, so deleting it costs nothing at review and buys
        a dead link that only surfaces months later as a blank space. Duplicated
        rules need duplicated tests, and the mutation check is how you find out
        that you did not write one.
        """
        note_id = _write(connection)
        with pytest.raises(NoteLinkTargetUnknownError), transaction(connection):
            repo.add_link(
                connection,
                note_id,
                Link(to_kind=LinkKind.CARD, to_id="card_9999999999999"),
            )
        # And nothing was written.
        assert repo.get_by_id(connection, note_id).links == ()

    def test_a_note_cannot_link_to_itself(self, connection: sqlite3.Connection) -> None:
        # `_write` opens its own transaction, so this one must not be nested.
        note_id = _write(connection)
        with pytest.raises(NoteLinkSelfError), transaction(connection):
            repo.add_link(
                connection, note_id, Link(to_kind=LinkKind.NOTE, to_id=note_id)
            )

    def test_two_notes_in_the_same_millisecond_both_survive(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The collision the cards repository is still vulnerable to.

        Both writes pass the *same* ``now``, so a `<millis>`-only id collides and
        the second INSERT dies with a bare ``UNIQUE constraint failed``. Losing a
        note to "快速记一句" is not acceptable for the feature whose whole point is
        that you can write things down.
        """
        first = _write(connection, title="第一句")
        second = _write(connection, title="第二句")
        assert first != second
        assert {r.note.id for r in repo.list_all(connection)} == {first, second}
        assert repo.get_by_id(connection, first).note.title == "第一句"
        assert repo.get_by_id(connection, second).note.title == "第二句"

    def test_backlinks_answer_what_points_here(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The function that makes this a knowledge system rather than a folder.

        ``references/research/02``: every notes app links note-to-note, and that
        is not a differentiator. Being able to ask "which of my notes refers to
        this card" and get an answer is.
        """
        with transaction(connection):
            card_id = cards_repo.create(
                connection,
                CardDraft(
                    content="渠道库存是先行指标",
                    claim_type=ClaimType.SUPPORTING,
                    source_url="https://example.com/r",
                    source_title="调研",
                    origin=CardOrigin.USER_WRITTEN,
                    priority=3,
                    status=CardStatus.ACTIVE,
                ),
                now=NOW,
            ).id
        a = _write(connection, links=(Link(to_kind=LinkKind.CARD, to_id=card_id),))
        b = _write(connection, links=(Link(to_kind=LinkKind.CARD, to_id=card_id),))
        _write(connection, title="无关的一篇")

        assert repo.backlinks_for(connection, LinkKind.CARD, card_id) == [a, b]

    #: A review and a lesson written directly, for the link tests below. The rows go
    #: in raw because this is about **link resolution**, not about the recording path
    #: — and going through `lesson.record_lesson` would make these two tests fail for
    #: reasons belonging to another file. `test_lessons.py` covers the recording path.
    _LESSON = "lesson_1700000000000"
    _REVIEW = "review_1700000000000"
    _STAMP = "2026-09-20T02:15:00.000Z"

    def _write_a_lesson(self, connection: sqlite3.Connection) -> str:
        """A review and a lesson, raw.

        Written by hand rather than through ``lesson.record_lesson`` because this is
        about **link resolution**, and routing it through the recording path would
        make these tests fail for reasons that belong to ``test_lessons.py``. ⭐ The
        ``reviews`` row mirrors that file's ``_write_review``, which is the one known
        to satisfy the schema — my first attempt omitted a column and the
        ``IntegrityError`` named it, which is the good kind of failure.
        """
        with transaction(connection):
            # reviews -> decisions -> instruments, in that order, because the foreign
            # keys go that way and SQLite checks them as the rows land.
            connection.execute(
                "INSERT INTO instruments (market, code, name, name_source, name_fetched_at, "
                "asset_type, created_at) VALUES ('sh', '600519', ?, 'sina', ?, 'stock', ?)",
                ("贵州茅台", self._STAMP, self._STAMP),
            )
            connection.execute(
                "INSERT INTO decisions (id, market, code, action, rationale, counter_evidence, "
                "kill_criteria, thesis_id) VALUES (?, 'sh', '600519', 'buy', ?, ?, ?, NULL)",
                (
                    "2026-09-20T02:15:00.000Z",
                    "高端酒提价能力可持续",
                    "批价可能回落",
                    "[]",
                ),
            )
            connection.execute(
                "INSERT INTO reviews (id, decision_id, process_score, outcome, reviewed_at, "
                "due_at_snapshot, note, created_at) "
                "VALUES (?, ?, 2, NULL, ?, ?, NULL, ?)",
                (
                    self._REVIEW,
                    "2026-09-20T02:15:00.000Z",
                    self._STAMP,
                    self._STAMP,
                    self._STAMP,
                ),
            )
            connection.execute(
                "INSERT INTO lessons (lesson_id, review_id, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (self._LESSON, self._REVIEW, "先看批价", self._STAMP),
            )
        return self._LESSON

    def test_a_lesson_link_to_a_lesson_that_does_not_exist_is_refused(
        self, connection: sqlite3.Connection
    ) -> None:
        """A lesson link resolves now, so an unresolvable one is still a mistake.

        This used to read 「J5 教训转卡 is next round, so a lesson link cannot be written
        yet」 — the enum listed ``lesson`` so the schema, the enum and the docs agreed
        from the start, while the target table did not exist. Spec 030 built it, which
        broke the test, and a test whose docstring declared its own premise temporary
        *should* stop passing when the premise is met.

        The refusal survives for a better reason: ``note_links.to_id`` deliberately has
        no foreign key, so resolution happens in Python — and a target that does not
        resolve is exactly what that check exists to catch.
        """
        with pytest.raises(NoteLinkTargetUnknownError):
            _write(
                connection,
                links=(Link(to_kind=LinkKind.LESSON, to_id="lesson_1"),),
            )

    def test_a_lesson_link_to_an_existing_lesson_is_accepted(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The test that would have caught a wrong J5.

        A ``lessons`` table that existed but was not wired into link resolution would
        leave the test above green and only this one red. Together they say what
        neither can alone: unresolvable is refused, resolvable is not.

        ``LinkKind.LESSON`` was declared two specs before the table existed, on the
        principle that the enum, the schema and the documents should agree from the
        start rather than converge later. This is where that pays: no enum change, no
        migration and no documentation edit was needed to make the link work.
        """
        lesson_id = self._write_a_lesson(connection)
        note_id = _write(
            connection,
            links=(Link(to_kind=LinkKind.LESSON, to_id=lesson_id),),
        )
        # ⭐ `backlinks_for` returns **note ids**, not rows — one per linking note.
        # The first version of this asserted `[row.note.id for row in stored]`, which is
        # the shape the *write* path returns (`NoteRow.note.id`) and not this one.
        assert repo.backlinks_for(connection, LinkKind.LESSON, lesson_id) == [note_id]


# ── titles, listing, absence ────────────────────────────────────────────────


class TestTitlesAndListing:
    def test_a_blank_title_is_refused(self, connection: sqlite3.Connection) -> None:
        with pytest.raises(NoteTitleRequiredError):
            _write(connection, title="   ")

    def test_a_missing_note_raises_rather_than_returning_none(
        self, connection: sqlite3.Connection
    ) -> None:
        """A caller that treats "absent" as "empty note" would render a blank page
        for a deleted id and call it an empty vault."""
        with pytest.raises(NoteNotFoundError):
            repo.get_by_id(connection, "note_9999999999999")

    def test_notes_are_listed_newest_edit_first(self, connection: sqlite3.Connection) -> None:
        first = _write(connection, title="第一篇")
        second = _write(connection, title="第二篇")
        with transaction(connection):
            repo.update_body(
                connection, first, body="改过", now="2026-09-30T00:00:00.000Z"
            )
        assert [r.note.id for r in repo.list_all(connection)] == [first, second]

    def test_an_empty_vault_lists_nothing(self, connection: sqlite3.Connection) -> None:
        assert repo.list_all(connection) == []


# ── the domain validator on its own ─────────────────────────────────────────


def test_validate_draft_accepts_a_minimal_note() -> None:
    validate_draft(NoteDraft(title="一条笔记", body="正文"))


def test_validate_tag_leaves_case_alone() -> None:
    """⭐ Tags are trimmed and **nothing else**.

    Lowercasing would merge ``PE`` with ``pe`` behind the user's back, and a
    Chinese tag has no case to fold in the first place.
    """
    assert validate_tag("  PE  ") == "PE"
    assert validate_tag("估值") == "估值"
