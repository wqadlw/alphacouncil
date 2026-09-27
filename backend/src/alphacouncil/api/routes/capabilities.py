"""The capability matrix endpoint — what the data layer can serve, right now.

One honest map instead of a page discovering per-request that a feature is
dumb: `usable` (someone serves it), `candidates` (declared but all cooling,
with the seconds), `pending` (nobody declares it — "not wired yet", a fact
about the product rather than an error). Reading it triggers no network
traffic; it only reads provider declarations and the router's health
bookkeeping, so any page may consult it freely (spec 008).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from alphacouncil.api.deps import MarketData
from alphacouncil.core.time import utc_millis
from alphacouncil.providers.router import CapabilityCell

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


class CapabilitiesRead(BaseModel):
    """The full `Dataset` x `Market` map, sorted for stable rendering."""

    generated_at: str = Field(description="Server moment, ISO-8601 UTC.")
    capabilities: list[CapabilityCell] = Field(
        description="Every cell, sorted by dataset then venue. Never filtered."
    )


@router.get("", summary="Which datasets the data layer can serve, per venue")
def capabilities(market_data: MarketData) -> CapabilitiesRead:
    """Return the capability matrix in a stable order.

    Nothing here is filtered by state: `pending` cells travel with the rest,
    because "we know this is not wired yet" is the sentence that stops a user
    from mistaking a missing feature for a broken one.
    """
    cells = sorted(
        market_data.capability_matrix(),
        key=lambda cell: (cell.dataset.value, cell.market.value),
    )
    return CapabilitiesRead(generated_at=utc_millis(), capabilities=cells)
