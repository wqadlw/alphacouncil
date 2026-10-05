"""The metrics this build can compute, **for one market**. (spec 058)

## ⭐ Why this endpoint exists

Measured 2026-10-05, before this route existed:

```
  DecisionForm's kill-criterion input   placeholder="gross_margin"
  metrics.CATALOGUE + FINANCIAL_CATALOGUE  32 tokens, all with Chinese labels
  gross_margin in either                 no. ⭐ the real one is gp_margin「销售毛利率」
  domain validation                      [a-z][a-z0-9_]* — shape only, not existence
  POST /api/v1/decisions {metric: gross_margin}   201, stored verbatim
  any sentence at write time             none
```

⭐ So a reader who followed the product's own example got a kill criterion that **could never
be evaluated**, and the only place that would ever have said so — `read_metric`'s
`MetricStatus.UNKNOWN_METRIC` — runs months later, when the criterion comes due. ⭐ At that
point the sentence blames the data, and the data is fine: `read_metric`'s own docstring
says the early-return order exists precisely so 「a name this build cannot answer never
reaches an indicator that might return something plausible for it」.

⇒ ⭐ **The capability was already end to end. Only its timing was wrong.** This route moves
the question from *evaluation* to *entry*.

## ⭐ Why `market` is a required parameter

⭐⭐ **Not optional, and that is the point** (spec 058 §六 #2).

Measured: the capability matrix has `financial` as ``pending`` for ``bj`` — no provider
declares it for that venue — while `sh`/`sz` are ``usable``. ⭐ So **「I can compute these
32」 is not unconditionally true**: on a Beijing instrument the eight reported figures cannot
be produced at all, ⭐ and offering them would be the same lie this endpoint exists to
remove, pointed the other way.

⭐ An optional `market` would default to something, ⭐ and every such default is either 「all
32」 (a lie for `bj`) or a second code path to keep in step. ⭐ Requiring it makes the wrong
answer a **422** instead of a silent one, ⭐ which is constitution §0.2's 「能移到 ③/④ 的就移」:
the rule lives in the signature instead of in a convention nobody would remember.

## ⭐ Why this does not refuse uncomputable metrics

Because `criterion_sentence` has an entire sentence state for 「不在我们能算的指标里」,
⭐⭐ and replacing the free-text field with a `<select>` would make that sentence
**unreachable from the interface** — ⭐⭐ that is deleting a capability, not fixing a defect.
A metric the reader wants and this build lacks is a **fact about them**, and the domain
already accepts it (`[a-z][a-z0-9_]*`). ⇒ This endpoint tells the truth at entry time
instead; `spec 058` §2.1.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from alphacouncil.api.deps import MarketData
from alphacouncil.core.time import utc_millis
from alphacouncil.metrics import catalogue_entries
from alphacouncil.models.market import Market
from alphacouncil.providers.base import Dataset
from alphacouncil.providers.router import CapabilityState

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

__all__ = ["router"]


class MetricCell(BaseModel):
    """One computable metric, in the words the reader reads it in."""

    token: str = Field(description="The name to write into a kill criterion.")
    label: str = Field(
        description=(
            "Chinese label. ⭐ Shown instead of the token, ⭐ because a private vocabulary "
            "is the thing this endpoint exists to remove."
        )
    )
    dataset: Dataset = Field(
        description="⭐ Which provider dataset must work for this to be computable here. "
        "Exposed because the reader is entitled to know which of these come from 行情 and "
        "which from 财报 — ⭐ and because 'it depends' is the honest answer, not a shrug."
    )


class MetricCatalogueRead(BaseModel):
    """What this build can compute, for one market. **Never filtered by anything else.**"""

    generated_at: str = Field(description="Server moment, ISO-8601 UTC.")
    market: Market = Field(description="⭐ Required. See the module docstring.")
    metrics: list[MetricCell] = Field(
        description="⭐ **Only what this market can compute.** ⭐ Empty is a real answer: "
        "it is what a venue with no declared provider returns, ⭐ and it is the sentence the "
        "reader most needs ⭐ — that nothing here can be watched at all."
    )
    #: ⭐ The tokens this market *cannot* compute, with the dataset each one is waiting on.
    #: ⭐ **Included on purpose** (spec 058 §2.1): the reader may still write them, ⭐ so
    #: hiding them would make the interface argue with a decision the domain permits.
    unavailable: list[str] = Field(
        description="Tokens excluded for this market, sorted. ⭐ Empty for sh/sz."
    )


@router.get("", summary="Which metrics this build can compute, for one market")
def metrics(
    market_data: MarketData,
    # ⭐⭐ **No default at all, not even `Query(...)`.** ⭐ FastAPI treats a parameter with no
    # default as required, ⭐ so the rule lives in the signature — ⭐ and `Query(...)` as a
    # default is the idiom `B008` exists to complain about, ⭐ which is how the first version
    # of this line was written. ⭐ Every other query parameter in this codebase uses
    # `Annotated[…, Query()]` for the same reason.
    market: Annotated[Market, Query(description="sh / sz / bj. ⭐ Required.")],
) -> MetricCatalogueRead:
    """Return the computable metrics for ``market``, and say which ones are not.

    ⭐ **Availability comes from the router's own capability matrix**, not from a list
    written here. ⭐ A hardcoded 「all 32」 would be correct today and wrong the day a
    provider lands for `bj`, ⭐ and it would be wrong in the one direction that matters:
    offering a reader something this build cannot produce.

    ⭐ **`CANDIDATES` counts as unavailable.** Measured, no cell is in that state today, ⭐
    but 「a provider says it might handle this」 is not 「this build can compute it」, ⭐ and
    the sentence a reader gets must be true on the day they read it.
    """
    usable = {
        cell.dataset
        for cell in market_data.capability_matrix()
        if cell.market is market and cell.state is CapabilityState.USABLE
    }

    entries = catalogue_entries()
    computable = [entry for entry in entries if entry.dataset in usable]
    blocked = sorted(entry.token for entry in entries if entry.dataset not in usable)

    return MetricCatalogueRead(
        generated_at=utc_millis(),
        market=market,
        metrics=[
            MetricCell(token=entry.token, label=entry.label, dataset=entry.dataset)
            for entry in computable
        ],
        unavailable=blocked,
    )
