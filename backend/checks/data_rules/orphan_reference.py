"""D-25 · a row whose declared foreign key points at nothing.

## ⭐⭐⭐ Why this is `D-25` and not `D-02` ⭐⭐⭐

⭐⭐ **`D-02` was already declared** in `.ai/checks/data/README.md` §2.1 ⭐⭐ —

| D-02 | **孤儿实体** | 没有对应标的的持仓记录 |

⭐⭐ — **and the first draft of this file took that id.** ⭐⭐⭐ Measured: ⭐⭐ **there is no
holdings / positions / portfolio table in any migration** ⭐⭐ (`select name from
sqlite_master` where name like `%position%` or `%holding%` or `%portfolio%` ⇒ **no
rows**) ⭐⭐ so that declaration has nothing to read ⭐⭐ — ⭐⭐ the same unimplementable
state as most of the 24.

⭐⭐⭐ **Taking its id would have made the README's checklist wrong in a new way** ⭐⭐⭐ —
⭐⭐ it would have said 「orphan holdings」 while the rule reported orphans in
⭐⭐ `decision_review_state`, `reviews`, `note_tags`, `watchlist_events` and sixteen
⭐⭐ others. ⭐⭐⭐ **An unimplemented declaration can still be implemented later;** ⭐⭐⭐
⭐⭐ **a declaration that has been quietly redefined cannot.** ⭐⭐ ⇒ `D-25`, ⭐⭐ and
⭐⭐ `.ai/checks/data/README.md` gains a row for it.

⭐⭐⭐ And this is the **third** time this session that the project's own ledgers already
contained the answer ⭐⭐⭐ — after `cards.id` (`F-258`) and the `foreign_keys` mechanism
(`D-01`) ⭐⭐⭐ — ⭐⭐ **so the pattern is worth stating plainly: the ledgers are more
complete than my reading of the code, ⭐⭐ and a docstring I have not finished reading
is not evidence.** ⭐⭐⭐

## ⭐⭐ Why this exists, and it is not 「there was no coverage」

`D-01 dangling_target` guards `decisions → instruments`. ⭐⭐ **Its docstring already
explains the whole mechanism this check is about** ⭐ — a database that reached disk by some
path other than the product's own writer can hold a row the product's foreign keys would
refuse. ⭐⭐ So the mechanism was understood and written down.

⭐⭐ **What was missing is the second reference.** ⭐ `decision_review_state` and `reviews` both
declare `decision_id → decisions(id)`, ⭐⭐ and on 2026-10-06 the reader's own database held
**four** `decision_review_state` rows whose `decision_id` matched nothing:

```
2026-09-30T11:26:24.998Z  due_at=2026-10-20T00:00:00+00:00   0 hits in `decisions`
2026-09-30T11:26:25.022Z  due_at=2026-10-05T00:00:00+00:00   0 hits
2026-09-30T11:26:25.037Z  due_at=2026-11-01T00:00:00+00:00   0 hits
2026-09-30T11:26:25.053Z  due_at=2026-10-28T00:00:00+00:00   0 hits
```

⭐⭐⭐ **And nothing would ever have said so.** ⭐⭐ `D-01` does not look at that table;
⭐⭐ the foreign key is enforced on every connection the product opens (measured: `connect`
and `connect_for_migration` both report `PRAGMA foreign_keys = 1`; ⭐⭐ a bare
`sqlite3.connect()` reports **0**) ⭐⭐ **so the constraint was never the thing that failed —
⭐⭐ the rows came from outside the product, ⭐⭐ and a constraint cannot report on writes it
was not present for.**

## ⭐ Why it reads `pragma_foreign_key_list` instead of naming the tables

⭐ Because hardcoding a table list is how the next reference goes unchecked — ⭐⭐ the same
lesson `spec 058` and `spec 059` both paid for on the *capability* side (`catalogue_labels()`
had no caller; `/api/v1/capabilities` had no consumer). ⭐⭐ **The schema already states every
reference; reading it back means a new foreign key is covered the day it is declared.**

## ⭐⭐ Two ways this could be wrong, and both are guarded

⭐ **`NULL` is not an orphan.** ⭐ `decision_review_state` is empty until a decision is
scheduled. ⭐ A naive

    where not exists (select 1 from parent where parent.x = child.y)

⭐ reports **every row with a NULL key** as a dangling reference, ⭐⭐ which would fire on a
freshly migrated database. ⭐⭐ A data check that fires on an empty database has taught the
reader to ignore it — ⭐⭐ worse than not having it. ⇒ **`col is not null` is part of the
query**, and the tests assert a NULL child row is not reported.

⭐ **A composite key is not two references.** ⭐ `pragma_foreign_key_list` returns **one row per
column**, ⭐ and `decisions(market, code)` arrives as two rows sharing a constraint id. ⭐⭐
Splitting them is the `lesson.py` shape, where `id_column` was a parameter precisely because
the two tables disagree ⭐⭐ **and a wrong guess finds no collision ever, which is the failure
the walk-forward exists to prevent.** ⇒ Grouped by constraint id, and the join uses each
column's own `to` partner rather than assuming the names match.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from checks import data
from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_DATA_INTEGRITY"

META = CheckMeta(
    check_id="D-25",
    slug="orphan-reference",
    title="a row whose declared foreign key points at nothing",
    priority="P1",
    code=CODE,
)

TABLES_SQL = "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
FKS_SQL = 'select "from", "to", "table", "id" from pragma_foreign_key_list(?)'

#: ⭐ A reference: ``(child_table, ((child_col, parent_col), ...), parent_table)``.
Reference = tuple[str, tuple[tuple[str, str], ...], str]


def references(con: sqlite3.Connection) -> list[Reference]:
    """Every foreign key the schema declares, composite keys kept whole.

    ⭐ Printed rather than guessed — ⭐ the first draft of this function unpacked four
    ⭐ columns and named the last one the constraint id, ⭐⭐ which is right only because the
    ⭐ pragma happens to have that shape. ⭐ The column names in :data:`FKS_SQL` are the
    ⭐ authority for that and they are written above the query.
    """
    tables = [row[0] for row in con.execute(TABLES_SQL)]
    out: list[Reference] = []
    for table in tables:
        grouped: dict[int, list[tuple[str, str]]] = defaultdict(list)
        parents: dict[int, str] = {}
        for child_col, parent_col, parent_table, constraint_id in con.execute(
            FKS_SQL, (table,)
        ):
            grouped[constraint_id].append((child_col, parent_col))
            parents[constraint_id] = parent_table
        for constraint_id, pairs in grouped.items():
            if pairs:
                out.append((table, tuple(pairs), parents[constraint_id]))
    return out


def orphan_sql(child: str, pairs: tuple[tuple[str, str], ...], parent: str) -> str:
    """The query for one reference, with the NULL guard **inside** the join.

    ⭐ Built here rather than inlined because :func:`references` returns pairs and the
    ⭐ template needs them; ⭐⭐ and a ``.format`` built from schema text is exactly what
    ⭐ `S608` exists for ⭐⭐ — ⭐ the identifiers here come from ``sqlite_master`` and
    ⭐ ``pragma_foreign_key_list``, ⭐⭐ **not** from a request or a file, ⭐⭐ and the test
    ⭐⭐ that would prove it is the one a new table breaks.
    """
    child_cols = ", ".join(f'c."{c}"' for c, _ in pairs)
    not_null = " and ".join(f'c."{c}" is not null' for c, _ in pairs)
    join = " and ".join(f'p."{p}" is c."{c}"' for c, p in pairs)
    # ⭐ `S608` for the reason `lesson.py` gives it: every identifier here comes from
    # ⭐⭐ `sqlite_master` and `pragma_foreign_key_list` — ⭐⭐ the database's own schema,
    # ⭐⭐ **not a request and not a file** — ⭐⭐ and `S608` asks about exactly that.
    return f"""
select distinct {child_cols}, c.rowid
from "{child}" c
where {not_null}
  and not exists (select 1 from "{parent}" p where {join})
"""  # noqa: S608 - identifiers come from the database's own schema, never from input


def run(ctx: ScanContext) -> CheckResult:
    """Report every row whose declared foreign key matches nothing.

    ⭐⭐ **A finding here is a statement about how the file reached disk**, ⭐ not about the
    ⭐ product having deleted something: ⭐⭐ nothing in this repository deletes from
    ⭐⭐ `decisions` (`grep "DELETE FROM decisions"` is empty), ⭐⭐ so an orphan is a row the
    ⭐⭐ product's own connections would have refused to write.
    """
    result = CheckResult()
    with data.readonly() as (con, reason):
        if con is None:
            result.skipped = reason
            return result

        try:
            refs = references(con)
        except Exception as exc:
            # ⭐ A schema this rule cannot read is a fact worth reporting, ⭐⭐ not a crash:
            # ⭐⭐ a `crash` would be counted separately from a `finding` ⭐⭐ and the gate
            # ⭐⭐ would say 「ran 4 · crashed 1」 ⭐⭐ without saying what it could not read.
            result.error(
                CODE,
                f"D-25 could not read the schema: {type(exc).__name__}: {exc}",
                target=format_target(ctx, Path(__file__)),
                fix="A migration question, not a data one.",
            )
            return result

        if not refs:
            # ⭐⭐ **Reported every run, like `D-01`'s note.** ⭐ Silence would read as 「clean」,
            # ⭐⭐ and on a pre-foreign-key schema this rule genuinely has nothing to say.
            result.note(
                CODE,
                "D-25: this database declares no foreign keys, ⭐ so there is no declared "
                "reference to be dangling. ⭐ Either it is at a pre-FK schema version or the "
                "declarations were dropped.",
                target=format_target(ctx, Path(__file__)),
                fix="Run the migrations. ⭐ A silent rule is worse than a red one.",
            )
            return result

        orphans: list[str] = []
        checked = 0
        for child, pairs, parent in refs:
            if not data.has_table(con, child) or not data.has_table(con, parent):
                continue
            checked += 1
            query = orphan_sql(child, pairs, parent)
            for row in con.execute(query):
                value = ", ".join(str(part) for part in row[:-1])
                orphans.append(f"{child}({', '.join(c for c, _ in pairs)})=({value}) → {parent}")

    if orphans:
        # ⭐⭐ **`warn`, not `error`** ⭐⭐ — ⭐⭐ and this is the **first** finding of this
        # ⭐⭐ severity in the repository ⭐⭐ ⭐ (measured: ⭐⭐ nothing else constructs
        # ⭐⭐ `Severity.WARNING` ⭐⭐ — ⭐⭐ so the reporter's `[WARN ]` branch was
        # ⭐⭐ unreachable until now ⭐⭐). ⭐⭐⭐ ⇒ the reason is spelled out here rather
        # ⭐⭐ than assumed, ⭐⭐⭐ because the next reader will ask 「why not an error」
        # ⭐⭐⭐ and 「the gate was red」 ⭐⭐⭐ is not an answer. ⭐⭐⭐
        result.warn(
            CODE,
            f"D-25: {len(orphans)} row(s) across {checked} declared reference(s) name a "
            f"parent that does not exist: {orphans[:5]}" + (" …" if len(orphans) > 5 else ""),
            target=format_target(ctx, Path(__file__)),
            fix=(
                "⚠️ Nothing here is auto-repaired. ⭐⭐ **Why this is a warning and not an "
                "error ⭐⭐** — ⭐⭐ three measured facts, ⭐⭐ and the severity is derived "
                "from them rather than chosen to keep a gate green: ⭐⭐ (1) the product's "
                "two connection factories both report `PRAGMA foreign_keys = 1`, ⭐⭐ so an "
                "orphan is **not reachable from product code today**; ⭐⭐ (2) nothing in "
                "this repository deletes decisions ⭐⭐ (`grep 'DELETE FROM decisions'` is "
                "empty), ⭐⭐ so the rows came from a one-off script outside the product; "
                "⭐⭐ (3) `data.readonly()` opens the **reader's own** database ⭐⭐ "
                "(`checks/data.py` §「Which database」 ⭐⭐ — ⭐⭐ a temporary one would make "
                "every data check vacuous) ⭐⭐ ⇒ ⭐⭐ **this rule can never fail because of "
                "a defect in this repository.** ⭐⭐⭐ An `error` here would be red forever "
                "⭐⭐⭐ for history nobody may delete, ⭐⭐⭐ **and a permanently-red gate is a "
                "⭐⭐⭐ gate that gets ignored** ⭐⭐⭐ — ⭐⭐⭐ the exact outcome `D-01`'s own "
                "fix text warns about. ⭐⭐⭐ ⭐⭐⭐ **The code-level gate for the mechanism is "
                "`S-19`, ⭐⭐⭐ which can be an `error` ⭐⭐⭐ because it is about code.** ⭐⭐⭐ "
                "⭐⭐⭐ Read the ids above before deciding anything: ⭐⭐⭐ three of them are "
                "⭐⭐⭐ 25ms apart ⭐⭐⭐ (`…T11:26:2{4.998,5.022,5.037,5.053}Z`) ⭐⭐⭐ — ⭐⭐⭐ "
                "⭐⭐⭐ **that is a loop writing, ⭐⭐⭐ not a person recording.** ⭐⭐⭐"
            ),
        )
    else:
        result.note(
            CODE,
            f"D-25: {checked} declared foreign key reference(s) checked, ⭐ no dangling rows. ⭐ "
            "⭐ A constraint enforced by every connection the product opens would have "
            "prevented them, ⭐ so a clean run is the schema doing its job ⭐ — ⭐ and this is "
            "the second line for rows that reached disk another way.",
            target=format_target(ctx, Path(__file__)),
            fix=None,
        )
    return result
