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
#: from the providers' declared datasets x venues on 2026-09-27; changing a
#: declaration without changing this table fails here first, which is the
#: point — a silently dumb page is worse than a red test.
EXPECTED_STATES: dict[tuple[str, str], str] = {
    ("adj_factor", "sh"): "usable",
    ("adj_factor", "sz"): "usable",
    ("adj_factor", "bj"): "pending",
    ("daily", "sh"): "usable",
    ("daily", "sz"): "usable",
    ("daily", "bj"): "pending",
    ("financial", "sh"): "pending",
    ("financial", "sz"): "pending",
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
    """Six usable cells, nine pending, zero candidates — as declared."""
    router = default_router(cache=None)

    assert _states(router) == EXPECTED_STATES


def test_pending_cells_carry_the_not_wired_yet_reason() -> None:
    """`pending` is a fact about the product ("nobody declares this"), not an
    error — the reason must say so, or a reader would mistake it for breakage."""
    router = default_router(cache=None)

    cells = {(cell.dataset.value, cell.market.value): cell for cell in router.capability_matrix()}
    financial = cells[("financial", "sh")]

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
