"""⭐ Recovery is keyed on the **reason**, not on 「it failed」 (spec 043).

`.ai/error-codes.md` requires the split and then explains why in one sentence:

> ⚠️ **限流与封 IP 必须分成两个 code** -- **恢复策略不同**(降速 vs 等 20 小时),
> 程序与用户都需要区分。

⭐ Until spec 043 both conditions produced ``DATA_SOURCE_FORBIDDEN``, both raised
``ProviderBlockedError``, and the router had exactly **one** cooldown for them. The enum
split was real on paper and changed no behaviour -- ⭐ and a split that changes no
behaviour is a rename.

So these tests assert the **durations**. A test that only checked 「a blocked source goes
into cooldown」 passed against all three cases, and would keep passing if they were merged
again tomorrow.

## The clock is hand-cranked

A ban cools a source down for twenty hours. Asserting that with a real clock would either
sleep or lie about the elapsed time, so :class:`_HandClock` advances only when a test says
so, and every duration here is read at ``t = 0``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import (
    DataResult,
    DataStatus,
    Market,
    Quote,
    RealtimeQuote,
    Symbol,
)
from alphacouncil.providers import router as router_mod
from alphacouncil.providers.base import Dataset, ProviderCapabilities
from alphacouncil.providers.router import MarketDataRouter

STAMP = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
MOUTAI = Symbol(market=Market.SH, code="600519")


class _HandClock:
    """Time only moves when a test moves it."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Failing:
    """Answers everything with one fixed error code."""

    name = "failing"
    capabilities = ProviderCapabilities(datasets=frozenset({Dataset.REALTIME}))

    def __init__(self, code: ErrorCode) -> None:
        self._code = code

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        return DataResult.error(self._code, source=self.name, fetched_at=STAMP)

    def get_daily(
        self, symbol: Symbol, *, start: object = None, end: object = None
    ) -> DataResult[list[Quote]]:
        return DataResult.error(self._code, source=self.name, fetched_at=STAMP)


def _quote() -> RealtimeQuote:
    return RealtimeQuote(
        symbol=MOUTAI,
        price=1500.0,
        prev_close=1498.5,
        open=1499.0,
        high=1502.0,
        low=1497.0,
        volume=1.0,
        amount=1.0,
        quoted_at=STAMP,
        source="failing",
        fetched_at=STAMP,
    )


def _left(router: MarketDataRouter) -> float | None:
    """Seconds left on the one cell this file's providers declare, **or ``None``**.

    ⭐ ``None`` is passed through rather than folded into ``0.0`` because that is the
    documented contract -- 「Null when healthy」 -- and a helper returning ``0.0`` would make
    「healthy」 and 「cooling with no time left」 the same answer. ⭐ They differ: the first
    means the source will be asked, the second that it is skipped this instant and asked
    the next.
    """
    states = {
        (cell.dataset.value, cell.market.value): cell
        for cell in router.capability_matrix()
    }
    remaining: float | None = states[("realtime", "sh")].sources[0].cooldown_remaining_s
    return remaining


def _cooled_down(router: MarketDataRouter) -> float:
    """Seconds left, for the tests that are about a source that *is* cooling."""
    remaining = _left(router)
    assert remaining is not None, "expected this source to be cooling"
    return remaining


def _router(provider: _Failing, clock: _HandClock | None = None) -> MarketDataRouter:
    """⭐ Always a hand-cranked clock.

    ⭐ The first draft of this file left the clock at its ``time.monotonic`` default and
    compared a **duration** against it -- so ``300.0`` came back as ``299.99934``, which
    read as a rounding problem and was actually the two calls being real seconds apart.
    ⭐ A duration assertion against a running clock can only ever be a tolerance assertion,
    and a tolerance is exactly what would hide a real off-by-one.
    """
    return MarketDataRouter([provider], cache=None, clock=clock or _HandClock())


def _ask(router: MarketDataRouter) -> DataResult[RealtimeQuote]:
    return router.get_realtime(MOUTAI)


class TestTheThreeRecoveriesDiffer:
    def test_a_refusal_waits_five_minutes(self) -> None:
        router = _router(_Failing(ErrorCode.DATA_SOURCE_FORBIDDEN))

        _ask(router)

        assert _cooled_down(router) == pytest.approx(router_mod._BLOCKED_COOLDOWN_S)

    def test_a_throttle_waits_thirty_seconds(self) -> None:
        """⭐ 降速, not 「be told off for five minutes」. A busy source is back before anyone
        notices, and a refusal's cooldown over a condition that clears by itself makes a
        whole failover rotation happen for nothing."""
        router = _router(_Failing(ErrorCode.DATA_SOURCE_RATE_LIMITED))

        _ask(router)

        assert _cooled_down(router) == pytest.approx(router_mod._RATE_LIMITED_COOLDOWN_S)

    def test_a_ban_waits_twenty_hours(self) -> None:
        """⭐ 「请等待约 20 小时或更换网络；**不要重试**」 -- the number the doc gives, and
        the reason a ban is not merely 「blocked for longer」."""
        router = _router(_Failing(ErrorCode.DATA_SOURCE_IP_BLOCKED))

        _ask(router)

        assert _cooled_down(router) == pytest.approx(20 * 3600.0)

    def test_the_three_numbers_are_three_numbers(self) -> None:
        """⭐ The assertion that survives the next person to edit the table.

        ⭐ Three cases with three identical durations is a table with one entry and two
        aliases, and it would satisfy every duration test above.
        """
        durations = {
            router_mod._BLOCKED_COOLDOWN_S,
            router_mod._RATE_LIMITED_COOLDOWN_S,
            router_mod._IP_BLOCKED_COOLDOWN_S,
        }

        assert len(durations) == 3

    def test_a_ban_outlasts_a_throttle_by_a_wide_margin(self) -> None:
        """⭐ Asserted as a **ratio**, not as two constants.

        ⭐ A later edit to either number should not be able to quietly invert the ordering
        while every ``== constant`` assertion above still passes, because both constants
        would have moved together.
        """
        assert router_mod._IP_BLOCKED_COOLDOWN_S > 100 * router_mod._RATE_LIMITED_COOLDOWN_S


class TestTheTableIsComplete:
    @pytest.mark.parametrize(
        "code",
        [
            ErrorCode.DATA_SOURCE_FORBIDDEN,
            ErrorCode.DATA_SOURCE_RATE_LIMITED,
            ErrorCode.DATA_SOURCE_IP_BLOCKED,
        ],
    )
    def test_each_reason_is_in_the_table(self, code: ErrorCode) -> None:
        assert code in router_mod._COOLDOWN_BY_CODE

    def test_a_transport_fault_is_not_in_the_table(self) -> None:
        """⭐ ⭐ **The guard against the guard.**

        ⭐ Before spec 043 the branch read ``if error_code is DATA_SOURCE_FORBIDDEN``, so
        「a code that is not in the table」 and 「a code that means 『come back sooner』」 were
        the same case. ⭐ A recovery table that grows an entry by accident turns a fatal
        fault into a skipped-source one, and the added line looks like the others in review.
        """
        assert ErrorCode.DATA_SOURCE_UNREACHABLE not in router_mod._COOLDOWN_BY_CODE
        assert ErrorCode.DATA_NO_DATA not in router_mod._COOLDOWN_BY_CODE
        assert ErrorCode.DATA_UNVERIFIABLE not in router_mod._COOLDOWN_BY_CODE

    def test_an_unlisted_code_needs_three_strikes(self) -> None:
        """⭐ An unreachable source gets the short repeated-failure fuse, and it takes
        **three** of them first -- a transport fault is cheap, and one flaky DNS answer
        should not take a source out."""
        router = _router(_Failing(ErrorCode.DATA_SOURCE_UNREACHABLE))

        _ask(router)
        assert _left(router) is None

        _ask(router)
        _ask(router)

        assert _cooled_down(router) == pytest.approx(router_mod._FAILURE_COOLDOWN_S)


class TestARecoveryEndsTheCooldown:
    def test_one_good_answer_ends_a_ban_immediately(self) -> None:
        """⭐ A twenty-hour cooldown must not outlive its own cause.

        ⭐ The cause here is *our* behaviour, not the source's state: a ban we caused by
        hammering clears when we stop hammering, so a source that answers is proof the ban
        is over. ⭐ Reading it the other way -- 「keep it out for the full twenty hours no
        matter what」 -- would make the system unable to recover from its own mistake.
        """

        class _Recovers(_Failing):
            def __init__(self) -> None:
                super().__init__(ErrorCode.DATA_SOURCE_IP_BLOCKED)
                self.broken = True

            def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
                if self.broken:
                    # ⭐ Flip **before** returning the error, so the *next* call succeeds.
                    # ⭐ The first version flipped it on the way to the good answer, which
                    # meant the flag was still true when the router asked again and the
                    # provider failed forever — ⭐ the test then failed as 「a ban never
                    # lifts」 when the truth was that the fake could not recover.
                    self.broken = False
                    return super().get_realtime(symbol)
                return DataResult.ok(_quote(), source=self.name, fetched_at=STAMP)

        clock = _HandClock()
        router = _router(_Recovers(), clock)

        _ask(router)
        assert _cooled_down(router) == pytest.approx(20 * 3600.0)

        clock.advance(20 * 3600.0)
        _ask(router)

        assert _left(router) is None

    def test_a_cooling_source_is_not_asked_again(self) -> None:
        """⭐ ⭐ The point of a cooldown: a source that is cooling is **skipped**, not
        re-tried politely.

        ⭐ Without this, every request pays a request to a source we have already decided
        to leave alone -- ⭐ which is precisely how 「we were told to slow down」 turns back
        into the ban it was warning about.
        """

        class _Counting(_Failing):
            def __init__(self) -> None:
                super().__init__(ErrorCode.DATA_SOURCE_RATE_LIMITED)
                self.asked = 0

            def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
                self.asked += 1
                return super().get_realtime(symbol)

        provider = _Counting()
        router = _router(provider)

        _ask(router)
        _ask(router)
        _ask(router)

        assert provider.asked == 1


class TestTheFailureIsNotAnAbsence:
    @pytest.mark.parametrize(
        "code",
        [
            ErrorCode.DATA_SOURCE_RATE_LIMITED,
            ErrorCode.DATA_SOURCE_IP_BLOCKED,
            ErrorCode.DATA_SOURCE_FORBIDDEN,
        ],
    )
    def test_no_reason_is_reported_as_no_data(self, code: ErrorCode) -> None:
        """⭐ §4.6, and the reason the codes had to be split at the **source** too.

        ⭐ A rate-limited or banned symbol must never read as 「this instrument has no
        data」: one is a fact about the instrument, the other about us. ⭐ All three reasons
        in one test rather than three, because they are one invariant -- ⭐ and mypy's
        ``comparison-overlap`` was pointing out that the three separate tests each
        restated an assertion the previous one had already narrowed.
        """
        assert _Failing(code).get_realtime(MOUTAI).status is DataStatus.ERROR
