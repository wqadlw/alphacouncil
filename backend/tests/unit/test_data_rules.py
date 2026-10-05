"""Fixtures for the data checks ⭐ — ⭐ and the reason this file cannot be short.

## Why fixtures at all, when all three report zero on the reader's own rows

Measured 2026-10-04 against ``%LOCALAPPDATA%\\AlphaCouncil\\alphacouncil.db``: ⭐ ``decisions``
5 rows with 0 rows lacking counter-evidence, ⭐ ``audit_log`` **0 rows**. ⭐ A gate that
reports zero on real data is indistinguishable from a gate that is broken ⭐ and
`.ai/checks/data/README.md` rule 3 requires a fixture for exactly this reason.

# ⭐⭐ **And rule 1 says the opposite thing at the same time**: an empty database must pass.
# ⭐ Both hold only because they are about different databases ⭐ — ⭐ the gate reads the
reader's, ⭐ this file builds its own. ⭐ Confusing the two is how a data check becomes a
check that can never fail.

## ⭐⭐ And what building the fixtures measured about the schema itself

Writing rows the constraints accept ⭐ — ⭐ which is the only way a fixture can prove a check
bites ⭐ — ⭐ ran into three things the declarations never mention:

1. ⭐ **`decisions` has a composite foreign key** ``(market, code) -> instruments`` ⭐ and
   ``PRAGMA foreign_keys = 1`` ⭐ ⇒ ⭐ **D-01's subject is unreachable through the product's
   writer.** ⭐ `TestD01ReachesPastTheForeignKey` turns the pragma off to build one ⭐ ⭐
   which is the only way ⭐ ⭐ and ⭐ ⭐ which is precisely the restore-from-a-backup case
   D-01's docstring names.
2. ⭐ **`CHECK (length(trim(counter_evidence)) > 0)` ⭐ uses ``trim()`` ⭐ which strips
   spaces only.** ⭐ A tab, a newline and a full-width space are all accepted ⭐ ⭐ and all
   three are what D-07 is for ⭐ ⭐ and ``trim()`` calls every one of them content.
3. ⭐ ``audit_log.detail`` is capped at **500** by its own CHECK ⭐ ⇒ ⭐ D-22's band is
   201..500 ⭐ ⭐ and above that the rule is never consulted.

## How the rules are pointed at a database without being patched

``checks/data.configured_path`` resolves through ``Settings()``, ⭐ whose ``env_prefix`` is
``ALPHACOUNCIL_`` ⭐ ⇒ ⭐ **the environment variable ``ALPHACOUNCIL_DATABASE_PATH`` is the whole
seam.** ⭐ No monkeypatching of the module, ⭐ so these tests exercise the same resolution path
the gate uses ⭐ — ⭐ and `tests/conftest.py:64` already sets that variable for every other
test, ⭐ which is why ``configured_path()`` re-reads settings per call instead of caching one.

## ⭐⭐ The empty-database test does not expect three clean results, and that is the point

``test_all_three_are_clean_and_none_skip`` ⭐ ⭐ asserts that **D-01 reports its note on an empty
database.** ⭐ A first draft expected three clean results ⭐ ⭐ and pytest disagreed ⭐ ⭐ and
pytest was right: ⭐ D-01's finding is that the schema already prevents its subject ⭐ ⭐ and
that is true of an empty database ⭐ ⭐ and of a full one ⭐ ⭐ and of the reader's ⭐.

# ⭐⭐ **If D-01 went quiet when there was nothing wrong ⭐ then a green gate would mean 「there
are no dangling rows」 ⭐ ⭐ when the truth is 「the question could not arise」** ⭐ ⭐ and that
conflation is this round's entire subject.
"""

from __future__ import annotations

import ast
import re
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from checks.data_registry import DATA_MODULE_BY_ID, DATA_RULES
from checks.data_rules import audit_detail_length, counter_evidence_blank, dangling_target
from checks.framework import CheckResult, Issue
from checks.scan import ScanContext

from alphacouncil.core.config import get_settings as get_settings_call
from alphacouncil.storage import db, migrate

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
CTX = ScanContext(repo_root=REPO_ROOT)
MARKET, CODE = "sh", "600000"
STAMP = "2026-04-01T00:00:00.000Z"
MODULES = (dangling_target, counter_evidence_blank, audit_detail_length)
RULE_BY_ID = {rule.meta.check_id: rule for rule in DATA_RULES}


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def reader_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A migrated database at the shipped schema, pointed at by the environment.

    # ⭐ Built with the same two calls ``test_card.py:146-154`` uses ⭐ — ⭐ because a fixture
    that hand-wrote its own ``CREATE TABLE`` ⭐ ⭐ would test the fixture's schema ⭐ ⭐ rather
    than the product's ⭐ ⭐ and the whole point is that these rules read the product's.
    """
    path = tmp_path / "alphacouncil.db"
    connection = db.connect_for_migration(path)
    try:
        migrate.apply(connection, database_path=path)
    finally:
        connection.close()
    monkeypatch.setenv("ALPHACOUNCIL_DATABASE_PATH", str(path))
    # ⭐ `get_settings()` is `lru_cache(maxsize=1)` ⭐ and `tests/conftest.py:65`
    # clears it ⭐ ⭐ so every test that moves this variable must ⭐ ⭐ else the
    # application keeps the previous test's path ⭐ ⭐ and a test reads a database
    # nobody put anything in. ⭐⭐ Three `setenv` calls in this file did not, ⭐⭐ and
    # the symptom was a criterion from the reader's own rows appearing in an
    # assertion three files away ⭐⭐ `F-233`'s shape ⭐⭐ with live data.
    _clear_settings_cache()
    yield path


def write(path: Path, sql: str, params: tuple[object, ...] = ()) -> None:
    """Insert one row through a second, writable connection.

    # ⭐ ``mode=ro`` is the point ⭐ and a fixture that reached for the gate's own handle could
    not tell the read-only guarantee from a write.
    """
    con = db.connect(path)
    try:
        con.execute(sql, params)
        con.commit()
    finally:
        con.close()


def add_instrument(path: Path, market: str = MARKET, code: str = CODE) -> None:
    write(
        path,
        "insert into instruments (market, code, asset_type, created_at)"
        " values (?, ?, 'stock', ?)",
        (market, code, STAMP),
    )


def add_decision(
    path: Path,
    counter: str = "the case against: it may not reopen",
    row_id: str = "2026-04-02T00:00:00.000Z",
    market: str = MARKET,
    code: str = CODE,
) -> None:
    write(
        path,
        "insert into decisions (id, market, code, action, rationale, counter_evidence,"
        " kill_criteria) values (?, ?, ?, 'buy', 'because', ?, '[]')",
        (row_id, market, code, counter),
    )


def add_audit(path: Path, detail: str, row_id: str = "2026-04-03T00:00:00.000Z") -> None:
    write(
        path,
        "insert into audit_log (id, actor, action, detail)"
        " values (?, 'user', 'note.write', ?)",
        (row_id, detail),
    )


def bypass_foreign_keys(path: Path, market: str, code: str) -> None:
    """Write a decision whose instrument does not exist ⭐ — ⭐ the only way to reach D-01's
    subject at all. ⭐ Measured: with the pragma on, the insert raises ``FOREIGN KEY
    constraint failed`` ⭐ ⭐ and ``TestD01ReachesPastTheForeignKey`` pins that too ⭐ ⭐ so
    this helper cannot quietly stop being necessary."""
    con = sqlite3.connect(path)
    try:
        con.execute("pragma foreign_keys = off")
        con.execute(
            "insert into decisions (id, market, code, action, rationale,"
            " counter_evidence, kill_criteria) values (?, ?, ?, 'buy', 'because', 'against',"
            " '[]')",
            ("2026-04-04T00:00:00.000Z", market, code),
        )
        con.commit()
    finally:
        con.close()


#: ⭐ `S608` is suppressed below ⭐ — ⭐ every caller passes one of three literals written in
#: ⭐ this file ⭐ ⭐ and a table name cannot be a bound parameter in SQLite anyway ⭐ ⭐ so
#: ⭐ the alternative would be three near-identical helpers ⭐ ⭐ one per table ⭐ ⭐ each with
#: ⭐ its own connection and its own `finally`.
def _clear_settings_cache() -> None:
    """Forget the application's cached settings ⭐ — see the fixture for why."""
    from alphacouncil.core.config import get_settings

    get_settings.cache_clear()


def rows_of(path: Path, table: str) -> int:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        query = f"select count(*) from {table}"  # noqa: S608 - table is one of three literals here
        return int(con.execute(query).fetchone()[0])
    finally:
        con.close()


def issues_of(result: CheckResult) -> list[Issue]:
    return list(result.issues)


def codes_of(result: CheckResult) -> list[str]:
    return [issue.code for issue in issues_of(result)]


def severities(result: CheckResult) -> list[str]:
    return [issue.severity.value for issue in issues_of(result)]


def messages(result: CheckResult) -> list[str]:
    return [issue.message for issue in issues_of(result)]


# ------------------------------------------------------------------- rule 1: empty is ok


class TestAnEmptyDatabasePasses:
    """README rule 1 ⭐ — ⭐ 「空数据库必须通过」 ⭐ — ⭐ and the reason it needs a test: the
    gate reads the *reader's* database, ⭐ so nothing else here proves that a fresh install
    produces no *defects* on its first run."""

    def test_no_defect_and_nothing_skipped_on_a_freshly_migrated_database(
        self, reader_db: Path
    ) -> None:
        for module in MODULES:
            result = module.run(CTX)
            assert result.skipped is None, f"{module.META.check_id} skipped: {result.skipped}"
            defects = [
                issue
                for issue in issues_of(result)
                if issue.severity.value in ("error", "warning")
            ]
            assert defects == [], f"{module.META.check_id}: {[i.message for i in defects]}"

    def test_an_empty_database_still_gets_the_d01_note(self, reader_db: Path) -> None:
        """⭐⭐ **The point of D-01, and the reason this class does not expect silence.**
        # ⭐ An empty database says nothing about whether its *schema* prevents a dangling
        reference ⭐ ⭐ and the schema is what the note is about."""
        assert severities(dangling_target.run(CTX)) == ["info"]
        assert severities(counter_evidence_blank.run(CTX)) == []
        assert severities(audit_detail_length.run(CTX)) == []

    def test_the_database_really_is_empty(self, reader_db: Path) -> None:
        for table in ("decisions", "instruments", "audit_log"):
            assert rows_of(reader_db, table) == 0


# ------------------------------------------------- an absent database skips, never passes


class TestNoDatabaseIsASkip:
    """``dev.py:288-292`` ⭐ — 「a skipped gate is not a passing gate」."""

    def test_a_path_that_does_not_exist_yields_a_skip_and_no_findings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALPHACOUNCIL_DATABASE_PATH", str(tmp_path / "never-created.db"))
        _clear_settings_cache()
        for module in MODULES:
            result = module.run(CTX)
            assert result.skipped, f"{module.META.check_id} did not skip"
            assert result.issues == [], f"{module.META.check_id} reported while skipping"

    def test_the_skip_says_why(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALPHACOUNCIL_DATABASE_PATH", str(tmp_path / "never-created.db"))
        assert "no configured database" in (dangling_target.run(CTX).skipped or "")

    def test_a_file_that_is_not_a_database_is_a_skip_not_a_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ ⭐ **A path that exists and will not open is a fact to report, not a traceback.**
        # ⭐ SQLite defers reading the header ⭐ ⭐ so ``connect`` succeeds ⭐ ⭐ and the
        ``DatabaseError`` arrives on the first query ⭐ ⭐ outside ``readonly()``'s ``except``
        # ⭐ ⭐ and inside the runner's ``crashed`` list ⭐ ⭐ which the summary prints as a
        # ⭐ ⭐ different line from ``findings`` ⭐. ⭐ A reader skimming that summary sees a
        # ⭐ ⭐ number and no explanation."""
        junk = tmp_path / "not-a-database.db"
        junk.write_text("this is not a sqlite file", encoding="utf-8")
        monkeypatch.setenv("ALPHACOUNCIL_DATABASE_PATH", str(junk))
        _clear_settings_cache()
        result = counter_evidence_blank.run(CTX)
        assert result.skipped, "a file that cannot be opened gave a clean bill of health"
        assert "would not open" in (result.skipped or "")


# ------------------------------------------------------------------------- D-01


class TestD01ReachesPastTheForeignKey:
    """⭐ ⭐ D-01's subject is unreachable through the product's writer ⭐ ⭐ measured ⭐ ⭐ and
    the reason these fixtures turn the pragma off is written into the rule's docstring."""

    def test_the_schema_refuses_the_row_the_check_looks_for(self, reader_db: Path) -> None:
        """⭐ **The measurement, as an assertion.** ⭐ If this stops holding ⭐ ⭐ then
        ``bypass_foreign_keys`` is building something the product can no longer produce ⭐ ⭐
        and D-01's docstring is wrong a second time."""
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            add_decision(reader_db)

    def test_a_dangling_row_is_reported_when_one_exists(self, reader_db: Path) -> None:
        bypass_foreign_keys(reader_db, MARKET, CODE)
        result = dangling_target.run(CTX)
        # ⭐ Both facts ⭐ ⭐ because a reader who only saw the note would think the check
        # ⭐ found nothing.
        assert severities(result) == ["info", "error"], severities(result)
        assert f"{MARKET}/{CODE}" in messages(result)[1]

    def test_a_matching_pair_is_not_a_dangling_reference(self, reader_db: Path) -> None:
        """⭐ ⭐ **The guard on the pair.** ⭐ The first draft of this test added an
        # ⭐ instrument for ``sh/600000`` ⭐ ⭐ inserted a decision for ``sh/600001`` ⭐ ⭐ and
        # ⭐ expected no finding ⭐ ⭐ reasoning that 「the code differs so it is a different
        # ⭐ instrument and therefore not the one being referenced」 ⭐. ⭐ That is backwards ⭐ ⭐
        # ⭐ and the assertion failed ⭐ ⭐ which is the test having done its job: ⭐ a decision
        # ⭐ ⭐ naming ``sh/600001`` references the instrument ``sh/600001`` ⭐ ⭐ and if that
        # ⭐ ⭐ instrument does not exist the reference dangles ⭐ ⭐ whatever exists at
        # ⭐ ⭐ ``sh/600000`` ⭐. ⭐ **A pair join has no notion of a nearby match.**"""
        add_instrument(reader_db)
        add_decision(reader_db)
        assert severities(dangling_target.run(CTX)) == ["info"]

    def test_the_same_code_in_another_market_is_still_dangling(self, reader_db: Path) -> None:
        """⭐ ⭐ **And the case that proves the join uses both halves.** ⭐ ``sz/600000``
        # ⭐ ⭐ exists ⭐ ⭐ the decision names ``sh/600000`` ⭐ ⭐ and a check that joined on
        # ⭐ ⭐ ``code`` alone would call that clean ⭐ ⭐ because a row with that code exists ⭐ ⭐
        # ⭐ ⭐ which is exactly the bug a six-digit A-share code invites ⭐ ⭐ since ``600000``
        # ⭐ ⭐ in Shanghai and in Shenzhen are different companies."""
        add_instrument(reader_db, market="sz", code=CODE)
        bypass_foreign_keys(reader_db, MARKET, CODE)
        result = dangling_target.run(CTX)
        assert severities(result) == ["info", "error"], (
            "a code-only join would have called this clean"
        )

    def test_the_note_names_the_declared_finding(self, reader_db: Path) -> None:
        add_instrument(reader_db)
        add_decision(reader_db)
        message = messages(dangling_target.run(CTX))[0]
        assert "foreign key" in message
        assert "0 row(s) found now" in message, message
        assert "target_id" in message, "the declaration's wrong column name is not named"

    def test_a_missing_table_is_reported_rather_than_raised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Eleven of the twenty-four declared checks name a table or column that is not
        # ⭐ there ⭐ ⭐ and a rule that raised ``OperationalError`` on the first of them would
        # ⭐ tell the reader nothing about the rest."""
        bare = tmp_path / "bare.db"
        sqlite3.connect(bare).close()
        monkeypatch.setenv("ALPHACOUNCIL_DATABASE_PATH", str(bare))
        _clear_settings_cache()
        result = dangling_target.run(CTX)
        assert codes_of(result) == ["CHECK_DATA_INTEGRITY"]
        assert "cannot run" in messages(result)[0]


# ------------------------------------------------------------------------- D-07


class TestD07FindsWhatTrimCannot:
    """⭐ Each case below is accepted by ``decisions_counter_evidence_required`` ⭐ ⭐ so
    every one of them is a row the reader's own database can hold ⭐ ⭐ and ``trim()`` calls
    every one of them content. ⭐ ``TestTheSchemaAcceptsWhatD07Rejects`` pins the other half."""

    @pytest.mark.parametrize(
        "value",
        ["\t", "\n", " \t\n ", "\u3000", "\x0c"],
        ids=["tab", "newline", "mixed", "full-width-space", "form-feed"],
    )
    def test_whitespace_only_counter_evidence_is_reported(
        self, reader_db: Path, value: str
    ) -> None:
        add_instrument(reader_db)
        add_decision(reader_db, counter=value)
        assert counter_evidence_blank.run(CTX).issues != [], (
            f"{value!r} carries no readable content and was not reported"
        )

    def test_a_written_counter_evidence_is_clean(self, reader_db: Path) -> None:
        add_instrument(reader_db)
        add_decision(reader_db, counter="it may not reopen")
        assert counter_evidence_blank.run(CTX).issues == []

    def test_surrounding_whitespace_around_text_is_clean(self, reader_db: Path) -> None:
        """⭐ ⭐ **The guard on the guard.** ⭐ The predicate removes six characters before
        # ⭐ measuring the length ⭐ ⭐ and a predicate that removed *text* ⭐ ⭐ or one that
        # ⭐ compared against ``''`` after replacing ⭐ ⭐ would report every padded sentence as
        # ⭐ ⭐ blank ⭐ ⭐ which is a check that cries wolf and gets switched off."""
        add_instrument(reader_db)
        add_decision(reader_db, counter="  it may not reopen \t ")
        assert counter_evidence_blank.run(CTX).issues == []

    def test_the_predicate_is_not_trim(self) -> None:
        """⭐ ⭐ **The regression assertion for the reason this check exists.** ⭐ It reads the
        # ⭐ module's own SQL ⭐ ⭐ and it asserts the query does **not** contain ``trim(`` ⭐ ⭐
        # ⭐ because a future edit that helpfully \"simplified\" it back to ``trim()`` ⭐ ⭐
        # ⭐ looking exactly like the tidy version of the code ⭐ ⭐ would make this check unable
        # ⭐ ⭐ to fire ⭐ ⭐ and the tests above would still pass ⭐ ⭐ because their fixtures
        # ⭐ ⭐ would no longer be insertable."""
        sql = counter_evidence_blank.SQL
        assert "trim(" not in sql, "the predicate went back to trim(), which is the bug"
        assert "replace(" in sql
        assert len(counter_evidence_blank.BLANKS) == 6


class TestTheSchemaAcceptsWhatD07Rejects:
    """⭐ The other half of the same fact ⭐ ⭐ written as a test because a check whose
    # ⭐ fixtures the schema refuses is a check never observed to work."""

    @pytest.mark.parametrize(
        "value", ["\t", "\n", "\u3000"], ids=["tab", "newline", "full-width-space"]
    )
    def test_the_constraint_lets_these_through(self, reader_db: Path, value: str) -> None:
        add_instrument(reader_db)
        add_decision(reader_db, counter=value)  # ⭐ not raising is the assertion
        con = sqlite3.connect(f"file:{reader_db}?mode=ro", uri=True)
        try:
            stored = con.execute(
                "select counter_evidence from decisions order by id desc limit 1"
            ).fetchone()[0]
        finally:
            con.close()
        assert stored == value

    def test_the_constraint_does_still_refuse_an_empty_one(self, reader_db: Path) -> None:
        add_instrument(reader_db)
        with pytest.raises(sqlite3.IntegrityError, match="counter_evidence"):
            add_decision(reader_db, counter="")

    def test_the_constraint_uses_trim(self, reader_db: Path) -> None:
        """⭐ ⭐ The hole, named in a place that will fail if a migration fixes it. ⭐ When
        # ⭐ somebody closes it ⭐ ⭐ this test goes red ⭐ ⭐ and the red is the good news ⭐ ⭐
        # ⭐ and D-07's docstring gets a second paragraph saying so."""
        con = sqlite3.connect(f"file:{reader_db}?mode=ro", uri=True)
        try:
            sql = con.execute(
                "select sql from sqlite_master where name = 'decisions'"
            ).fetchone()[0]
        finally:
            con.close()
        assert "length(trim(counter_evidence)) > 0" in sql, (
            "the constraint no longer uses trim() ⭐ — ⭐ if it now covers whitespace "
            "completely, D-07 has nothing left to find and this file's docstring is stale"
        )


# ------------------------------------------------------------------------- D-22


class TestD22AuditDetailLength:
    def test_a_row_at_the_limit_is_clean(self, reader_db: Path) -> None:
        add_audit(reader_db, "x" * audit_detail_length.DETAIL_LIMIT)
        assert audit_detail_length.run(CTX).issues == []

    def test_a_row_past_the_limit_is_reported(self, reader_db: Path) -> None:
        add_audit(reader_db, "x" * (audit_detail_length.DETAIL_LIMIT + 1))
        result = audit_detail_length.run(CTX)
        assert codes_of(result) == ["CHECK_DATA_INTEGRITY"]
        assert str(audit_detail_length.DETAIL_LIMIT) in messages(result)[0]

    def test_the_limit_sits_below_the_schema_ceiling(self, reader_db: Path) -> None:
        """⭐ ⭐ **Otherwise D-22 could never fire.** ⭐ ``audit_log`` caps ``detail`` at 500
        # ⭐ ⭐ and a threshold at or above that is dead code ⭐ ⭐ and the only thing standing
        # ⭐ ⭐ between a rule and dead code is somebody comparing two numbers."""
        con = sqlite3.connect(f"file:{reader_db}?mode=ro", uri=True)
        try:
            sql = con.execute(
                "select sql from sqlite_master where name = 'audit_log'"
            ).fetchone()[0]
        finally:
            con.close()
        assert "length(detail) <= 500" in sql
        assert audit_detail_length.DETAIL_LIMIT < 500


# ----------------------------------------------------- the registry and the declarations


class TestTheRegistryIsTheOneTheRunnerUses:
    def test_every_module_meta_is_the_meta_bound_in_the_registry(self) -> None:
        """⭐ ``registry.py:14-18`` binds each rule's ``META`` explicitly ⭐ 「so a rule
        # ⭐ accidentally left out shows up as a diff rather than as silence」 ⭐ ⭐ and nothing
        # ⭐ checked that on the data side ⭐ ⭐ which is how twelve entries came to sit in
        # ⭐ ``APPEND_ONLY_TABLES`` for a table no migration creates."""
        for rule in DATA_RULES:
            module = sys.modules[DATA_MODULE_BY_ID[rule.meta.check_id]]
            assert module is not None, DATA_MODULE_BY_ID[rule.meta.check_id]
            assert module.META is rule.meta, rule.meta.check_id

    def test_the_derived_module_path_is_the_rule_s_own_module(self) -> None:
        """⭐ ⭐ ``DATA_MODULE_BY_ID`` builds each path from ``slug.replace('-', '_')`` ⭐ ⭐
        which is a convention nobody checks ⭐ ⭐ and a rule whose slug stops matching its
        # ⭐ filename resolves to ``None`` ⭐ ⭐ and ``None.META`` raises **inside a test**
        # ⭐ ⭐ rather than at start-up ⭐ ⭐ where the runner would say which id is broken."""
        for check_id, dotted in DATA_MODULE_BY_ID.items():
            module = sys.modules[dotted]
            assert Path(module.__file__ or "").stem == RULE_BY_ID[check_id].meta.slug.replace(
                "-", "_"
            ), check_id

    def test_every_module_in_the_package_is_registered(self) -> None:
        """⭐⭐ **Mutation M6, and the mirror of the test above.**

        # ⭐ Removing ``D-07`` from ``DATA_RULES`` ⭐ ⭐ deleting nothing ⭐ ⭐ left **259 tests
        green** ⭐ ⭐ and ``checks/data_registry.py``'s own docstring claims this registry
        # ⭐ ⭐ exists precisely so that 「a rule accidentally left out shows up as a diff
        # ⭐ ⭐ rather than as silence」 ⭐⭐. ⭐⭐ It did not ⭐⭐ and the five other mutations
        # ⭐ ⭐ going red is exactly why the sixth one was noticed: ⭐⭐ a run where everything
        # ⭐ ⭐ bites makes the one that does not stand out.

        # ⭐ The direction matters ⭐ ⭐ — ⭐ the other test walks the registry ⭐ ⭐ this one walks
        # ⭐ ⭐ the **package** ⭐ ⭐ so the pair covers a rule registered twice ⭐ ⭐ a rule
        # ⭐ ⭐ registered under the wrong id ⭐ ⭐ and a rule present but unregistered.
        """
        package = Path(sys.modules[DATA_MODULE_BY_ID["D-01"]].__file__ or "").parent
        on_disk = {p.stem for p in package.glob("*.py") if p.stem != "__init__"}
        registered = {dotted.rsplit(".", 1)[1] for dotted in DATA_MODULE_BY_ID.values()}
        assert on_disk == registered, (
            f"modules on disk but not in the registry: {sorted(on_disk - registered)} ⭐ — ⭐ a "
            f"rule that exists and never runs ⭐ ⭐ and registered but absent: "
            f"{sorted(registered - on_disk)}"
        )

    def test_the_two_resolvers_cannot_disagree(self) -> None:
        """⭐⭐ **The fork, asserted shut.**

        # ⭐⭐ Measured 2026-10-05 ⭐ — ⭐ `get_settings()` is `lru_cache(maxsize=1)` and a fresh
        # ⭐⭐ `Settings()` reads the environment ⭐ ⭐ so after a test moves
        # ⭐⭐ `ALPHACOUNCIL_DATABASE_PATH` without clearing it ⭐ ⭐ the application and
        # ⭐⭐ everything else name **different files**. ⭐⭐ That happened tonight ⭐ ⭐ and it put
        # ⭐⭐ a criterion out of the reader's real database inside an assertion three files away.

        # ⭐⇒ `checks/data.py` now resolves through `get_settings()` ⭐ ⭐ so there is one answer
        # ⭐⭐ per process ⭐ ⭐ and this test exists so the next person adding a *second*
        # ⭐⭐ resolver meets a red test ⭐ ⭐ rather than a mystery failure three rounds from now
        # ⭐⭐ ⭐ ⭐ which is `F-239`'s shape again ⭐ ⭐ ⭐ except this time it gets caught.
        """
        from alphacouncil.core.config import Settings

        _clear_settings_cache()
        assert Path(get_settings_call().database_path) == Path(Settings().database_path)

        monkey = pytest.MonkeyPatch()
        try:
            elsewhere = REPO_ROOT / "nowhere" / "elsewhere.db"
            monkey.setenv("ALPHACOUNCIL_DATABASE_PATH", str(elsewhere))
            # ⭐ Without the clear, these differ ⭐ — ⭐ and that is the whole test.
            assert Path(get_settings_call().database_path) != Path(
                Settings().database_path
            ), (
                "the cache no longer holds ⭐ — ⭐ if `get_settings()` stopped caching, ⭐ "
                "conftest.py's `cache_clear()` calls become harmless noise ⭐ ⭐ and this "
                "test's premise has expired ⭐ ⭐ ⭐ which is worth knowing, ⭐ ⭐ not worth "
                "⭐⭐ silently keeping"
            )
        finally:
            monkey.undo()
        _clear_settings_cache()

    def test_the_ids_are_the_ones_the_declaration_lists(self) -> None:
        text = (REPO_ROOT / ".ai" / "checks" / "data" / "README.md").read_text(
            encoding="utf-8"
        )
        for rule in DATA_RULES:
            assert re.search(rf"\|\s*{rule.meta.check_id}\s*\|", text), (
                f"{rule.meta.check_id} runs but the declaration does not list it ⭐ — "
                "⭐ a gate that checks something nobody wrote down"
            )

    def test_no_rule_opens_its_own_connection(self) -> None:
        """⭐ ⭐ The first batch is read-only ⭐ ⭐ and that is a **connection string** ⭐ ⭐
        not a convention ⭐ ⭐ because a rule that opened its own handle could write. ⭐ Read
        # ⭐ ⭐ through ``ast`` ⭐ ⭐ not by grepping the text ⭐ ⭐ because two of these modules
        # ⭐ ⭐ mention ``sqlite3.connect`` **in their docstrings** ⭐ ⭐ to explain exactly
        # ⭐ ⭐ why they do not call it ⭐ ⭐ and a text search cannot tell a call from a
        # ⭐ ⭐ mention."""
        for rule in DATA_RULES:
            module = sys.modules[DATA_MODULE_BY_ID[rule.meta.check_id]]
            source = Path(module.__file__ or "").read_text(encoding="utf-8")
            opened = [
                node.func.attr
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "connect"
            ]
            assert opened == [], (
                f"{rule.meta.check_id} calls {opened} ⭐ — ⭐ read-only lives in checks/data.py"
            )
            assert "data.readonly()" in source, rule.meta.check_id

    def test_the_conditions_the_rules_depend_on_are_real(self) -> None:
        """⭐ ⭐ **The measurement that started this round, as a test.** ⭐ 2026-10-04 a probe
        # ⭐ found that eleven of the twenty-four declared checks name a column that exists
        # ⭐ nowhere in the schema ⭐ ⭐ and two name a table that does not exist ⭐ ⭐ so 「24
        # ⭐ checks specified, 0 written」 was false in a stronger way than it looked. ⭐ A probe
        # ⭐ is not a permanent asset; ⭐ this is.

        # ⭐ Read from the **migrations** ⭐ ⭐ not from a live database ⭐ ⭐ because the live
        # ⭐ database's path is an environment variable ⭐ ⭐ and in a unit test that variable
        # ⭐ ⭐ points at a file that may not exist ⭐ ⭐ which is how the first draft of this
        # ⭐ ⭐ test failed with 「unable to open database file」 ⭐ ⭐ a failure about its own
        # ⭐ ⭐ plumbing rather than about the thing it asserts.
        """
        columns = _columns_from_migrations()
        broken = [
            f"{check_id} ({name}): `{table}.{column}`"
            for check_id, (name, needs) in DECLARED_PRECONDITIONS.items()
            for table, column in needs
            if column not in columns.get(table, set())
        ]
        assert broken == [], (
            "these declared checks cannot be written as declared ⭐ — ⭐ which is a defect in "
            f"the declaration, not in the code: {broken}"
        )


def _columns_from_migrations() -> dict[str, set[str]]:
    """Every column every migration creates ⭐ — ⭐ the rule's own ``_CREATE_TABLE`` parser ⭐
    # ⭐ so this cannot drift from what ``S-04`` sees."""
    from checks.rules.check_append_only_triggers import _CREATE_TABLE, strip_sql_comments
    from checks.scan import ScanContext as Ctx

    ctx = Ctx(repo_root=REPO_ROOT)
    files = ctx.files_with_suffix(ctx.backend, ".sql")
    out: dict[str, set[str]] = {}
    for path in files:
        text = strip_sql_comments(ctx.text(path))
        for match in _CREATE_TABLE.finditer(text):
            table = match.group("name").lower()
            block = text[match.start() : text.find(";", match.start()) + 1]
            names = set(re.findall(r"^\s{4,}([a-z_]+)\s+[A-Z]", block, re.M))
            out.setdefault(table, set()).update(names)
    return out


#: ⭐ Every declared check whose precondition the schema can answer for ⭐ — ⭐ read as
#: ``(table, column)`` ⭐ ⭐ because the README's prose says 「`decisions.target_id`」 ⭐ ⭐
#: which is a column that does not exist ⭐ ⭐ and that mistake is the finding.
DECLARED_PRECONDITIONS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "D-01": ("悬空引用", (("decisions", "market"), ("instruments", "code"))),
    "D-07": ("缺反面证据", (("decisions", "counter_evidence"),)),
    "D-22": ("审计日志含敏感内容", (("audit_log", "detail"),)),
}
