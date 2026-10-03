"""The capability matrix (spec 008) — declarations plus health, never network.

Marked ``unit``: ``capability_matrix`` only reads provider declarations and
the router's own health bookkeeping, so the *real production router* can be
inspected without a single request — which is what makes the strongest test
in this file possible: the production matrix, pinned cell by cell with dead
literals, so any provider that silently drops a capability turns the suite
red instead of turning a page dumb.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import DataResult, Market, Quote, RealtimeQuote, Symbol
from alphacouncil.providers import default_router
from alphacouncil.providers.base import Dataset, ProviderCapabilities
from alphacouncil.providers.router import CapabilityState, MarketDataRouter

pytestmark = pytest.mark.unit

STAMP = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

MOUTAI = Symbol(market=Market.SH, code="600519")

#: The production capability map, written dead (constitution 8.3). Derived
#: from the providers' declared datasets x venues; changing a declaration
#: without changing this table fails here first, which is the point — a
#: silently dumb page is worse than a red test.
#:
#: ⭐ **2026-10-03, D4 wiring:** `BaostockFinancial` joined `default_router()` **for its
#: declaration** (`router.py:_declarations`), so `financial x sh` and `financial x sz`
#: moved `pending` → `usable`. ⚠️ **`financial x bj` is still `pending`**, and it is
#: pending for a reason about the world rather than about wiring: the source
#: declares `SH` and `SZ` only. This table went red first, on purpose.
EXPECTED_STATES: dict[tuple[str, str], str] = {
    ("adj_factor", "sh"): "usable",
    ("adj_factor", "sz"): "usable",
    ("adj_factor", "bj"): "pending",
    ("daily", "sh"): "usable",
    ("daily", "sz"): "usable",
    ("daily", "bj"): "pending",
    ("financial", "sh"): "usable",
    ("financial", "sz"): "usable",
    ("financial", "bj"): "pending",
    ("instruments", "sh"): "pending",
    ("instruments", "sz"): "pending",
    ("instruments", "bj"): "pending",
    ("realtime", "sh"): "usable",
    ("realtime", "sz"): "usable",
    ("realtime", "bj"): "pending",
}


def _states(router: MarketDataRouter) -> dict[tuple[str, str], str]:
    return {
        (cell.dataset.value, cell.market.value): cell.state.value
        for cell in router.capability_matrix()
    }


# ---------------------------------------------------------------------------
# the production matrix, pinned
# ---------------------------------------------------------------------------


def test_the_production_matrix_is_exactly_what_the_declarations_say() -> None:
    """Eight usable cells, seven pending, zero candidates — as declared.

    ⭐ Two of them are financial, and they moved when the source was wired. The count
    is in this docstring on purpose: a reader who changes a declaration sees the
    sentence disagree with the table before the assertion fires.
    """
    router = default_router(cache=None)

    assert _states(router) == EXPECTED_STATES


def test_pending_cells_carry_the_not_wired_yet_reason() -> None:
    """`pending` is a fact about the product ("nobody declares this"), not an
    error — the reason must say so, or a reader would mistake it for breakage."""
    router = default_router(cache=None)

    cells = {(cell.dataset.value, cell.market.value): cell for cell in router.capability_matrix()}
    # ⭐ **`financial x sh` is no longer an example of anything** — it is usable now.
    # `bj` is the cell that stays pending, and it stays pending because the source
    # does not declare that venue.
    financial = cells[("financial", "bj")]

    assert financial.state is CapabilityState.PENDING
    assert financial.sources == []
    assert financial.reason is not None
    assert "no provider" in financial.reason


def test_usable_cells_name_their_healthy_sources_in_priority_order() -> None:
    """The realtime cell names tencent then sina — the effective priority the
    capability-driven selection produces, not a hard-coded assumption."""
    router = default_router(cache=None)

    cells = {(cell.dataset.value, cell.market.value): cell for cell in router.capability_matrix()}
    realtime = cells[("realtime", "sh")]

    assert realtime.state is CapabilityState.USABLE
    assert realtime.reason is None
    assert [source.name for source in realtime.sources] == ["tencent", "sina"]


# ---------------------------------------------------------------------------
# the candidates path — declared, but all cooling
# ---------------------------------------------------------------------------


class _RefusingProvider:
    """Declares realtime everywhere and refuses everything with a 403."""

    name = "refusing"
    capabilities = ProviderCapabilities(datasets=frozenset({Dataset.REALTIME}))

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        return DataResult.error(ErrorCode.DATA_SOURCE_FORBIDDEN, source=self.name, fetched_at=STAMP)

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: object = None,
        end: object = None,
    ) -> DataResult[list[Quote]]:
        return DataResult.error(ErrorCode.DATA_SOURCE_FORBIDDEN, source=self.name, fetched_at=STAMP)


def test_a_blocked_source_turns_its_cells_into_candidates() -> None:
    """After a 403 the provider cools down for 300s; every cell it declared
    alone must read `candidates` — declared but not currently servable."""
    router = MarketDataRouter([_RefusingProvider()], cache=None)
    router.get_realtime(MOUTAI)

    cells = {(cell.dataset.value, cell.market.value): cell for cell in router.capability_matrix()}
    cell = cells[("realtime", "sh")]

    assert cell.state is CapabilityState.CANDIDATES
    assert cell.reason is not None
    assert cell.sources[0].healthy is False
    assert cell.sources[0].cooldown_remaining_s is not None
    assert cell.sources[0].cooldown_remaining_s > 0

    def test_one_awake_source_keeps_the_cell_usable_despite_a_cooling_neighbour() -> None:
        """`usable` means at least one awake declarer — a cooling neighbour is
        recorded honestly (healthy=false) but does not drag the cell down."""

        class _Healthy:
            name = "healthy"
            capabilities = ProviderCapabilities(datasets=frozenset({Dataset.REALTIME}))

            def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
                # The one fetch the router legitimately makes in this test.
                return DataResult.ok(
                    RealtimeQuote.model_validate(
                        {
                            "symbol": MOUTAI,
                            "price": 1237.0,
                            "prev_close": 1251.0,
                            "open": 1250.0,
                            "high": 1255.0,
                            "low": 1230.0,
                            "volume": 2_400_000.0,
                            "amount": 2.97e9,
                            "quoted_at": STAMP,
                            "source": "healthy",
                            "fetched_at": STAMP,
                        }
                    ),
                    source=self.name,
                    fetched_at=STAMP,
                )

            def get_daily(
                self,
                symbol: Symbol,
                *,
                start: object = None,
                end: object = None,
            ) -> DataResult[list[Quote]]:
                raise AssertionError("capability_matrix must never fetch")

        refusing = _RefusingProvider()
        router = MarketDataRouter([refusing, _Healthy()], cache=None)
        router.get_realtime(MOUTAI)  # refusing fails; healthy answers → cached ok

        cells = {
            (cell.dataset.value, cell.market.value): cell for cell in router.capability_matrix()
        }
        cell = cells[("realtime", "sh")]

        assert cell.state is CapabilityState.USABLE
        by_name = {source.name: source for source in cell.sources}
        assert by_name["refusing"].healthy is False
        assert by_name["healthy"].healthy is True
        assert by_name["healthy"].cooldown_remaining_s is None


class TestTheFinancialSourceIsDeclaredButNotRoutable:
    """⭐ The distinction this whole step rests on.

    `providers/financial.py:160-164` argues that a financial source is a **second protocol**
    rather than a mode of `MarketDataProvider`, 「and the router can hold both」. Holding both
    is only safe if **holding** and **routing to** are separate, which is what
    `_declarations()` and `_candidates()` are for.

    ⚠️ `router._candidates` is private, and the test reaches it on purpose: the claim is about
    that private's contract, not about a public result. A public assertion could only prove
    that *something* is routed, not *this* is not.
    """

    def test_the_matrix_reports_the_financial_source_for_its_venues(self) -> None:
        from alphacouncil.providers.financial import BaostockFinancial

        router = default_router(cache=None)
        cells = {
            (cell.dataset.value, cell.market.value): cell for cell in router.capability_matrix()
        }

        for venue in ("sh", "sz"):
            cell = cells[("financial", venue)]
            assert cell.state is CapabilityState.USABLE
            assert [source.name for source in cell.sources] == [BaostockFinancial().name]

    def test_its_cells_come_from_the_wiring_and_not_from_something_else(self) -> None:
        """⭐ Drop `financial=` and the cells go back to `pending`.

        This is the control: without it, 「the cells are usable」 could be caused by anything,
        and the tripwire table above would be updated for the wrong reason.
        """
        bare = MarketDataRouter([])
        cells = {(cell.dataset.value, cell.market.value): cell for cell in bare.capability_matrix()}

        assert cells[("financial", "sh")].state is CapabilityState.PENDING
        assert cells[("financial", "sh")].reason is not None

    def test_the_market_path_would_not_try_to_hand_it_a_price_request(self) -> None:
        """⭐ The failure `_candidates` must never produce: `_route()` would call `get_daily`.

        Today this also holds by coincidence — no market provider happens to declare
        `FINANCIAL` — so the assertion is here because ⭐ **coincidence is not a guard**: the
        day one does, the market path would start calling `get_daily` on a source that has no
        such method.
        """
        router = default_router(cache=None)

        assert router._candidates(Dataset.FINANCIAL, MOUTAI) == []
        assert router._candidates(Dataset.DAILY, MOUTAI), "the market path still works"

    def test_the_two_lists_are_not_the_same_object(self) -> None:
        """⭐ Cheap structural check: appending to one must not touch the other."""
        router = default_router(cache=None)
        before_market = list(router._providers)
        before_financial = list(router._financial)

        router._financial.append(object())  # type: ignore[arg-type]

        assert router._providers == before_market
        assert len(router._financial) == len(before_financial) + 1
