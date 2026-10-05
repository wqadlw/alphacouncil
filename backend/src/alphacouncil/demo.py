"""A seeded library that is unmistakably not the reader's own. (spec 057)

## Why this exists

Measured 2026-10-05 on the reader's real database::

    instruments 2 · watchlist_events 8 · decisions 5
    cards 0 · notes 0 · reviews 0 · lessons 0

⭐ **The knowledge layer is empty**, and that layer is the whole difference between this
product and a P&L log — the external survey found the entire English trading-journal
category P&L-first *by construction*, and AlphaCouncil's constraints are what makes it
different. So the review queue, the note recall and the lesson queue open empty every day,
⭐ **not because they are broken but because there has never been anything to review.**

## ⭐ The one guarantee in this file

:func:`demo_database_path` is a **subdirectory** of the real one, and :func:`refuse_to_overwrite`
raises if anyone asks this module to seed the real path.

⚠️ **Everything else here is a prompt, not a guarantee.** The banner (``ALPHACOUNCIL_DEMO``)
can be forgotten; a filename can be renamed. This function is the layer that **fails loudly**,
and constitution §0.2 requires exactly that: 「能不能把这条规则从 ① 移到 ③ 或 ④？能移就必须移」.

## ⭐ Why the seed goes through the domain functions

Because otherwise the schedule is fiction. ``note_recall.enroll`` and ``record_review``
call the real FSRS scheduler, so 「下次 2026-10-03」 is a **computed due date**, not a string
somebody typed. ⭐ The one-shot script that produced the README screenshots did this and was
then deleted (`F-140`), which is why those screenshots cannot be regenerated from the repo —
this module is the version that stays.

## ⭐ Why the copy obeys red line 1 word for word

`S-03 no-prediction-field` scans the whole tree, so a seed sentence carrying a price target
or a directional forecast turns the gate red — and **a demo library must not be the reason a
gate is red**. ``tests/unit/test_demo_library.py`` pins this rather than trusting the author.

⚠️ **This docstring had to be reworded too, for the same reason** (see the comment above
``_NOTES``): `S-03` reads string literals **including comments**, ⭐ so the first draft —
which quoted the banned words in order to say they were banned — failed the very rule it
was describing. ⭐ Three of this file's paragraphs exist because a gate disagreed with me,
which is about the right number of paragraphs for a seeder.
"""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from alphacouncil.core.config import default_database_path
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.card import CardDraft, CardOrigin, CardStatus, ClaimType
from alphacouncil.domain.decision import (
    ComparisonOperator,
    Decision,
    DecisionAction,
    KillCriterion,
)
from alphacouncil.domain.note import Link, LinkKind, NoteDraft
from alphacouncil.domain.review import Outcome, Review
from alphacouncil.domain.scheduling import ReviewRating
from alphacouncil.domain.watchlist import WatchlistEvent, WatchlistEventKind
from alphacouncil.models.market import AssetType, Market, Symbol
from alphacouncil.storage import db as dbmod
from alphacouncil.storage import migrate as migmod
from alphacouncil.storage.repositories import cards as cards_repo
from alphacouncil.storage.repositories import decisions as decisions_repo
from alphacouncil.storage.repositories import note_recall as recall_repo
from alphacouncil.storage.repositories import notes as notes_repo
from alphacouncil.storage.repositories import reviews as reviews_repo
from alphacouncil.storage.repositories import scheduling as sched_repo
from alphacouncil.storage.repositories import watchlist as watchlist_repo

__all__ = [
    "DemoSeeded",
    "demo_database_path",
    "refuse_to_overwrite",
    "seed",
]


def demo_database_path() -> Path:
    """Where the demo library lives: a **subdirectory** of the real one.

    ⭐ A subdirectory rather than a sibling filename, because a sibling invites
    ``alphacouncil-demo.db`` → renamed to ``alphacouncil.db`` by somebody in a hurry.
    A directory is a little harder to confuse with a file.
    """
    return default_database_path().parent / "demo" / "alphacouncil.db"


def refuse_to_overwrite(path: Path) -> None:
    """Refuse to seed the reader's real database. **This is the guarantee.**

    ⚠️ Not a warning: it raises. A warning in a developer tool is a line that scrolls past,
    and the consequence of getting this wrong is writing fabricated decisions into the only
    copy of somebody's investment record — which red lines 3, 13 and 15 and
    ``agent-guide.md``'s 「不替用户写决策记录」 all exist to prevent.

    The comparison is on the **resolved** path so that ``./alphacouncil.db`` and the real
    one cannot both slip through as "different strings".
    """
    resolved = Path(path).expanduser().resolve()
    real = default_database_path().expanduser().resolve()
    if resolved == real:
        raise ValueError(
            f"refusing to seed the reader's real database at {real}. "
            "spec 057: demo data belongs in `demo_database_path()` only — writing here "
            "would put fabricated decisions into the reader's own record."
        )


#: Every table the demo is supposed to fill, and therefore every table whose emptiness makes
#: the demo a failure rather than a small demo. ⭐ **This list is the contract**: `seed`
#: refuses to return success unless every name here has at least one row, so adding a table
#: here turns 「that queue is empty again」 into a loud error instead of a mystery.
_DEMO_TABLES: tuple[str, ...] = (
    "instruments",
    "watchlist_events",
    "decisions",
    "cards",
    "notes",
    "reviews",
    "note_reviews",
    "card_schedule",
    "note_schedule",
)


class DemoSeeded:
    """What actually landed, counted rather than assumed.

    ⭐ **Spec 057 §六 lists 「播种『成功』但库是空的」 as a way this lies.** A seeder that
    returns ``None`` and lets the caller print 「done」 is exactly that. So this carries
    counts, :func:`seed` verifies every table in :data:`_DEMO_TABLES`, and :attr:`measured`
    keeps the read-back numbers so the caller prints what is **in the file** rather than what
    the writer believed it wrote.
    """

    def __init__(self) -> None:
        self.instruments = 0
        self.watchlist_events = 0
        self.decisions = 0
        self.cards = 0
        self.notes = 0
        #: A decision review — the `reviews` table, what the retrospective quadrant reads.
        self.decision_reviews = 0
        #: A note recall — the `note_reviews` table, what FSRS wrote.
        #:
        # ⭐ **Two counters, not one.** The first version had a single `reviews` and
        # incremented it from both `reviews_repo.record` and `recall_repo.record_review`,
        # ⭐ so it reported 4 while the two tables held 1 and 6. ⭐ `dev.py demo` printed
        # `reviews 4 (in file: 1)` and that mismatch is the only reason this was caught —
        # ⭐ the 「measured」 column exists precisely so a counter that has drifted from the
        # file cannot hide, and it did its job on the code that produced it.
        self.note_reviews = 0
        #: Row counts read back from the finished file. ⭐ Empty until :func:`seed` fills it,
        #: because a tally the seeder produced about itself is a claim, not a measurement.
        self.measured: dict[str, int] = {}

    def total(self) -> int:
        return (
            self.instruments
            + self.watchlist_events
            + self.decisions
            + self.cards
            + self.notes
            + self.decision_reviews
            + self.note_reviews
        )

    def as_lines(self) -> list[str]:
        """What the command prints — ⭐ **the measured rows, not the self-reported ones.**

        The two columns are different numbers on purpose. ⭐ `notes 6` is what the seeder
        believes it wrote; ⭐ `notes 6 (in file: 6)` is what a reader can go and check. ⭐
        When they disagree, this line is the only place that says so, ⭐ and it has already
        earned its keep — see :attr:`note_reviews`.
        """
        pairs = (
            ("instruments", self.instruments),
            ("watchlist_events", self.watchlist_events),
            ("decisions", self.decisions),
            ("cards", self.cards),
            ("notes", self.notes),
            ("reviews", self.decision_reviews),
            ("note_reviews", self.note_reviews),
        )
        lines = [
            f"  {name:<20}{claimed:<6}(in file: {self.measured.get(name, '?')})"
            for name, claimed in pairs
        ]
        # The two schedules have no self-reported counter, because ⭐ `enroll` reports how
        # many rows it touched and that number was never kept. ⭐ Printing only the measured
        # side is the honest option; inventing a claimed side to match the layout would be
        # the other one.
        for name in ("card_schedule", "note_schedule"):
            lines.append(f"  {name:<20}{'-':<6}(in file: {self.measured.get(name, '?')})")
        return lines


# --------------------------------------------------------------------- content
#
# ⭐ **Every string below obeys red line 1**: no price target, no prediction, no advice.
# `tests/unit/test_demo_library.py` asserts that rather than trusting this comment.
#
# ⚠️⚠️ **And this comment had to be reworded once, which is the honest evidence for the
# rule.** The first version named the two banned words while *explaining* that they are
# banned, and `S-03 no-prediction-field` failed on it — ⭐ `CHECK_PREDICTION_FIELD: string
# literal containing ... is prediction/prescription-shaped`. ⭐ **`S-03` scans string
# literals including comments**, so prose *about* the rule trips the rule. ⭐ That is the
# same shape as `F-244` (a docstring naming ruff's suppression marker literally, which then
# suppresses the very line it was describing), and the fix is the same: reword the prose,
# do not loosen the check.
#
# ⭐ And this comment needed it twice: the first reword still contained the marker's own
# name, and ruff read *that* as a directive on this line. ⭐ Writing about a suppression
# mechanism is itself a suppression hazard, which is worth knowing once rather than twice.
#
# The three instruments are real A-share codes so the daily bars resolve; ⭐ **the claims
# are invented** and every one of them is a statement about a mechanism rather than about a
# price, which is the only kind of sentence a demo can carry without becoming a tip.

_MOUTAI = Symbol(market=Market.SH, code="600519", asset_type=AssetType.STOCK)
_CMB = Symbol(market=Market.SH, code="600036", asset_type=AssetType.STOCK)
_CATL = Symbol(market=Market.SZ, code="300750", asset_type=AssetType.STOCK)

_NOTES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "渠道库存是白酒的先行指标",
        "渠道库存周转天数连续三个季度下降，通常领先报表两个季度。\n\n"
        "跟踪方法：经销商库存 + 批价走势 + 打款节奏。批价与库存同向恶化时，"
        "报表端的收入还会好看一段时间。",
        ("白酒", "方法"),
    ),
    (
        "毛利率连续三年高于 90% 说明什么",
        "高毛利本身不是结论。⭐ 要问的是它来自定价权还是成本优势 —— "
        "前者需要品牌被反复选择，后者需要规模效应不被对手打断。\n\n"
        "这两者的可逆性完全不同。",
        ("白酒", "估值"),
    ),
    (
        "批价与出厂价之间那道差",
        "批价是渠道愿意付的价，出厂价是厂家愿意发的价。两者的差是渠道的账，"
        "而这个账最终会回到厂家的报表上 —— 只是时间未知。",
        ("白酒",),
    ),
    (
        "零售银行护城河来自负债端",
        "存款成本低于同业，资产端收益率相差不多，这就是护城河。\n\n"
        "要跟踪的是存款结构里活期占比的变化 —— 它反映的是客户有没有在换银行。",
        ("银行", "方法"),
    ),
    (
        "净息差收窄的两种原因",
        "一是资产端收益率下行，二是负债端成本上行。两者的应对完全不同，"
        "而报表把它们合并成一行。",
        ("银行",),
    ),
    (
        "产能利用率比产能更值得看",
        "产能是计划，利用率是事实。⭐ 扩产公告只能告诉你计划了什么，"
        "利用率告诉你计划有没有被市场接住。",
        ("新能源", "方法"),
    ),
)

_CARDS: tuple[tuple[str, str, str], ...] = (
    (
        "渠道库存领先报表",
        "白酒渠道深度调研",
        "https://example.com/demo/baijiu-channel-2024",
    ),
    (
        "高毛利来自定价权",
        "白酒公司年报对比",
        "https://example.com/demo/baijiu-margin-2024",
    ),
    (
        "存款成本是银行护城河",
        "商业银行年度披露摘要",
        "https://example.com/demo/bank-nim-2024",
    ),
    (
        "利用率比产能诚实",
        "动力电池产业链跟踪",
        "https://example.com/demo/battery-utilisation-2024",
    ),
)

_DECISIONS: tuple[tuple[Symbol, DecisionAction, str, str, KillCriterion], ...] = (
    (
        _MOUTAI,
        DecisionAction.BUY,
        "批价企稳且渠道库存降到近三年低位，报表的收入压力应该已经释放得差不多了。",
        "批价仍在下跌，说明渠道还在去库存；上一轮同样的判断错了 9 个月。",
        KillCriterion(
            metric="close",
            operator=ComparisonOperator.LT,
            threshold=1280.0,
            as_of=date(2026, 12, 31),
        ),
    ),
    (
        _CMB,
        # ⚠️ **`DecisionAction` has no `WATCH`** (BUY/ADD/HOLD/TRIM/EXIT), and it has no
        # `WATCH` because it describes a *position*, which is a concept this product has no
        # table for yet (D2 持仓 is unstarted). ⭐ `HOLD` is the closest true statement —
        # 「keeping this in view」 — and ⭐ **the demo does not get a ninth action invented
        # to make its sentence nicer.** The kill criterion is what carries the meaning.
        DecisionAction.HOLD,
        "存款成本持续低于同业，净息差收窄的幅度应该小于市场担心的程度。",
        "如果活期存款占比下降，负债端成本会先于资产端上行。",
        KillCriterion(
            metric="close",
            operator=ComparisonOperator.LT,
            threshold=34.0,
            as_of=date(2026, 12, 31),
        ),
    ),
)


def seed(database_path: Path, *, now: datetime | None = None) -> DemoSeeded:
    """Create the demo library at ``database_path``. **Refuses the real database.**

    Idempotent in the only sense that matters: ⭐ **it removes an existing demo library
    first**, so running it twice gives the same library rather than doubling it. ⭐ It never
    touches anything outside ``database_path``.
    """
    refuse_to_overwrite(database_path)

    moment = now or datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        stale.unlink(missing_ok=True)

    # ⭐⭐ **The connection is closed on every path, including the failing ones** — and that
    # second clause is the whole reason this is a separate function.
    #
    # The first version closed the connection at the *end* of a 150-line body, which handles
    # the success path and nothing else. ⭐ `TestTheModuleDoesNotLie` then made a write fail
    # on purpose and the leak showed up: a `ResourceWarning: unclosed database` that pytest
    # escalates to a failure.
    #
    # ⭐ **Why that is not a tidiness complaint.** On Windows an open SQLite handle keeps the
    # file locked, so a *failed* seed leaves the demo database locked ⭐ — and the next
    # `dev.py demo` dies in `stale.unlink()` with `PermissionError`, before it can try
    # again. ⭐ A seeder whose failure bricks its own command is worse than one that fails
    # cleanly, so this is the property being bought.
    with contextlib.closing(dbmod.connect_for_migration(path)) as connection:
        migmod.apply(connection, database_path=path, migrations=migmod.load_migrations())
        return _fill(connection, moment)

    # ⚠️ Unreachable, and that is the point: ⭐ **`return` is inside the `with`**, so the
    # close happens before the caller sees a tally. A version that assigned the result and
    # fell through to a `close()` at the bottom would reopen the exact hole, ⭐ which is
    # why the structure is this way round rather than the tidier-looking other way round.


def _fill(connection: sqlite3.Connection, moment: datetime) -> DemoSeeded:
    """Write the library into an already-open, already-migrated connection.

    Split out of :func:`seed` only so the connection's lifetime is owned by one `with`
    block. ⭐ The body has no cleanup responsibility of its own, and must not grow one.
    """
    tally = DemoSeeded()

    # ---- watchlist: two instruments, with reasons (red line: a reason is not a note) ----
    for symbol, reason in (
        (_MOUTAI, "渠道库存降到近三年低位；跟踪批价与打款节奏。"),
        (_CMB, "存款成本持续低于同业；跟踪净息差与活期占比。"),
        (_CATL, "利用率比产能更早反映需求；跟踪月度装机与排产。"),
    ):
        with dbmod.transaction(connection):
            watchlist_repo.append(
                connection,
                WatchlistEvent(
                    kind=WatchlistEventKind.ADDED, symbol=symbol, reason=reason
                ),
            )
            tally.watchlist_events += 1
    tally.instruments = 3

    # ---- notes: the layer that measured zero rows on the reader's database ----
    note_ids: list[str] = []
    for index, (title, body, tags) in enumerate(_NOTES):
        with dbmod.transaction(connection):
            note_id = notes_repo.create(
                connection,
                NoteDraft(
                    title=title,
                    body=body,
                    tags=tags,
                    links=(),
                    symbols=(),
                    as_of=date(2026, 10, 5),
                ),
                # ⭐ `utc_millis`, not `.isoformat()`. ⭐ The first version passed
                # `isoformat()`, which yields a `+00:00` suffix, and the schema's
                # `notes_created_at_check` demands exactly
                # `strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at` ⇒
                # `IntegrityError: CHECK constraint failed`. ⭐ The CHECK is the constraint
                # doing its job; the fix is the codebase's own stamper, not a looser format.
                now=utc_millis(moment - timedelta(days=30 * (len(_NOTES) - index))),
            ).note.id  # ⭐ `NoteRow.note.id`, not `NoteRow.id` — printed, not guessed
            note_ids.append(note_id)
            tally.notes += 1

    # ⭐ Two links, so backlinks have something to point at — the knowledge graph is a
    # feature (regressions/0021) and a demo with no links would understate the product.
    with dbmod.transaction(connection):
        notes_repo.add_link(
            connection,
            note_ids[1],
            Link(
                to_kind=LinkKind.NOTE,
                to_id=note_ids[0],
                to_title="渠道库存是白酒的先行指标",
            ),
        )
        notes_repo.add_link(
            connection,
            note_ids[4],
            Link(
                to_kind=LinkKind.NOTE,
                to_id=note_ids[3],
                to_title="零售银行护城河来自负债端",
            ),
        )

    # ---- cards: a source is mandatory (provenance rule), so every one carries one ----
    #
    # ⭐ Each card gets its own `captured_at`, one day apart, for two reasons and the
    # second one is the reason this was ever a bug. `card_id` is minted from the stamp,
    # so four cards written in the same millisecond collide on the primary key. ⭐ That is
    # now fixed in `cards.py` (it was a deferred "pending product decision" — spec 057),
    # but **a seeder that stamps every row identically is testing the collision path by
    # accident**, ⭐ and a demo whose four cards claim the same capture moment is also a
    # worse demo: the knowledge layer's whole point is a claim's provenance *including when
    # you learned it*. Distinct stamps make the demo true and keep the walk-forward honest.
    card_ids: list[str] = []
    for index, (content, source_title, source_url) in enumerate(_CARDS):
        with dbmod.transaction(connection):
            card_id = cards_repo.create(
                connection,
                CardDraft(
                    content=content,
                    claim_type=ClaimType.SUPPORTING,
                    source_url=source_url,
                    source_title=source_title,
                    origin=CardOrigin.USER_WRITTEN,
                    priority=3,
                    status=CardStatus.ACTIVE,
                ),
                now=utc_millis(moment - timedelta(days=40 - 7 * index)),
            ).id
            card_ids.append(card_id)
            tally.cards += 1

    # ---- decisions: reason + counter-evidence + a structured kill criterion ----
    for index, (symbol, action, rationale, counter, criterion) in enumerate(_DECISIONS):
        with dbmod.transaction(connection):
            decision_id = decisions_repo.append(
                connection,
                Decision(
                    action=action,
                    symbol=symbol,
                    rationale=rationale,
                    counter_evidence=counter,
                    kill_criteria=(criterion,),
                ),
            ).id
            tally.decisions += 1

        # A review slot due in the past, so the retrospective queue has something real.
        with dbmod.transaction(connection):
            reviews_repo.schedule(
                connection,
                decision_id,
                due_at=moment - timedelta(days=20 - 10 * index),
                now=moment - timedelta(days=120),
            )

    # ---- one completed review, so the four-quadrant surface has a verdict on screen ----
    with dbmod.transaction(connection):
        first = decisions_repo.list_all(connection)[0].id
        reviews_repo.record(
            connection,
            first,
            # ⭐ `Review` carries `decision_id` as its first positional argument — measured
            # (`domain.review.Review.__init__`), ⭐ and the second version of this file
            # got a `TypeError` for omitting it.
            Review(
                decision_id=first,
                process_score=4,
                outcome=Outcome.GOOD,
                note="渠道库存确实降到了低位。",
            ),
            now=moment - timedelta(days=5),
        )
        tally.decision_reviews += 1

    # ---- ⭐ FSRS via the product's own domain functions, so the due dates are computed ----
    #
    # ⭐ **`tally.note_reviews` is incremented per `record_review` call, and the first
    # version incremented it once per note instead.** That made the tally read 3 while the
    # table held 6, ⭐ and the 「measured」 column caught it — `reviews 4 (in file: 1)` on
    # the command's own output is what exposed it. ⭐ Worth recording as the second time
    # the claimed/measured split paid for itself in this one file: ⭐ a single counter for
    # two tables, and a counter placed outside the loop that owns it.
    for index, note_id in enumerate(note_ids[:3]):
        with dbmod.transaction(connection):
            recall_repo.enroll(connection, note_id, now=moment - timedelta(days=14))
        with dbmod.transaction(connection):
            recall_repo.record_review(
                connection,
                note_id,
                ReviewRating.HARD if index == 0 else ReviewRating.GOOD,
                now=moment - timedelta(days=10 - index),
            )
            tally.note_reviews += 1
        with dbmod.transaction(connection):
            recall_repo.record_review(
                connection,
                note_id,
                ReviewRating.GOOD,
                now=moment - timedelta(days=3),
            )
            tally.note_reviews += 1

    for card_id in card_ids[:2]:
        with dbmod.transaction(connection):
            sched_repo.enroll(connection, card_id, now=moment - timedelta(days=7))

    connection.commit()

    # ⭐ **Count, never assume** (spec 057 §六). A seeder that returns success for an empty
    # library is the failure this class of tool has.
    measured = _count_rows(connection)
    tally.measured = measured
    #
    # ⭐ **Every name in `_DEMO_TABLES`, not just the notes.** A queue the demo exists to
    # fill, found empty, means the demo did not do its one job — and the alternative is a
    # reader opening an empty page and concluding the product is broken.
    empty = sorted(name for name, rows in measured.items() if rows <= 0)
    if empty:
        raise RuntimeError(
            "demo seeding reported success but these tables are empty or unreadable: "
            + ", ".join(f"{name}={measured[name]}" for name in empty)
        )
    return tally


def _count_rows(connection: sqlite3.Connection) -> dict[str, int]:
    """Row counts read back from the file, so 「seeded」 is a measurement.

    ⭐ **Every table the seeder claims to fill, not one of them.** The first version
    returned all eight and `seed` looked at `notes` alone, ⭐ which is a mechanism built
    and then not used — the same defect as a guard that checks the wrong object (`F-255`).
    `:func:`_DEMO_TABLES` is what ties the two together: `seed` verifies every name in it.

    ⚠️ **A table that cannot be read is `-1`, not `0`.** The distinction is the whole point:
    `0` means 「present and empty」 and `-1` means 「not there」, ⭐ and collapsing them would
    turn a missing table into a passing check — a migration that did not run would look like
    an empty queue, which is precisely the shape of failure this whole module exists
    because of.
    """
    out: dict[str, int] = {}
    for table in _DEMO_TABLES:
        try:
            # ⭐ `S608` here for the same reason `lesson.py` gives it: the interpolation is a
            # **literal from `_DEMO_TABLES`, a fixed tuple in this file** — ⭐ there is no
            # caller-supplied value anywhere on this path, which is the whole of what S608
            # asks about. `
            row = connection.execute(
                f"SELECT count(*) FROM {table}"  # noqa: S608 - table name is a literal in this module
            ).fetchone()
            out[table] = -1 if row is None else int(row[0])
        except sqlite3.Error:
            out[table] = -1
    return out
