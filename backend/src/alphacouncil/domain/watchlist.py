"""Watchlist rules — why the pool is an event log, not a table with a column.

The product asks the user to write *why* they are following an instrument. The
obvious schema is a ``watchlist`` table with a ``reason`` column, and it is the
wrong one — for a reason about the product rather than about storage:

* A mutable ``reason`` can be edited. An agent holding write access to that
  column (permission tier 4, ADR-0010) could rewrite the user's own words, and
  the earlier wording would be gone. An append-only event log cannot lose it,
  and that is what lets the product still answer "you said this three times, and
  the outcomes were …" — product highlight 2.
* Changing your mind becomes a *record* rather than an *edit*, which is what
  makes the revision reviewable later.

So this module's job is small and sharp: make it impossible to build an event
the user could not have written. The append-only guarantee itself lives in the
database (``storage/migrations/0001_initial.up.sql``), because a rule that
exists only in Python is a rule the next caller can walk around.

Which rule is enforced where is not accidental — constitution 0.2 asks for every
rule to sit as low on the ladder as it will go:

===========================  ====================================================
rule                         enforced by
===========================  ====================================================
the instrument is valid      the ``symbol`` parameter is a :class:`Symbol`, so it
                             cannot be built without passing validation
only a revision supersedes   ``added`` / ``removed`` do not accept the parameter
                             at all; the database CHECKs the same thing
a revision names its         ``reason_revised`` has no default for
predecessor                  ``supersedes_id``
a reason is a real sentence  :meth:`WatchlistEvent.__post_init__` — the one rule
                             worth stating three times, because it is the only
                             one with a message the *user* reads
===========================  ====================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import Symbol

__all__ = [
    "MAX_REASON_CHARS",
    "WatchlistAlreadyRemovedError",
    "WatchlistError",
    "WatchlistEvent",
    "WatchlistEventKind",
    "WatchlistNotFollowedError",
    "WatchlistReasonRequiredError",
    "WatchlistReasonTooLongError",
    "WatchlistState",
    "added",
    "reason_revised",
    "removed",
    "require_followed",
]

#: Mirrors ``watchlist_events_reason_length_check`` in the initial migration.
#: The two are cross-checked against ``storage/constraints.json`` by a test, so
#: changing one without the other fails the build rather than surprising a user
#: with a constraint error after they finished typing.
MAX_REASON_CHARS = 2000


class WatchlistEventKind(StrEnum):
    """The kinds the database CHECK constraint also knows. Keep them in step."""

    ADDED = "added"
    REMOVED = "removed"
    REASON_REVISED = "reason_revised"


class WatchlistError(ValueError):
    """A watchlist event that could not have come from the user."""

    code: ErrorCode = ErrorCode.WATCHLIST_REASON_REQUIRED


class WatchlistReasonRequiredError(WatchlistError):
    """The reason was missing or blank.

    Its own code because the message is the point: the user has to be told to
    write something, and "the event was rejected" would not tell them that.
    """

    code = ErrorCode.WATCHLIST_REASON_REQUIRED


class WatchlistReasonTooLongError(WatchlistError):
    """The reason exceeded :data:`MAX_REASON_CHARS`."""

    code = ErrorCode.WATCHLIST_REASON_TOO_LONG


class WatchlistNotFollowedError(WatchlistError):
    """The instrument has no events at all, so there is nothing to act on.

    Raised instead of the API inventing a 404: the domain knows the state, the
    route knows the status code, and keeping those apart is what stops the same
    failure from being reported two different ways depending on which layer
    noticed it first.
    """

    code = ErrorCode.WATCHLIST_NOT_FOLLOWED


class WatchlistAlreadyRemovedError(WatchlistError):
    """The newest event is a removal, so the instrument is no longer followed.

    Distinct from :class:`WatchlistNotFollowedError` on purpose: "never added"
    and "added, then removed" lead to different user-facing copy — one offers to
    add, the other offers to re-add — and collapsing them would force the UI to
    read the difference out of an English sentence.
    """

    code = ErrorCode.WATCHLIST_ALREADY_REMOVED


def _normalise_reason(reason: str) -> str:
    """Trim a reason and refuse one that is empty or over-long.

    Trimming here rather than at the call site is what keeps the domain and the
    database agreeing: the schema checks ``length(reason) <= 2000`` on the value
    as stored, so a caller that stored the raw text could pass this check and
    still be rejected by the database.
    """
    cleaned = reason.strip()
    if not cleaned:
        msg = (
            "a watchlist reason cannot be blank — it is the sentence the user is "
            "held to when the position goes wrong"
        )
        raise WatchlistReasonRequiredError(msg)
    if len(cleaned) > MAX_REASON_CHARS:
        msg = f"reason is {len(cleaned)} characters; the ceiling is {MAX_REASON_CHARS}"
        raise WatchlistReasonTooLongError(msg)
    return cleaned


@dataclass(frozen=True, slots=True)
class WatchlistEvent:
    """One row of ``watchlist_events``, guaranteed well-formed.

    Build one with :func:`added`, :func:`removed` or :func:`reason_revised`.
    The constructor is public only because a dataclass cannot hide it; those
    three are the intended API, and :meth:`__post_init__` re-checks their work
    so a direct call cannot smuggle in an event the user could not have written.
    """

    kind: WatchlistEventKind
    symbol: Symbol
    reason: str | None = None
    supersedes_id: int | None = None

    def __post_init__(self) -> None:
        """Normalise the reason, and refuse an event that has none.

        Only the reason rule is repeated here. The structural rules — a revision
        names its predecessor, nothing else does — are already enforced by the
        named constructors and by CHECK constraints, and a third copy would need
        a third error code for a condition only a programmer can cause.
        """
        if self.reason is None:
            if self.kind is not WatchlistEventKind.REMOVED:
                msg = f"a {self.kind.value} event must state why"
                raise WatchlistReasonRequiredError(msg)
            return
        # The documented way to write a field on a frozen dataclass: __init__
        # cannot do it for us because the normalised value is not the argument.
        object.__setattr__(self, "reason", _normalise_reason(self.reason))


@dataclass(frozen=True, slots=True)
class WatchlistState:
    """The newest event for one instrument: what the user may do next.

    It lives in the domain rather than beside the query that produces it,
    because it is the input to a rule — "you may only amend what you are still
    following" — and a rule that takes a storage type cannot be tested without
    storage.
    """

    event_id: int
    kind: WatchlistEventKind


def added(symbol: Symbol, reason: str) -> WatchlistEvent:
    """Start following an instrument, stating why.

    The reason is required and positional, so leaving it out is a ``TypeError``
    at the call site rather than a row the user cannot explain later.
    """
    return WatchlistEvent(WatchlistEventKind.ADDED, symbol, reason=reason)


def removed(symbol: Symbol, *, reason: str | None = None) -> WatchlistEvent:
    """Stop following an instrument.

    A reason is optional here — leaving needs no justification. If one is given
    it still has to be a real sentence, so ``reason=""`` is refused rather than
    quietly stored as an empty string.
    """
    return WatchlistEvent(WatchlistEventKind.REMOVED, symbol, reason=reason)


def reason_revised(symbol: Symbol, reason: str, *, supersedes_id: int) -> WatchlistEvent:
    """Replace the reason, naming the event being replaced.

    ``supersedes_id`` has no default because a revision that cannot point at
    what it replaced is not traceable, and the whole value of the log is that
    every change can be read back in order.
    """
    return WatchlistEvent(
        WatchlistEventKind.REASON_REVISED,
        symbol,
        reason=reason,
        supersedes_id=supersedes_id,
    )


def require_followed(state: WatchlistState | None, symbol: Symbol) -> WatchlistState:
    """Refuse an action that assumes the instrument is currently followed.

    Reading the newest event is storage's job; interpreting it is this module's,
    so the API does not grow a branch that decides what is allowed. Returning the
    state rather than ``None`` is what lets a caller use the id without a second
    query and without asserting to the type checker that it exists.

    Args:
        state: The newest event, or ``None`` when there is no event at all.
        symbol: The instrument, for the message.

    Returns:
        ``state``, once it is known to be actionable.

    Raises:
        WatchlistNotFollowedError: The instrument has never been added.
        WatchlistAlreadyRemovedError: The newest event is a removal.
    """
    if state is None:
        msg = f"{symbol.full} is not in the watchlist"
        raise WatchlistNotFollowedError(msg)
    if state.kind is WatchlistEventKind.REMOVED:
        msg = f"{symbol.full} was removed — re-add it rather than amending it"
        raise WatchlistAlreadyRemovedError(msg)
    return state
