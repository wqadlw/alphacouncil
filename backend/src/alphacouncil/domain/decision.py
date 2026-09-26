"""Decision records — the gate that makes "I will sell if …" mean something.

A decision row is the product's most valuable artefact, because it is the only
text written **before** the outcome is known. Everything else — the price, the
financials, the news — can be reconstructed afterwards. This cannot: once the
result is in, a person who did not write down their reasoning will remember
having had better reasoning than they did. That is not a character flaw, it is
how memory works, and the entire point of this table is to be the thing that
does not bend.

Which is why the id is a **server-generated millisecond timestamp** and not a
counter or a client value. The id is not an identifier, it is the evidence:
"this was written at 21:40 on the 26th, and the price moved on the 28th" is a
claim nobody can retract later. A client-supplied id would let the author
backdate their own foresight, and the API rejects the attempt rather than
ignoring it (see ``api/routes/decisions.py``).

Three fields are required, and the schema enforces all three so a caller
reaching past this module with raw SQL cannot skip them:

* ``rationale`` — why the trade.
* ``counter_evidence`` — **the only field that can resist confirmation bias.**
  It is required because the bias is not optional: a person who has decided
  something will find reasons for it, and the only known countermeasure is to
  make them write the other side down before they are allowed to proceed.
* ``kill_criteria`` — the structured conditions under which the reasoning is
  wrong. Structured, not prose, because a sentence cannot be evaluated and
  therefore cannot ever tell anyone anything (ADR-0017 #5).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import Symbol

__all__ = [
    "MAX_TEXT_CHARS",
    "ComparisonOperator",
    "Decision",
    "DecisionAction",
    "DecisionCounterEvidenceRequiredError",
    "DecisionError",
    "DecisionKillCriteriaRequiredError",
    "DecisionTextTooLongError",
    "KillCriterion",
    "record",
]

#: Mirrors ``decisions_rationale_length_check`` and
#: ``decisions_counter_evidence_length_check``. Cross-checked against
#: ``storage/constraints.json`` by a test, so changing one without the other
#: fails the build rather than surprising a user after they finished typing.
MAX_TEXT_CHARS = 2000

#: A metric name is a token, not a sentence. Deliberately a *shape* rule and not
#: a closed set: the metric catalogue belongs to the financial-data layer (D4),
#: which is not built, and inventing a list here would mean rejecting a valid
#: metric the day D4 lands. Shape validation still catches what actually goes
#: wrong — ``"gross margin"``, ``"毛利率"``, a stray space — without pretending
#: to know names it does not.
_METRIC_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


class DecisionAction(StrEnum):
    """What was decided. The five values ``decisions_action_check`` also knows."""

    BUY = "buy"
    ADD = "add"
    HOLD = "hold"
    TRIM = "trim"
    EXIT = "exit"


class ComparisonOperator(StrEnum):
    """How a metric is compared to a threshold.

    Symbols rather than words (``lt`` / ``gt``) because this is the one part of a
    predicate the user writes by hand, and ``<`` is what they would type in a
    spreadsheet or a screener. A closed set, so an unparseable predicate is
    rejected at the door instead of stored and discovered later by an evaluator
    that cannot act on it.
    """

    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    EQ = "=="
    NEQ = "!="


class DecisionError(ValueError):
    """A decision that could not have come from the user."""

    code: ErrorCode = ErrorCode.DECISION_RATIONALE_REQUIRED


class DecisionRationaleRequiredError(DecisionError):
    """The rationale was missing or blank."""

    code = ErrorCode.DECISION_RATIONALE_REQUIRED


class DecisionCounterEvidenceRequiredError(DecisionError):
    """The counter-evidence was missing or blank.

    Its own code rather than sharing the rationale's, because this is the field
    the product is built around: "how often do users leave the counter-evidence
    blank" has to be answerable, and it stops being answerable the moment the
    two failures share a name.
    """

    code = ErrorCode.DECISION_COUNTER_EVIDENCE_REQUIRED


class DecisionKillCriteriaRequiredError(DecisionError):
    """No falsifiable condition was given.

    A decision with no kill criteria is not a decision, it is a hope — and the
    schema cannot catch this one, because an empty JSON array satisfies
    ``json_valid(...) AND json_type(...) = 'array'``. So the floor is raised
    here, in the domain, and the reason it is *not* a schema constraint is
    written down rather than left to be rediscovered: SQLite cannot add a CHECK
    to an existing table, so enforcing it there means rebuilding ``decisions``
    and re-creating its append-only triggers. That is a real cost, and the
    specification (constitution rule 21) asks for the *form* to be structured —
    which the schema does enforce — not for a minimum count.
    """

    code = ErrorCode.DECISION_KILL_CRITERIA_REQUIRED


class DecisionTextTooLongError(DecisionError):
    """The rationale or the counter-evidence exceeded :data:`MAX_TEXT_CHARS`."""

    code = ErrorCode.DECISION_TEXT_TOO_LONG


def _normalise(text: str, *, field: str, blank_error: type[DecisionError]) -> str:
    """Trim ``text`` and refuse it if it is blank or over-long.

    Trimming here rather than at the call site is what keeps this module and the
    schema agreeing: the database checks ``length(trim(rationale)) > 0`` on the
    value as stored, so a caller that stored the raw text could pass this check
    and still be rejected by the database.
    """
    cleaned = text.strip()
    if not cleaned:
        raise blank_error(
            f"a decision's {field} cannot be blank — it is the sentence that "
            "tells you, later, whether you were reasoning or reacting"
        )
    if len(cleaned) > MAX_TEXT_CHARS:
        raise DecisionTextTooLongError(
            f"{field} is {len(cleaned)} characters; the ceiling is {MAX_TEXT_CHARS}"
        )
    return cleaned


@dataclass(frozen=True, slots=True)
class KillCriterion:
    """One falsifiable condition: ``{metric, operator, threshold, as_of}``.

    Read it as a sentence — "as of 2026-12-31, gross_margin is below 0.55" — and
    the reason each field exists becomes obvious. It is stored this way rather
    than as that sentence because a sentence cannot be *evaluated*: nothing can
    watch it, so it can never come and find you, and "the data comes to you"
    (product highlight 3) is exactly what this structure buys.

    ``as_of`` is a **point-in-time cutoff**, not a deadline. Financial figures
    are stored with the date they were announced, and an evaluation reads only
    what had been announced by ``as_of`` (constitution rule 20). Reading a
    figure that was published later than the question was asked is how
    backtesting quietly becomes a fantasy.
    """

    metric: str
    operator: ComparisonOperator
    threshold: float
    as_of: date

    def __post_init__(self) -> None:
        """Refuse a predicate nothing could ever evaluate."""
        if not _METRIC_PATTERN.fullmatch(self.metric):
            msg = (
                f"{self.metric!r} is not a metric name — expected lowercase "
                "letters, digits and underscores, starting with a letter"
            )
            raise DecisionKillCriteriaRequiredError(msg)
        # JSON has no way to spell NaN or infinity; Python's encoder writes them
        # as bare `NaN` / `Infinity`, which no other JSON parser accepts. A
        # threshold that cannot survive the round trip would corrupt the record
        # on the way out, so it is refused on the way in.
        if not math.isfinite(self.threshold):
            msg = f"threshold must be a finite number, got {self.threshold!r}"
            raise DecisionKillCriteriaRequiredError(msg)

    def to_json(self) -> dict[str, object]:
        """Render the stored form. ``as_of`` is an ISO date, not a datetime."""
        return {
            "metric": self.metric,
            "operator": self.operator.value,
            "threshold": self.threshold,
            "as_of": self.as_of.isoformat(),
        }

    @classmethod
    def from_json(cls, raw: object) -> KillCriterion:
        """Decode one stored predicate. A malformed row is corruption, not a default."""
        if not isinstance(raw, dict):
            msg = f"kill criterion must be an object, got {type(raw).__name__}"
            raise DecisionKillCriteriaRequiredError(msg)
        try:
            return cls(
                metric=str(raw["metric"]),
                operator=ComparisonOperator(str(raw["operator"])),
                threshold=float(str(raw["threshold"])),
                as_of=date.fromisoformat(str(raw["as_of"])),
            )
        except KeyError as exc:
            msg = f"kill criterion is missing {exc.args[0]!r}"
            raise DecisionKillCriteriaRequiredError(msg) from exc


@dataclass(frozen=True, slots=True)
class Decision:
    """One row of ``decisions``, guaranteed well-formed.

    Build one with :func:`record`. The constructor is public only because a
    dataclass cannot hide it; :meth:`__post_init__` re-checks the factory's work
    so a direct call cannot smuggle in a row the user could not have written.
    """

    action: DecisionAction
    symbol: Symbol
    rationale: str
    counter_evidence: str
    kill_criteria: tuple[KillCriterion, ...]
    thesis_id: str | None = None

    def __post_init__(self) -> None:
        """Normalise the two texts, and require at least one falsifiable condition."""
        object.__setattr__(
            self,
            "rationale",
            _normalise(
                self.rationale,
                field="rationale",
                blank_error=DecisionRationaleRequiredError,
            ),
        )
        object.__setattr__(
            self,
            "counter_evidence",
            _normalise(
                self.counter_evidence,
                field="counter_evidence",
                blank_error=DecisionCounterEvidenceRequiredError,
            ),
        )
        if not self.kill_criteria:
            raise DecisionKillCriteriaRequiredError(
                "a decision needs at least one falsifiable condition — without "
                "one there is nothing that could ever tell you that you were wrong"
            )

    def kill_criteria_json(self) -> str:
        """The exact text stored in the ``kill_criteria`` column.

        ``separators`` and ``ensure_ascii=False`` are not cosmetic: the schema
        round-trips this through ``json_valid``, and a stable rendering means two
        identical decisions produce identical bytes, which is what makes the
        column comparable in a diff.
        """
        return json.dumps(
            [criterion.to_json() for criterion in self.kill_criteria],
            ensure_ascii=False,
            separators=(",", ":"),
        )


def record(
    symbol: Symbol,
    action: DecisionAction,
    *,
    rationale: str,
    counter_evidence: str,
    kill_criteria: tuple[KillCriterion, ...],
    thesis_id: str | None = None,
) -> Decision:
    """Build a decision. Every field that matters is required and positional.

    ``rationale``, ``counter_evidence`` and ``kill_criteria`` have no defaults,
    so omitting one is a ``TypeError`` at the call site rather than a row that
    cannot answer the question it was created to answer.
    """
    return Decision(
        action=action,
        symbol=symbol,
        rationale=rationale,
        counter_evidence=counter_evidence,
        kill_criteria=kill_criteria,
        thesis_id=thesis_id,
    )
