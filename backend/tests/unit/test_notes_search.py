"""Searching the vault (spec 027).

A note you cannot find is a note you have lost, so this file is mostly about
**failure modes** rather than about search working:

* two characters — 「利率」, 「白酒」, 「估值」 — must find the note. trigram cannot
  do that, which is why :func:`search` has a second path, and a search box that
  says "no results" for the most natural query in this domain would tell the
  reader the note does not exist;
* the index must follow an edit, in **both** directions. A stale row is the worst
  failure this feature has: the note is on screen and the search disagrees;
* a reader who types `%` must not receive the whole vault;
* a reader who types FTS5 query syntax must get text searched, not an error.

The two paths are also held to **agreeing**: the same query must not return one
set of notes at 2 characters and a different set at 3. That equivalence is the
property a reader would notice first if it broke, and nothing else would catch it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from alphacouncil.domain.note import NoteDraft
from alphacouncil.storage import db, migrate
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import notes as repo

NOW = "2026-09-28T00:00:00.000Z"
LATER = "2026-09-29T00:00:00.000Z"


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


def _write(
    connection: sqlite3.Connection, title: str, body: str = "正文", **extra: object
) -> str:
    draft = NoteDraft(
        title=title,
        body=body,
        tags=tuple(extra.get("tags", ())),  # type: ignore[arg-type]
    )
    with transaction(connection):
        return repo.create(connection, draft, now=NOW).note.id


def _titles(connection: sqlite3.Connection, query: str) -> list[str]:
    return [row.note.title for row in repo.search(connection, query)]


# ── the two-character floor ────────────────────────────────────────────────


class TestTwoCharactersStillFindTheNote:
    """⭐ trigram's floor is 3 characters, and this domain searches for 2."""

    def test_a_two_character_query_finds_a_note(self, connection: sqlite3.Connection) -> None:
        _write(connection, "利率上行的观察")
        _write(connection, "白酒行业产能出清")
        _write(connection, "估值要看现金流")
        assert _titles(connection, "利率") == ["利率上行的观察"]

    @pytest.mark.parametrize("needle", ["利率", "白酒", "估值", "宏观", "渠道"])
    def test_the_words_this_domain_actually_searches_for(
        self, connection: sqlite3.Connection, needle: str
    ) -> None:
        """Not an arbitrary 2-character string — the ones a reader would type."""
        _write(connection, f"关于{needle}的一篇笔记")
        assert _titles(connection, needle) == [f"关于{needle}的一篇笔记"]

    def test_a_two_character_query_finds_text_in_the_body(
        self, connection: sqlite3.Connection
    ) -> None:
        _write(connection, "一篇标题无关的笔记", body="先看现金流，再看增长。")
        assert _titles(connection, "现金") == ["一篇标题无关的笔记"]

    def test_a_query_at_the_boundary_length_uses_the_index(
        self, connection: sqlite3.Connection
    ) -> None:
        """3 is the first length FTS5 can match, so it is the boundary case that
        must work on the *other* path from 2 — otherwise a reader sees the index
        wake up with no explanation."""
        _write(connection, "现金流比利润重要")
        assert _titles(connection, "现金流") == ["现金流比利润重要"]


class TestTheTwoPathsAgree:
    """⭐ The same query must not return different notes at different lengths."""

    @pytest.mark.parametrize(
        "needle",
        [
            "利率",
            "利率上行",
            "现金流",
            "自由现金流优先",
            "周期股",
            "不存在的词",
            "PE",
            "a",
        ],
    )
    def test_fts_and_substring_find_the_same_notes(
        self, connection: sqlite3.Connection, needle: str
    ) -> None:
        _write(connection, "利率上行与周期股", body="现金流优先，不要看利润")
        _write(connection, "白酒行业产能出清", body="批价是先行指标")
        _write(connection, "估值框架", body="先看现金流")

        indexed = (
            _titles(connection, needle)
            if len(needle.strip()) >= repo.MIN_FTS_CHARS
            else None
        )
        # The substring path is the ground truth: a pure contiguous test with no
        # tokeniser involved.
        substring = [
            row.note.title
            for row in repo.list_all(connection)
            if needle in row.note.title or needle in row.note.body
        ]
        if indexed is None:
            assert substring == _titles(connection, needle)
        else:
            assert indexed == substring, (
                f"{needle!r}: the indexed path and the substring path disagree"
            )


# ── the index must follow writes ───────────────────────────────────────────


class TestTheIndexFollowsTheNotes:
    """⭐ The failure this whole feature's correctness rests on."""

    def test_the_index_follows_an_edit_in_both_directions(
        self, connection: sqlite3.Connection
    ) -> None:
        """Old words must **stop** matching, not just new ones start.

        An insert-only index is the easy half to get right and the useless half:
        the note would findable by a phrase it no longer contains, which looks
        like a random extra result and is very hard to attribute to a bug. FTS5
        virtual tables have no UPDATE, so the trigger must delete before it
        inserts — `test_the_index_row_count_tracks_notes` would also catch it, but
        only once the rows had multiplied, so this is the earlier signal.
        """
        note_id = _write(connection, "原标题", body="这里写的是自由现金流")

        assert _titles(connection, "自由现金流") == ["原标题"]

        with transaction(connection):
            repo.update_body(
                connection,
                note_id,
                title="新标题",
                body="这里写的是利润表",
                now=LATER,
            )

        assert repo.search(connection, "自由现金流") == [], "stale text still matches"
        assert _titles(connection, "利润表") == ["新标题"]

    def test_a_deleted_note_is_not_findable(self, connection: sqlite3.Connection) -> None:
        """⚠️ Read the next test before trusting this one.

        The guarantee here is the **JOIN**, not the delete trigger: search selects
        ``FROM notes_fts JOIN notes``, so a row left behind in the index is
        invisible to results. Removing the ``AFTER DELETE`` trigger entirely leaves
        this test green — a mutation check proved exactly that.

        So this test pins what a reader experiences, and
        :meth:`test_a_delete_does_not_leave_an_orphan_index_row` pins the trigger.
        Both are worth having, and conflating them is what let the mutation
        through: a test that says 「not findable」 and a trigger that says
        「not retained」 are different claims about different mechanisms.
        """
        _write(connection, "会被删掉的一篇", body="独特的三字词组")
        assert repo.search(connection, "独特的三") != []

        with transaction(connection):
            connection.execute("DELETE FROM notes")

        assert repo.search(connection, "独特的三") == []

    def test_a_delete_does_not_leave_an_orphan_index_row(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ The invariant the join hides, stated directly.

        A stale row after a delete is invisible in results — the join drops it — so
        it is not a correctness bug. It is still a bug: the index grows without
        bound, and the first symptom is a database that has quietly doubled in
        size, which surfaces months later as slowness nobody can attribute.

        That is the whole argument for the ``AFTER DELETE`` trigger, so it is the
        thing the trigger's test has to assert.

        ⭐ The id is captured **before** the delete. The first draft recovered it
        from the index afterwards — which fails the moment the trigger works, so
        the test only passed while the bug was present, in the one place it was
        looking for the bug. A test that requires its own bug to survive is a test
        that measures the wrong thing.
        """
        doomed = _write(connection, "会被删掉的一篇", body="独特的三字词组")
        _write(connection, "会留下的另一篇", body="另一段独特文字")

        with transaction(connection):
            connection.execute("DELETE FROM notes WHERE id = ?", (doomed,))

        orphans = connection.execute(
            "SELECT count(*) FROM notes_fts WHERE note_id = ?", (doomed,)
        ).fetchone()[0]
        assert orphans == 0, "the delete trigger left a row behind"

        indexed = connection.execute("SELECT count(*) FROM notes_fts").fetchone()[0]
        actual = connection.execute("SELECT count(*) FROM notes").fetchone()[0]
        assert indexed == actual == 1

    def test_the_index_row_count_tracks_notes(
        self, connection: sqlite3.Connection
    ) -> None:
        """The blunt check: one index row per note, no more and no fewer.

        A duplicated index row is invisible in results — it only doubles the size
        and skews nothing visible — so nothing else in this file would notice it.
        """
        for index in range(4):
            _write(connection, f"第{index}篇", body="共同的正文")

        indexed = connection.execute("SELECT count(*) FROM notes_fts").fetchone()[0]
        actual = connection.execute("SELECT count(*) FROM notes").fetchone()[0]
        assert indexed == actual == 4

    def test_the_index_can_be_rebuilt_from_notes(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ This is what makes ``0008``'s ``destructive_down: false`` a fact.

        The manifest claims dropping the search migration cannot lose a word the
        user wrote, because the index is derived. A claim in a manifest is a
        promise nobody re-checks, and "we can rebuild it" turns into "we can
        rebuild it" for ever after someone changes what goes into the index. So
        the rebuild is executed, and the results are compared — not just the row
        count.
        """
        _write(connection, "重建测试", body="自由现金流优先")
        connection.execute("DELETE FROM notes_fts")
        connection.execute(
            "INSERT INTO notes_fts (note_id, title, body)"
            " SELECT id, title, body FROM notes"
        )
        assert _titles(connection, "自由现金流") == ["重建测试"]


# ── a reader's string is text, not syntax ──────────────────────────────────


class TestHostileInput:
    @pytest.mark.parametrize(
        "needle", ['"', '"未闭合', "a*", "NEAR(a b)", "-x", "AND", "a OR b", "NEAR", "*"]
    )
    def test_fts_query_syntax_is_searched_as_text_not_rejected(
        self, connection: sqlite3.Connection, needle: str
    ) -> None:
        """FTS5 has a query language. Passed raw, `"` or `NEAR` is a **syntax
        error** — which reaches the reader as a failure, not as "no results", and
        so reads as the app being broken.

        The phrase is searched **whole**, so it is long enough to be on the
        indexed path (which is the only path with a language to misread) and it is
        guaranteed contiguous in the text. The first draft padded the token with a
        suffix and looked for `needle + suffix`, which is *not* adjacent in a title
        written as ``f"{needle} {suffix}"`` — so every case failed on a
        construction error and would have passed for the wrong reason if the
        spacing had happened to line up.
        """
        phrase = f"开头{needle}结尾标记"
        _write(connection, phrase, body=f"正文里也有{phrase}")
        assert repo.search(connection, phrase) != [], f"{needle!r} was not searched as text"

    def test_a_percent_sign_does_not_return_the_whole_vault(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ Found by spec 026's mutation check on the *tag* filter, then fixed
        there with a test. Here the shape changed instead, so the test cannot be
        forgotten: ``LIKE '%%%'`` returns 4 of 4 rows; ``instr`` returns 1.

        A reader who types ``%`` into a two-character search would otherwise get
        every note in the vault and no indication that the filter was ignored.
        """
        # The note must *literally* contain the character. The first draft called
        # it 「百分号在标题」, which contains 百 — the Chinese word for
        # "hundred" — so the assertion passed for the wrong reason and would have
        # kept passing if `instr` had been replaced by `LIKE` again.
        _write(connection, "标题里有%符号", body="普通的正文")
        _write(connection, "普通标题一", body="普通正文")
        _write(connection, "普通标题二", body="普通正文")
        _write(connection, "普通标题三", body="普通正文")

        assert _titles(connection, "%") == ["标题里有%符号"]

    def test_an_underscore_does_not_return_the_whole_vault(
        self, connection: sqlite3.Connection
    ) -> None:
        """`LIKE '%_%'` matches **every** row of at least one character — which is
        all of them. Measured: 4 of 4 with `LIKE`, 0 with `instr`."""
        _write(connection, "标题里有_下划线", body="普通的正文")
        _write(connection, "普通标题", body="普通正文")
        _write(connection, "另一个标题", body="普通正文")

        assert _titles(connection, "_") == ["标题里有_下划线"]


# ── what search does not do ────────────────────────────────────────────────


class TestSearchFiltersItDoesNotReorder:
    def test_results_stay_in_edit_order(
        self, connection: sqlite3.Connection
    ) -> None:
        """⭐ `bm25()` is available and deliberately unused.

        Relevance-sorting would make the same notes appear in a different order
        depending on whether a query happened to be typed — and the value of a
        notes list is 「我最近写了什么」, not 「哪条最匹配」. Both paths carry the
        same `ORDER BY updated_at DESC` as `list_all`, and this pins it.
        """
        _write(connection, "先写的匹配", body="共同关键词")
        _write(connection, "后写的匹配", body="共同关键词")

        # The note written *first* is the one edited *last*, so it now has the
        # later `updated_at` and must come **first**. The first draft asserted the
        # opposite, and the code was right: an ordering test that expects the
        # wrong order teaches you to distrust the code that works.
        with transaction(connection):
            repo.update_body(
                connection,
                _first_id(connection, "先写的匹配"),
                body="共同关键词 改",
                now=LATER,
            )

        assert _titles(connection, "共同关键词") == ["先写的匹配", "后写的匹配"]
        assert [r.note.title for r in repo.list_all(connection)] == _titles(
            connection, "共同关键词"
        )

    def test_an_empty_query_returns_the_whole_vault(self, connection: sqlite3.Connection
    ) -> None:
        """Clearing the box is the same as never having typed anything.

        Returning nothing for an empty query would make a page look broken the
        instant the reader cleared the box, which is the most common single
        keystroke in a search field.
        """
        _write(connection, "一", body="一")
        _write(connection, "二", body="二")
        assert _titles(connection, "") == [r.note.title for r in repo.list_all(connection)]
        assert _titles(connection, "   ") == [r.note.title for r in repo.list_all(connection)]

    def test_search_reads_the_title(self, connection: sqlite3.Connection) -> None:
        _write(connection, "标题里有这个词", body="正文无关")
        assert _titles(connection, "这个词") == ["标题里有这个词"]

    def test_search_reads_the_body(self, connection: sqlite3.Connection) -> None:
        _write(connection, "标题无关", body="正文里有这个词")
        assert _titles(connection, "这个词") == ["标题无关"]

    def test_search_does_not_read_tags_and_the_scope_is_where_it_should_be(
        self, connection: sqlite3.Connection
    ) -> None:
        """Tags are searchable through their own control, one row above the list.

        Putting tags into the index would mean the trigger had to re-read
        `note_tags` on every note write and re-index on every tag change, and
        `note_tags` rows are not part of the note row. That is a real cost for a
        capability that already exists as one click. So the boundary is stated
        rather than left to be discovered.

        The title is 「一条普通的笔记」 and the body 「正文也没有」. The first draft
        wrote 「没有这个词」, which *contains* the term — so `search` did find it,
        the assertion failed, and the tag lookup was the only thing actually
        holding the test up. A test whose subject appears in its own fixture is
        worth re-reading before its failure is believed.
        """
        _write(connection, "一条普通的笔记", body="正文也没有", tags=("这个词",))
        assert repo.search(connection, "这个词") == []
        assert [r.note.title for r in repo.list_by_tag(connection, "这个词")] == [
            "一条普通的笔记"
        ]

    def test_search_and_the_tag_filter_compose(
        self, connection: sqlite3.Connection
    ) -> None:
        """Both are needed: a query narrows the body, a tag narrows the set."""
        _write(connection, "宏观判断", body="流动性收紧", tags=("宏观",))
        _write(connection, "估值判断", body="流动性宽松", tags=("估值",))

        found = [
            row
            for row in repo.search(connection, "流动性")
            if "宏观" in row.tags
        ]
        assert [row.note.title for row in found] == ["宏观判断"]


def _first_id(connection: sqlite3.Connection, title: str) -> str:
    row = connection.execute("SELECT id FROM notes WHERE title = ?", (title,)).fetchone()
    assert row is not None, f"no note titled {title!r}"
    return str(row["id"])


# ── the pattern helper on its own ──────────────────────────────────────────


def test_fts_pattern_doubles_inner_quotes() -> None:
    """FTS5's own escaping rule; a lone `"` would otherwise open a phrase that
    never closes, and SQLite reports a syntax error rather than searching."""
    assert repo.fts_pattern('a"b') == '"a""b"'
    assert repo.fts_pattern("plain") == '"plain"'


def test_a_note_written_before_the_index_existed_is_still_searchable(
    connection: sqlite3.Connection, database_path: Path
) -> None:
    """A trigger only sees writes that happen after it is created.

    On a real upgrade the triggers land in the same migration as the table, so
    there is no window — but a *rebuild* has to be explicit, and the manifest's
    ``down_note`` tells the reader to run it. This pins that the recipe in the
    note actually works.
    """
    _write(connection, "升级前写的", body="独特的三字词组")
    connection.execute("DELETE FROM notes_fts")
    assert repo.search(connection, "独特的三") == []

    connection.execute(
        "INSERT INTO notes_fts (note_id, title, body) SELECT id, title, body FROM notes"
    )
    assert _titles(connection, "独特的三") == ["升级前写的"]


def test_as_of_does_not_leak_into_the_index(
    connection: sqlite3.Connection,
) -> None:
    """The cutoff date is a `date`, not text, and is not part of what a reader
    searches for. Asserted because the index is built from *selected columns* —
    a future `SELECT *` rebuild would start indexing it, and a search for a
    year would then return every note with a cutoff in that year.
    """
    draft = NoteDraft(
        title="有截止日的笔记",
        body="正文",
        as_of=date(2026, 8, 31),
    )
    with transaction(connection):
        note_id = repo.create(connection, draft, now=NOW).note.id
    assert repo.get_by_id(connection, note_id).as_of == date(2026, 8, 31)
    assert repo.search(connection, "2026-08-31") == []
