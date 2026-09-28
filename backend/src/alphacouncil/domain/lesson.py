"""Lessons — what a review taught you (spec 030 · J5).

A **lesson** is the third thing this product knows how to hold, and it is the one
the owner's original brief named and nothing implemented: 「要可以记录任何和金融股市
相关的**知识和经验**」. Knowledge got notes (spec 026). Experience is this file.

## What a lesson is, precisely

A lesson is a statement the reader wrote **after** reviewing a decision, saying
what they now know that they did not know before. Its provenance is a real event
they were present for — a review — and **not** a URL.

⭐ **That is the whole reason this is not a card**, and it is worth stating because
the first draft of this spec got it wrong. The diagnosis that produced notes
(spec 026, recorded in `status.md`) reads:

    `cards` 表被 `source_url` 必填 + `source_title` 必填 + 前端硬编码单只 6 位代码
    三条锁死 → 宏观判断、方法论、**教训**、读书笔记全都记不下

A lesson is one of the four things `cards` could not hold. Putting it back by
weakening `cards`' provenance rule would invert the reason notes exist — and in
SQLite it would not even be free, because the two `NOT NULL`s cannot be dropped
without rebuilding a table three others reference. A lesson has no URL to give, and
that is not a defect; it is the definition.

## ⭐ A lesson is **immutable**, and that is not a limitation

K1 deliberately gives cards no edit verb, so 「我当时复习的那条」 is always the same
row. A lesson is the same kind of thing: if you want to change it, the honest move
is to write a second lesson, because the edited one is no longer the thing you
learned.

This is load-bearing, because it removes work rather than adding it. spec 028 found
that **notes are mutable**, so a note in the queue can be rewritten and FSRS's
memory strength would then hang off **text that no longer exists** — the scheduler
would be lying, which this project's whole argument forbids. So `note_reviews` grew
a third outcome, `reset`.

⭐ **A lesson needs no `reset`, and so it reuses `ReviewOutcome` unchanged** — the
two-value one from `domain.scheduling`. That is not an omission to remember to avoid;
it is inherited from a shared vocabulary. Of the three review ledgers, the two
holding immutable things (cards, lessons) have two outcomes and the one holding a
mutable thing (notes) has three. The asymmetry is the evidence that lessons and
cards are the same kind of object.

## And 「转卡」 is a separate, explicit act

Promoting a lesson to a card is `lesson_promotions`, an append-only ledger with a
`UNIQUE` lesson — never a column on `lessons`, because `lessons` is immutable.

Promotion **demands a source**, and that demand is derived rather than invented: a
card's provenance is a URL, a lesson has none, so

> 「我拿不出出处」= 这条已经是一条教训了，它还不是卡片。

Which is the right answer. 「转卡」 is a judgement, not a data copy. A thought
recorded but not yet signed is already a note (spec 026), which is where it belongs.
The gate is the most valuable part of this feature: it blocks 「把一条还没想清楚的
东西签上名，然后让它以卡片的身份被复习」.

A promotion does **not** remove the lesson from its own queue. Red line 7 must not
have an escape hatch, and an escape hatch is worse than not having the feature.
The lesson is the experience; the card is the signed version. Both existing is
correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.domain.scheduling import ReviewOutcome, ReviewRating, ScheduleState

__all__ = [
    "MAX_CONTENT_CHARS",
    "MAX_SOURCE_TITLE_CHARS",
    "Lesson",
    "LessonAlreadyPromotedError",
    "LessonContentBlankError",
    "LessonDraft",
    "LessonError",
    "LessonNotFoundError",
    "LessonPromotion",
    "LessonPromotionSourceError",
    "LessonRecordOutcome",
    "LessonReviewMissingError",
    "LessonReviewRow",
    "LessonScheduleRow",
    "LessonTooLongError",
    "validate_content",
    "validate_promotion_source",
]

#: A lesson is a sentence or two. 1000 is the same bound `notes` uses, chosen so
#: that 「写成一条笔记」 and 「写成一条教训」 cannot disagree about how much fits —
#: the difference between the two is the evidence, not the room.
MAX_CONTENT_CHARS = 1000

#: Same bound as `cards.source_title` (255), because a promotion writes into it.
MAX_SOURCE_TITLE_CHARS = 255


class LessonRecordOutcome(StrEnum):
    """Why a row landed in ``lesson_reviews``, beyond the two interactions.

    ⭐ **One extra value, and it is not ``reset``.** It is ``enrolled``, for the row
    written by the enrolment that the red line makes mandatory. It exists in the
    ledger (not just in ``lessons``) because the enrolment is the one interaction
    whose reason a reader will later want to audit: 「这条为什么在队列上」 has an
    answer on the row, not only in a changelog.

    There is no ``reset`` and there cannot be: ``lessons`` is immutable, so the text
    a lesson's memory strength hangs off never stops existing. See the module
    docstring — this is the same argument that made ``note_reviews`` need one.
    """

    ENROLLED = "enrolled"
    REVIEWED = "reviewed"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class LessonDraft:
    """What the reader types when turning a review into a lesson.

    Only the content. A lesson has no title, no tags and no symbols, because it has
    exactly one piece of evidence — the review it came from — and adding
    free-form fields around it would invite a reader to file it away where nothing
    will ever find it again.
    """

    content: str


@dataclass(frozen=True, slots=True)
class Lesson:
    """A lesson, as read back.

    ⭐ **No ``decision_id`` field, matching a table with no such column.** The
    decision is one join away through ``review_id``, and keeping a second copy of a
    fact that can disagree with the first is the hazard this project's
    append-only discipline exists to avoid — in a new place. The first version of
    this dataclass did have the field, and mypy caught the disagreement by
    refusing to build the object.
    """

    lesson_id: str
    review_id: str
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LessonScheduleRow:
    """「现在怎么样」— the truth for one lesson on the queue.

    Deliberately not ``ScheduleRow``: that type's first field is named ``card_id``,
    and a row about a lesson with a field called ``card_id`` is a lie in a field
    name. Same reason ``NoteScheduleRow`` exists.
    """

    lesson_id: str
    fsrs_card_id: int
    payload: str
    state: ScheduleState
    due_at: datetime
    enrolled_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class LessonReviewRow:
    """One row of the append-only ledger."""

    id: str
    lesson_id: str
    outcome: LessonRecordOutcome
    rating: ReviewRating | None
    reviewed_at: datetime
    duration_ms: int | None
    from_due_at: datetime
    to_due_at: datetime
    from_state: ScheduleState
    to_state: ScheduleState


@dataclass(frozen=True, slots=True)
class LessonPromotion:
    """A lesson that has been signed as a card.

    Exists as its own row rather than a column on ``lessons`` because ``lessons`` is
    immutable. The two UNIQUE constraints that carry the real weight are in the
    migration, not here — a dataclass cannot make a duplicate impossible, and
    「每条教训最多转一次、每张卡片只来自一条教训」 has to be true in the database.
    """

    lesson_id: str
    card_id: str
    promoted_at: datetime


# ── errors ──────────────────────────────────────────────────────────────────


class LessonError(ValueError):
    """A lesson that could not have come from the reader."""

    code: ErrorCode = ErrorCode.LESSON_CONTENT_BLANK


class LessonContentBlankError(LessonError):
    """The lesson has no content.

    Mirrors ``NOTE_BODY_BLANK`` rather than inventing a gentler rule: a lesson with
    no words is a scheduling item that comes back to the reader to be read, and
    there is nothing to read. The red line would then be satisfied in form and empty
    in substance, which is the failure a red line must not have.
    """

    code = ErrorCode.LESSON_CONTENT_BLANK


class LessonTooLongError(LessonError):
    code = ErrorCode.LESSON_TEXT_TOO_LONG


class LessonNotFoundError(LessonError):
    code = ErrorCode.LESSON_NOT_FOUND


class LessonReviewMissingError(LessonError):
    """A lesson was offered for a decision that has not been reviewed.

    ⭐ Not 「没有那次复盘」, and not 「复盘还没到期」, but specifically
    **「还没写」** — the review row does not exist yet, or exists without a
    ``reviewed_at``. A lesson is a statement about what a review taught you, so it
    has nothing to attach to before the review is written, and attaching it to the
    *scheduled* review instead would date the lesson to a moment that has not
    happened.
    """

    code = ErrorCode.LESSON_REVIEW_MISSING


class LessonAlreadyPromotedError(LessonError):
    """The lesson already became a card.

    Raised rather than returned as a second, silent success: promoting twice would
    produce two cards claiming the same provenance, and the reader would have no way
    to tell which one they signed.
    """

    code = ErrorCode.LESSON_ALREADY_PROMOTED


class LessonPromotionSourceError(LessonError):
    """A promotion was attempted without a source.

    ⭐ **The most important error in this module**, and it is the product rather
    than the plumbing. A card's provenance is a URL; a lesson has none. So the act
    of promoting is where the reader has to say 「这条我现在愿意署名，出处是……」 — and
    if they cannot, they have not got a card, they have got a lesson, which is
    already saved. See the module docstring.
    """

    code = ErrorCode.LESSON_PROMOTION_SOURCE_REQUIRED


# ── validation ──────────────────────────────────────────────────────────────


def validate_content(raw: str) -> str:
    """The lesson body, checked.

    Body **verbatim** like a note body (``notes.create`` does not trim either, and
    has a test holding the backend to byte-for-byte storage). What is rejected is
    emptiness, checked with ``strip()`` so a lesson of spaces is not a lesson.
    """
    if raw.strip() == "":
        raise LessonContentBlankError("教训不能全空 —— 「我下次先看批价」这样就够。")
    if len(raw) > MAX_CONTENT_CHARS:
        raise LessonTooLongError(
            f"教训最多 {MAX_CONTENT_CHARS} 字，当前 {len(raw)} 字。"
        )
    return raw


def validate_promotion_source(url: str | None, title: str | None) -> tuple[str, str]:
    """The source a promotion must carry, checked the way ``cards`` checks one.

    Returns ``(url, title)`` trimmed. Both are required — a card whose source is a
    bare link with no title is a link the reader cannot recognise in a list, and
    ``cards`` has required both since spec 003.

    ⭐ Raised as one error on purpose. The two conditions are one judgement — 「我拿
    不出处」 — and splitting them into two codes would let the UI ask for a URL, get
    it, and then fail on the title, which reads as the UI's fault.
    """
    clean_url = (url or "").strip()
    clean_title = (title or "").strip()
    if clean_url == "" or clean_title == "":
        raise LessonPromotionSourceError(
            "转成卡片要给出处：一个链接和它的标题。"
            "拿不出出处就说明这条还只是一条教训 —— 它已经记下来了，不会丢。"
        )
    if not clean_url.startswith(("http://", "https://")):
        raise LessonPromotionSourceError(
            f"出处必须以 http:// 或 https:// 开头，当前是「{clean_url[:40]}」。"
        )
    if len(clean_title) > MAX_SOURCE_TITLE_CHARS:
        raise LessonPromotionSourceError(
            f"出处标题最多 {MAX_SOURCE_TITLE_CHARS} 字，当前 {len(clean_title)} 字。"
        )
    return clean_url, clean_title


#: Re-exported so callers do not have to reach into ``domain.scheduling`` for the
#: interaction vocabulary. A lesson's outcomes are these plus ``enrolled``.
INTERACTION_OUTCOMES = (ReviewOutcome.REVIEWED, ReviewOutcome.DEFERRED)
