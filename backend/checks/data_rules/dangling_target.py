"""D-01 · a decision that names an instrument the record does not have.

## ⭐⭐ The sentence this file's first draft got wrong, and why it was wrong

The draft said:

    「It is the only reference-integrity check in the set, and the schema does not provide
      one: SQLite does not enforce foreign keys unless PRAGMA foreign_keys = ON and even then
      no declaration exists for it in any migration.」

# ⭐⭐ **Both halves are false, and I asserted them without measuring.** ⭐ Measured
2026-10-04, on a freshly migrated database:

- ⭐ ``PRAGMA foreign_keys`` is **1** on the connections the product opens ⭐ — ⭐
  `storage/db.py` turns it on ⭐ — ⭐ not off
- ⭐ ``decisions`` declares a **composite foreign key** ``(market, code) -> instruments`` ⭐
- ⭐ **17 tables** declare at least one foreign key
- ⭐⭐ **and inserting a decision for an absent instrument is refused** ⭐ — ⭐
  ``FOREIGN KEY constraint failed`` ⭐ — ⭐ on ``on_delete=NO ACTION``, ⭐ so deleting the
  instrument is refused too

⇒ ⭐⭐ **The dangling reference D-01 looks for is a state this database cannot hold.** ⭐
Measured: rows D-01 would report on the reader's own database = **0** ⭐, ⭐ and not because
the data is clean ⭐ — ⭐ because the state is unreachable.

# ⚠️⭐ **That is not a reason to keep the check** ⭐ — ⭐ `README` rule 3 requires a fixture, ⭐
and a fixture for this one has to insert a row the schema forbids. ⭐ So D-01 stays in the
registry ⭐ **and reports the finding that matters**, ⭐ which is the one about this file:

# ⭐⭐ **A gate in the gate list whose declared subject is unreachable is worse than no gate**
# ⭐ — ⭐ because it reads as coverage of 「悬空引用」 ⭐ while the coverage is a foreign key in
``0001_initial.up.sql`` ⭐ and has been all along. ⭐ Reporting that is the check's only
remaining job, ⭐ and it does it on every run whether or not there is a dangling row.

## The second line, and it is a real one

# ⭐ The FK is enforced **by the product's connections**. ⭐ A restore from a backup, ⭐ or a
# file that reached disk by some path other than the product's own writer, ⭐ **can hold the
# dangling row** ⭐ and the product's FK would never have noticed.

# ⭐⭐⭐ **Measured 2026-10-06 — ⭐ and this paragraph was wrong about one of its three
# ⭐⭐ examples.** ⭐ It used to say:
#
# > A restore from a backup, a migration run — `connect_for_migration` — and this check's own
# > handle — `sqlite3.connect(..., mode=ro)` — all open with `foreign_keys` **off**, because
# > SQLite's default is off and only `storage/db.py` changes it.
#
# ⭐⭐ **Measured, on a freshly migrated database:**
#
# | how it was opened                     | `PRAGMA foreign_keys` |
# |---------------------------------------|------------------------|
# | `storage.db.connect`                  | **1** |
# | `storage.db.connect_for_migration`    | **1** |
# | ⭐ a bare `sqlite3.connect()`          | ⭐⭐ **0** |
#
# ⇒ ⭐⭐ **So `connect_for_migration` is NOT one of the ways to write a dangling row.** ⭐ A
# ⭐ migration run cannot produce one, ⭐ and `dev.py demo`'s seeder — ⭐ which seeds through
# ⭐ `connect_for_migration` — ⭐⭐ **cannot produce one either.**
#
# ⭐⭐⭐ **And this paragraph cost a real measurement.** ⭐ spec 060's first draft reasoned
# ⭐⭐ that the four orphan `decision_review_state` rows in the reader's own database
# ⭐⭐ (ids `…2{4.998,5.022,5.037,5.053}Z`, 25ms apart) had been written by a connection
# ⭐⭐ with foreign keys off, ⭐⭐ **and it named `connect_for_migration` as that
# ⭐⭐ connection** ⭐⭐ — ⭐ **on the strength of this paragraph**, ⭐ not on a measurement.
# ⭐⭐ The paragraph was wrong, ⭐⭐ and the conclusion drawn from it was wrong with it.
# ⭐⭐ The surviving conclusion is *narrower* and is now measured: ⭐⭐ **both of the product's
# ⭐⭐ connection factories enforce the constraint, ⭐⭐ so those rows can only have come
# ⭐⭐ from outside the product.**
#
# ⭐⭐ **What did not change is the sentence this file exists to make**, ⭐ and it is stated
# ⭐⭐ here rather than in a changelog because it is the one a reader needs:
# ⭐⭐ **a file that reached disk through a connection with `foreign_keys` off holds rows
# ⭐⭐ this database would otherwise refuse to hold** ⭐⭐ — ⭐⭐ and nothing inside the
# ⭐⭐ product would ever say so. ⭐⭐ `D-02` now says so about
# ⭐⭐ `decision_review_state → decisions`, ⭐⭐ which is where four such rows were found.
"""

from __future__ import annotations

from pathlib import Path

from checks import data
from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_DATA_INTEGRITY"

META = CheckMeta(
    check_id="D-01",
    slug="dangling-target",
    title="a decision that names an instrument the record does not have",
    priority="P1",
    code=CODE,
)

#: ⚠️ The declaration used to say `decisions.target_id`. ⭐ There is no such column ⭐ — the
#: instrument is named by `(market, code)` on both sides, ⭐ and that is what this joins on ⭐
#: ⭐ the same pair the foreign key is declared on.
SQL = """
select d.id, d.market, d.code
from decisions d
where not exists (
    select 1 from instruments i where i.market = d.market and i.code = d.code
)
order by d.id
"""

FOREIGN_KEY_SQL = """
select count(*) from pragma_foreign_key_list('decisions')
where "table" = 'instruments' and "from" in ('market', 'code')
"""


def run(ctx: ScanContext) -> CheckResult:
    """Report dangling decisions, and say out loud that the schema already prevents them.

    # ⭐ **Both, every run.** ⭐ A run with nothing to report still states the foreign key, ⭐
    because the thing worth knowing is not 「there are no dangling rows」 ⭐ — ⭐ that is the
    database doing its job ⭐ — ⭐ it is 「this check is standing behind a constraint that has
    been there since migration 0001, ⭐ and the declaration never said so」.
    """
    result = CheckResult()
    with data.readonly() as (con, reason):
        if con is None:
            result.skipped = reason
            return result
        for table in ("decisions", "instruments"):
            if not data.has_table(con, table):
                result.error(
                    CODE,
                    f"D-01 cannot run: the database has no {table} table",
                    target=format_target(ctx, Path(__file__)),
                    fix="A migration question, not a data one.",
                )
                return result
        declared = int(con.execute(FOREIGN_KEY_SQL).fetchone()[0])
        rows = list(con.execute(SQL))

    if declared:
        result.note(
            CODE,
            f"D-01: the schema declares {declared} foreign key column(s) from "
            f"`decisions` to `instruments`, ⭐ so a dangling reference is a state this "
            f"database refuses to hold. ⭐ This check is the second line for a file that "
            f"reached disk without `PRAGMA foreign_keys = ON` ⭐ — ⭐ and the declaration's "
            f"`decisions.target_id` sentence is wrong on top of that ⭐ (there is no such "
            f"column; the pair is `(market, code)`). ⭐ {len(rows)} row(s) found now.",
            target=format_target(ctx, Path(__file__)),
            fix="Either close D-01 and let the foreign key be the whole story, ⭐ or keep "
            "it as the restore-path check and say so in `.ai/checks/data/README.md`. ⭐ "
            "⭐ Keeping it without saying so is what produced this warning.",
        )
    # ⭐⭐ **`if`, not `elif`, ⭐ and that is the whole fix.** ⭐ `declared` is 2 on every
    # ⭐ database this product makes ⭐ ⭐ so under `elif` the row branch was unreachable ⭐ ⭐
    # ⭐ and a dangling reference would have gone unreported ⭐ ⭐ forever ⭐ ⭐ while the test
    # ⭐ ⭐ that was supposed to catch it ⭐ ⭐ failed with `['info']` ⭐ ⭐ and was read as a
    # ⭐ ⭐ fixture problem ⭐ ⭐ because the fixture was the newer half.
    if rows:
        result.error(
            CODE,
            f"D-01: {len(rows)} decision(s) name an instrument that is not in `instruments`: "
            f"{[f'{m}/{c}' for _, m, c in rows[:5]]}",
            target=format_target(ctx, Path(__file__)),
            fix="⚠️ Nothing here is auto-repaired: the decision is the reader's own writing "
            "(README rule 5), ⭐ so this is MANUAL by construction. ⭐ And note the shape: "
            "⭐ a dangling row with **no** foreign key declared means this file came from "
            "somewhere other than the product's own writer.",
        )
    return result
