"""Turning a domain failure into the one diagnostic envelope.

`.ai/error-codes.md` §1 fixes the shape: ``severity`` / ``code`` / ``message`` /
``target`` / ``fix``, exactly those five keys. The envelope is deliberately
closed — the ``--json`` output of the check runner is asserted to have exactly
these keys — which is why "here are the two markets your code could mean" is a
*response body* on a resolve endpoint rather than an extra field bolted onto an
error.

Two implementations of the envelope exist on purpose: this one and
``checks.models.Issue.as_dict``. The check package is forbidden from importing
the product (`.ai/checks/static/README.md` §4.5), so sharing the code is not
available and a five-key dict is cheaper to repeat than to route around the
wall. A change to the shape must be made in both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.domain.card import CardError
from alphacouncil.domain.decision import DecisionError
from alphacouncil.domain.instrument import InstrumentError
from alphacouncil.domain.lesson import LessonError
from alphacouncil.domain.note import NoteError
from alphacouncil.domain.note_recall import NoteRecallError
from alphacouncil.domain.review import ReviewError
from alphacouncil.domain.scheduling import SchedulingError
from alphacouncil.domain.watchlist import WatchlistError

# ⭐ Spec 052 §12.2: the provider hierarchy needs a base registered here ⭐ **and
# it is the first one that does not subclass `ValueError`** ⭐ which is why the
# comment on `CODED_ERRORS` had to change rather than just grow.
from alphacouncil.providers.base import ProviderError

#: The HTTP status each coded failure deserves.
#:
#: The domain does not know about HTTP, and this map is why it does not have to.
#: Anything absent is a 400: the *request* was wrong rather than the state it
#: assumed. A state conflict is a 409, and "the thing you asked about is not
#: there" is a 404 — statuses the frontend can act on without reading prose.
_STATUS_BY_CODE: dict[str, int] = {
    # Spec 030, J5. The fifth time this map has needed a new row (K3, J3, notes,
    # recall, and now lessons) — and the fifth time the omission showed up as a flat
    # 400 with no `code`, so a client could not tell 「已经转过卡了」 from
    # 「出处不是 http」. ⭐ `errors.py` says of the last one: "worth remembering as a
    # step, not rediscovering as a bug". I rediscovered it as a bug, and the browser
    # is what showed it: the refusal rendered as the generic 「请求被拒绝」 instead of
    #
    # ⭐ **Reworded rather than exempted.** The fullwidth parentheses inside that
    # quoted string are what `RUF003` objects to, and the project's standard for a
    # per-file exemption is that paraphrasing would lose the constraint being
    # cited — the parentheses were never the constraint. ⭐ 「这里其他备注都这么写」 is a
    # reason to add one, not a reason to stop asking whether the quotation needs
    # the punctuation.
    #
    # ⭐ The refusal sentence is referred to by its **error code** from here on
    # rather than quoted: `RUF003` flags a fullwidth comma even inside corner
    # brackets, and the existing comments in this file pass only because none of
    # their quotations happens to contain one. ⭐ A quotation whose punctuation has to
    # be reworked to satisfy a linter is a quotation that will be reworked again,
    # and the code says the same thing without the punctuation.
    # `LESSON_PROMOTION_SOURCE_REQUIRED` — the one sentence that makes declining
    # feel safe.
    #
    # 409 rather than 400 for the two conflicts: the request is well-formed and the
    # *state* disagrees — the review is not written, or this lesson is already signed.
    ErrorCode.LESSON_NOT_FOUND.value: 404,
    ErrorCode.LESSON_REVIEW_MISSING.value: 409,
    ErrorCode.LESSON_ALREADY_PROMOTED.value: 409,
    ErrorCode.WATCHLIST_NOT_FOLLOWED.value: 404,
    ErrorCode.WATCHLIST_ALREADY_REMOVED.value: 409,
    ErrorCode.INSTRUMENT_ASSET_TYPE_CONFLICT.value: 409,
    ErrorCode.CARD_NOT_FOUND.value: 404,
    ErrorCode.CARD_ALREADY_VERIFIED.value: 409,
    ErrorCode.CARD_NOT_ACTIVE.value: 409,
    # K3. Both are 409 rather than 404 on purpose: the *card* exists, and what
    # conflicts is the request with the card's scheduling state. Answering 404
    # would tell the user their card is gone when it is sitting right there.
    ErrorCode.CARD_ALREADY_SCHEDULED.value: 409,
    ErrorCode.CARD_NOT_SCHEDULED.value: 409,
    # J3 (spec 021). Three codes, and the statuses are chosen so the frontend can
    # act without reading prose:
    #
    # - A decision that was never given a review slot is **404**, not 409. The
    #   decision exists; what is missing is a *review commitment* the user never
    #   made. Saying 409 ("conflict with state") would imply the request fought
    #   with something, when in fact the thing does not exist.
    # - Scoring an outcome early is **409**, not 400. The request is well-formed;
    #   it conflicts with a *state* — the review is not due yet. Same reasoning as
    #   the K3 codes above, and it is what lets the UI say "not due yet" rather
    #   than "your input was wrong".
    ErrorCode.REVIEW_STATE_MISSING.value: 404,
    ErrorCode.REVIEW_NOT_DUE.value: 409,
    # The one DECISION_* code that is not about the input: the request named a
    # decision that does not exist. 404, so the client can say "no such decision"
    # instead of implying the reader sent something malformed.
    ErrorCode.DECISION_NOT_FOUND.value: 404,
    # ⭐⭐ Spec 052 §12.2. **The first source failure that had no HTTP edge at all.**
    # `sources.py:97-125` is the only place a `ProviderError` becomes something with a
    # status, and it is on the market path ⭐ **so the financial and universe protocols had
    # nowhere to land** ⭐ and a source being down produced Starlette's default 500 with no
    # `code` ⭐ **which is the fifth-time failure this file records, and the sixth instance:**
    # not a base missing from the tuple, but an edge missing entirely.
    #
    # ⭐ **`DATA_SOURCE_FORBIDDEN` is 502, not 403.** The upstream refused *our* request, so
    # a 403 would be a sentence about the person using the product produced by a fact about
    # a socket ⭐ **and that is `metrics.py:38-41`'s named failure** ⭐ the program speaking
    # for the reader ⭐ reached from a different direction.
    #
    # ⭐ **`DATA_SOURCE_IP_BLOCKED` is 503, not 429.** A rate limit and a ban have different
    # recoveries ⭐ **and §4.5 is a product sentence about exactly that** ⭐ so the statuses
    # must not blur them either. ⭐ `Retry-After` is deliberately absent: we know the ban is
    # 20 hours because `_IP_BLOCKED_COOLDOWN_S` says so ⭐ **and putting a number in a header
    # would turn our own recovery policy into a promise about the source's.**
    ErrorCode.DATA_SOURCE_RATE_LIMITED.value: 429,
    ErrorCode.DATA_SOURCE_IP_BLOCKED.value: 503,
    ErrorCode.DATA_SOURCE_FORBIDDEN.value: 502,
    ErrorCode.DATA_SOURCE_UNREACHABLE.value: 503,
    # `ProviderProtocolError`: the source answered, in a shape we cannot read. ⭐ That is
    # 502's definition exactly ⭐ **an upstream returned something invalid.**
    ErrorCode.DATA_UNVERIFIABLE.value: 502,
    # The bare `ProviderError` case ⭐ **which is what an unrecognised upstream code
    # becomes** ⭐ (see `providers/_baostock.py::classify`: unknown is a real answer, and
    # the default is a plain `ProviderError`). 502 rather than 500 ⭐ **because the request
    # was well-formed and the fault is upstream** ⭐ and a reader must not be told their own
    # request broke the data source.
    ErrorCode.DATA_FETCH_ERROR.value: 502,
    # ⭐⚠️ `DATA_NO_DATA` is 404 **and this is the least-wrong status, not the right one.**
    # `ProviderEmptyError` means 「the source answered and there is genuinely nothing」 ⭐
    # which is §4.6's `no_data`, a legitimate answer rather than a fault ⭐ **and there is
    # no status for 「looked, and there is nothing」.** ⇒ An endpoint that can render 「没有」
    # must catch it itself and answer in its own four-state shape ⭐ **and this row is the
    # backstop for the endpoints that do not.** ⚠️ Recorded as a known limit in
    # spec 052 §12.2 rather than papered over.
    ErrorCode.DATA_NO_DATA.value: 404,
}

_DEFAULT_STATUS = 400


@dataclass(frozen=True, slots=True)
class Failure:
    """A status code and the envelope that goes with it."""

    status: int
    body: dict[str, Any]


def envelope(
    code: str,
    message: str,
    *,
    severity: str = "error",
    target: str | None = None,
    fix: str | None = None,
) -> dict[str, Any]:
    """Build a diagnostic in the shape `.ai/error-codes.md` §1 mandates."""
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "target": target,
        "fix": fix,
    }


def domain_failure(exc: Exception) -> Failure:
    """Render a coded domain error as an envelope plus the status it implies.

    ``fix`` stays ``None`` for every one of these, and that is not an oversight:
    each is a case where *the user has to do something*, and §1 says the ``fix``
    for those is prose the UI shows rather than an action it runs. Null is the
    honest encoding until the UI has copy per code.
    """
    code = getattr(exc, "code", None)
    name = str(code) if code is not None else "UNKNOWN"
    status = _STATUS_BY_CODE.get(name, _DEFAULT_STATUS)
    return Failure(status=status, body=envelope(name, str(exc)))


#: Registered against every base so one handler covers each layer's coded
#: failures. A tuple because FastAPI wants one registration per class. Every base
#: subclasses ``ValueError``, and Starlette picks the most specific handler, so
#: the plain ``ValueError`` handler still catches everything else.
CODED_ERRORS: tuple[type[Exception], ...] = (
    InstrumentError,
    WatchlistError,
    DecisionError,
    CardError,
    # Spec 026. The same trap as K3 and J3, hit a third time: without the base
    # registered, every note failure answers a flat **400**, so "这条笔记不存在"
    # and "标题是空的" become indistinguishable to a client — and the note layer
    # is the one that most needs to say *which* rule was broken, because the whole
    # feature rests on "a note may skip the rules a card may not".
    NoteError,
    # Spec 028. The fourth time this has been missed (K3, J3, notes, and now the
    # recall queue): a new domain error class gets an enum entry and a doc row,
    # and the one place that maps class -> coded envelope is forgotten. The
    # symptom is always the same — a bare 400 with no `code`, so a client cannot
    # tell 「这条笔记不在队列上」 from 「标题是空的」. Worth
    # remembering as a step, not rediscovering as a bug.
    NoteRecallError,
    # K3. Without this the review queue's failures fall through to the plain
    # `ValueError` handler and every one of them answers **400** — which is how
    # "this card is already on the queue" ends up looking like a malformed
    # request. The domain raises coded errors; registering the base is what makes
    # the code mean anything at the HTTP edge.
    SchedulingError,
    # J3 (spec 021). Same trap as K3, hit again on the way in: without the base
    # registered, every decision-review failure answers a flat **400** — so "this
    # decision was never given a review date" (404) and "you tried to score the
    # outcome before it was due" (409) would both look like a malformed request,
    # and the UI could not tell the user which mistake they made.
    ReviewError,
    # J5 (spec 030). ⭐ The **fifth** time this tuple has needed a new base, and the
    # comment above has said twice that it is worth remembering as a step rather than
    # rediscovering as a bug. Adding a domain error class therefore has **three**
    # places to touch, not two: the enum, the doc table, and this tuple — and the
    # third is the one that is easy to miss because nothing fails when it is.
    LessonError,
    # ⭐⭐ Spec 052 §12.2. **The first base here that is not a `ValueError`**, so the
    # sentence at the top of this tuple is now half true ⭐ **and being half true is
    # why the test was written.** It used to read 「Every base subclasses ValueError,
    # and Starlette picks the most specific handler, so the plain ValueError handler
    # still catches everything else」 ⭐ **that second half is the load-bearing one and
    # it still holds** ⭐ registration is by class, not by base, so `ProviderError`
    # catches all seven of its subclasses ⭐ **including the two that are siblings
    # rather than subclasses** (`ProviderRateLimitedError` and
    # `ProviderIpBlockedError`, `base.py:106-108`) ⭐ which a chain of `except` clauses
    # would have separated by ordering luck.
    ProviderError,
)
