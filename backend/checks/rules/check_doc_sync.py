"""S-12 — the rule list in the document and the rules in the code stay in step.

**Defect guarded:** ``.ai/checks/static/README.md`` §5, the "当前状态" table that
says which scripts exist. That table has already been wrong once: it listed
twelve checks and described zero implementations, and nothing failed. A
governance document that silently drifts from reality is worse than no document,
because it is believed.

Anti-pattern (forbidden)::

    # .ai/checks/static/README.md
    | **S-13** | `no-flaky-clock` | ... | 7.9 |     # described, never implemented
    # checks/rules/  — no module for S-13

Correct form::

    # the README row and the module exist together, or neither does
    checks/rules/no_flaky_clock.py   ->  META.check_id == "S-13"

Why a test cannot catch this: the check modules are dev tooling, not product
code, and their *existence* is not something any execution path reveals. A test
can import the registry and confirm it is non-empty; only a comparison against
the document can confirm the two lists agree.

Three comparisons, in both directions, plus the slugs:

* an id in the README with no rule → **error** (the document promises a guard
  that does not exist — this is the exact failure that prompted the rule);
* an id in the registry with no README row → **error** (an unregistered guard
  cannot be reviewed, and will be deleted as unexplained);
* a slug that differs between the two → **warning** (they will drift apart
  further otherwise).
"""

from __future__ import annotations

import re

from checks.framework import CheckMeta, CheckResult, ScanContext

CODE = "CHECK_DOC_DRIFT"

META = CheckMeta(
    check_id="S-12",
    slug="check-doc-sync",
    title="the rule list in the document matches the rules in the code",
    priority="P2",
    code=CODE,
)


DOC_PATH = ".ai/checks/static/README.md"

#: `| **S-01** | \`no-raw-http\` | ... |` — the first two cells of a rule row.
_ROW = re.compile(r"^\|\s*\*\*(?P<check_id>S-\d+)\*\*\s*\|(?P<rest>.*)\|\s*$", re.MULTILINE)

#: The slug, when the row has one. The P1 rows name the check in prose instead.
_SLUG = re.compile(r"`(?P<slug>[a-z][a-z0-9]*(?:-[a-z0-9]+)+)`")


def documented_rules(document: str) -> dict[str, str | None]:
    """``{"S-01": "no-raw-http", "S-07": None}`` from the README tables."""
    found: dict[str, str | None] = {}
    for match in _ROW.finditer(document):
        slug = _SLUG.search(match.group("rest"))
        found[match.group("check_id")] = slug.group("slug") if slug else None
    return found


def run(ctx: ScanContext) -> CheckResult:
    """Compare the documented rule list with the registry."""
    result = CheckResult()
    document = ctx.doc(DOC_PATH)
    if document is None:
        result.skipped = f"{DOC_PATH} not found — nothing to compare against"
        return result

    documented = documented_rules(document)
    implemented = {meta.check_id: meta for meta in ctx.registry}

    for check_id in sorted(set(documented) - set(implemented)):
        result.error(
            CODE,
            f"{DOC_PATH} lists `{check_id}` but no rule implements it",
            target=DOC_PATH,
            fix=f'Implement `checks/rules/*.py` with `META.check_id = "{check_id}"`, or '
            "remove the row. A documented guard that does not exist is the defect "
            "this rule was written for.",
        )
    for check_id in sorted(set(implemented) - set(documented)):
        result.error(
            CODE,
            f"rule `{check_id}` ({implemented[check_id].slug}) is not listed in {DOC_PATH}",
            target=f"backend/checks/rules/{implemented[check_id].slug.replace('-', '_')}.py",
            fix=f"Add a row for `{check_id}` to the matching priority table in {DOC_PATH}.",
        )
    for check_id in sorted(set(documented) & set(implemented)):
        slug = documented[check_id]
        if slug is not None and slug != implemented[check_id].slug:
            result.warn(
                CODE,
                f"`{check_id}` is called `{slug}` in {DOC_PATH} but "
                f"`{implemented[check_id].slug}` in code",
                target=DOC_PATH,
                fix="Make them identical; the slug is how the rule is referred to everywhere else.",
            )
    return result


__all__ = ["META", "run"]
