"""S-19 — every connection the product opens enforces foreign keys.

**Defect guarded:** append-only integrity. SQLite's ``foreign_keys`` pragma is
**per-connection** and **defaults to off**, so the 21 declared references across 17
tables are not a property of the database file ⭐ — they are a property of *whoever
opened it*. Measured 2026-10-06:

===========================  ==========================
how the database was opened  ``PRAGMA foreign_keys``
===========================  ==========================
``storage.db.connect``      **1**
``storage.db.connect_for_migration`` **1**
a bare ``sqlite3.connect()`` **0**
===========================  ==========================

Anti-pattern (forbidden)::

    con = sqlite3.connect(path)          # ← foreign_keys is OFF here
    con.execute("INSERT INTO decision_review_state VALUES (…)")

Correct form::

    from alphacouncil.storage import db
    con = db.connect(path)               # ← the factory sets the pragma

Why a test cannot catch this: the defect is **absent**. A connection with the
pragma off accepts every write the product makes and rejects none, so the whole
suite passes and the file on disk quietly accumulates rows the schema says cannot
exist. ⭐ It was not a test that found this ⭐ — ⭐ it was ``D-25`` reading the
reader's own database and finding **four** ``decision_review_state`` rows whose
``decision_id`` matched no decision, written 25ms apart ⭐⭐ — **a loop, not a
person.**

⭐⭐ And this is where the severity lives ⭐⭐ — ⭐⭐ `D-25` reports the *effect* on the
reader's accumulated data and is therefore a ``warning``, ⭐⭐ because those rows can
neither be deleted (nothing in this repository deletes decisions) nor be produced
again (both factories enforce the pragma). ⭐⭐ **A permanently-red gate is a gate that
gets ignored** ⭐⭐ — ⭐⭐ this rule is the one that can be an ``error``, ⭐⭐ because it
is about code, ⭐⭐ and a code defect can be fixed. ⭐⭐

The three exemptions this rule's first draft declared ⭐⭐ — ⭐⭐ **two of which were dead**
⭐⭐ — ⭐⭐ are the reason :data:`EXEMPT` is now **one** entry ⭐⭐:

==========================  ==========  =========================================
declared                    exists?     actually reachable by this rule?
==========================  ==========  =========================================
``storage/db.py``          yes         ⭐⭐ **yes** ⭐⭐ — it sets the pragma
``storage/migrations.py``   ⭐⭐ **no** ⭐⭐ ⭐⭐ **no** ⭐⭐ ⭐⭐ — the file is ``migrate.py``
``checks/data.py``         yes         ⭐⭐ **no** ⭐⭐ — outside ``ctx.product``
==========================  ==========  =========================================

⭐⭐⭐ **Both mistakes are ``F-226`` again** ⭐⭐⭐ — ⭐⭐ a filename written by pattern rather
than read ⭐⭐ (``migrations.py`` ⭐⭐ because the module *defines* ``load_migrations`` ⭐⭐)
⭐⭐⭐ — ⭐⭐ and a dead entry is worse than no entry, ⭐⭐⭐ because a table of exemptions
⭐⭐⭐ is a claim about what was examined, ⭐⭐⭐ and an entry that never fires claims a
⭐⭐⭐ file was read when it was not. ⭐⭐⭐ ⇒ ``tests/unit/test_static_checks.py`` asserts
⭐⭐⭐ every ``EXEMPT`` key **exists on disk and is under ``ctx.product``**, ⭐⭐⭐ so a dead
⭐⭐⭐ exemption becomes a test failure rather than a silent untruth. ⭐⭐⭐

⭐ ``migrate.py`` needs no exemption ⭐⭐ — ⭐⭐ its six ``sqlite3.Connection`` occurrences
⭐⭐ are **parameter annotations**, ⭐⭐ and it never opens a connection itself.
"""

from __future__ import annotations

import ast

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_FOREIGN_KEYS_OFF"

META = CheckMeta(
    check_id="S-19",
    slug="foreign-keys-not-off",
    title="a connection to the reader's database must enforce foreign keys",
    priority="P0",
    code=CODE,
)

#: ⭐⭐ **One entry, and it is the factory that sets the pragma.** ⭐⭐ Each exemption names
#: ⭐⭐ *why* rather than pointing at a line, ⭐⭐ because the reason is what a reviewer
#: ⭐⭐ reads six months from now ⭐⭐ and the line number will have moved.
EXEMPT: dict[str, str] = {
    "backend/src/alphacouncil/storage/db.py": (
        "this is where `PRAGMA foreign_keys = ON` is set ⭐⭐ — it is the factory, ⭐⭐ "
        "not a caller, ⭐⭐ and it is the only file allowed to open a database itself"
    ),
}

_FIX = (
    "Open the database through `alphacouncil.storage.db.connect` ⭐⭐ — it sets "
    "`PRAGMA foreign_keys = ON` on every connection ⭐⭐ — ⭐⭐ or, if this really is a "
    "one-off script, say so in its docstring ⭐⭐ because a bare `sqlite3.connect()` "
    "against the reader's file ⭐⭐ **is how the four orphan rows in "
    "`decision_review_state` got there** ⭐⭐ (`D-25` reports them)."
)


def _is_sqlite_connect(call: ast.Call) -> bool:
    """Whether the call is ``sqlite3.connect(...)`` or ``sqlite3.Connection(...)``.

    ⭐⭐ **Both spellings are checked** ⭐⭐ — ⭐⭐ a bare ``sqlite3.Connection(path)``
    ⭐⭐ opens a real database with the pragma off ⭐⭐ and is exactly as capable of
    ⭐⭐ writing an orphan ⭐⭐ — ⭐⭐ and the first draft of this rule looked only for
    ⭐⭐ ``connect`` ⭐⭐, ⭐⭐ which would have passed that file clean. ⭐⭐ `demo.py` has
    ⭐⭐ two ``sqlite3.Connection`` occurrences ⭐⭐ **and they are type annotations**
    ⭐⭐ (a parameter annotation, not a call) ⭐⭐ — ⭐⭐ so this must test the node, ⭐⭐
    ⭐⭐ not the text of the line. ⭐⭐⭐
    """
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in {"connect", "Connection"}:
        return False
    # ⭐⭐ An annotation is not a call. ⭐⭐ `def _fill(connection: sqlite3.Connection)`
    # ⭐⭐ parses as a bare Name inside an annotation, ⭐⭐ **not** as an `ast.Call`,
    # ⭐⭐ — ⭐⭐ so reaching this function at all already means a call ⭐⭐; ⭐⭐ the
    # ⭐⭐ remaining risk is `sqlite3.connect` used as a *default* or in a decorator,
    # ⭐⭐ which is still a call and still opens a file. ⭐⭐ ⭐ And an attribute on
    # ⭐⭐ anything other than `sqlite3` ⭐⭐ (`some_shim.connect(path)`) ⭐⭐ is a
    # ⭐⭐ different factory with its own contract, ⭐⭐ so it is not this rule's
    # ⭐⭐ business ⭐⭐ — ⭐⭐ guessing at other libraries' pragmas is how a rule
    # ⭐⭐ cries wolf.
    return isinstance(func.value, ast.Name) and func.value.id == "sqlite3"


def run(ctx: ScanContext) -> CheckResult:
    """Find every SQLite connection in the product that bypasses the factory."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        tree = ctx.tree(path)
        if tree is None:
            continue
        rel = ctx.rel(path)
        if rel in EXEMPT:
            # ⭐⭐ **Still appended to `files`** ⭐⭐ — ⭐⭐ `apply_exemptions` walks
            # ⭐⭐ `result.files` for unreasoned suppressions, ⭐⭐ and a file the rule
            # ⭐⭐ chose not to read must not be invisible to it. ⭐⭐
            result.files.append(path)
            continue
        result.files.append(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_sqlite_connect(node):
                continue
            result.error(
                CODE,
                f"`{ctx.rel(path)}:{node.lineno}` opens SQLite without the factory ⭐⭐ — "
                "`PRAGMA foreign_keys` is **off** on that connection",
                target=format_target(ctx, path, node.lineno),
                fix=_FIX,
            )
    return result
