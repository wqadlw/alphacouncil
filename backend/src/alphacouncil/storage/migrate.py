"""Schema migrations — versioned, snapshotted, and reversible on paper.

The rules come from constitution 5.1/5.5 and ADR-0012, and each one exists
because of a specific way a desktop application loses a user's only copy of
their data:

1. **A published migration is never edited**, only appended to. Somebody's
   database has already run it, so editing it makes the schema depend on *when*
   it was installed.
2. **Every migration declares a ``down``.** Where the downgrade would destroy
   user data it must say so explicitly rather than pretend to be reversible —
   see ``manifest.json`` and :func:`rollback`.
3. **A verified snapshot is taken before upgrading**: ``VACUUM INTO`` followed by
   a SHA-256 of the result, so "we have a backup" is a fact with a checksum
   rather than a claim.
4. **The version lives in ``PRAGMA user_version``, which is transactional.**
   Verified on 2026-09-26: bumping the version and applying the DDL in one
   transaction, then rolling back, restores both the version and the schema. So
   a migration that fails halfway leaves the database exactly as it was — not
   half-upgraded, which is the state that turns a bad release into a lost
   database.
5. **No migration is ever inferred from a filename.** ``manifest.json`` lists
   them in order: sorting filenames breaks the moment the version crosses a
   digit boundary (``00010`` sorts before ``0009``).

Version comparison is three-way (constitution 5.5). A database **newer** than
the application is refused rather than downgraded — a newer build may have added
a constraint the older one does not know about, so writing to it would corrupt
data in a way no error would report.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from itertools import pairwise
from pathlib import Path

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.storage.db import transaction

__all__ = [
    "MANIFEST_NAME",
    "MAX_VERSION",
    "MIGRATIONS_DIR",
    "DatabaseNewerThanAppError",
    "DestructiveRollbackError",
    "Migration",
    "MigrationError",
    "MigrationReport",
    "NoUpgradePathError",
    "SchemaPlan",
    "SchemaState",
    "SnapshotError",
    "apply",
    "load_migrations",
    "plan",
    "rollback",
    "schema_version",
    "snapshot",
    "split_statements",
]

#: Where the numbered ``.sql`` files and their manifest live.
MIGRATIONS_DIR = Path(__file__).with_name("migrations")
MANIFEST_NAME = "manifest.json"

#: ``PRAGMA user_version`` is a 32-bit signed integer, and it **wraps silently**
#: rather than erroring: verified 2026-09-26 that setting it to ``2**31`` reads
#: back ``0``. A manifest typo would therefore produce a database that looks like
#: it never upgraded, for ever, with nothing logged — so the range is checked
#: when the manifest is read instead of when it is applied.
MAX_VERSION = 2**31 - 1


# ---------------------------------------------------------------------------
# Failures — each carries its managed code (``.ai/error-codes.md`` §2.6)
# ---------------------------------------------------------------------------


class MigrationError(RuntimeError):
    """A migration could not be applied. Carries the managed error code."""

    code: ErrorCode = ErrorCode.MIGRATION_FAILED


class SnapshotError(MigrationError):
    """The pre-migration snapshot failed, so the migration must not proceed."""

    code = ErrorCode.MIGRATION_SNAPSHOT_FAILED


class DatabaseNewerThanAppError(MigrationError):
    """The database was written by a newer build. Refuse; never downgrade."""

    code = ErrorCode.STORAGE_DB_NEWER_THAN_APP


class NoUpgradePathError(MigrationError):
    """The database is older, but no migration bridges the gap."""

    code = ErrorCode.STORAGE_DB_NO_UPGRADE_PATH


class DestructiveRollbackError(MigrationError):
    """Refused: rolling back would delete user-written records."""

    code = ErrorCode.MIGRATION_FAILED


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Migration:
    """One versioned step, with its rollback."""

    version: int
    name: str
    up: Path
    down: Path
    destructive_down: bool
    down_note: str


def load_migrations(directory: Path | None = None) -> tuple[Migration, ...]:
    """Read ``manifest.json`` and resolve every file it names.

    Args:
        directory: Override for tests; defaults to :data:`MIGRATIONS_DIR`.

    Returns:
        Migrations ordered by version.

    Raises:
        MigrationError: The manifest is malformed, names a file that is absent,
            or declares a version outside ``1..MAX_VERSION``. A missing ``.sql``
            is fatal rather than skipped: silently skipping would let a release
            ship with an unapplied migration.
    """
    root = directory if directory is not None else MIGRATIONS_DIR
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        msg = f"migration manifest not found at {manifest_path}"
        raise MigrationError(msg)

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    migrations: list[Migration] = []
    for entry in raw["migrations"]:
        up = root / entry["up"]
        down = root / entry["down"]
        for path in (up, down):
            if not path.is_file():
                msg = f"manifest lists {path.name}, which does not exist"
                raise MigrationError(msg)
        version = int(entry["version"])
        if not 0 < version <= MAX_VERSION:
            msg = (
                f"migration version {version} is outside 1..{MAX_VERSION}. "
                "PRAGMA user_version is a 32-bit signed integer and wraps silently, "
                "so this would be stored as some other number."
            )
            raise MigrationError(msg)
        migrations.append(
            Migration(
                version=version,
                name=str(entry["name"]),
                up=up,
                down=down,
                destructive_down=bool(entry.get("destructive_down", False)),
                down_note=str(entry.get("down_note", "")),
            )
        )

    migrations.sort(key=lambda item: item.version)
    _assert_contiguous(migrations)
    return tuple(migrations)


def _assert_contiguous(migrations: list[Migration]) -> None:
    """Reject a manifest with duplicate or gapped versions."""
    for previous, current in pairwise(migrations):
        if current.version != previous.version + 1:
            msg = (
                f"migration versions must be contiguous: {previous.version} is followed by "
                f"{current.version}. A gap means some database cannot be upgraded."
            )
            raise MigrationError(msg)


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


class SchemaState(StrEnum):
    """The three-way comparison of constitution 5.5, plus the gap case."""

    UP_TO_DATE = "up_to_date"
    NEEDS_UPGRADE = "needs_upgrade"
    DATABASE_NEWER = "database_newer"
    NO_UPGRADE_PATH = "no_upgrade_path"


@dataclass(frozen=True, slots=True)
class SchemaPlan:
    """What :func:`apply` would do, without doing it."""

    state: SchemaState
    current_version: int
    target_version: int
    pending: tuple[Migration, ...]
    message: str


def schema_version(connection: sqlite3.Connection) -> int:
    """Read ``PRAGMA user_version``."""
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def plan(
    connection: sqlite3.Connection, migrations: tuple[Migration, ...] | None = None
) -> SchemaPlan:
    """Decide what must happen, and refuse the cases that must not."""
    available = migrations if migrations is not None else load_migrations()
    target = available[-1].version if available else 0
    current = schema_version(connection)

    if current > target:
        return SchemaPlan(
            SchemaState.DATABASE_NEWER,
            current,
            target,
            (),
            f"database is at version {current}, this build knows {target} — "
            "the database was written by a newer build. Upgrade the program; "
            "downgrading is not supported.",
        )
    if current == target:
        return SchemaPlan(SchemaState.UP_TO_DATE, current, target, (), "already up to date")

    pending = tuple(item for item in available if item.version > current)
    if not pending or pending[0].version != current + 1:
        return SchemaPlan(
            SchemaState.NO_UPGRADE_PATH,
            current,
            target,
            pending,
            f"database is at version {current} and the next known migration is "
            f"{pending[0].version if pending else 'none'} — there is no path from here.",
        )
    return SchemaPlan(
        SchemaState.NEEDS_UPGRADE,
        current,
        target,
        pending,
        f"{len(pending)} migration(s) to apply: {current} -> {target}",
    )


# ---------------------------------------------------------------------------
# SQL execution
# ---------------------------------------------------------------------------


def split_statements(script: str) -> list[str]:
    """Split a SQL script into complete statements.

    ``sqlite3.complete_statement`` knows about string literals and ``BEGIN … END``
    trigger bodies, which a naive ``split(";")`` does not — and every append-only
    trigger in this schema contains semicolons inside its body.

    There is no "is this statement blank?" guard on the append, and that is not an
    omission: ``complete_statement`` returns ``False`` for whitespace-only input
    (verified 2026-09-26), so whenever it returns ``True`` the buffer contains at
    least a ``;``. A guard was there and could never be false, which is the same
    dead-code case as an ``isinstance`` check the type checker already made.

    Splitting rather than using ``executescript`` is deliberate: ``executescript``
    issues an implicit ``COMMIT`` before running, which would break the
    "version bump and DDL in one transaction" guarantee the module docstring
    describes.

    Raises:
        MigrationError: The script ends mid-statement, which means the file is
            truncated rather than merely unusual.
    """
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        msg = f"script ends with an incomplete statement: {buffer.strip()[:80]!r}"
        raise MigrationError(msg)
    return statements


def _run_script(connection: sqlite3.Connection, script: str, version: int) -> None:
    """Apply one script and bump the version, atomically.

    Both halves are inside a single transaction, which SQLite honours for
    ``PRAGMA user_version`` — verified 2026-09-26. A failure therefore leaves the
    database at the previous version *and* the previous schema.

    A failing statement is re-raised as :class:`MigrationError` rather than left
    as a raw ``sqlite3.OperationalError`` (fixed 2026-09-26). The reason is not
    tidiness: every other failure in this module already carries a managed code,
    so a caller that handles migrations by catching :class:`MigrationError` would
    silently miss the most likely failure of all — a malformed script — and
    surface an unmapped SQLite message instead. The statement position is
    included because "near \";\": syntax error" is not actionable in a
    200-line migration.
    """
    statements = split_statements(script)
    with transaction(connection):
        for position, statement in enumerate(statements, start=1):
            try:
                connection.execute(statement)
            except sqlite3.Error as exc:
                msg = (
                    f"migration {version} failed at statement "
                    f"{position}/{len(statements)}: {exc}"
                )
                raise MigrationError(msg) from exc
        # PRAGMA does not accept a bound parameter; `version` is an int read
        # from our own manifest, never from user input.
        try:
            connection.execute(f"PRAGMA user_version = {version:d}")
        except sqlite3.Error as exc:  # pragma: no cover - see below
            # Unreachable through this module's public surface, and kept anyway.
            # `PRAGMA user_version = N` was verified on 2026-09-26 never to fail
            # on a writable connection, even for out-of-range N (it wraps
            # silently instead — which `load_migrations` now rejects up front).
            # The only connection where it does fail is read-only, and on such a
            # connection the DDL above fails first. So this is belt-and-braces
            # for a caller that does not exist yet, marked rather than deleted
            # because deleting it would restore the very defect fixed above:
            # a migration failure reported in an unmanaged shape.
            msg = f"migration {version} failed while recording its version: {exc}"
            raise MigrationError(msg) from exc


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def snapshot(connection: sqlite3.Connection, destination: Path) -> str:
    """Copy the database with ``VACUUM INTO`` and return the copy's SHA-256.

    ``VACUUM INTO`` refuses to overwrite an existing file, which is what makes
    "every retry produces a new snapshot and old snapshots stay byte-identical"
    (ADR-0012 rule 5) true by construction rather than by discipline.

    Args:
        connection: Any open connection to the database.
        destination: File to create. Its parent is created if needed.

    Returns:
        The hex digest of the snapshot.

    Raises:
        SnapshotError: The copy failed. Callers must treat this as fatal — a
            migration without a verified snapshot is the scenario the rule
            exists to prevent.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection.execute("VACUUM INTO ?", (str(destination),))
    except sqlite3.Error as exc:
        msg = f"snapshot to {destination} failed: {exc}"
        raise SnapshotError(msg) from exc
    return hashlib.sha256(destination.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """What actually happened."""

    from_version: int
    to_version: int
    applied: tuple[int, ...]
    snapshot_path: Path | None
    snapshot_sha256: str | None
    state: SchemaState

    @property
    def changed(self) -> bool:
        """Whether the schema was modified."""
        return bool(self.applied)


def _snapshot_name(database_path: Path | str, version: int) -> str:
    """A unique, sortable snapshot filename (ADR-0012 rule 5)."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    stem = Path(database_path).stem if isinstance(database_path, Path) else "alphacouncil"
    return f"{stem}.v{version}.{stamp}.db"


def apply(
    connection: sqlite3.Connection,
    *,
    database_path: Path | str,
    snapshot_dir: Path | None = None,
    migrations: tuple[Migration, ...] | None = None,
) -> MigrationReport:
    """Bring the database up to the newest known version.

    Args:
        connection: A migration-profile connection (``temp_store=FILE``,
            ``synchronous=FULL``).
        database_path: Used to name the snapshot and to detect a brand-new
            database that has nothing worth copying.
        snapshot_dir: Where snapshots go. Defaults to ``<database>/../snapshots``.
        migrations: Override for tests.

    Returns:
        A report; ``applied`` is empty when the database was already current.

    Raises:
        DatabaseNewerThanAppError: The database is from a newer build.
        NoUpgradePathError: The version gap cannot be bridged.
        SnapshotError: The pre-migration snapshot failed.
        MigrationError: A migration script failed. The database is left at the
            previous version *and* the previous schema, because the DDL and the
            version bump share one transaction.
    """
    current_plan = plan(connection, migrations)
    if current_plan.state is SchemaState.DATABASE_NEWER:
        raise DatabaseNewerThanAppError(current_plan.message)
    if current_plan.state is SchemaState.NO_UPGRADE_PATH:
        raise NoUpgradePathError(current_plan.message)
    if current_plan.state is SchemaState.UP_TO_DATE:
        return MigrationReport(
            current_plan.current_version,
            current_plan.target_version,
            (),
            None,
            None,
            SchemaState.UP_TO_DATE,
        )

    # A database at version 0 has no schema and no rows: there is nothing to
    # snapshot, and `VACUUM INTO` on a file that does not exist yet is noise.
    snap_path: Path | None = None
    snap_digest: str | None = None
    if current_plan.current_version > 0:
        directory = snapshot_dir or Path(database_path).parent / "snapshots"
        snap_path = directory / _snapshot_name(database_path, current_plan.current_version)
        snap_digest = snapshot(connection, snap_path)

    applied: list[int] = []
    for migration in current_plan.pending:
        _run_script(connection, migration.up.read_text(encoding="utf-8"), migration.version)
        applied.append(migration.version)

    return MigrationReport(
        current_plan.current_version,
        current_plan.target_version,
        tuple(applied),
        snap_path,
        snap_digest,
        SchemaState.NEEDS_UPGRADE,
    )


def rollback(
    connection: sqlite3.Connection,
    *,
    target_version: int,
    allow_destructive: bool = False,
    migrations: tuple[Migration, ...] | None = None,
) -> MigrationReport:
    """Step the schema back to ``target_version``.

    Raises:
        DestructiveRollbackError: A step would delete user-written records and
            ``allow_destructive`` was not set. The message names the snapshot to
            restore instead, because that is the supported way back.
        MigrationError: The target is not reachable by stepping down.
    """
    available = migrations if migrations is not None else load_migrations()
    current = schema_version(connection)
    if target_version > current:
        msg = f"cannot roll back up: current {current}, target {target_version}"
        raise MigrationError(msg)
    if target_version < 0:
        msg = f"target_version must be >= 0, got {target_version}"
        raise MigrationError(msg)

    steps = [item for item in available if target_version < item.version <= current]
    steps.sort(key=lambda item: item.version, reverse=True)

    blocking = [item for item in steps if item.destructive_down]
    if blocking and not allow_destructive:
        names = ", ".join(f"{item.version} ({item.down_note})" for item in blocking)
        msg = (
            f"refusing to roll back: step(s) {names} would delete user data. "
            "Restore the pre-migration snapshot instead, or pass "
            "--allow-destructive if you truly intend to discard it."
        )
        raise DestructiveRollbackError(msg)

    rolled: list[int] = []
    for migration in steps:
        _run_script(connection, migration.down.read_text(encoding="utf-8"), migration.version - 1)
        rolled.append(migration.version)

    return MigrationReport(
        from_version=current,
        to_version=target_version,
        applied=tuple(rolled),
        snapshot_path=None,
        snapshot_sha256=None,
        state=SchemaState.NEEDS_UPGRADE,
    )
