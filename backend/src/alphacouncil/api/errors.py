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
from alphacouncil.domain.watchlist import WatchlistError

#: The HTTP status each coded failure deserves.
#:
#: The domain does not know about HTTP, and this map is why it does not have to.
#: Anything absent is a 400: the *request* was wrong rather than the state it
#: assumed. A state conflict is a 409, and "the thing you asked about is not
#: there" is a 404 — statuses the frontend can act on without reading prose.
_STATUS_BY_CODE: dict[str, int] = {
    ErrorCode.WATCHLIST_NOT_FOLLOWED.value: 404,
    ErrorCode.WATCHLIST_ALREADY_REMOVED.value: 409,
    ErrorCode.INSTRUMENT_ASSET_TYPE_CONFLICT.value: 409,
    ErrorCode.CARD_NOT_FOUND.value: 404,
    ErrorCode.CARD_ALREADY_VERIFIED.value: 409,
    ErrorCode.CARD_NOT_ACTIVE.value: 409,

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
)
