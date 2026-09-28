"""Reviews: the four quadrants, and the gate that keeps an outcome from arriving early.

This module is the product's thesis in pure logic. Everything else in the project
is plumbing; this is the claim:

> **A decision being right and a decision being good are two different things,
> and keeping them apart is the only honest way to learn.**

The quadrants (``项目总纲`` P0-3):

=========================  =====================
process · outcome          verdict
=========================  =====================
good  · good               ``REPEAT``     应重复
good  · bad / failed       ``ACCEPTABLE`` 可接受
bad   · good               ``DANGEROUS``  最危险
bad   · bad / failed       ``FIX``        必须改
=========================  =====================

### Why ``outcome`` is a classification and not a number

Red line 10 says that in the dangerous quadrant — a bad decision that happened to
pay — the product must **not display the profit figure**. If the table stored a
return, "not display" would be a *rendering* rule, and a number that already
exists **leaks**: into logs, into exports, into the next API field somebody adds.
So ``outcome`` is an enum, and there is no number to withhold. **The missing column
is red line 10 resting on the data model rather than on somebody remembering.**

``failed`` is a first-class value (ADR-0014), and its whole purpose is to stop
"a loss but…" phrasing: a loss is called ``failed``, not a harvest with volatility.

### The hard gate

``项目总纲``: **结果分在到期前必须留空** — you may not score the outcome before the
review is due, because scoring early *is* hindsight: the number is already known
and it will colour the judgement of the process.

That rule exists in two places, deliberately. In the schema, as
``CHECK (reviewed_at >= due_at_snapshot)`` — ISO-8601 timestamps compare
lexicographically, so copying the due date into the review row lets the database
refuse an early score **even from a caller that went around this module**. And
here, as a domain rule, so the failure arrives as our error with our code.

Moving a rule from discipline into the database is constitution 0.2 ("能移就必须移"),
and this is one of the cleanest cases of it: no test has to trust anybody's
good intentions.

### The soft spot, stated rather than hidden

**The process score is the user's own.** Nothing here makes it objective, and no
amount of schema will. What resists hindsight is structural, not statistical:

1. ``decisions.rationale`` and ``counter_evidence`` are **append-only** — the
   words being graded are still there, unmodified, so the grade is anchored to
   something that cannot be retrofitted;
2. the outcome is blank until due, so the grade is written without it in view.

In other words: **what gets graded is not a memory, it is a passage of text that
is still on the page.** Everything else in this module is bookkeeping.

A 3 is counted as a *bad* process, not a middling one. That is a judgement, not a
fact, and it is written down here so a later reader does not "fix" it into a
symmetric rule: a 3 means the process was mediocre, and mediocre is precisely the
category worth changing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from alphacouncil.core.error_codes import ErrorCode

__all__ = [
    "GOOD_PROCESS_MIN",
    "MAX_NOTE_CHARS",
    "MAX_PROCESS_SCORE",
    "MIN_PROCESS_SCORE",
    "Outcome",
    "ProcessBand",
    "Quadrant",
    "QuadrantJudgement",
    "Review",
    "ReviewError",
    "ReviewNotDueError",
    "ReviewNoteBlankError",
    "ReviewScoreInvalidError",
    "judge",
    "process_band",
]


class ReviewError(ValueError):
    """A review that could not have come from the user."""

    code: ErrorCode = ErrorCode.REVIEW_SCORE_INVALID


class ReviewScoreInvalidError(ReviewError):
    """The process score is outside 1..5."""

    code = ErrorCode.REVIEW_SCORE_INVALID


class ReviewNotDueError(ReviewError):
    """An outcome was recorded before the review was due.

    Scoring early is hindsight: the number is already known and it colours the
    judgement of the process. ``项目总纲`` calls this a hard gate, and the schema
    enforces it independently (spec 020 §2.3).
    """

    code = ErrorCode.REVIEW_NOT_DUE


class ReviewNoteBlankError(ReviewError):
    """A note was supplied but is only whitespace."""

    code = ErrorCode.REVIEW_NOTE_BLANK


MIN_PROCESS_SCORE = 1
MAX_PROCESS_SCORE = 5

#: A 3 is "bad", not "middling" — see the module docstring. Written down because
#: it is a judgement and the next reader will otherwise assume it is a typo.
GOOD_PROCESS_MIN = 4

MAX_NOTE_CHARS = 1000

_SCORE_TEXT = re.compile(r"^\s*[1-5]\s*$")


class Outcome(StrEnum):
    """How it turned out — a **classification**, deliberately not a number.

    ``failed`` is first-class (ADR-0014). Its purpose is to make a loss say
    "failed" rather than "a harvest with volatility".
    """

    GOOD = "good"
    BAD = "bad"
    FAILED = "failed"

    @property
    def is_good(self) -> bool:
        """Only ``good`` counts as a good outcome; ``bad`` and ``failed`` do not."""
        return self is Outcome.GOOD


class ProcessBand(StrEnum):
    """Whether the way the decision was made was sound."""

    GOOD = "good"
    BAD = "bad"


class Quadrant(StrEnum):
    """The four cells, with the product's own word for each.

    ``DANGEROUS`` carries a rule with it: no profit figure may be shown. There
    is nothing to withhold in the data model, so this is a statement about what
    the *interface* may add, not about what it must hide.
    """

    REPEAT = "repeat"
    ACCEPTABLE = "acceptable"
    DANGEROUS = "dangerous"
    FIX = "fix"
    #: The outcome is blank, so the cell is genuinely undetermined. Not an error
    #: and not a default: before the review is due, "how did it turn out" is
    #: **unknown**, and reporting any quadrant here would be the system guessing
    #: (constitution 4.6 — ``unavailable`` must not dress itself up as an answer).
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class QuadrantJudgement:
    """The cell a review falls into, and what the product may say about it."""

    quadrant: Quadrant
    process: ProcessBand
    outcome: Outcome | None

    @property
    def withholds_outcome_figure(self) -> bool:
        """Whether a profit figure may be shown for this review.

        Always ``True`` in practice, because ``Outcome`` carries no figure — this
        exists so the rule has a name that a UI can consult rather than a comment
        nobody reads, and so a future numeric outcome has one place to make this
        return ``False`` (which the tests would then force it to justify).
        """
        return True

    def guidance(self) -> str:
        """The one line this quadrant is allowed to print.

        Deliberately a function of the quadrant alone. It never mentions the
        outcome's magnitude, because there is no magnitude, and because a line of
        copy that varies with a number is how "失败但…" phrasing gets in (red line
        10).
        """
        return {
            Quadrant.REPEAT: "这个过程值得重复：下次遇到同类情况，按同样的方式做。",
            Quadrant.ACCEPTABLE: "过程站得住，结果没配合。这通常不是你推理的问题。",
            Quadrant.DANGEROUS: (
                "这次结果好，但你当时写下的理由撑不住它。"
                "按当时的方式做，下一次同样的运气不一定在。"
            ),
            Quadrant.FIX: "过程和结果都不支持当时的判断。改的是过程，不是运气。",
            # Say that it is unanswered. The alternative — borrowing a line from a
            # neighbouring cell — would be a sentence about a result nobody has
            # recorded yet.
            Quadrant.UNKNOWN: "结果还没到能打分的时候。这一栏先空着。",
        }[self.quadrant]


def process_band(score: int) -> ProcessBand:
    """Which band a 1..5 process score falls into.

    A 3 is ``BAD``. Written down, because a symmetric rule (>= 3 is good) is the
    obvious "cleanup" and it would move the boundary without anyone noticing.
    """
    if not (MIN_PROCESS_SCORE <= score <= MAX_PROCESS_SCORE):
        msg = f"process score must be {MIN_PROCESS_SCORE}..{MAX_PROCESS_SCORE}, got {score}"
        raise ReviewScoreInvalidError(msg)
    return ProcessBand.GOOD if score >= GOOD_PROCESS_MIN else ProcessBand.BAD


def judge(score: int, outcome: Outcome | None) -> QuadrantJudgement:
    """Place a review in a quadrant.

    ``outcome=None`` means the outcome is still blank — before the review is due,
    or deliberately not scored. It yields a judgement with no quadrant, because
    "how did it turn out" is genuinely unanswered, and returning a quadrant here
    would be the system guessing (constitution 4.6: ``unavailable`` must not dress
    itself up as an answer).
    """
    band = process_band(score)
    if outcome is None:
        return QuadrantJudgement(quadrant=Quadrant.UNKNOWN, process=band, outcome=None)

    good_process = band is ProcessBand.GOOD
    if good_process and outcome.is_good:
        quadrant = Quadrant.REPEAT
    elif good_process:
        quadrant = Quadrant.ACCEPTABLE
    elif outcome.is_good:
        quadrant = Quadrant.DANGEROUS
    else:
        quadrant = Quadrant.FIX
    return QuadrantJudgement(quadrant=quadrant, process=band, outcome=outcome)


@dataclass(frozen=True, slots=True)
class Review:
    """One review: the process score, and an outcome that is not yet known."""

    decision_id: str
    process_score: int
    outcome: Outcome | None = None
    reviewed_at: datetime | None = None
    due_at: datetime | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        """Reject a review the user could not have written."""
        if not _SCORE_TEXT.match(str(self.process_score)):
            msg = f"process score must be {MIN_PROCESS_SCORE}..{MAX_PROCESS_SCORE}"
            raise ReviewScoreInvalidError(msg)
        if self.note is not None and not self.note.strip():
            raise ReviewNoteBlankError("a review note cannot be whitespace only")
        if self.note is not None and len(self.note) > MAX_NOTE_CHARS:
            msg = f"review note is {len(self.note)} characters; the ceiling is {MAX_NOTE_CHARS}"
            raise ReviewScoreInvalidError(msg)
        # The order is checked **only when the caller supplied both ends**.
        # They usually cannot: the due date lives in `decision_review_state`,
        # and a caller that had to look it up to build a review would be
        # reading the very state the repository is about to write. The real
        # enforcement is the repository (against the authoritative row) and
        # the schema CHECK — this is the same rule said in a third place, for
        # the benefit of anyone constructing a `Review` on its own.
        if (
            self.outcome is not None
            and self.due_at is not None
            and self.reviewed_at is not None
            and self.reviewed_at < self.due_at
        ):
            msg = (
                f"an outcome cannot be scored before the review is due "
                f"(due {self.due_at.isoformat()}, reviewed "
                f"{self.reviewed_at.isoformat()}) — scoring early is hindsight"
            )
            raise ReviewNotDueError(msg)

    def judgement(self) -> QuadrantJudgement:
        return judge(self.process_score, self.outcome)


def is_due(due_at: datetime, *, as_of: datetime) -> bool:
    """Whether a decision's review has come round.

    The date is injected rather than read from the clock, for the same reason as
    everywhere else in this project: a rule you cannot ask twice is a rule you
    cannot check. On the boundary day the answer is *due* — the review is on the
    reader's desk that morning, not the day after.
    """
    return as_of >= due_at


def outcome_still_blank(*, due_at: datetime, as_of: datetime) -> bool:
    """Whether the outcome must remain unrecorded (red lines 4 and 6)."""
    return not is_due(due_at, as_of=as_of)
