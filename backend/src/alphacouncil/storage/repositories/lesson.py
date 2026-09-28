"""Lessons: the repository (spec 030 · J5).

## What this module is for

Red line 7 says **每条教训必须生成一条调度项（FSRS）** — every lesson must produce a
scheduling item. The recorded gap was 「机制有了，每条教训自动生成还没有」, and the
word doing the work is **自动**. Today a card is scheduled because the reader asked;
a note is enrolled because the reader asked. Nothing in the product creates a
scheduling item on its own.

⭐ So :func:`record_lesson` is the first write in this codebase that ends with a
scheduling item **unconditionally**. Not "and then usually", not "and then if the
caller remembers" — the next statement, in the same transaction, with no branch
between them. That is the entire mechanism, and it is why this is a repository
function rather than two calls a route could forget to pair.

## The atomicity is the point, and it is tested backwards

If the ``lesson_schedule`` insert fails, the lesson must not exist either. That is
not a nice property to have, it is the property the red line *is*: 「每条教训生成一
条调度项」 is a statement about the database, not about the code path that happened
to run. So ``tests/unit/test_lessons.py`` blocks the schedule insert with a trigger
and asserts the lesson write **fails and leaves nothing behind** — which is a
stronger claim than asserting the schedule row is present, and the only one that
would notice a future refactor that moved the insert into a different transaction.

## Promotion is a separate, later act, and it demands a source

:meth:`promote_lesson` writes a ``card`` and one ``lesson_promotions`` row. The
source is **required**, and that is derived rather than invented: a card's
provenance is a URL, a lesson has none, so 「我拿不出出处」 means this is a lesson and
not yet a card. It is already saved either way — nothing is lost by declining to
sign it, which is the point.

The promotion does **not** touch the lesson's schedule. Red line 7 must not have an
escape hatch: 「转了卡所以不用再复习了」 is exactly the kind of branch that turns a
guarantee back into a suggestion, and it would be invisible.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any, cast

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.card import CardDraft, CardOrigin, CardStatus, ClaimType
from alphacouncil.domain.lesson import (
    Lesson,
    LessonAlreadyPromotedError,
    LessonNotFoundError,
    LessonPromotion,
    LessonRecordOutcome,
    LessonReviewMissingError,
    LessonReviewRow,
    LessonScheduleRow,
    validate_content,
    validate_promotion_source,
)
from alphacouncil.domain.scheduling import (
    ReviewRating,
    ScheduleState,
    as_utc_iso,
    parse_due,
    rating_to_fsrs,
    require_utc,
    state_of,
)
from alphacouncil.storage.db import require_open_transaction
from alphacouncil.storage.repositories import cards

__all__ = [
    "due_lessons",
    "get_lesson",
    "get_promotion",
    "list_lessons_for_review",
    "promote_lesson",
    "record_from_review",
    "record_lesson",
    "record_review",
]


# ── SQL ─────────────────────────────────────────────────────────────────────

_INSERT_LESSON = """
INSERT INTO lessons (lesson_id, review_id, content, created_at)
VALUES (?, ?, ?, ?)
"""

_SELECT_LESSON = """
SELECT lesson_id, review_id, content, created_at
FROM lessons WHERE lesson_id = ?
"""

_SELECT_LESSONS_FOR_REVIEW = """
SELECT lesson_id, review_id, content, created_at
FROM lessons
WHERE review_id = ?
ORDER BY created_at ASC, lesson_id ASC
"""

_INSERT_SCHEDULE = """
INSERT INTO lesson_schedule
    (lesson_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_SCHEDULE = """
SELECT lesson_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at
FROM lesson_schedule WHERE lesson_id = ?
"""

_SELECT_DUE = """
SELECT lesson_id, fsrs_card_id, state_json, state, due_at, enrolled_at, updated_at
FROM lesson_schedule
WHERE due_at <= ?
ORDER BY due_at ASC, lesson_id ASC
LIMIT ?
"""

_INSERT_REVIEW = """
INSERT INTO lesson_reviews
    (id, lesson_id, outcome, rating, reviewed_at, duration_ms,
     from_due_at, to_due_at, from_state, to_state)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_UPDATE_SCHEDULE_AFTER_REVIEW = """
UPDATE lesson_schedule SET state_json = ?, state = ?, due_at = ?, updated_at = ?
WHERE lesson_id = ?
"""

_SELECT_PROMOTION = """
SELECT lesson_id, card_id, promoted_at
FROM lesson_promotions WHERE lesson_id = ?
"""

_INSERT_PROMOTION = """
INSERT INTO lesson_promotions (lesson_id, card_id, promoted_at)
VALUES (?, ?, ?)
"""


#: How far past the requested millisecond to look for a free id. 1000 is one
#: second; past that two rows are no longer "the same moment", and a review row is
#: evidence of *when the reader acted*. Inherited from ``note_recall`` (which
#: documents the same hazard) rather than reinvented with a different number.
_ID_COLLISION_LIMIT = 1_000


# ── helpers ─────────────────────────────────────────────────────────────────


def _new_id(
    connection: sqlite3.Connection, prefix: str, table: str, id_column: str
) -> str:
    """A millisecond-stamped id that is not already taken.

    Walks forward rather than raising on collision, for the reason
    ``note_recall._new_id`` gives: a test suite does write several rows in one
    millisecond, and losing a review row loses **evidence** — while the only
    alternative to walking forward is overwriting one, which is the failure the
    whole append-only discipline exists to prevent.
    """
    base = int(time.time() * 1000)
    for offset in range(_ID_COLLISION_LIMIT):
        candidate = f"{prefix}_{base + offset}"
        # ⭐ `id_column` is a parameter because the two tables disagree: `lessons`
        # keys on `lesson_id` and `lesson_reviews` on `id`. The first version
        # assumed `id` and raised `no such column` on every lesson, which is a
        # louder failure than the one worth worrying about — a version that
        # checked the *wrong* table would have found no collision ever, and that is
        # the failure this function exists to prevent.
        taken = connection.execute(
            f"SELECT 1 FROM {table} WHERE {id_column} = ?",  # noqa: S608 - both are literals at every call site
            (candidate,),
        ).fetchone()
        if taken is None:
            return candidate
    raise RuntimeError(
        f"无法为这一行生成唯一 id：同一毫秒内已有多达 {_ID_COLLISION_LIMIT} 条。"
    )


def _fresh_fsrs_card(
    fsrs_card_id: int, *, due: datetime
) -> tuple[int, str, ScheduleState, datetime]:
    """A brand-new FSRS card, due at ``due``, described in our terms.

    Third copy of this function (``cards``, ``note_recall``, and now lessons) and a
    real duplication. The card version returns a card-named tuple; the note version
    returns a note-named one; a shared version would have to return four values
    against a caller-supplied shape, which trades a duplicated body for a
    parameterised one. The *body* is identical because ``fsrs`` takes an int either
    way. ⭐ Copied rather than abstracted, and recorded here so the fourth copy is a
    decision rather than a drift.
    """
    import fsrs

    card = fsrs.Card(card_id=fsrs_card_id)
    payload = dict(card.to_dict())
    payload["card_id"] = fsrs_card_id
    payload["due"] = as_utc_iso(due)
    return (
        fsrs_card_id,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        state_of(payload),
        due,
    )


def _row_to_lesson(row: sqlite3.Row) -> Lesson:
    return Lesson(
        lesson_id=row["lesson_id"],
        review_id=row["review_id"],
        content=row["content"],
        created_at=parse_due(row["created_at"]),
    )


def _row_to_schedule(row: sqlite3.Row) -> LessonScheduleRow:
    return LessonScheduleRow(
        lesson_id=row["lesson_id"],
        fsrs_card_id=int(row["fsrs_card_id"]),
        payload=row["state_json"],
        state=ScheduleState(row["state"]),
        due_at=parse_due(row["due_at"]),
        enrolled_at=parse_due(row["enrolled_at"]),
        updated_at=parse_due(row["updated_at"]),
    )


def _stamp(moment: datetime) -> str:
    """A stamp-column timestamp: UTC, in the one spelling the schema asserts.

    ⭐ **Not** ``as_utc_iso``, which is the *due* columns' format. Every
    ``created_at`` / ``enrolled_at`` / ``updated_at`` / ``reviewed_at`` column
    asserts ``strftime('%Y-%m-%dT%H:%M:%fZ', x) = x``, so those two formatters are
    not interchangeable and the difference is not cosmetic — the schema's own
    ordering checks compare these strings.
    """
    return utc_millis(moment)


def _next_fsrs_id(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(
            "SELECT COALESCE(MAX(fsrs_card_id), 0) + 1 FROM lesson_schedule"
        ).fetchone()[0]
    )


def _review_id_for_decision(connection: sqlite3.Connection, decision_id: str) -> str:
    """The review a lesson would attach to, or say there is none.

    ⭐ The check is for a **row**, not for a score. ``reviews.process_score`` is
    ``NOT NULL`` and ``reviewed_at`` is ``NOT NULL``, so a review row exists only
    once the reader has actually written it — the *schedule* lives in
    ``decision_review_state`` and is a different thing entirely. Attaching a lesson
    to a scheduled-but-unwritten review would date it to a moment that has not
    happened, which is the one thing the whole timestamp discipline exists to stop.
    """
    row = connection.execute(
        "SELECT id FROM reviews WHERE decision_id = ? ORDER BY reviewed_at DESC, id DESC LIMIT 1",
        (decision_id,),
    ).fetchone()
    if row is None:
        raise LessonReviewMissingError(
            f"决策 {decision_id} 还没有写复盘 —— 教训是复盘教出来的东西，"
            "先把那次复盘写完再记教训。"
        )
    return str(row["id"])


# ── recording ───────────────────────────────────────────────────────────────


def record_from_review(
    connection: sqlite3.Connection,
    decision_id: str,
    content: str,
    *,
    now: datetime | None = None,
) -> tuple[Lesson, LessonScheduleRow]:
    """Turn a decision's review into a lesson. **One transaction, three rows.**

    The order matters and is not arbitrary: the lesson goes in first so the schedule
    row has a parent to reference, and the ledger row goes in last so that a failure
    anywhere above rolls the whole thing back rather than leaving an enrolment with
    no record of why it happened.

    :func:`record_lesson` holds the three writes; this only resolves the review. It
    exists so the route does not have to know that ``lessons`` stores a ``review_id``
    while the reader thinks in terms of a decision.
    """
    require_open_transaction(connection, operation="lesson.record_from_review")
    review_id = _review_id_for_decision(connection, decision_id)
    return record_lesson(connection, review_id, content, now=now)


def record_lesson(
    connection: sqlite3.Connection,
    review_id: str,
    content: str,
    *,
    now: datetime | None = None,
) -> tuple[Lesson, LessonScheduleRow]:
    """Write the lesson, enrol it, and record the enrolment. All or nothing.

    ⭐⭐ **This function is red line 7.**

    The three inserts are consecutive and unconditional. There is no code path that
    writes a lesson without a scheduling item, because there is no code path that
    writes a lesson and then *decides* about the scheduling item — the decision was
    made when the red line was written down. That is the difference between
    「每条教训自动生成」 being a promise the code keeps and being a step the code
    performs.

    ⭐ It does **not** go through a check-then-insert, deliberately. The obvious
    shape is 「if not already scheduled: schedule it」, and that shape turns the
    guarantee into a conditional — one exception, one code path, and the red line
    now has a clause nobody wrote down. A fresh lesson has no schedule row, so the
    condition is always true, and a condition that is always true is a branch that
    only exists to be wrong.

    The lesson is due **immediately** (``learning``, due = this moment), and that is
    a product judgement rather than a default: a lesson is by definition something
    the reader has already been wrong about once, so it is the one thing in this
    product that has earned an immediate revisit. A card they typed a minute ago has
    not.
    """
    moment = require_utc(now or datetime.now(UTC), field="now")
    body = validate_content(content)
    require_open_transaction(connection, operation="lesson.record_lesson")

    exists = connection.execute(
        "SELECT 1 FROM reviews WHERE id = ?", (review_id,)
    ).fetchone()
    if exists is None:
        raise LessonReviewMissingError(
            f"复盘 {review_id} 不存在 —— 教训要挂在一次真实写下的复盘上。"
        )

    lesson_id = _new_id(connection, "lesson", "lessons", "lesson_id")
    connection.execute(_INSERT_LESSON, (lesson_id, review_id, body, _stamp(moment)))

    # ⭐ No `if` between the lesson and its schedule. See the docstring.
    fsrs_id = _next_fsrs_id(connection)
    _fsrs, payload, state, due = _fresh_fsrs_card(fsrs_id, due=moment)
    stamp = _stamp(moment)
    connection.execute(
        _INSERT_SCHEDULE,
        (lesson_id, fsrs_id, payload, state.value, as_utc_iso(due), stamp, stamp),
    )

    # And the reason it is on the queue, on the row rather than only in a changelog.
    # ⭐ No rating and no duration: the reader has not recalled anything yet, and
    # recording a grade on their behalf would dress a forced enrolment as a
    # remembered fact.
    connection.execute(
        _INSERT_REVIEW,
        (
            _new_id(connection, "lesson_review", "lesson_reviews", "id"),
            lesson_id,
            LessonRecordOutcome.ENROLLED.value,
            None,
            stamp,
            None,
            stamp,
            stamp,
            state.value,
            state.value,
        ),
    )

    lesson = Lesson(
        lesson_id=lesson_id,
        review_id=review_id,
        content=body,
        created_at=moment,
    )
    schedule = LessonScheduleRow(
        lesson_id=lesson_id,
        fsrs_card_id=fsrs_id,
        payload=payload,
        state=state,
        due_at=due,
        enrolled_at=moment,
        updated_at=moment,
    )
    return lesson, schedule


# ── reading ─────────────────────────────────────────────────────────────────


def get_lesson(connection: sqlite3.Connection, lesson_id: str) -> Lesson:
    row = connection.execute(_SELECT_LESSON, (lesson_id,)).fetchone()
    if row is None:
        raise LessonNotFoundError(f"教训 {lesson_id} 不存在。")
    return _row_to_lesson(row)


def list_lessons_for_review(
    connection: sqlite3.Connection, review_id: str
) -> tuple[Lesson, ...]:
    rows = connection.execute(_SELECT_LESSONS_FOR_REVIEW, (review_id,)).fetchall()
    return tuple(_row_to_lesson(row) for row in rows)


def due_lessons(
    connection: sqlite3.Connection,
    *,
    as_of: datetime,
    limit: int = 50,
) -> tuple[tuple[LessonScheduleRow, Lesson], ...]:
    """The queue, oldest due first, each row with the lesson it belongs to.

    ⭐ **No title, no count, no ordering by anything the reader chose** — the same
    three refusals ``note_recall.due_notes`` makes and for the same reasons. Ties
    break on ``lesson_id`` so the order is stable between calls: a queue that
    reshuffles on every open makes 「我处理过了」 feel futile.
    """
    require_utc(as_of, field="as_of")
    rows = connection.execute(_SELECT_DUE, (as_utc_iso(as_of), limit)).fetchall()
    out: list[tuple[LessonScheduleRow, Lesson]] = []
    for row in rows:
        schedule = _row_to_schedule(row)
        out.append((schedule, get_lesson(connection, schedule.lesson_id)))
    return tuple(out)


# ── reviewing ───────────────────────────────────────────────────────────────


def record_review(
    connection: sqlite3.Connection,
    lesson_id: str,
    rating: ReviewRating,
    *,
    now: datetime | None = None,
    duration_ms: int | None = None,
) -> LessonReviewRow:
    """Record a revisit and move the schedule.

    ``again`` means 「我**不**同意我学到的东西了」 rather than 「我忘了」 — a lesson is
    something the reader concluded, so the interesting failure is not forgetting it
    but no longer believing it, and calling that "you forgot" would label the most
    valuable answer this queue can collect as a lapse.

    ``duration_ms`` is stored and never compared (red line 11).
    """
    import fsrs

    moment = require_utc(now or datetime.now(UTC), field="now")
    require_open_transaction(connection, operation="lesson.record_review")

    row = connection.execute(_SELECT_SCHEDULE, (lesson_id,)).fetchone()
    if row is None:
        raise LessonNotFoundError(f"教训 {lesson_id} 不在队列上。")

    schedule = _row_to_schedule(row)
    payload = json.loads(schedule.payload)
    # ⭐ `from_dict`, not `Card(card_id=..., **payload)`: the payload already
    # carries `card_id` (that is why `_fresh_fsrs_card` writes it in, so the stored
    # JSON and the `fsrs_card_id` column cannot disagree), so passing it twice is a
    # TypeError — and a second argument that *could* disagree with the first is the
    # shape to avoid regardless. `note_recall` already reads the payload this way.
    fsrs_card = fsrs.Card.from_dict(cast("Any", payload))

    # ⭐ `enable_fuzzing=False`, and the reason is a promise rather than a
    # preference. FSRS jitters due dates so intervals are not predictable; that is
    # right for a human-facing scheduler and wrong here, because the product
    # promises a lesson is due **immediately** and the queue is ordered by
    # `due_at`. With fuzzing on, two lessons recorded in the same second could come
    # back in either order and every schedule test would be flaky for a reason that
    # has nothing to do with the code under test. `note_recall` disables it for the
    # same reason; writing it here without the comment would have read as an
    # unexplained deviation from the library's default.
    scheduler = fsrs.Scheduler(enable_fuzzing=False)
    fsrs_card, _log = scheduler.review_card(
        fsrs_card, rating_to_fsrs(rating), moment, duration_ms
    )
    new_payload = dict(fsrs_card.to_dict())
    new_payload["card_id"] = schedule.fsrs_card_id
    new_state = state_of(new_payload)
    encoded = json.dumps(new_payload, ensure_ascii=False, separators=(",", ":"))

    connection.execute(
        _UPDATE_SCHEDULE_AFTER_REVIEW,
        # Five placeholders: four in the SET and one in the `WHERE lesson_id = ?`.
        # The id is repeated rather than folded in with a subquery because the row is
        # already located and a second lookup would be a second thing that can
        # disagree about which row this is.
        (encoded, new_state.value, as_utc_iso(fsrs_card.due), _stamp(moment), lesson_id),
    )
    connection.execute(
        _INSERT_REVIEW,
        (
            _new_id(connection, "lesson_review", "lesson_reviews", "id"),
            lesson_id,
            LessonRecordOutcome.REVIEWED.value,
            rating.value,
            _stamp(moment),
            duration_ms,
            as_utc_iso(schedule.due_at),
            as_utc_iso(fsrs_card.due),
            schedule.state.value,
            new_state.value,
        ),
    )
    return LessonReviewRow(
        id="",
        lesson_id=lesson_id,
        outcome=LessonRecordOutcome.REVIEWED,
        rating=rating,
        reviewed_at=moment,
        duration_ms=duration_ms,
        from_due_at=schedule.due_at,
        to_due_at=fsrs_card.due,
        from_state=schedule.state,
        to_state=new_state,
    )


# ── promotion ───────────────────────────────────────────────────────────────


def get_promotion(connection: sqlite3.Connection, lesson_id: str) -> LessonPromotion | None:
    row = connection.execute(_SELECT_PROMOTION, (lesson_id,)).fetchone()
    if row is None:
        return None
    return LessonPromotion(
        lesson_id=row["lesson_id"],
        card_id=row["card_id"],
        promoted_at=parse_due(row["promoted_at"]),
    )


def promote_lesson(
    connection: sqlite3.Connection,
    lesson_id: str,
    source_url: str | None,
    source_title: str | None,
    *,
    now: datetime | None = None,
    claim_type: ClaimType = ClaimType.NEUTRAL,
) -> LessonPromotion:
    """Sign the lesson as a card. **Requires a source.**

    ⭐ **The source is the feature.** A card's provenance is a URL; a lesson has
    none. So this is the moment the reader has to say 「这条我现在愿意署名，出处是……」,
    and if they cannot, they have not got a card — they have got a lesson, which is
    already saved and already on its queue. Nothing is lost by declining, and that
    is what makes declining a reasonable answer rather than a failure.

    ⭐ ``origin`` is ``user_written``, never ``ai_generated``: the text is the
    reader's own sentence about their own mistake, and the source they supplied is
    only where they found support. Marking it AI-generated would be the one
    unforced misattribution in the whole knowledge layer.

    ``claim_type`` defaults to ``neutral`` because **a lesson is not by itself a
    claim in either direction** — 「下次先看批价」 is a method, not a position. A
    reader who wants it directional says so, and the value is a decision rather than
    a default that quietly asserts one.

    ⭐ The lesson's schedule is **not** touched. Red line 7 gets no escape hatch: a
    branch that says 「转了卡就不用再复习了」 is exactly the kind of clause that turns
    a guarantee back into a suggestion, and it would be invisible.
    """
    url, title = validate_promotion_source(source_url, source_title)
    moment = require_utc(now or datetime.now(UTC), field="now")
    require_open_transaction(connection, operation="lesson.promote_lesson")

    existing = get_promotion(connection, lesson_id)
    if existing is not None:
        raise LessonAlreadyPromotedError(
            f"教训 {lesson_id} 已经转成卡片 {existing.card_id} 了 —— "
            "一张卡片只来自一条教训，转两次会出现两张都声称同一份出处的卡片。"
        )
    lesson = get_lesson(connection, lesson_id)

    card = cards.create(
        connection,
        CardDraft(
            content=lesson.content,
            claim_type=claim_type,
            source_url=url,
            source_title=title,
            origin=CardOrigin.USER_WRITTEN,
            # ⭐ 3, and the number is a refusal. `priority` is `IN (1..5)` and it
            # ranks the reader's own backlog, which red line 11 is about not doing.
            # A lesson is a verified mistake, which argues for 5 — and picking 5
            # here would smuggle a judgement about *what to attend to first* into a
            # field the reader owns, out of a function that has no basis for one.
            # Middle is the honest answer to a question this code cannot answer.
            priority=3,
            status=CardStatus.ACTIVE,
        ),
        now=_stamp(moment),
    )
    connection.execute(
        _INSERT_PROMOTION, (lesson_id, card.id, _stamp(moment))
    )
    return LessonPromotion(
        lesson_id=lesson_id, card_id=card.id, promoted_at=moment
    )
