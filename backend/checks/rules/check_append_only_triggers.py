"""S-04 — append-only tables must be enforced by triggers, not by convention.

**Defect guarded:** constitution 5.4.1 and product red line 4. "Append-only" is a
claim about the database. If it lives only in a document, then the day someone
writes an ``UPDATE`` — to fix a typo, to "correct" an outcome, to clean up test
data — nothing stops them, and the decision journal quietly loses the property
that makes it worth keeping: *what you wrote before you knew the answer*.

Anti-pattern (forbidden)::

    CREATE TABLE decisions (
        id INTEGER PRIMARY KEY,
        rationale TEXT NOT NULL
    );
    -- nothing prevents UPDATE or DELETE

Correct form::

    CREATE TABLE decisions (...);

    CREATE TRIGGER decisions_no_update BEFORE UPDATE ON decisions
    BEGIN SELECT RAISE(ABORT, 'decisions is append-only: 改变想法请追加新记录'); END;

    CREATE TRIGGER decisions_no_delete BEFORE DELETE ON decisions
    BEGIN SELECT RAISE(ABORT, 'decisions is append-only: 记录不可删除'); END;

Why a test cannot catch this: a test can only prove that the paths it calls
behave. It cannot prove that no other path will ever issue an ``UPDATE`` — and
the ``UPDATE`` that breaks the journal will be written next year, by someone
who has never read this file. Only the database can refuse it.

**Implementation note.** SQL has no parser in the standard library, so this rule
reads text rather than an AST — the one place the "AST, never regex" rule cannot
apply. To keep it honest it strips ``--`` and ``/* */`` comments first, and the
authoritative check on the live schema remains the runtime layer
(``.ai/checks/data/``), which reads ``PRAGMA`` output from a real database. This
rule is the cheap early warning; that one is the proof.

**A hole this rule had, and how it was closed.** The first version reported an
error only for tables in ``created & APPEND_ONLY_TABLES``. So the day the schema
landed *without* an append-only table, the intersection was empty, no error was
emitted, and the rule reported **clean** — while having checked nothing. A rule
that finds nothing to look at must say so, which is the same T-19 distinction
the runner already makes for ``skipped``. The check is now: schema files found,
append-only tables found, *and the second set is empty* → ``skipped``.
"""

from __future__ import annotations

import re
from pathlib import Path

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_MISSING_TRIGGER"

META = CheckMeta(
    check_id="S-04",
    slug="check-append-only-triggers",
    title="append-only tables carry BEFORE UPDATE / BEFORE DELETE triggers",
    priority="P0",
    code=CODE,
)


#: Tables that must be append-only, from constitution 5.4.1: the decision
#: journal, the review conclusions, the thesis version history, and the audit
#: trail — plus the watchlist event log, whose entries are what the user wrote
#: down and which red line 15 forbids an agent from editing (tier ④).
#: card_events (K2, spec 013) joins them: a card lifecycle event is itself
#: an audit record and must never be rewritten after the fact.
#: Adding a table here is the whole cost of extending the rule.
APPEND_ONLY_TABLES = frozenset(
    {
        "decisions",
        "reviews",
        "thesis_versions",
        "audit_log",
        "watchlist_events",
        "card_events",
    }
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'\[]?(?P<name>[A-Za-z_][A-Za-z0-9_]*)[\"'\]]?",
    re.IGNORECASE,
)
_BEFORE_UPDATE = re.compile(
    r"CREATE\s+TRIGGER\s+\S+\s+BEFORE\s+UPDATE\s+ON\s+[\"'\[]?(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_BEFORE_DELETE = re.compile(
    r"CREATE\s+TRIGGER\s+\S+\s+BEFORE\s+DELETE\s+ON\s+[\"'\[]?(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def strip_sql_comments(text: str) -> str:
    """Remove SQL comments so a commented-out trigger is not mistaken for one."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def run(ctx: ScanContext) -> CheckResult:
    """Check every schema file that creates an append-only table."""
    result = CheckResult()
    candidates = ctx.files_with_suffix(ctx.backend, ".sql")
    candidates += ctx.python_files(ctx.backend / "migrations")
    if not candidates:
        result.skipped = (
            "no schema files yet (no *.sql and no migrations/ package) — "
            "the rule cannot observe anything until S1 lands migrations"
        )
        return result

    observed: set[str] = set()
    for path in candidates:
        result.files.append(path)
        observed |= _check_file(ctx, path, result)

    if not observed:
        result.skipped = (
            f"scanned {len(candidates)} schema file(s) but none creates an append-only "
            "table — the rule observed nothing to guard. Constitution 5.4.1 requires the "
            "decision journal, the review conclusions, the thesis history and the audit "
            "trail to exist, so their absence is a gap rather than a pass."
        )
    return result


def _check_file(ctx: ScanContext, path: Path, result: CheckResult) -> set[str]:
    """Report missing triggers in one schema file; return the tables it declares."""
    text = strip_sql_comments(ctx.text(path))
    created = {match.group("name").lower() for match in _CREATE_TABLE.finditer(text)}
    guarded_update = {match.group("name").lower() for match in _BEFORE_UPDATE.finditer(text)}
    guarded_delete = {match.group("name").lower() for match in _BEFORE_DELETE.finditer(text)}

    observed = created & APPEND_ONLY_TABLES
    for table in sorted(observed):
        missing: list[str] = []
        if table not in guarded_update:
            missing.append(f"BEFORE UPDATE (raise `{table} is append-only`)")
        if table not in guarded_delete:
            missing.append(f"BEFORE DELETE (raise `{table} is append-only`)")
        if not missing:
            continue
        result.error(
            CODE,
            f"`{table}` is append-only but has no " + " and no ".join(missing),
            target=format_target(ctx, path),
            fix=f"Add `CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}` and "
            f"`CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}`, each raising "
            "`RAISE(ABORT, ...)`. Constitution 5.4.1.",
        )
    return observed


__all__ = ["META", "run"]
