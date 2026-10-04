"""Forward declarations on the append-only list ⭐ — ⭐ and why this file exists at all.

## ⭐⭐⭐ What this file was first, and why that was wrong

First draft: ⭐ **every table on `APPEND_ONLY_TABLES` is created by a migration** ⭐ — ⭐ with a
docstring explaining that the fifteenth name ⭐ ⭐ `thesis_versions` ⭐ ⭐ was never created by
any migration ⭐ ⭐ and that the rule was 「green about a table it cannot see」. ⭐ It also removed
the entry and added a finding to `check_append_only_triggers.run`.

⭐⭐⭐ **All of that was wrong, and `tests/unit/test_storage.py` said so at line 698.**

    def test_the_static_rule_still_expects_the_tables_that_do_not_exist_yet(self):
        「Documents the gap rather than letting it look like agreement.」
        「**The ledger had been right about a table that did not exist yet**, ⭐ which is
          the whole reason a forward declaration is worth keeping: ⭐ it records the intent
          before there is code to check, ⭐ so the rule cannot be quietly narrowed later.」
        assert missing == {"thesis_versions"}

⇒ ⭐⭐ So the silence is **correct**, ⭐ the practice is deliberate ⭐ ⭐ documented ⭐ ⭐ and
pinned to exactly one name. ⭐ Reporting it would have been the defect.

## ⭐ And the one real thing the measurement found

⭐ Reading the rule ⭐ ⭐ `.ai/status.md` ⭐ ⭐ ADR-0013 ⭐ ⭐ `constitution.md` ⭐ ⭐
`.ai/memory/decisions.md` ⭐ ⭐ five places ⭐ ⭐ told me nothing about that ⭐ ⭐ and **the
rationale was in a test's docstring** ⭐ ⭐ where someone reading the code does not look.

⭐⭐ **That is a genuine gap and it is not this file's job to close** ⭐ ⭐ because the test
already holds the decision and a second copy of it would rot separately ⭐ ⭐ — ⭐ the exact
mistake `TestGateVerdictRules`' own docstring warns about ⭐ ⭐ 「a test that re-implements the
rule is a second rule」. ⭐ It goes into `.ai/memory` as an observation about where this
repository keeps decisions, ⭐ and here it stays a measurement.

## ⭐⭐ So what is left, and it is worth something

The forward declaration is **informal**: ⭐ `test_storage.py` pins the *set* ⭐ ⭐
``missing == {"thesis_versions"}`` ⭐ ⭐ which catches a table vanishing ⭐ ⭐ but says nothing
about a table **arriving** undeclared ⭐ ⭐ ⭐ an author who adds a name to
`APPEND_ONLY_TABLES` for a table no migration creates ⭐ ⭐ gets a passing suite ⭐ ⭐ and the
next person's reading of that list is wrong.

⇒ This file makes the declaration **explicit and separate** ⭐ ⭐ `FORWARD_DECLARED`` ⭐ ⭐ and
asserts the two sets partition the list ⭐ ⭐ so adding a forward declaration is a line in
**this** file ⭐ ⭐ visible in review ⭐ ⭐ next to the one that explains why each one exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from checks.rules.check_append_only_triggers import (
    _BEFORE_DELETE,
    _BEFORE_UPDATE,
    _CREATE_TABLE,
    APPEND_ONLY_TABLES,
    strip_sql_comments,
)
from checks.scan import ScanContext

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
CTX = ScanContext(repo_root=REPO_ROOT)


#: ⭐⭐ **The names on `APPEND_ONLY_TABLES` that no migration creates yet** ⭐ ⭐ each with the
#: reason it is there ⭐ ⭐ so that adding a name to this set is a decision somebody wrote down
#: ⭐ rather than an accident in a frozenset.
FORWARD_DECLARED: dict[str, str] = {
    "thesis_versions": (
        "constitution 5.4.1 names the thesis history; ADR-0013 designs the SCD-2 table. "
        "⭐ `.ai/status.md` records J2 as not started ⭐ — ⭐ so this is a promise, not a "
        "⭐ forgotten migration. ⭐ Pinned by `test_storage.py`'s "
        "⭐ `test_the_static_rule_still_expects_the_tables_that_do_not_exist_yet` ⭐ ⭐ which "
        "⭐ asserts this set is exactly `{`thesis_versions`}` ⭐ ⭐ and says why: a declaration "
        "⭐ about a table that does not exist yet is the point ⭐ ⭐ so the list cannot be "
        "⭐ quietly narrowed."
    ),
}


def _schema_files(ctx: ScanContext) -> list[Path]:
    files = ctx.files_with_suffix(ctx.backend, ".sql")
    files += ctx.python_files(ctx.backend / "migrations")
    return files


def _created_tables(ctx: ScanContext) -> set[str]:
    """Every table any migration creates ⭐ — ⭐ the rule's own regexes ⭐ ⭐ not a second
    parser ⭐ ⭐ because a measurement taken with a different parser than the rule uses is a
    measurement of the parser."""
    created: set[str] = set()
    for path in _schema_files(ctx):
        text = strip_sql_comments(ctx.text(path))
        created |= {m.group("name").lower() for m in _CREATE_TABLE.finditer(text)}
    return created


class TestForwardDeclarationsAreDeclaredHere:
    def test_every_declaration_is_a_name_the_list_carries(self) -> None:
        extra = sorted(set(FORWARD_DECLARED) - APPEND_ONLY_TABLES)
        assert extra == [], (
            f"declared forward but not on the append-only list: {extra} ⭐ — ⭐ remove it, "
            f"or add the name to the list with its triggers"
        )

    def test_the_two_files_that_hold_this_decision_agree(self) -> None:
        """⭐⭐ **The non-redundant assertion, and the only reason this file is not a copy.**

        ⭐ `test_storage.py` pins the set with ``missing == {"thesis_versions"}`` ⭐ ⭐ this file
        ⭐ explains what each name is for ⭐ ⭐ and the two were written for different reasons ⭐ ⭐
        ⭐ so they can drift ⭐ ⭐ and nothing would notice.

        ⭐⭐ **Read out of that file rather than asserted beside it.** ⭐ A second hard-coded
        ⭐⭐ copy of the set is a third place to update ⭐ ⭐ and `TestGateVerdictRules`' own
        ⭐⭐ docstring in this repository already names that mistake ⭐ — ⭐⭐ 「a test that
        ⭐⭐ re-implements the rule is a second rule, ⭐⭐ and it rots separately」 ⭐ — ⭐⭐ so
        ⭐⭐ this parses the other file's assertion ⭐ ⭐ and a change there fails here.
        """
        source = (
            REPO_ROOT / "backend" / "tests" / "unit" / "test_storage.py"
        ).read_text(encoding="utf-8")
        found = re.search(r"assert missing == \{([^}]*)\}", source)
        assert found, "test_storage.py no longer pins the missing set ⭐ — ⭐ update this file"
        theirs = set(re.findall(r'"([^"]+)"', found.group(1)))
        assert theirs == set(FORWARD_DECLARED), (
            f"test_storage.py pins {sorted(theirs)} ⭐ — ⭐ this file declares "
            f"{sorted(FORWARD_DECLARED)} ⭐ — ⭐ one of the two is stale"
        )

    def test_every_declaration_is_still_actually_a_forward_declaration(self) -> None:
        """⭐ ⭐ **The guard on the guard.** ⭐ When J2 lands and the migration creates the
        ⭐ table ⭐ ⭐ this name stops being a forward declaration ⭐ ⭐ and leaving it here
        ⭐ ⭐ would make the file's name a lie ⭐ ⭐ while every assertion in it still passed ⭐ ⭐
        ⭐ ⭐ because ``test_storage.py`` would have gone red first ⭐ ⭐ and nobody reads two
        ⭐ ⭐ files when one is red."""
        created = _created_tables(CTX)
        stale = sorted(set(FORWARD_DECLARED) & created)
        assert stale == [], (
            f"declared as forward but a migration creates it now: {stale} ⭐ — ⭐ remove it "
            f"from FORWARD_DECLARED ⭐ ⭐ which is the last step of landing the feature"
        )

    def test_every_declaration_says_why(self) -> None:
        """⭐ A set of names with empty strings beside them is a list ⭐ ⭐ not a rationale."""
        for name, why in FORWARD_DECLARED.items():
            assert len(why) > 60, f"{name} has no reason, only a name"

    def test_the_regexes_still_see_the_tables_the_migrations_create(self) -> None:
        """⭐ If ``_CREATE_TABLE`` stopped matching ⭐ ⭐ every test in this file would pass
        ⭐ ⭐ for the wrong reason ⭐ ⭐ and would pass the same wrong way on the name that is
        ⭐ ⭐ genuinely forward-declared ⭐ ⭐ ⭐ which is the one case the file is about."""
        created = _created_tables(CTX)
        migrations = CTX.files_with_suffix(CTX.backend, ".sql")
        assert created, f"{len(migrations)} migration file(s) read, zero tables recognised"
        unrecognised = [
            m.group(1)
            for path in migrations
            for m in re.finditer(
                r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([A-Za-z_]\w*)",
                strip_sql_comments(CTX.text(path)),
                re.I,
            )
            if m.group(1).lower() not in created
        ]
        assert sorted(set(unrecognised)) == [], (
            f"created but `_CREATE_TABLE` does not recognise them: "
            f"{sorted(set(unrecognised))} ⭐ — ⭐ the rule would stop seeing them silently"
        )

    def test_the_created_tables_all_carry_both_triggers(self) -> None:
        """⭐ The half ``run()`` checks ⭐ ⭐ stated here as a repository invariant so a failure
        ⭐ ⭐ names the table instead of a file. ⭐ Forward-declared names are excluded ⭐ ⭐
        ⭐ which is the whole difference between this file and the wrong first draft ⭐ ⭐
        ⭐ there was nothing to exclude."""
        guarded: dict[str, set[str]] = {}
        for path in _schema_files(CTX):
            text = strip_sql_comments(CTX.text(path))
            for match in _BEFORE_UPDATE.finditer(text):
                guarded.setdefault(match.group("name").lower(), set()).add("update")
            for match in _BEFORE_DELETE.finditer(text):
                guarded.setdefault(match.group("name").lower(), set()).add("delete")
        short = {
            table: sorted({"update", "delete"} - guarded.get(table, set()))
            for table in sorted(APPEND_ONLY_TABLES - set(FORWARD_DECLARED))
            if guarded.get(table, set()) != {"update", "delete"}
        }
        assert short == {}, f"created and listed but not fully guarded: {short}"
