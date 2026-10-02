"""BaoStock as a financial data source (spec 043 · D4).

## ⭐ What this is, and what it deliberately is not

One API — ``query_profit_data`` — and the eight numbers it returns in a single round trip.
⭐ **The unit of rate limiting is 「how many metrics per call」, not 「how many rows per
call」** (spec 043 §3): the six BaoStock financial endpoints share their ``pubDate`` and
``statDate`` columns, so taking all six is six round trips for one document. One endpoint
is the honest first step, and this module is written so that adding the other five is
adding a method rather than adding a second design.

## ⭐ The three facts that shaped this file, all measured

Recorded in ``.ai/specs/041-foundation-research/research.md`` §4:

1. ⭐ **It bans IPs.** ``error_code 10001011`` is 「IP 已加入黑名单」 in BaoStock's own
   documentation. ⭐ So this provider maps it to :class:`ErrorCode.DATA_SOURCE_IP_BLOCKED`
   and **not** to a generic fetch error — §4.5 is explicit that 「限流」 and 「封 IP」 are
   two things with different recovery, and a provider that cannot tell them apart cannot
   honour that.
2. ⭐ **It is not thread-safe.** Its own docs say to use processes, not threads. ⭐ The
   session is a process-level resource guarded by one lock, which is also the first of
   §4.5's required mechanisms (串行化).
3. ⭐ **Its valuation columns are point-in-time.** Measured: ``peTTM`` on the bar for
   2024-01-02 reads 29.73, while today it reads 18.97 — so a historical bar is not
   backfilled. ⭐ **That is why this module does not read them at all**: they are
   *quote* fields, not financial ones, and which ``Dataset`` they belong to is a
   decision this spec explicitly declines to make (§7).

## ⭐ Why the login is not on the request path

``logout()`` is left to process exit. ⭐ A ``logout`` called from a request handler means
the *next* request re-logs-in, and a failed re-login would be reported as
「this instrument has no financial data」 — ⭐ which is the four-state violation
constitution §4.6 exists to prevent, arrived at by a different road.

## ⭐ A maintained allowlist, and where this file's visibility ends

``import baostock`` opens a socket **inside the package**, so ``S-01`` cannot see it by
reading our files. It can only see it because ``baostock`` is named in that rule's module
list. ⭐ That list is maintained by hand and stated as such in
``checks/rules/no_raw_http.py``; this module is on the other side of that hole, and
nothing in the type system or the test suite would notice a second socket-opening
dependency being added.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable

import structlog

from alphacouncil.models.market import Market, Symbol
from alphacouncil.providers.base import (
    BatchSemantics,
    Dataset,
    ProviderCapabilities,
    ProviderEmptyError,
    ProviderError,
    ProviderIpBlockedError,
    ProviderProtocolError,
    ProviderUnreachableError,
)

log = structlog.get_logger(__name__)

__all__ = [
    "IP_BLOCKED_CODE",
    "BaostockFinancial",
    "FinancialDataProvider",
    "FinancialPeriod",
]

#: BaoStock's own code for 「your address is on the blacklist」. ⭐ A string, because it is
#: a wire value from another system: a typo in an int would be invisible until a real
#: ban happened.
IP_BLOCKED_CODE = "10001011"

#: ⭐ Gap between calls, in seconds. §4.5 requires 最小间隔; this is a **floor, not a
#: budget** — ⭐ and the jitter below is what keeps several sessions from converging on
#: the same instant. BaoStock's docs do not publish a rate limit, so this number is a
#: guess that is honest about being one.
_MIN_INTERVAL_S = 0.35
_JITTER_S = 0.20

#: ⭐ `float("inf")` parses without raising, so the finiteness check has to be explicit.
#: One number, no dependency: `math.isfinite` would do the same thing and this is the
#: only place that needs it.
_MAX_FINITE = float("inf")

#: One session per process. ⭐ **Not** per request — see the module docstring.
_LOCK = threading.Lock()
_LOGGED_IN = False
_LAST_CALL: float | None = None
_MONOTONIC: Any = None


def _monotonic() -> float:
    global _MONOTONIC
    if _MONOTONIC is None:
        import time

        _MONOTONIC = time.monotonic
    return float(_MONOTONIC())


@dataclass(frozen=True, slots=True)
class FinancialPeriod:
    """One reported period, as announced.

    ⭐ **Both dates, always.** ``period_end`` is 「which stretch of time this report is
    about」 and ``announced_at`` is 「when anyone could first have read it」 — and a
    criterion written on the first date must not be able to see a figure the second date
    had not published yet. ⭐ Storing one without the other is the single way to make
    financial data quietly look-ahead, and constitution §4.4 / red line 17 both name it.
    """

    symbol: Symbol
    period_end: date
    announced_at: date
    roe_avg: float | None
    np_margin: float | None
    gp_margin: float | None
    net_profit: float | None
    eps_ttm: float | None
    revenue: float | None
    total_shares: float | None
    float_shares: float | None

    @property
    def known(self) -> int:
        """How many of the eight metrics this row actually carries."""
        return sum(
            1
            for value in (
                self.roe_avg,
                self.np_margin,
                self.gp_margin,
                self.net_profit,
                self.eps_ttm,
                self.revenue,
                self.total_shares,
                self.float_shares,
            )
            if value is not None
        )


@runtime_checkable
class FinancialDataProvider(Protocol):
    """A source of point-in-time financial periods.

    ⭐ **A second protocol rather than a mode of :class:`MarketDataProvider`.** That one
    requires ``get_daily``, and a financial source cannot serve it -- ⭐ so making this a
    flag on one protocol would have forced a provider to declare a capability it does not
    have, which is the exact thing ``ProviderCapabilities`` exists to prevent. 「一个说
    行情的协议, 一个说财务的」 -- and the router can hold both.
    """

    @property
    def name(self) -> str:
        ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        ...

    def get_financial(
        self, symbol: Symbol, *, years: int = 8
    ) -> list[FinancialPeriod]:
        """Reported periods for one symbol, newest first.

        Returns an **empty list to mean empty** and raises for a fault — the same
        contract as ``get_daily``. ⭐ Never ``[None]`` to mean 「the source is down」,
        because those are different sentences and §4.6 is about keeping them apart.
        """
        ...


@contextmanager
def _session() -> Iterator[Any]:
    """Serialise every BaoStock call, and throttle between them.

    ⭐ Three mechanisms, and they are the three §4.5 names for this layer: **串行化**
    (the lock, because the library is not thread-safe), **最小间隔** (``_MIN_INTERVAL_S``)
    and **随机抖动** (the jitter, so two sessions do not line up).

    ⭐ **The lock is held across the caller's body**, not only around the one library call.
    That is deliberate and it is the opposite of what a tighter-looking design would do:
    the thing being protected is the **session**, which is a single process-wide socket,
    so a caller that interleaves two library calls would let the other thread log in on top
    of it. ⭐ The cost is real — one slow caller delays every other caller — and it is paid
    knowingly, because the alternative is a corruption that is intermittent and therefore
    unreproducible.
    """
    global _LOGGED_IN, _LAST_CALL

    with _LOCK:
        import baostock as bs

        if not _LOGGED_IN:
            result = bs.login()
            if getattr(result, "error_code", "0") != "0":
                _raise_for(getattr(result, "error_code", ""), getattr(result, "error_msg", ""))
            _LOGGED_IN = True
            log.info("baostock.session_opened")

        _throttle_wait()
        try:
            yield bs
        finally:
            # ⭐ The timestamp moves in `finally`, so a **failed** call still counts.
            # §7.8 says this in as many words: 「失败也算一次访问」, and a throttle that
            # forgives failures is exactly the one that gets an address banned.
            _LAST_CALL = _monotonic()


def _throttle_wait() -> None:
    """Sleep until this call is allowed to happen.

    ⭐ **The floor plus a jitter, minus however long the last call took** — so a caller
    that spent 30s doing its own work comes back with credit instead of paying the
    full interval again. Clamped at zero, which is the only reason the subtraction is safe.

    ⭐ **The first call is not delayed.** There is no previous access to be spaced away
    from, and adding an unconditional sleep to the first request of a process makes the
    cold path visibly slower for no compliance benefit.
    """
    if _LAST_CALL is None:
        return
    # `random` is a fine source of jitter and a terrible source of anything else, so the

    # one who should have to see the justification.
    wait = _MIN_INTERVAL_S + random.uniform(0.0, _JITTER_S) - (  # noqa: S311
        _monotonic() - _LAST_CALL
    )
    if wait > 0.0:
        time.sleep(wait)


def _raise_for(error_code: str, message: str) -> None:
    """Map a BaoStock error code onto this project's own vocabulary.

    ⭐ §4.5: 「限流」 and 「封 IP」 are two things with different recovery, so they are two
    error codes. Collapsing them would leave the router unable to tell 「slow down」 from
    「come back tomorrow」 — and the operator unable to tell a transient from a ban.
    """
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


def _rows(result: Any) -> Iterator[dict[str, str]]:
    """Walk a BaoStock ``QueryResult`` into dicts, checking the shape on the way.

    ⭐ The library returns **strings** for every field, including numbers. A silent
    ``float("")`` failure would look like 「no data」, so the shape is checked here
    rather than at each call site.
    """
    if getattr(result, "error_code", "0") != "0":
        _raise_for(result.error_code, getattr(result, "error_msg", ""))
    fields: Sequence[str] = getattr(result, "fields", ())
    while result.next():
        row = result.get_row_data()
        if len(row) != len(fields):
            raise ProviderProtocolError(
                f"baostock returned {len(row)} values for {len(fields)} fields"
            )
        yield dict(zip(fields, row, strict=True))


def _number(raw: str | None) -> float | None:
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
    return value if -_MAX_FINITE < value < _MAX_FINITE else None


def _day(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _symbol(code: str) -> Symbol:
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


class BaostockFinancial:
    """BaoStock, for :class:`FinancialPeriod` only."""

    def __init__(self, *, now: Callable[[], date] | None = None) -> None:
        # ⭐ A clock, injected, so the quarter boundary and the throttle's timing are
        # testable without sleeping or waiting for a quarter to turn over.
        self._now = now

    @property
    def name(self) -> str:
        return "baostock"

    @property
    def capabilities(self) -> ProviderCapabilities:
        # ⭐ **FINANCIAL and nothing else.** This provider cannot serve a daily bar, and
        # saying so here is what stops the router from ever asking it for one.
        # ⭐ **The notes field is required, not optional** (§4.5: the degradation path has
        # to state how it differs from the primary, in a form a program can read) — and
        # for a single-source dataset the honest note is that there is no primary.
        return ProviderCapabilities(
            datasets=frozenset({Dataset.FINANCIAL}),
            markets=frozenset({Market.SH, Market.SZ}),
            batch_semantics=BatchSemantics.INDEPENDENT,
            supports_batch=False,
            notes=(
                "D4 的唯一财务源, 没有主源可降级. 公告滞后**不是常数**: 实测 2026Q1 为 25 天"
                "/ 2026Q2 为 46 天 / 2024 年报为 93 天(2026-09-30 实测), 所以"
                "'约 2 个月' 是一个错的说法. valuation 字段 peTTM/pbMRQ 虽逐日 PIT,"
                "但属行情口径, 本 provider 不读 -- 归入哪个 Dataset 是另一个决定"
            ),
        )

    def get_financial(self, symbol: Symbol, *, years: int = 8) -> list[FinancialPeriod]:
        """Reported periods for one symbol, newest announcement first.

        ⭐ Eight years of quarters is 32 rows from one symbol, and the endpoint takes a
        **single** ``(year, quarter)`` — ⭐ so this is 32 serialised calls. That is the
        real cost of this source and it is stated here rather than discovered later.
        """
        if years <= 0:
            raise ValueError(f"years must be positive, got {years}")
        today = self._today()
        out: list[FinancialPeriod] = []
        with _session() as bs:
            for year in range(today.year, today.year - years, -1):
                for quarter in (4, 3, 2, 1):
                    if (year, quarter) > (today.year, (today.month - 1) // 3 + 1):
                        continue
                    out.extend(self._quarter(bs, symbol, year, quarter))
        # ⭐ Sorted by **announcement**, not by period: a restatement announces later and
        # is the version a reader should see. Sorting by period would put a Q3 restatement
        # before a Q4 that was announced first.
        out.sort(key=lambda item: (item.announced_at, item.period_end), reverse=True)
        return out

    def _today(self) -> date:
        """Today, from the injected clock when there is one.

        ⭐ Typed as ``Callable[[], date]`` rather than ``Any`` so mypy can still check the
        call: an injected clock that returns a ``datetime`` is a **test bug**, and the
        annotation is what makes it one at type-check time rather than at 3am.
        """
        if self._now is not None:
            return self._now()
        from datetime import date as _date

        return _date.today()

    def _quarter(
        self, bs: Any, symbol: Symbol, year: int, quarter: int
    ) -> Iterator[FinancialPeriod]:
        code = f"{symbol.market.value}.{symbol.code}"
        result = bs.query_profit_data(code=code, year=year, quarter=quarter)
        for row in _rows(result):
            announced = _day(row["pubDate"])
            period = _day(row["statDate"])
            # ⭐ **A report whose announcement precedes its period end is not data we can
            # use.** BaoStock's data has been clean, and a CHECK in migration 0011 already
            # refuses such a row — ⭐ so the guard here exists to turn a *source* fault
            # into an error rather than into a row that fails to insert much later.
            if announced < period:
                raise ProviderProtocolError(
                    f"baostock announced {announced} for a period ending {period}"
                )
            yield FinancialPeriod(
                symbol=symbol,
                period_end=period,
                announced_at=announced,
                roe_avg=_number(row.get("roeAvg")),
                np_margin=_number(row.get("npMargin")),
                gp_margin=_number(row.get("gpMargin")),
                net_profit=_number(row.get("netProfit")),
                eps_ttm=_number(row.get("epsTTM")),
                revenue=_number(row.get("MBRevenue")),
                total_shares=_number(row.get("totalShare")),
                float_shares=_number(row.get("liqaShare")),
            )
