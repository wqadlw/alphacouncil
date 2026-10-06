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
        # reviews (J3, spec 020; already required by constitution 5.4.1 as "the
        # review conclusions", implemented for real in migration 0006). Commented
        # here because the name collides with `card_reviews` below, and a decision
        # review is the only place the user records how they reasoned about an
        # outcome — editing one edits the evidence that the process was ever
        # honestly graded. ADR-0014: it is a separate table precisely so it never
        # writes back onto `decisions`.
        "reviews",
        # ⭐ `thesis_versions` ⭐ — ⭐ **no migration creates it yet, and that is deliberate.**
        # ⭐ Constitution 5.4.1 names the thesis history ⭐ ⭐ ADR-0013 designs it ⭐ ⭐ so the
        # ⭐ list records the intent before there is code to check ⭐ ⭐ and `test_storage.py`'s
        # ⭐⭐ `test_the_static_rule_still_expects_the_tables_that_do_not_exist_yet`
        # ⭐⭐ says so in as many words and pins the set to exactly this one name.
        # ⭐ When J2 lands ⭐⭐ the migration creates the table and that assertion becomes
        # ⭐⭐ `set()` ⭐⭐ which is the point of pinning it.
        "thesis_versions",
        "audit_log",
        "watchlist_events",
        "card_events",
        # card_reviews (K3, spec 018): a review is an event that happened to the
        # user's memory, and re-writing one would let a past recall be edited into
        # a better past recall — the same reason the other six tables are here.
        "card_reviews",
        # note_reviews (spec 028): the same argument, one step further. A card
        # review answers 「did I recall this claim?」 and a note review answers
        # 「do I still hold this view?」 — and the second question is the one the
        # product's thesis is built on. Editing a past answer would let a changed
        # mind be retrofitted into never having held the old one, which is exactly
        # the hindsight bias the whole record is meant to survive.
        "note_reviews",
        # lesson_reviews (spec 030): the same argument a third time, and the third
        # table to need it. A lesson review answers 「do I still hold what I
        # learned?」 — and like `note_reviews` it is the product's thesis rather
        # than a detail: a lesson is the reader's own account of a mistake, so
        # editing a past answer to it edits the evidence that they were ever
        # wrong, which is the one thing the record exists to keep.
        #
        # ⭐ It is also the ledger that makes 「这条为什么在队列上」 auditable: the
        # row `enrolled` is written by the enrolment red line 7 makes mandatory,
        # so the reason a lesson is on the queue is on the row rather than only in
        # a changelog nobody reads in six months.
        "lesson_reviews",
        # lessons (spec 030): the one that **is not a ledger**. A lesson is the
        # reader's own account of a mistake, and the whole no-`reset` argument in
        # spec 030 §2.1 rests on it being immutable — which was a convention until
        # these two triggers. ⭐ The failure they prevent is not hypothetical: an
        # `update_lesson` would have left FSRS's memory strength attached to text
        # that no longer exists, which is the exact bug spec 028 fixed for notes by
        # adding a third outcome. Here the answer is instead to forbid the edit.
        #
        # Listed in `APPEND_ONLY_TABLES` even though it holds no review rows, so
        # that the ledger's `append_only: true` and the guards on disk are
        # cross-checked against each other. A convention with no trigger is a
        # comment; a convention with a trigger plus this cross-check is enforced.
        "lessons",
        # financial_reports (spec 043, D4): the first table here that is **neither a
        # ledger nor anything the user wrote**. Its rows are rows a source published,
        # and the reason they cannot be rewritten is different from all the others:
        # an `UPDATE` on this table is not 「editing the past」, it is **making the past
        # say something we never saw** — and nothing about it looks like tampering. A
        # restatement arrives from the source with a **later `announced_at`** and is
        # inserted as a new row, which is why `announced_at` is part of the primary
        # key. ⭐ That is why 「append-only」 is the whole feature here: a table whose
        # primary key carries the announcement date cannot express an overwrite at all,
        # and the triggers make the same promise the key does.
        "financial_reports",
        # notifications_sent (spec 044): the first table here whose contents are **about
        # the reader rather than about the market**. ⭐ The deletion failure is not a lost
        # cache entry — ⭐ deleting a row makes the same criterion notify *again*, to
        # somebody who already dealt with it, ⭐ and that looks exactly like a bug while
        # being the program's version of nagging. ⭐ `sent_at` has no TTL either, because
        # 「you cannot un-hear something」 is not a cache property.
        "notifications_sent",
        # decision_scratch_events (spec 060): the same reason again, and the
        # sharpest version of it. 「这条是试验记录」 is an act the reader performed,
        # not a fact about the market, so overwriting the verb would rewrite what
        # they did and deleting the row would erase that they ever did it. The
        # state is the last row precisely so that no edit is needed to change it.
        "decision_scratch_events",
        # lesson_promotions (spec 030): **not** a review, and a different reason.
        # The other nine tables are histories of things that *happened to* the
        # reader. This one is a promise they made: 「这条教训我已经签成卡片了」. A
        # row that can be updated would let that promise be silently re-pointed at
        # a different card, and then `lesson_promotions` would say the card has a
        # provenance it no longer has — which is the same failure as a dangling
        # source on a card, reached from the other direction.
        #
        # The two UNIQUE constraints already make the *content* unchangeable (one
        # promotion per lesson, one lesson per card), so what append-only adds is
        # that the row cannot be removed either: un-promoting would leave a card
        # whose declared origin no longer exists.
        "lesson_promotions",
        # index_constituents (spec 052): the first table here that holds **neither a
        # ledger nor anything the reader wrote nor anything about the market** — it
        # holds *a fact about the world, at the resolution the source publishes it*.
        # ⭐ And the reason it cannot be rewritten is the sharpest version of the
        # `financial_reports` argument: an `UPDATE` here does not look like editing a
        # note, it looks like **correcting a roster**. The failure is not 「somebody
        # tampered with the past」 ⭐ **it is that a quietly-corrected roster produces a
        # perfectly plausible wrong answer about who was in an index**, which is the
        # one question this product's own PIT tables exist to answer.
        #
        # ⭐ The `UPDATE` temptation is specifically large here, and that is why the
        # trigger message says 「上次扫错了就再扫一次」: a re-scan is a **new
        # observation** with its own `fetched_at` in the primary key, so the honest
        # repair exists and does not require an overwrite.
        "index_constituents",
        # index_universe_sweeps (spec 052): the same argument, one level up, and a
        # **stronger** one. Its rows are not facts about the index ⭐ **they are facts
        # about what we knew and when** — 「我们知道的最后一天」. ⭐ Editing a row here
        # turns 「我们当时就知道」 into 「我们当时还不知道」 after the fact, ⭐ which is
        # the one thing `data-sources.md:137` calls a 僵尸报价 in a different costume:
        # silence, no error, and a reader who cannot tell.
        "index_universe_sweeps",
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
    # ⭐⭐⚠️ **A finding lived here for part of 2026-10-04 and was removed ⭐ by a test.**
    #
    # ⭐ The measurement was right: ⭐ `APPEND_ONLY_TABLES` holds **15** names ⭐ and **14**
    # ⭐ were created by any migration ⭐ ⭐ `thesis_versions` being the fifteenth. ⭐ A first
    # ⭐ draft of this rule reported that as an error ⭐ ⭐ removed the entry ⭐ ⭐ and shipped a
    # ⭐ test to keep the two in step.
    #
    # ⚠️⭐ **And the measurement was the wrong thing to conclude from.** ⭐ The forward
    # ⭐ declaration is deliberate ⭐ ⭐ documented ⭐ ⭐ and pinned by `test_storage.py`'s
    # ⭐ `test_the_static_rule_still_expects_the_tables_that_do_not_exist_yet` ⭐ which
    # ⭐ ⭐ says that a declaration about a table not yet created is the point ⭐ ⭐ so the
    # ⭐ list cannot be quietly narrowed. ⭐ So the silence is correct ⭐ ⭐ and reporting
    # ⭐ it would have been the defect.
    #
    # ⭐⭐⭐ **How it went wrong, because the shape is the lesson:** ⭐ I read this rule ⭐
    # ⭐ `.ai/status.md` ⭐ ⭐ ADR-0013 ⭐ ⭐ `constitution.md` ⭐ ⭐
    # ⭐ `.ai/memory/decisions.md` ⭐ ⭐ five places ⭐ ⭐ and not the tests ⭐ ⭐ which
    # ⭐ ⭐ is where the rationale lived ⭐ ⭐ including the one sentence
    # ⭐⭐ that would have stopped me. ⭐⭐ **A decision recorded only in a test's
    # ⭐⭐ docstring is a decision nobody reading the code finds** ⭐⭐ and that goes into
    # ⭐⭐ `.ai/memory` ⭐⭐ but it did not license the edit ⭐⭐ the test was already
    # ⭐⭐ doing its job.
    #
    # ⭐ And the shape is the round's own subject ⭐ ⭐ a claim nobody checked ⭐⭐ asserted
    # ⭐ five times over ⭐⭐ with a docstring ⭐⭐ a comment block ⭐⭐ a test file ⭐⭐ a
    # ⭐⭐ spec section and a `why_not` string ⭐⭐ before running the suite that held the
    # ⭐⭐ answer.
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
