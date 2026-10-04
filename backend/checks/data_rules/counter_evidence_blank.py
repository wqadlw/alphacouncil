"""D-07 · a decision whose counter-evidence holds no readable content.

## ⭐⭐ What measurement said on 2026-10-04, and it changed this check twice

**First:** `decisions` carries `CHECK (length(trim(counter_evidence)) > 0)` ⭐ — ⭐ so a check
looking for an empty one seemed redundant ⭐ — ⭐ and the first version of this rule used
`trim(counter_evidence) = ''`, ⭐ the same function as the constraint.

**Then, with the foreign key satisfied so the CHECK was what answered:**

| value | schema | `trim()` sees it? |
|---|---|---|
| `''` | rejected | — |
| `'  '` | rejected | — |
| `'\t'` | **accepted** | ⭐ **no** |
| `'\n'` | **accepted** | ⭐ **no** |
| `' \t\n '` | **accepted** | ⭐ **no** |
| `'　'` (full-width space) | **accepted** | ⭐ **no** |
| `'\x0c'` (form feed) | **accepted** | ⭐ **no** |
| real text | accepted | no ⭐ and correctly so |

⭐⭐⭐ **So a decision whose entire case against itself is one tab is in the database right
now, and neither the schema's CHECK nor this rule's first version would have said anything.**

⭐ `trim()` removes spaces ⭐ and only spaces ⭐ — ⭐ SQLite's `replace()` is what removes
named characters, ⭐ and the predicate below names six. ⭐ **The constraint inherits `trim()`'s
blind spot** ⭐ and so did the check ⭐ — ⭐ which is why this file's comment says the check is
the second line and why the *first* line is reported in spec 054 §二 as needing a migration.
That migration is **not** in this change: ⭐ it edits a constraint guarding red line 4, ⭐ and
`constitution.md` requires the owner's nod for a red line's implementation constraint.

## Measured on the reader's own rows

    decisions rows = 5 · rows with no readable counter-evidence = 0

⚠️ Zero ⭐ — ⭐ and `test_data_rules.py` writes five rows the real database does not have ⭐
precisely so that this query has been observed to find something.
"""

from __future__ import annotations

from pathlib import Path

from checks import data
from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_DATA_INTEGRITY"

META = CheckMeta(
    check_id="D-07",
    slug="counter-evidence-blank",
    title="a decision whose counter-evidence holds no readable content",
    priority="P1",
    code=CODE,
)

#: ⭐ The characters a human would not call content. ⭐ Named one by one ⭐ — ⭐ because the
#: alternative is ``trim()`` ⭐ and `trim()` is exactly the bug this check exists to cover.
#: ⭐ The full-width space is here because a Chinese input method produces one from a keystroke
#: ⭐ that looks like it pressed nothing.
BLANKS = ("' '", "char(9)", "char(10)", "char(13)", "char(12)", "'　'")

EXPR = "counter_evidence"
for _blank in BLANKS:
    EXPR = f"replace({EXPR}, {_blank}, '')"

#: ⭐ ``length(...) = 0`` ⭐ and not ``= ''`` ⭐ because a value made *only* of whitespace is
#: ⭐ shorter than the string it came from ⭐ — ⭐ the length test is what makes 「有内容」 and
#: ⭐ 「有字符」 different questions.
#:
#: ⚠️ `S608` is suppressed on the line below. ⭐ The interpolated part is `EXPR` ⭐ — ⭐
#: assembled **at import time** from this module's own `BLANKS` ⭐ ⭐ a literal tuple of six
#: characters written in this file ⭐ ⭐ never from input ⭐ ⭐ a caller ⭐ ⭐ a row ⭐ ⭐ or an
#: environment variable. ⭐ There is nothing to inject ⭐ and the alternative ⭐ ⭐ spelling the
#: predicate out twice ⭐ ⭐ would let the two copies drift apart silently.
SQL = f"""
select id, market, code from decisions
where length({EXPR}) = 0
order by id
"""  # noqa: S608 - EXPR is built from BLANKS above, not from anything a caller supplies


def run(ctx: ScanContext) -> CheckResult:
    """Find decisions with nothing readable written against them."""
    result = CheckResult()
    with data.readonly() as (con, reason):
        if con is None:
            result.skipped = reason
            return result
        if not data.has_table(con, "decisions"):
            result.error(
                CODE,
                "D-07 cannot run: the database has no decisions table",
                target=format_target(ctx, Path(__file__)),
                fix="A migration question, not a data one.",
            )
            return result
        rows = list(con.execute(SQL))
    if rows:
        result.error(
            CODE,
            f"D-07: {len(rows)} decision(s) record no readable case against themselves: "
            f"{[f'{m}/{c}' for _, m, c in rows[:5]]}",
            target=format_target(ctx, Path(__file__)),
            fix="Red line 4's implementation constraint. ⚠️ MANUAL by construction ⭐ — "
            "the counter-evidence is the reader's own reasoning, ⭐ and a check that "
            "invented one would be inventing their thinking.",
        )
    return result
