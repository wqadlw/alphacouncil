"""The parts of BaoStock that are not about a dataset (spec 052, §12.1).

⭐ **Why this module exists at all.** The session, the throttle and the resultset
cursor were private to :mod:`alphacouncil.providers.financial`, which is correct for
one dataset and wrong for two. A second provider would have had three ways to go and
all three are bad:

- **copy the functions** ⭐ **two homes for one fact.** This repository's tolerance for
  that is zero, and the copy is the kind that survives: ``_number`` is short, correct,
  and completely unfalsifiable on its own.
- **widen ``financial.py``** until it is 「the baostock module」 ⭐ **which is the same
  fact under a worse name**, and it is what ``financial.py:3-10`` explicitly says it is
  not written to be.
- **extract them** ⭐ **what this is.** One place that owns 「how BaoStock is spoken to」,
  and each provider keeps only what is about its own dataset.

⭐ **The second reason is the load-bearing one, and it is a bug rather than a taste.**
The throttle lives in module globals — ``_LOCK``, ``_LOGGED_IN``, ``_LAST_CALL`` — and
BaoStock is **one process-wide socket** (``financial.py``'s own module docstring says
the library is not thread-safe). ⭐ Two provider modules each with their own globals
would be **two throttles over one socket**, so the measured floor between calls would
hold within a module and not across the process. ⭐ And the floor is what §4.5 is:
a source that bans an address does not care which module asked.

⚠️ **What this module deliberately does not hold.** It has no ``Dataset``, no
capabilities, no ``notes``. ⭐ Those are per-provider claims, and ``financial.py:362-366``
is right that a provider must declare what it can serve — a shared module that knew the
dataset would be a second place where that answer lives.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date
from typing import Any, NoReturn

import structlog

from alphacouncil.models.market import Market, Symbol
from alphacouncil.providers.base import (
    ProviderEmptyError,
    ProviderError,
    ProviderIpBlockedError,
    ProviderProtocolError,
    ProviderUnreachableError,
)

log = structlog.get_logger(__name__)

#: BaoStock's own code for 「your address is on the blacklist」. ⭐ A string, because it is
#: a wire value from another system: a typo in an int would be invisible until a real
#: ban happened.
IP_BLOCKED_CODE = "10001011"

#: ⭐ Gap between calls, in seconds. §4.5 requires 最小间隔; this is a **floor, not a
#: budget** — ⭐ and the jitter below is what keeps several sessions from converging on
#: the same instant. BaoStock's docs do not publish a rate limit, so this number is a
#: guess that is honest about being one.
#:
#: ⭐ **One set of numbers for the process, not one per module** ⭐ — see the module
#: docstring. A second provider that kept its own copy would be a second floor over the
#: same socket, and the measured 「45 calls then a reset」 would become 「45 per module」.
MIN_INTERVAL_S = 0.35
JITTER_S = 0.20

#: ⭐ `float("inf")` parses without raising, so the finiteness check has to be explicit.
#: One number, no dependency: `math.isfinite` would do the same thing and this is the
#: only place that needs it.
MAX_FINITE = float("inf")

#: ⭐ One session per process. ⭐ **Not** per request, and now **not per module** —
#: `baostock.common.context.default_socket` is a single global inside the library, so
#: these three names guard one socket and have to live beside it.
LOCK = threading.Lock()
LOGGED_IN = False
LAST_CALL: float | None = None
_MONOTONIC: Any = None


def _monotonic() -> float:
    global _MONOTONIC
    if _MONOTONIC is None:
        import time as _time

        _MONOTONIC = _time.monotonic
    return float(_MONOTONIC())


@contextmanager
def session() -> Iterator[Any]:
    """Serialise every BaoStock call, and throttle between them.

    ⭐ Three mechanisms, and they are the three §4.5 names for this layer: **串行化**
    (the lock, because the library is not thread-safe), **最小间隔** (``MIN_INTERVAL_S``)
    and **随机抖动** (the jitter, so two sessions do not line up).

    ⭐ **The lock is held across the caller's body**, not only around the one library
    call. That is deliberate and it is the opposite of what a tighter-looking design
    would do: the thing being protected is the **session**, which is a single
    process-wide socket, so a caller that interleaves two library calls would let the
    other thread log in on top of it. ⭐ The cost is real — one slow caller delays every
    other caller — and it is paid knowingly, because the alternative is a corruption
    that is intermittent and therefore unreproducible.
    """
    global LOGGED_IN, LAST_CALL

    with LOCK:
        import baostock as bs

        if not LOGGED_IN:
            result = bs.login()
            if getattr(result, "error_code", "0") != "0":
                raise_for(getattr(result, "error_code", ""), getattr(result, "error_msg", ""))
            LOGGED_IN = True
            log.info("baostock.session_opened")

        _throttle_wait()
        try:
            yield bs
        finally:
            # ⭐ The timestamp moves in `finally`, so a **failed** call still counts.
            # §7.8 says this in as many words: 「失败也算一次访问」, and a throttle that
            # forgives failures is exactly the one that gets an address banned.
            LAST_CALL = _monotonic()


def _throttle_wait() -> None:
    """Sleep until this call is allowed to happen.

    ⭐ **The floor plus a jitter, minus however long the last call took** — so a caller
    that spent 30s doing its own work comes back with credit instead of paying the
    full interval again. Clamped at zero, which is the only reason the subtraction is safe.

    ⭐ **The first call is not delayed.** There is no previous access to be spaced away
    from, and adding an unconditional sleep to the first request of a process makes the
    cold path visibly slower for no compliance benefit.
    """
    if LAST_CALL is None:
        return
    # `random` is a fine source of jitter and a terrible source of anything else, so the
    # constant is named at the point of use where someone has to see the justification.
    wait = MIN_INTERVAL_S + random.uniform(0.0, JITTER_S) - (  # noqa: S311
        _monotonic() - LAST_CALL
    )
    if wait > 0.0:
        time.sleep(wait)


#: ⭐ **The shared code table, as exception *classes* rather than instances.** Each
#: provider words its own message, because 「no data for that period」 and 「no such
#: index」 are different sentences and the table has no business choosing between them.
_CODE_TO_ERROR: Mapping[str, type[ProviderError]] = {
    IP_BLOCKED_CODE: ProviderIpBlockedError,
    "-1": ProviderUnreachableError,
    "-2": ProviderProtocolError,
    "-3": ProviderEmptyError,
}


def classify(error_code: str) -> type[ProviderError] | None:
    """The exception class for a BaoStock code, or ``None`` if the code is unknown.

    ⭐ Unknown is a real answer and not a failure: several codes are endpoint-specific
    (see ``extra`` on :func:`raise_for`), and a dataset that recognises one of them
    should not have to edit this table to say so. ⭐ **A code nobody recognises becomes a
    bare ``ProviderError``** ⭐ which carries ``DATA_FETCH_ERROR`` and therefore no
    cooldown, so a new upstream code shows up as 「fetch failed」 rather than as the
    「slow down」 it may actually mean.
    """
    return _CODE_TO_ERROR.get(error_code)


def raise_for(
    error_code: str,
    message: str,
    *,
    extra: Mapping[str, type[ProviderError]] | None = None,
) -> NoReturn:
    """Map a BaoStock error code onto this project's own vocabulary.

    ⭐ §4.5: 「限流」 and 「封 IP」 are two things with different recovery, so they are two
    error codes. Collapsing them would leave the router unable to tell 「slow down」 from
    「come back tomorrow」 — and the operator unable to tell a transient from a ban.

    ⭐ ``extra`` is checked **first** and exists because the constituent endpoint has
    codes this table does not: measured ``10004010`` (a malformed date) and ``10002007``
    (a network receive failure). ⭐ The precedence matters ⭐ a dataset that has read a
    code more carefully than the generic table has must win, because that reading is the
    newer evidence.
    """
    if extra is not None:
        specific = extra.get(error_code)
        if specific is not None:
            raise specific(f"baostock error {error_code}: {message}") from None
    if error_code == IP_BLOCKED_CODE:
        # ⭐ **The ban code, not the refusal code.** BaoStock's ``10001011`` names the ban
        # outright, and §4.5's two different recoveries are then real: 20 hours of no
        # requests from this address, rather than five minutes of 「come back later」.
        raise ProviderIpBlockedError(f"baostock banned this address: {message}") from None
    if error_code in {"-1"}:
        raise ProviderUnreachableError(f"baostock network error: {message}") from None
    if error_code in {"-2"}:
        raise ProviderProtocolError(f"baostock rejected the request: {message}") from None
    if error_code in {"-3"}:
        # ⭐ `ProviderEmptyError`, not something 「unavailable」: BaoStock answered and
        # said 「this period has no data」. ⭐ That is §4.6's `no_data` — a business
        # result — and calling it 「存在但无法确认」 would put a sentence about *our*
        # knowledge where the source stated a fact.
        raise ProviderEmptyError(f"baostock has no data for that period: {message}") from None
    raise ProviderError(f"baostock error {error_code}: {message}")


def rows(result: Any) -> Iterator[dict[str, str]]:
    """Walk a BaoStock ``QueryResult`` into dicts, checking the shape on the way.

    ⭐ The library returns **strings** for every field, including numbers. A silent
    ``float("")`` failure would look like 「no data」, so the shape is checked here
    rather than at each call site.
    """
    if getattr(result, "error_code", "0") != "0":
        raise_for(result.error_code, getattr(result, "error_msg", ""))
    fields: Sequence[str] = getattr(result, "fields", ())
    while result.next():
        row = result.get_row_data()
        if len(row) != len(fields):
            raise ProviderProtocolError(
                f"baostock returned {len(row)} values for {len(fields)} fields"
            )
        yield dict(zip(fields, row, strict=True))


def number(raw: str | None) -> float | None:
    """A BaoStock numeric cell, or ``None``.

    ⭐ **One rule: not a finite number → absent.** ``""``, ``"--"``, ``"n/a"``,
    ``"None"``, ``"abc"``, ``"nan"``, ``"inf"``, ``"1e400"`` all end up as ``None``, and
    ``"0"`` and ``"-1"`` come through as themselves. ⭐ Nothing becomes ``0.0`` because it
    failed to parse — red line 6: a company that reported nothing did not report zero.

    ⭐⭐ **This used to be a list of 「absent」 spellings plus a parse attempt, and the
    mutation check deleted the list.** Every single value it named — ``""``, ``"--"``,
    ``"None"``, ``"null"``, ``"n/a"`` — also happens to make ``float()`` raise, and the two
    cases it *did not* cover (``"nan"``, ``"1e400"``) are handled by the finiteness check.
    ⭐ So the list was pure redundancy: a guard that no test can tell apart from its own
    absence. ⭐ Deleting it is the fix, and the reason is recorded here because 「there used
    to be a pattern here」 is exactly the kind of thing a later reader should not
    re-add.

    ⭐ Unparseable becomes ``None`` rather than raising, on purpose: one odd cell must not
    cost the other nine, and this table's purpose is to be read partially. ⭐ The opposite
    choice — raise a protocol error — turns 「this field is odd」 into 「this instrument has
    no financial data for 32 quarters」, because the exception escapes the whole fetch.

    ⭐⭐ **``nan`` is why the finiteness check is not optional.** ``float("nan")`` does not
    raise. ⭐ And a stored `nan` is *worse* than a ``NULL``: ``nan > 0.5`` is false, so a
    criterion reads it as 「not met」, while ``nan != 0`` is **true**, so anything comparing
    against zero believes it is a real reading. ⭐ SQLite will store it in a ``REAL`` column
    under ``STRICT`` without complaint. A missing number must be missing, not a number that
    disagrees with arithmetic.
    """
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if -MAX_FINITE < value < MAX_FINITE else None


def day(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def symbol(code: str) -> Symbol:
    """``sh.600519`` → :class:`Symbol`.

    ⭐ The market comes from BaoStock's own prefix and is **never inferred from the
    number** — red line 16, because ``000001`` is the Shanghai Composite on ``sh`` and
    Ping An Bank on ``sz``, and a rule that guesses is a rule that will be wrong once.
    """
    market, _, digits = code.partition(".")
    try:
        return Symbol(market=Market(market), code=digits)
    except ValueError as exc:
        raise ProviderProtocolError(f"baostock code {code!r} has no known market") from exc


__all__ = [
    "IP_BLOCKED_CODE",
    "JITTER_S",
    "LAST_CALL",
    "LOCK",
    "LOGGED_IN",
    "MAX_FINITE",
    "MIN_INTERVAL_S",
    "classify",
    "day",
    "number",
    "raise_for",
    "rows",
    "session",
    "symbol",
]
