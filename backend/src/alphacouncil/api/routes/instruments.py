"""Resolving a ticker to an instrument — the server half of "which one did you mean".

This endpoint exists because of a property of the error envelope, and it is worth
recording so nobody folds it back in later. `.ai/error-codes.md` §1 fixes the
diagnostic at exactly five keys, and the check runner's `--json` output is
asserted to have exactly those — so there is nowhere to put "here are the two
markets your code could mean" inside a failure. That is the right answer anyway:
an ambiguous ticker is not an error, it is a *question*, and the input is one
answer short of being valid.

So the ambiguous case is a 200 carrying the choices. The frontend posts the
choice back to the watchlist route and never needs to know the code-segment
table, which is the point — a second copy of that table in TypeScript would
drift from the one in :mod:`alphacouncil.domain.instrument` with nothing to
catch it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from alphacouncil.domain.instrument import TickerAmbiguousError, parse_ticker
from alphacouncil.models.market import AssetType, Market

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


class ResolveStatus(StrEnum):
    """Which of the two answers this is.

    An enum rather than a boolean because the two states carry different data —
    a resolved instrument or a list of choices — and a boolean would leave five
    of the fields meaningless without saying which five.
    """

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


class InstrumentResolveRead(BaseModel):
    """The answer, in one shape for both statuses."""

    status: ResolveStatus
    code: str
    market: Market | None = None
    asset_type: AssetType | None = None
    display: str | None = Field(
        default=None,
        description="Conventional form, e.g. 600519.SH. Absent while ambiguous.",
    )
    candidates: list[Market] = Field(
        default_factory=list,
        description="Markets the code could mean. Empty unless ambiguous.",
    )


@router.get("/resolve", summary="Resolve a ticker, reporting ambiguity instead of failing")
def resolve(
    ticker: Annotated[str, Query(min_length=1, description="600519 / sh600519 / 600519.SH")],
    market: Market | None = None,
    asset_type: AssetType = AssetType.STOCK,
) -> InstrumentResolveRead:
    """Resolve ``ticker``, or list the markets it could mean.

    ``market`` is what the user picks when the response came back ``ambiguous``.
    Passing it up front is also how a caller overrides the derived market — and
    how it gets told when the two disagree.

    Raises:
        TickerInvalidError: The text is not a ticker, or contradicts a stated
            market. Surfaces as the standard diagnostic envelope with a 400.
    """
    try:
        symbol = parse_ticker(ticker, market=market, asset_type=asset_type)
    except TickerAmbiguousError as exc:
        return InstrumentResolveRead(
            status=ResolveStatus.AMBIGUOUS,
            code=exc.ticker,
            candidates=sorted(exc.candidates, key=lambda item: item.value),
        )
    return InstrumentResolveRead(
        status=ResolveStatus.RESOLVED,
        code=symbol.code,
        market=symbol.market,
        asset_type=symbol.asset_type,
        display=symbol.full,
    )
