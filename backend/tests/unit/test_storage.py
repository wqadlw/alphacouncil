"""The schema's three declarations must agree with the schema that ships.

One schema is described in three hand-written places:

* ``migrations/0001_initial.up.sql`` — the implementation.
* ``migrations/manifest.json`` — which migrations run, and in what order.
* ``constraints.json`` — which CHECK constraints exist, in which of the
  constitutional categories.

Until this module existed, nothing compared them. That is not a hypothetical
gap: the ``$comment`` at the top of **both** JSON files already claimed that
``tests/unit/test_storage.py`` cross-checks them, and no such file existed — so
the claim itself was the only thing holding the declarations together. This
module is that file. (Found 2026-09-26 while writing the tests the comments
promised.)

Two decisions worth stating:

**The schema is read from a real database, not from the SQL text.** The checks
build the schema in an in-memory SQLite database using the real migration SQL
and read ``sqlite_master``, which stores the original ``CREATE TABLE`` text. So
the constraint names come from a schema that has actually been created — which
also proves the migration SQL parses.

**Categories are checked against their shape, not only their name.** Set
equality catches a constraint that is missing from the ledger; it does not catch
a constraint filed under the wrong category, because nothing else in the
codebase reads the category. The shape markers below are taken from the
constitution's own examples, so a category that drifts from its definition
fails here instead of silently becoming a label nobody can act on.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from checks.rules.check_append_only_triggers import APPEND_ONLY_TABLES

from alphacouncil.storage import db, migrate

pytestmark = pytest.mark.unit

#: The ledger sits next to the storage package's modules, not beside the
#: ``.sql`` files — ``0001_initial.up.sql`` used to say "同目录", which was
#: simply wrong. Fixed 2026-09-26.
LEDGER_PATH = Path(migrate.__file__).with_name("constraints.json")
MANIFEST_PATH = migrate.MIGRATIONS_DIR / migrate.MANIFEST_NAME

#: Marker substrings per category, derived from the constitution's examples
#: (§5.4.2 for the first five, §5.4.3 for ``required``).
#:
#: Each category maps to a tuple of **alternatives**; an alternative is a tuple
#: of substrings that must all appear. ``identity`` has three because the
#: constitution names it "标识非空" and describes the technique as "用 trim 防纯空白"
#: — but the schema also uses it for canonical forms, and a timestamp round-trip
#: (``strftime``) or a fixed-width digit code (``GLOB``) is the same kind of
#: statement about what the value *is*.
#:
#: The third ``identity`` alternative carries ``IS NULL`` deliberately, because
#: that is what separates it from ``required``::
#:
#:     identity  x IS NULL OR length(trim(x)) > 0   -- optional, but not blank
#:     required  length(trim(x)) > 0                -- mandatory, so no NULL case
#:
#: Both directions of that confusion are caught: ``required`` forbids any NULL
#: test, and ``identity`` will not accept a bare ``length(trim(x)) > 0``.
CATEGORY_MARKERS: dict[str, tuple[tuple[str, ...], ...]] = {
    "identity": (("strftime",), ("GLOB",), ("trim(", "IS NULL")),
    "enum": (("IN (",),),
    "json": (("json_valid",),),
    "length": (("length(", "<="),),
    # Either polarity: ``a IS NULL OR b IS NOT NULL`` states the rule forwards,
    # ``(a IS NULL) = (b IS NULL)`` states it as "both or neither" so that it
    # also refuses the reverse. Note "IS NOT NULL" does not contain "IS NULL" —
    # the two are separate substrings, which is why both appear here.
    "conditional_required": (("IS NOT NULL",), ("IS NULL",)),
    "required": (("trim(",),),
}

#: ``required`` is the one category that must *not* mention NULL: it says the
#: field is mandatory outright (constitution §5.4.3), not mandatory under a
#: condition.
CATEGORY_FORBIDDEN: dict[str, tuple[str, ...]] = {
    "required": ("IS NULL", "IS NOT NULL"),
}


# ---------------------------------------------------------------------------
# Reading the two sides
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SchemaObject:
    """One object as the database remembers creating it."""

    kind: str
    name: str
    sql: str


def _live_schema() -> tuple[SchemaObject, ...]:
    """Create the real schema in memory and return what ``sqlite_master`` holds.

    Applies the **whole shipped chain**, not one migration: since 0002 the
    schema's own tables span multiple `.sql` files, and "the schema" means the
    state a fresh install ends up in. The first version of this helper read
    only `[1]` — accurate while there was one migration, and a trap the moment
    a second landed: the ledger would describe a table the comparison could
    never see, and every ledger↔schema assertion would fail in both directions.
    """
    script = "\n".join(item.up.read_text(encoding="utf-8") for item in migrate.load_migrations())
    connection = sqlite3.connect(":memory:")
    try:
        for statement in migrate.split_statements(script):
            connection.execute(statement)
        rows = connection.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL"
        ).fetchall()
    finally:
        connection.close()
    return tuple(SchemaObject(str(kind), str(name), str(sql)) for kind, name, sql in rows)


def _table_ddl() -> dict[str, str]:
    """``{table name: CREATE TABLE text}`` for the schema's own tables."""
    return {
        item.name: item.sql
        for item in _live_schema()
        if item.kind == "table" and not item.name.startswith("sqlite_")
    }


def _trigger_names() -> frozenset[str]:
    """Every trigger the schema creates, lower-cased."""
    return frozenset(item.name.lower() for item in _live_schema() if item.kind == "trigger")


def _constraint_bodies(table_ddl: str) -> dict[str, str]:
    """``{constraint name: CHECK body}`` for one table.

    The body is found by counting parentheses, not by a lazy regex: the bodies
    nest (``((a) = (b))``), so a pattern written to stop at the first ``))``
    silently spans two constraints and reports their union. That is the same
    failure mode ``tests/unit/test_watchlist.py`` documents for its own reader.
    """
    bodies: dict[str, str] = {}
    for match in re.finditer(r"CONSTRAINT\s+(\w+)\s+CHECK\s*\(", table_ddl):
        cursor = match.end()
        depth = 1
        end = cursor
        while depth:
            depth += (table_ddl[end] == "(") - (table_ddl[end] == ")")
            end += 1
        bodies[match.group(1)] = table_ddl[cursor : end - 1]
    return bodies


def _ledger() -> dict[str, Any]:
    """The parsed ``constraints.json``."""
    loaded: dict[str, Any] = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return loaded


def _ledger_entries() -> dict[str, dict[str, Any]]:
    """``{table: entry}`` where an entry holds ``append_only`` and ``constraints``."""
    tables: dict[str, dict[str, Any]] = _ledger()["tables"]
    return tables


def _ledger_constraints() -> dict[str, dict[str, str]]:
    """``{table: {constraint name: category}}`` from the ledger."""
    return {table: entry["constraints"] for table, entry in _ledger_entries().items()}


def _declared_categories() -> tuple[str, ...]:
    categories: list[str] = _ledger()["categories"]
    return tuple(categories)


# ---------------------------------------------------------------------------
# manifest.json <-> the directory
# ---------------------------------------------------------------------------


class TestTheManifestMatchesTheDirectory:
    """A migration that is not registered is a migration that never runs."""

    def test_every_registered_file_exists(self) -> None:
        for item in migrate.load_migrations():
            assert item.up.is_file(), f"{item.up.name} is listed but missing"
            assert item.down.is_file(), f"{item.down.name} is listed but missing"

    def test_every_sql_file_is_registered(self) -> None:
        """The reverse direction. Without it, a new ``.sql`` file is dead weight.

        This is the failure the manifest exists to prevent, and it is silent by
        nature: an unregistered migration produces no error, no log line and no
        failing test — the schema simply never gains the change.
        """
        registered = set()
        for item in migrate.load_migrations():
            registered.add(item.up.name)
            registered.add(item.down.name)
        on_disk = {path.name for path in migrate.MIGRATIONS_DIR.glob("*.sql")}
        assert on_disk == registered, (
            f"unregistered: {sorted(on_disk - registered)}; "
            f"listed but absent: {sorted(registered - on_disk)}"
        )

    def test_each_version_has_one_up_and_one_down(self) -> None:
        for item in migrate.load_migrations():
            assert item.up.name == f"{item.version:04d}_{item.name}.up.sql"
            assert item.down.name == f"{item.version:04d}_{item.name}.down.sql"

    def test_versions_start_at_one_and_are_contiguous(self) -> None:
        versions = [item.version for item in migrate.load_migrations()]
        assert versions == list(range(1, len(versions) + 1))

    def test_a_gap_is_refused_rather_than_tolerated(self, tmp_path: Path) -> None:
        """The contiguity rule only counts if it can fail."""
        _materialise(tmp_path, [(1, "first"), (3, "third")])
        with pytest.raises(migrate.MigrationError, match="contiguous"):
            migrate.load_migrations(tmp_path)

    def test_a_listed_file_that_is_absent_is_refused(self, tmp_path: Path) -> None:
        """No files written — the manifest promises what the directory lacks."""
        _write_manifest(tmp_path, [(1, "first")])
        with pytest.raises(migrate.MigrationError, match="does not exist"):
            migrate.load_migrations(tmp_path)

    def test_a_missing_manifest_is_refused(self, tmp_path: Path) -> None:
        """An empty directory must not be read as "no migrations, nothing to do"."""
        with pytest.raises(migrate.MigrationError, match="manifest not found"):
            migrate.load_migrations(tmp_path)

    def test_a_version_that_cannot_be_stored_is_refused(self, tmp_path: Path) -> None:
        """``PRAGMA user_version`` is 32-bit and wraps silently: setting it to
        ``2**31`` reads back ``0`` (verified 2026-09-26). A manifest typo would
        therefore create a database that appears never to have upgraded, for
        ever, with nothing logged — so the range is checked when the manifest is
        read, not when it is applied."""
        _materialise(tmp_path, [(migrate.MAX_VERSION + 1, "too_big")])
        with pytest.raises(migrate.MigrationError, match="outside"):
            migrate.load_migrations(tmp_path)

    def test_the_largest_storable_version_is_still_accepted(self, tmp_path: Path) -> None:
        """The guard must not be so eager that it refuses a legal value."""
        _materialise(tmp_path, [(migrate.MAX_VERSION, "biggest")])
        assert [item.version for item in migrate.load_migrations(tmp_path)] == [migrate.MAX_VERSION]


class TestSplittingAScript:
    """``split_statements`` reads files it did not write, so it must fail loudly."""

    def test_a_truncated_script_is_refused(self) -> None:
        with pytest.raises(migrate.MigrationError, match="incomplete statement"):
            migrate.split_statements("CREATE TABLE t (\n    x TEXT\n")

    def test_the_error_names_what_was_left_over(self) -> None:
        with pytest.raises(migrate.MigrationError, match="CREATE TABLE"):
            migrate.split_statements("CREATE TABLE half_written (")

    def test_trigger_bodies_survive_intact(self) -> None:
        """The reason ``executescript`` and ``split(";")`` are both wrong here."""
        script = (
            "CREATE TRIGGER t_no_update BEFORE UPDATE ON t\n"
            "BEGIN SELECT RAISE(ABORT, 'a;b'); END;\n"
            "SELECT 1;\n"
        )
        statements = migrate.split_statements(script)
        assert len(statements) == 2
        assert statements[0].endswith("END;")
        assert "'a;b'" in statements[0]

    def test_blank_lines_between_statements_are_not_statements(self) -> None:
        assert migrate.split_statements("\nSELECT 1;\n\n\nSELECT 2;\n") == [
            "SELECT 1;",
            "SELECT 2;",
        ]

    def test_the_shipped_migration_splits_into_every_statement(self) -> None:
        """A count, not a spot check: if the reader silently swallowed a
        statement the schema would be missing an object and nothing else would
        notice until a trigger did not fire."""
        sql = _initial_up_sql()
        statements = migrate.split_statements(sql)
        assert len(statements) == 4 + 1 + 3 + 6  # tables + view + indexes + triggers
        assert all(statement.endswith(";") for statement in statements)


def _initial_up_sql() -> str:
    """The shipped initial migration's text."""
    return {item.version: item for item in migrate.load_migrations()}[1].up.read_text(
        encoding="utf-8"
    )


def _write_manifest(directory: Path, entries: list[tuple[int, str]]) -> None:
    """Write a manifest naming ``entries`` as ``(version, name)`` pairs.

    Writes only the manifest — a test that needs the ``.sql`` files too calls
    :func:`_materialise`, and a test that deliberately omits them calls this.
    """
    payload = {
        "migrations": [
            {
                "version": version,
                "name": name,
                "up": f"{version:04d}_{name}.up.sql",
                "down": f"{version:04d}_{name}.down.sql",
            }
            for version, name in entries
        ]
    }
    (directory / migrate.MANIFEST_NAME).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _materialise(directory: Path, entries: list[tuple[int, str]]) -> None:
    """Write a manifest *and* the empty ``.sql`` files it names."""
    _write_manifest(directory, entries)
    for version, name in entries:
        for direction in ("up", "down"):
            (directory / f"{version:04d}_{name}.{direction}.sql").write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# constraints.json <-> the live schema
# ---------------------------------------------------------------------------


class TestTheLedgerMatchesTheSchema:
    """Both directions. One direction alone lets a constraint go unregistered."""

    def test_every_ledger_table_exists(self) -> None:
        assert set(_ledger_constraints()) <= set(_table_ddl())

    def test_every_table_has_a_ledger_entry(self) -> None:
        """A table with no entry is a table whose constraints nobody declared."""
        assert set(_table_ddl()) == set(_ledger_constraints())

    def test_every_ledger_constraint_exists_in_the_schema(self) -> None:
        """Direction one: the ledger may not promise what the schema lacks."""
        live = {table: set(_constraint_bodies(ddl)) for table, ddl in _table_ddl().items()}
        for table, constraints in _ledger_constraints().items():
            missing = set(constraints) - live[table]
            assert not missing, f"{table} is missing from the schema: {sorted(missing)}"

    def test_every_schema_constraint_is_registered(self) -> None:
        """Direction two: the schema may not grow a constraint nobody declared.

        This is the direction that catches the real accident — a constraint
        added to the migration during a bug fix, and the ledger never updated,
        so the next reader believes the ledger is the complete list.
        """
        live = {table: set(_constraint_bodies(ddl)) for table, ddl in _table_ddl().items()}
        for table, constraints in _ledger_constraints().items():
            undeclared = live[table] - set(constraints)
            assert not undeclared, f"{table} has undeclared constraints: {sorted(undeclared)}"

    def test_the_schema_really_has_the_constraints_it_claims(self) -> None:
        """Guards the reader: if the extractor found nothing, the two set
        comparisons above would agree on two empty sets and pass."""
        bodies = {name for ddl in _table_ddl().values() for name in _constraint_bodies(ddl)}
        # 4 tables from 0001 + market_cache from 0002 + cards, card_symbols from 0003
        # = 28 + 14 + 3 = 45 — the number is written dead on purpose
        # (constitution 8.3): a new migration changes it, and that is exactly
        # when a human should look.
        assert len(bodies) == 45, f"expected 45 named constraints, found {len(bodies)}"

    def test_every_constraint_uses_a_declared_category(self) -> None:
        for table, constraints in _ledger_constraints().items():
            for name, category in constraints.items():
                assert category in _declared_categories(), f"{table}.{name} -> {category!r}"

    def test_the_declared_categories_are_the_marker_categories(self) -> None:
        """Every declared category must have a shape, or it is only a label."""
        assert set(_declared_categories()) == set(CATEGORY_MARKERS)

    def test_every_declared_category_is_actually_used(self) -> None:
        used = {c for table in _ledger_constraints().values() for c in table.values()}
        assert used == set(_declared_categories())


class TestEachCategoryMatchesItsShape:
    """A constraint filed under the wrong category is invisible to set equality."""

    @pytest.mark.parametrize("table", sorted(_ledger_constraints()))
    def test_constraints_have_the_shape_their_category_claims(self, table: str) -> None:
        bodies = _constraint_bodies(_table_ddl()[table])
        for name, category in _ledger_constraints()[table].items():
            body = bodies[name]
            alternatives = CATEGORY_MARKERS[category]
            matched = any(all(marker in body for marker in alt) for alt in alternatives)
            assert matched, (
                f"{table}.{name} is filed as {category!r} but its body matches none of "
                f"{alternatives}: {body}"
            )
            for forbidden in CATEGORY_FORBIDDEN.get(category, ()):
                assert forbidden not in body, (
                    f"{table}.{name} is filed as {category!r} but its body contains "
                    f"{forbidden!r}: {body}"
                )

    def test_the_marker_table_covers_every_category(self) -> None:
        """A category added to the ledger without a marker would never be checked."""
        assert set(CATEGORY_MARKERS) == set(_declared_categories())


# ---------------------------------------------------------------------------
# append-only: the ledger, the triggers, and the static rule
# ---------------------------------------------------------------------------


class TestAppendOnlyIsDeclaredOnceAndEnforcedOnce:
    """Three places know a table is append-only. They must name the same tables."""

    def test_every_append_only_table_has_both_triggers(self) -> None:
        triggers = _trigger_names()
        declared = [t for t, entry in _ledger_entries().items() if _is_append_only(entry)]
        assert declared, "the ledger marks nothing append-only — the check proves nothing"
        for table in declared:
            assert f"{table}_no_update" in triggers, f"{table} can be UPDATEd"
            assert f"{table}_no_delete" in triggers, f"{table} can be DELETEd"

    def test_every_table_with_triggers_is_declared_append_only(self) -> None:
        """The reverse: a trigger on an undeclared table means the ledger is stale."""
        triggers = _trigger_names()
        guarded = {name.removesuffix("_no_update").removesuffix("_no_delete") for name in triggers}
        declared = {t for t, entry in _ledger_entries().items() if _is_append_only(entry)}
        assert guarded == declared, f"triggers on undeclared tables: {sorted(guarded - declared)}"

    def test_the_ledger_agrees_with_the_static_rule(self) -> None:
        """S-04 keeps its own list of append-only tables. Two lists, one truth.

        Only the tables that exist are compared: ``reviews`` and
        ``thesis_versions`` are required by constitution 5.4.1 but arrive with
        J3 and J2, so the rule names them before the schema does.
        """
        existing = set(_table_ddl()) & APPEND_ONLY_TABLES
        declared = {t for t, entry in _ledger_entries().items() if _is_append_only(entry)}
        assert declared == existing

    def test_the_static_rule_still_expects_the_tables_that_do_not_exist_yet(self) -> None:
        """Documents the gap rather than letting it look like agreement."""
        missing = APPEND_ONLY_TABLES - set(_table_ddl())
        assert missing == {"reviews", "thesis_versions"}


def _is_append_only(entry: dict[str, Any]) -> bool:
    """Whether a ledger table entry is flagged append-only."""
    return bool(entry["append_only"])


# ---------------------------------------------------------------------------
# The connection opener
# ---------------------------------------------------------------------------


class TestTheConnectionOpener:
    """``connect`` accepts a ``Path`` or a ``str``, and the difference matters."""

    def test_a_path_gets_its_parent_directory_created(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "deeper" / "alphacouncil.db"
        connection = db.connect(nested)
        try:
            assert nested.parent.is_dir()
        finally:
            connection.close()

    def test_a_string_is_passed_through_to_sqlite(self) -> None:
        """``":memory:"`` is a str, not a path. Creating a *directory* named
        ``:memory:`` before opening it would silently turn a throwaway database
        into a file on disk."""
        connection = db.connect(":memory:")
        try:
            connection.execute("CREATE TABLE probe (x TEXT)")
            assert connection.execute("SELECT count(*) FROM probe").fetchone()[0] == 0
        finally:
            connection.close()
        assert not Path(":memory:").exists()


class TestTheConnectionSurvivesAnotherThread:
    """The regression guard for a defect that reached a user's screen.

    On 2026-09-26, ``GET /api/v1/instruments/{market}/{code}/quote`` answered
    **500 roughly half the time**, with

        sqlite3.ProgrammingError: SQLite objects created in a thread can only
        be used in that same thread.

    thrown from ``connection.close()`` in ``api/deps.py``. FastAPI runs a sync
    generator dependency through ``contextmanager_in_threadpool``, and
    ``__enter__`` and ``__exit__`` are not guaranteed to land on the same
    worker — so the connection was opened on one thread and closed on another.

    **Why these tests exist when the API tests did not catch it.** ``TestClient``
    runs the whole request on one thread, so the cross-thread path is never
    taken. No amount of API-level testing would have found this; it took a real
    browser against a real uvicorn. The behaviour is therefore pinned at the
    level where it actually happens — the connection itself — rather than
    somewhere it would be inferred.
    """

    def test_a_connection_opened_here_can_be_used_and_closed_elsewhere(
        self, tmp_path: Path
    ) -> None:
        connection = db.connect(tmp_path / "cross-thread.db")
        connection.execute("CREATE TABLE probe (value INTEGER)")
        connection.execute("INSERT INTO probe VALUES (7)")

        failures: list[BaseException] = []

        def other_thread() -> None:
            try:
                row = connection.execute("SELECT value FROM probe").fetchone()
                assert row["value"] == 7
                connection.close()
            except BaseException as exc:
                # Collected and re-raised on the test thread by the assertion
                # below. Catching it here rather than letting it escape is what
                # makes the failure *assertable*: an exception that dies inside
                # a thread prints a traceback and leaves the test green.
                failures.append(exc)

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()

        assert failures == [], (
            "a connection must survive being handled by a second thread — "
            "FastAPI's threadpool does exactly this, and refusing it returns 500"
        )

    def test_a_transaction_works_across_the_handover(self, tmp_path: Path) -> None:
        """Not just ``close()``. A write path touches the connection more, and
        the failing request was a read-only endpoint that still had to resolve
        the instrument first."""
        connection = db.connect(tmp_path / "cross-thread-tx.db")
        connection.execute("CREATE TABLE probe (value INTEGER)")

        failures: list[BaseException] = []

        def other_thread() -> None:
            try:
                with db.transaction(connection):
                    connection.execute("INSERT INTO probe VALUES (1)")
                    connection.execute("INSERT INTO probe VALUES (2)")
                assert connection.execute("SELECT count(*) FROM probe").fetchone()[0] == 2
                connection.close()
            except BaseException as exc:
                # Same reason as the test above: the failure has to travel back
                # to the test thread to be assertable.
                failures.append(exc)

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()

        assert failures == []
