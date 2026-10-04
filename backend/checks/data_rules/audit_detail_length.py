"""D-22 · an audit row whose detail carries content rather than a description of an action.

## What this guards

`constitution.md` 6.3 requires the audit trail to record **做了什么** ⭐ — ⭐ and the README's
D-22 says the same shape: 「审计日志含敏感内容 ⭐ 6.3（应只有『做了什么』，无『内容是什么』）」.

⭐ Of the twenty-four declared checks this is **one of only two** whose column *and* table
were right the first time ⭐ — ⭐ and it is the only one of the three implemented tonight
whose subject the schema does **not** already police. ⭐ That is not a compliment to D-22 ⭐
— ⭐ see below ⭐ — ⭐ it is the reason it is the only one that can fire.

## ⭐⭐ The threshold, and the ceiling above it that the declaration never mentions

`audit_log` carries `CHECK (detail IS NULL OR length(detail) <= 500)`.

⭐⭐ **So the schema caps this column at 500 characters, ⭐ and this check's threshold is 200.**
⭐ A band of 201..500 exists where the schema says fine and this check objects ⭐ — ⭐ which is
the band the rule is for ⭐ — ⭐ and above 500 the schema refuses the row ⭐ and this check never
sees it. ⭐ **The declaration 「审计日志含敏感内容」 ⭐ promises to catch sensitive content ⭐ and
the schema makes the worst case unreachable before the rule is consulted.** ⭐ The rule is
therefore a *mid-band* judgement, ⭐ not a safety net, ⭐ and saying 「500」 in a query would
have been a check that can never fire.

## Why 200, stated so it can be argued with

⭐ There is no principled value here ⭐ — ⭐ it is the point where 「which action was taken」
becomes 「what was written」. ⭐ A short note can be either. ⭐ The number is named, ⭐
documented, and exported ⭐ — ⭐ and `test_data_rules.py` pins one row *at* it and one *past*
it ⭐ so the boundary is a test and not a recollection.

## Measured on the reader's own rows

    audit_log rows = 0 · over the threshold = 0

⚠️ **Zero, and the table is empty** ⭐ — ⭐ so this check has **never run against anything**
on this machine ⭐ and its fixture matters more than the other two's: ⭐ a check whose subject
has zero rows has had zero chances to be wrong.
"""

from __future__ import annotations

from pathlib import Path

from checks import data
from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_DATA_INTEGRITY"

META = CheckMeta(
    check_id="D-22",
    slug="audit-detail-length",
    title="an audit row whose detail is long enough to be content, not an action",
    priority="P2",
    code=CODE,
)

#: ⭐ The judgement, named so it can be argued with ⭐ — ⭐ not a constant derived from
#: ⭐ anything. ⭐ **And it sits below the schema's own cap of 500 on purpose:** ⭐ the band
#: ⭐ between them is the only place this rule has anything to say.
DETAIL_LIMIT = 200

#: ⭐ The limit is a bound parameter, ⭐ not an f-string ⭐ — ⭐ `S608` is right that
#: ⭐ string-built SQL is a shape worth refusing, ⭐ and a rule that introduces one to express
#: ⭐ a constant has shown the shape is cheap. ⭐ `?` also survives someone raising the limit
#: ⭐ without touching the query text.
SQL = """
select id, action, length(detail) from audit_log
where length(detail) > ?
order by id
"""


def run(ctx: ScanContext) -> CheckResult:
    """Find audit rows carrying something longer than an action description."""
    result = CheckResult()
    with data.readonly() as (con, reason):
        if con is None:
            result.skipped = reason
            return result
        if not data.has_table(con, "audit_log"):
            result.error(
                CODE,
                "D-22 cannot run: the database has no audit_log table",
                target=format_target(ctx, Path(__file__)),
                fix="A migration question, not a data one.",
            )
            return result
        rows = list(con.execute(SQL, (DETAIL_LIMIT,)))
    if rows:
        result.error(
            CODE,
            f"D-22: {len(rows)} audit row/rows carry more than {DETAIL_LIMIT} characters of "
            f"detail, e.g. {[(a, n) for _, a, n in rows[:3]]}",
            target=format_target(ctx, Path(__file__)),
            fix="Constitution 6.3: the audit trail records what was done. ⭐ If a row needs "
            "that much text, ⭐ the content belongs in the record the action was taken on. "
            f"⚠️ Above {DETAIL_LIMIT + 1}..500 the schema still accepts it ⭐ and above 500 it "
            "refuses it ⭐ — ⭐ so this band is the rule's whole reach.",
        )
    return result
