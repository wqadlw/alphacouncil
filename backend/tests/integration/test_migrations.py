"""Migrations against a real database file.

Everything here needs an actual file on disk, because that is where the
guarantees live: a snapshot is a file with a checksum, ``PRAGMA user_version``
only survives if it is committed, and "the database is unchanged after a failed
migration" is a claim about bytes.

The chain used by the upgrade tests is **the project's real initial migration**,
copied verbatim, plus a synthetic second step. That matters: a synthetic v1
would let the tests pass while the shipped schema was broken.

⚠️ Until this module existed, ``snapshot()`` had **never run on a non-empty
database** — the only end-to-end exercise was a fresh install, where there is
nothing to copy and the function returns early. Every claim about the snapshot
in ``migrate.py`` was therefore untested. Found 2026-09-26.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.storage import db, migrate

pytestmark = pytest.mark.integration

#: A second migration step that is deliberately **non-destructive**: rolling it
#: back drops a table that only holds its own data, so ``rollback`` may do it
#: without permission. It is also a constitutional schema — STRICT, named
#: constraints, a canonical timestamp — so it exercises the same machinery as
#: the real one rather than sidestepping it.
_NOTES_UP = """\
CREATE TABLE notes (
    id    TEXT PRIMARY KEY,
    body  TEXT NOT NULL,

    CONSTRAINT notes_id_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', id) = id),
    CONSTRAINT notes_body_required_check
        CHECK (length(trim(body)) > 0)
) STRICT;
"""

_NOTES_DOWN = "DROP TABLE IF EXISTS notes;\n"

#: A third step, used to build a chain whose *oldest* entry is version 3 — the
#: shape a build has when versions 1 and 2 are no longer shipped. That is what
#: makes a database at version 1 unreachable.
_TAGS_UP = """\
CREATE TABLE tags (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL,

    CONSTRAINT tags_id_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', id) = id)
) STRICT;
"""

_TAGS_DOWN = "DROP TABLE IF EXISTS tags;\n"

_STEPS: dict[int, tuple[str, str, str, bool]] = {
    2: ("notes", _NOTES_UP, _NOTES_DOWN, False),
    3: ("tags", _TAGS_UP, _TAGS_DOWN, False),
}

#: A canonical timestamp, so the migration's own CHECK constraints accept it.
NOW = "2026-09-26T12:00:00.000Z"

Connect = Callable[[Path | str], sqlite3.Connection]


@pytest.fixture
def connect() -> Iterator[Connect]:
    """Open migration-profile connections and close them at teardown.

    Without this, ``sqlite3`` emits ``ResourceWarning: unclosed database`` when
    the collector eventually runs. ``filterwarnings = ["error"]`` turns that into
    a ``PytestUnraisableExceptionWarning`` attributed to whichever test happened
    to be executing at collection time — a failure in a test that did nothing
    wrong, which is the worst kind of flake to debug.
    """
    opened: list[sqlite3.Connection] = []

    def factory(path: Path | str) -> sqlite3.Connection:
        connection = db.connect_for_migration(path)
        opened.append(connection)
        return connection

    yield factory
    for connection in opened:
        connection.close()


def _chain(directory: Path, versions: tuple[int, ...]) -> tuple[migrate.Migration, ...]:
    """Materialise a migration chain in ``directory`` and load it.

    Version 1 is the project's real initial migration, copied byte for byte;
    the other versions come from :data:`_STEPS`. The chain is exactly
    ``versions`` — no version is added implicitly, because "a build whose oldest
    migration is 3" is a case the planner has to handle.
    """
    directory.mkdir(parents=True, exist_ok=True)
    real = {item.version: item for item in migrate.load_migrations()}[1]
    entries: list[dict[str, object]] = []
    for version in versions:
        if version == 1:
            shutil.copy(real.up, directory / real.up.name)
            shutil.copy(real.down, directory / real.down.name)
            entries.append(
                {
                    "version": 1,
                    "name": "initial",
                    "up": real.up.name,
                    "down": real.down.name,
                    "destructive_down": True,
                    "down_note": "test fixture: same note as the shipped manifest",
                }
            )
            continue
        name, up, down, destructive = _STEPS[version]
        (directory / f"{version:04d}_{name}.up.sql").write_text(up, encoding="utf-8")
        (directory / f"{version:04d}_{name}.down.sql").write_text(down, encoding="utf-8")
        entries.append(
            {
                "version": version,
                "name": name,
                "up": f"{version:04d}_{name}.up.sql",
                "down": f"{version:04d}_{name}.down.sql",
                "destructive_down": destructive,
                "down_note": "test fixture" if destructive else "",
            }
        )
    (directory / migrate.MANIFEST_NAME).write_text(
        json.dumps({"migrations": entries}, ensure_ascii=False), encoding="utf-8"
    )
    return migrate.load_migrations(directory)


def _objects(connection: sqlite3.Connection) -> set[str]:
    """Every table, view, index and trigger name in the database."""
    rows = connection.execute("SELECT name FROM sqlite_master").fetchall()
    return {str(row[0]) for row in rows}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_an_instrument_and_a_reason(connection: sqlite3.Connection) -> None:
    """Write the kind of row a user writes: an instrument and a stated reason.

    Raw SQL on purpose — this is a migration test, and the point is that the
    bytes survive an upgrade, not that the repository layer works.
    """
    connection.execute(
        "INSERT INTO instruments (market, code, asset_type, created_at) VALUES (?, ?, ?, ?)",
        ("sh", "600519", "stock", NOW),
    )
    connection.execute(
        "INSERT INTO watchlist_events (occurred_at, market, code, kind, reason) "
        "VALUES (?, ?, ?, ?, ?)",
        (NOW, "sh", "600519", "added", "估值到了我算得出来的区间"),
    )


class TestFreshInstall:
    def test_a_new_database_reaches_the_newest_version(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        chain = _chain(tmp_path / "migrations", (1, 2))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)

        report = migrate.apply(connection, database_path=database, migrations=chain)

        assert report.from_version == 0
        assert report.to_version == 2
        assert report.applied == (1, 2)
        assert report.changed is True
        assert migrate.schema_version(connection) == 2

    def test_a_new_database_snapshots_nothing(self, tmp_path: Path, connect: Connect) -> None:
        """Version 0 has no schema and no rows — there is nothing worth copying."""
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)

        report = migrate.apply(connection, database_path=database, migrations=chain)

        assert report.snapshot_path is None
        assert report.snapshot_sha256 is None
        assert not (tmp_path / "snapshots").exists()

    def test_applying_twice_changes_nothing(self, tmp_path: Path, connect: Connect) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)

        migrate.apply(connection, database_path=database, migrations=chain)
        again = migrate.apply(connection, database_path=database, migrations=chain)

        assert again.applied == ()
        assert again.changed is False
        assert again.state is migrate.SchemaState.UP_TO_DATE
        assert again.snapshot_path is None

    def test_the_shipped_schema_arrives_whole(self, tmp_path: Path, connect: Connect) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)

        migrate.apply(connection, database_path=database, migrations=chain)

        names = _objects(connection)
        assert {"instruments", "watchlist_events", "decisions", "audit_log"} <= names
        assert "watchlist_current" in names
        expected = {
            f"{table}_no_{verb}"
            for table in ("watchlist_events", "decisions", "audit_log")
            for verb in ("update", "delete")
        }
        assert expected <= names


class TestUpgradingKeepsWhatIsAlreadyThere:
    def test_the_rows_survive(self, tmp_path: Path, connect: Connect) -> None:
        first = _chain(tmp_path / "v1", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=first)
        _add_an_instrument_and_a_reason(connection)

        both = _chain(tmp_path / "v12", (1, 2))
        report = migrate.apply(connection, database_path=database, migrations=both)

        assert report.applied == (2,)
        assert report.from_version == 1
        assert report.to_version == 2
        row = connection.execute(
            "SELECT reason FROM watchlist_events WHERE code = ?", ("600519",)
        ).fetchone()
        assert row is not None
        assert row[0] == "估值到了我算得出来的区间"

    def test_the_snapshot_is_taken_and_verified(self, tmp_path: Path, connect: Connect) -> None:
        """ADR-0012 rule 3. "We have a backup" must be a checksum, not a claim."""
        first = _chain(tmp_path / "v1", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=first)
        _add_an_instrument_and_a_reason(connection)

        report = migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "v12", (1, 2))
        )

        assert report.snapshot_path is not None
        assert report.snapshot_path.is_file()
        assert report.snapshot_sha256 == _digest(report.snapshot_path)

    def test_the_snapshot_defaults_to_beside_the_database(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        first = _chain(tmp_path / "v1", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=first)
        _add_an_instrument_and_a_reason(connection)

        report = migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "v12", (1, 2))
        )

        assert report.snapshot_path is not None
        assert report.snapshot_path.parent == tmp_path / "snapshots"

    def test_the_snapshot_holds_the_state_from_before_the_upgrade(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        """A snapshot taken *after* the migration would be worthless, and the
        difference is invisible unless something opens the file and looks."""
        first = _chain(tmp_path / "v1", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=first)
        _add_an_instrument_and_a_reason(connection)

        report = migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "v12", (1, 2))
        )

        assert report.snapshot_path is not None
        restored = sqlite3.connect(report.snapshot_path)
        try:
            assert migrate.schema_version(restored) == 1
            assert "notes" not in _objects(restored)
            kept = restored.execute("SELECT reason FROM watchlist_events").fetchall()
        finally:
            restored.close()
        assert len(kept) == 1

    def test_an_empty_database_is_still_snapshotted(self, tmp_path: Path, connect: Connect) -> None:
        """Only version 0 skips the snapshot. A v1 database with zero rows still
        gets one, because the schema is what the snapshot is for — "empty" is a
        fact about rows, and it is not the condition."""
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=chain)

        report = migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "v12", (1, 2))
        )

        assert report.snapshot_path is not None
        assert report.snapshot_path.is_file()


class TestEveryAttemptGetsItsOwnSnapshot:
    """ADR-0012 rule 5, and the reason it is enforced by the filesystem."""

    def test_vacuum_into_refuses_to_overwrite(self, tmp_path: Path, connect: Connect) -> None:
        """This is what makes "unique per attempt" true by construction.

        ``_snapshot_name`` embeds microseconds, so collisions are unlikely — but
        "unlikely" is not a guarantee. ``VACUUM INTO`` refusing an existing file
        is, and this test pins that behaviour down rather than assuming it.
        """
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=_chain(tmp_path / "m", (1,)))

        target = tmp_path / "snapshots" / "fixed.db"
        migrate.snapshot(connection, target)

        with pytest.raises(migrate.SnapshotError, match="failed"):
            migrate.snapshot(connection, target)

    def test_a_retry_creates_a_new_file_and_leaves_the_old_one_alone(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        first = _chain(tmp_path / "v1", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=first)
        _add_an_instrument_and_a_reason(connection)

        both = _chain(tmp_path / "v12", (1, 2))
        opening = migrate.apply(connection, database_path=database, migrations=both)
        assert opening.snapshot_path is not None
        original_digest = _digest(opening.snapshot_path)

        migrate.rollback(connection, target_version=1, migrations=both)
        retry = migrate.apply(connection, database_path=database, migrations=both)

        assert retry.snapshot_path is not None
        assert retry.snapshot_path != opening.snapshot_path
        assert _digest(opening.snapshot_path) == original_digest


class TestTheDatabaseIsRefusedWhenItIsAhead:
    """Constitution 5.5. A newer build may have added a constraint this one does
    not know about, so writing to the database would corrupt data silently."""

    def test_a_newer_database_is_refused(self, tmp_path: Path, connect: Connect) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=chain)
        connection.execute("PRAGMA user_version = 99")

        with pytest.raises(migrate.DatabaseNewerThanAppError) as caught:
            migrate.apply(connection, database_path=database, migrations=chain)

        assert caught.value.code is ErrorCode.STORAGE_DB_NEWER_THAN_APP
        assert "99" in str(caught.value)

    def test_a_refused_upgrade_does_not_touch_the_database(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=chain)
        before = _objects(connection)
        connection.execute("PRAGMA user_version = 99")

        with pytest.raises(migrate.DatabaseNewerThanAppError):
            migrate.apply(connection, database_path=database, migrations=chain)

        assert migrate.schema_version(connection) == 99
        assert _objects(connection) == before

    def test_a_gap_with_no_path_is_refused(self, tmp_path: Path, connect: Connect) -> None:
        """A database at version 1, and a build whose oldest known step is 3."""
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(
            connection,
            database_path=database,
            migrations=_chain(tmp_path / "v1", (1,)),
        )

        starts_at_three = _chain(tmp_path / "v3", (3,))
        assert [item.version for item in starts_at_three] == [3]

        with pytest.raises(migrate.NoUpgradePathError) as caught:
            migrate.apply(connection, database_path=database, migrations=starts_at_three)

        assert caught.value.code is ErrorCode.STORAGE_DB_NO_UPGRADE_PATH
        assert migrate.schema_version(connection) == 1


class TestAFailedMigrationLeavesNothingBehind:
    """The property that turns a bad release into a bug instead of a lost database."""

    def _broken_chain(self, tmp_path: Path) -> tuple[migrate.Migration, ...]:
        """A chain whose step 2 has one valid statement and one invalid one."""
        _chain(tmp_path / "migrations", (1,))
        directory = tmp_path / "migrations"
        # If the version bump and the DDL were not in one transaction, the first
        # statement's table would survive.
        (directory / "0002_broken.up.sql").write_text(
            "CREATE TABLE half_applied (x TEXT);\nCREATE TABLE broken (;\n", encoding="utf-8"
        )
        (directory / "0002_broken.down.sql").write_text("", encoding="utf-8")
        manifest = directory / migrate.MANIFEST_NAME
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["migrations"].append(
            {
                "version": 2,
                "name": "broken",
                "up": "0002_broken.up.sql",
                "down": "0002_broken.down.sql",
                "destructive_down": False,
                "down_note": "",
            }
        )
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return migrate.load_migrations(directory)

    def test_the_version_is_not_bumped(self, tmp_path: Path, connect: Connect) -> None:
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "migrations", (1,))
        )

        with pytest.raises(migrate.MigrationError):
            migrate.apply(
                connection, database_path=database, migrations=self._broken_chain(tmp_path)
            )

        assert migrate.schema_version(connection) == 1

    def test_the_partial_ddl_is_rolled_back(self, tmp_path: Path, connect: Connect) -> None:
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "migrations", (1,))
        )
        before = _objects(connection)

        with pytest.raises(migrate.MigrationError):
            migrate.apply(
                connection, database_path=database, migrations=self._broken_chain(tmp_path)
            )

        assert _objects(connection) == before
        assert "half_applied" not in _objects(connection)

    def test_the_failure_is_reported_through_the_managed_code(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        """A raw ``sqlite3.OperationalError`` would escape every ``except
        MigrationError`` in the program, so the most likely failure of all would
        be the one reported in an unhandled shape."""
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "migrations", (1,))
        )

        with pytest.raises(migrate.MigrationError) as caught:
            migrate.apply(
                connection, database_path=database, migrations=self._broken_chain(tmp_path)
            )

        assert caught.value.code is ErrorCode.MIGRATION_FAILED
        assert "statement 2/2" in str(caught.value)
        assert isinstance(caught.value.__cause__, sqlite3.Error)

    def test_a_snapshot_is_taken_before_the_failing_step(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        """The snapshot must precede the attempt, not follow success — otherwise
        the one case that needs it is the one case that does not get it."""
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "migrations", (1,))
        )
        _add_an_instrument_and_a_reason(connection)

        with pytest.raises(migrate.MigrationError):
            migrate.apply(
                connection, database_path=database, migrations=self._broken_chain(tmp_path)
            )

        snapshots = sorted((tmp_path / "snapshots").glob("*.db"))
        assert len(snapshots) == 1
        restored = sqlite3.connect(snapshots[0])
        try:
            assert migrate.schema_version(restored) == 1
            assert restored.execute("SELECT count(*) FROM watchlist_events").fetchone()[0] == 1
        finally:
            restored.close()


class TestRollback:
    def test_a_destructive_rollback_is_refused_by_default(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=chain)
        _add_an_instrument_and_a_reason(connection)

        with pytest.raises(migrate.DestructiveRollbackError) as caught:
            migrate.rollback(connection, target_version=0, migrations=chain)

        assert "snapshot" in str(caught.value)
        assert migrate.schema_version(connection) == 1
        assert connection.execute("SELECT count(*) FROM watchlist_events").fetchone()[0] == 1

    def test_a_destructive_rollback_proceeds_when_explicitly_allowed(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=chain)
        _add_an_instrument_and_a_reason(connection)

        report = migrate.rollback(
            connection, target_version=0, allow_destructive=True, migrations=chain
        )

        assert report.applied == (1,)
        assert migrate.schema_version(connection) == 0
        assert not _objects(connection) & {"instruments", "watchlist_events", "decisions"}

    def test_a_non_destructive_step_needs_no_permission(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        both = _chain(tmp_path / "migrations", (1, 2))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=both)
        _add_an_instrument_and_a_reason(connection)

        report = migrate.rollback(connection, target_version=1, migrations=both)

        assert report.applied == (2,)
        assert migrate.schema_version(connection) == 1
        assert "notes" not in _objects(connection)
        # The destructive step was not part of this rollback, so the rows stay.
        assert connection.execute("SELECT count(*) FROM watchlist_events").fetchone()[0] == 1

    def test_rolling_back_up_is_refused(self, tmp_path: Path, connect: Connect) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=chain)

        with pytest.raises(migrate.MigrationError, match="roll back up"):
            migrate.rollback(connection, target_version=2, migrations=chain)

    def test_a_negative_target_is_refused(self, tmp_path: Path, connect: Connect) -> None:
        chain = _chain(tmp_path / "migrations", (1,))
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(connection, database_path=database, migrations=chain)

        with pytest.raises(migrate.MigrationError, match=">= 0"):
            migrate.rollback(connection, target_version=-1, migrations=chain)


class TestTheConnectionProfiles:
    """ADR-0012 rules 5-6: a migration and a query want opposite things."""

    def test_the_migration_profile_pays_for_safety(self, tmp_path: Path, connect: Connect) -> None:
        connection = connect(tmp_path / "m.db")
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == 1  # FILE
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_the_runtime_profile_does_not_sort_in_memory(self, tmp_path: Path) -> None:
        """``temp_store=MEMORY`` is a memory bound, not a speed knob: wealthfolio
        measured a million-row UPDATE peaking at 2 GiB under it and 76 MiB under
        FILE. This asserts the migration profile is the FILE one; the runtime
        profile is allowed the default."""
        migration = db.connect_for_migration(tmp_path / "m.db")
        runtime = db.connect(tmp_path / "r.db")
        try:
            assert migration.execute("PRAGMA temp_store").fetchone()[0] == 1
            assert runtime.execute("PRAGMA temp_store").fetchone()[0] != 1
        finally:
            migration.close()
            runtime.close()

    def test_foreign_keys_are_on_for_both(self, tmp_path: Path) -> None:
        """SQLite defaults this to OFF per connection, which would make every
        REFERENCES clause in the schema decorative."""
        for opener in (db.connect, db.connect_for_migration):
            connection = opener(tmp_path / f"{opener.__name__}.db")
            try:
                assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            finally:
                connection.close()

    def test_the_schema_can_actually_refuse_a_dangling_reference(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        """The previous test reads a PRAGMA. This one makes the database prove it."""
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "migrations", (1,))
        )

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                "INSERT INTO watchlist_events (occurred_at, market, code, kind, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (NOW, "sh", "999999", "added", "没有这个标的"),
            )


class TestTheTriggersFireOnTheMigratedDatabase:
    """S-04 reads the SQL text. This reads the running database.

    Both layers are needed: the static rule is the early warning, and this is
    the proof. The watchlist case is covered in ``test_watchlist_api.py``; these
    are the tables nothing else exercises.
    """

    @pytest.fixture
    def migrated(self, tmp_path: Path, connect: Connect) -> sqlite3.Connection:
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        migrate.apply(
            connection, database_path=database, migrations=_chain(tmp_path / "migrations", (1,))
        )
        connection.execute(
            "INSERT INTO instruments (market, code, asset_type, created_at) VALUES (?, ?, ?, ?)",
            ("sh", "600519", "stock", NOW),
        )
        connection.execute(
            "INSERT INTO decisions (id, market, code, action, rationale, counter_evidence, "
            "kill_criteria) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (NOW, "sh", "600519", "buy", "估值低", "毛利在下滑", "[]"),
        )
        connection.execute(
            "INSERT INTO audit_log (id, actor, action) VALUES (?, ?, ?)",
            (NOW, "user", "watchlist.add"),
        )
        return connection

    def test_a_decision_cannot_be_rewritten(self, migrated: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            migrated.execute("UPDATE decisions SET rationale = '换个说法'")

    def test_a_decision_cannot_be_deleted(self, migrated: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            migrated.execute("DELETE FROM decisions")

    def test_the_audit_trail_cannot_be_rewritten(self, migrated: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            migrated.execute("UPDATE audit_log SET action = 'something else'")

    def test_the_audit_trail_cannot_be_deleted(self, migrated: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            migrated.execute("DELETE FROM audit_log")

    def test_the_reason_field_cannot_be_edited_in_place(self, migrated: sqlite3.Connection) -> None:
        """Red line 15 tier ④: an agent may never rewrite a user's stated reason."""
        migrated.execute(
            "INSERT INTO watchlist_events (occurred_at, market, code, kind, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (NOW, "sh", "600519", "added", "因为我觉得会涨"),
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            migrated.execute("UPDATE watchlist_events SET reason = '估值修复'")

    def test_a_kill_criteria_must_be_a_json_array(self, migrated: sqlite3.Connection) -> None:
        """ADR-0017 #5. Free text cannot be compared against data, so the
        column is a predicate array and the database enforces it."""
        for bad in ("营收下滑", "{}", "null", "123"):
            with pytest.raises(sqlite3.IntegrityError, match="kill_criteria"):
                migrated.execute(
                    "INSERT INTO decisions (id, market, code, action, rationale, "
                    "counter_evidence, kill_criteria) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (NOW, "sh", "600519", "buy", "理由", "反面", bad),
                )

    def test_the_watchlist_view_derives_the_current_members(
        self, migrated: sqlite3.Connection
    ) -> None:
        migrated.execute(
            "INSERT INTO watchlist_events (occurred_at, market, code, kind, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (NOW, "sh", "600519", "added", "估值到了区间"),
        )
        current = migrated.execute("SELECT code FROM watchlist_current").fetchall()
        assert [row[0] for row in current] == ["600519"]

        migrated.execute(
            "INSERT INTO watchlist_events (occurred_at, market, code, kind) VALUES (?, ?, ?, ?)",
            (NOW, "sh", "600519", "removed"),
        )
        assert migrated.execute("SELECT code FROM watchlist_current").fetchall() == []


class TestTheRealSecondMigration:
    """The shipped 1→2 upgrade, on the shipped chain, with real user rows.

    Until 0002 existed, every "upgrade keeps data" claim ran against a
    *synthetic* second step (see ``_chain``) — the real one had never been
    applied to a database holding anything. status.md §五 recorded that gap
    as "升级链只在合成意义上被验证过"; these tests retire it.
    """

    def test_a_version_one_database_upgrades_with_its_rows_intact(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        real_first = {item.version: item for item in migrate.load_migrations()}[1]
        for statement in migrate.split_statements(real_first.up.read_text(encoding="utf-8")):
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        _add_an_instrument_and_a_reason(connection)

        report = migrate.apply(connection, database_path=database)

        assert report.applied == (2,)
        assert report.from_version == 1
        assert migrate.schema_version(connection) == 2
        row = connection.execute(
            "SELECT reason FROM watchlist_events WHERE code = ?", ("600519",)
        ).fetchone()
        assert row is not None
        assert row[0] == "估值到了我算得出来的区间"

    def test_the_upgraded_database_can_hold_cache_rows(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        real_first = {item.version: item for item in migrate.load_migrations()}[1]
        for statement in migrate.split_statements(real_first.up.read_text(encoding="utf-8")):
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        migrate.apply(connection, database_path=database)

        connection.execute(
            "INSERT INTO market_cache (cache_key, dataset, payload, expires_at) "
            "VALUES ('realtime:sh600519', 'realtime', '{\"status\": \"error\"}', 0)"
        )
        row = connection.execute(
            "SELECT payload FROM market_cache WHERE cache_key = 'realtime:sh600519'"
        ).fetchone()
        assert row is not None

    def test_the_snapshot_taken_before_the_upgrade_lacks_the_new_table(
        self, tmp_path: Path, connect: Connect
    ) -> None:
        """The snapshot is the pre-upgrade state: v1 schema, user rows, no cache."""
        database = tmp_path / "alphacouncil.db"
        connection = connect(database)
        real_first = {item.version: item for item in migrate.load_migrations()}[1]
        for statement in migrate.split_statements(real_first.up.read_text(encoding="utf-8")):
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        _add_an_instrument_and_a_reason(connection)

        report = migrate.apply(connection, database_path=database)

        assert report.snapshot_path is not None
        assert report.snapshot_sha256 == _digest(report.snapshot_path)
        snapshot = sqlite3.connect(report.snapshot_path)
        try:
            tables = {
                str(row[0]) for row in snapshot.execute("SELECT name FROM sqlite_master").fetchall()
            }
            assert "market_cache" not in tables
            assert "watchlist_events" in tables
            rows = snapshot.execute("SELECT count(*) FROM watchlist_events").fetchone()[0]
            assert rows == 1
        finally:
            snapshot.close()
