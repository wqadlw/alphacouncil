"""The universe as an API: who was in it, when, and how stale the answer is.

Three endpoints, and ⭐ **the third one is not optional** — spec 052 §2.4 and
§4.2: a roster that does not say how old it is is `data-sources.md:137`'s 僵尸报价 in
another costume, and this source has a **weekly** resolution, so the newest grid point can
be up to seven days behind the day the page is opened.

Written straight against the tables rather than through a repository module, ⭐ and that is
a deliberate scope choice for the first cut: `spec 052 §12.5` puts
`storage/repositories/index_universe.py` next, and ⭐ **the query shapes here are the ones
it will have to serve** ⭐ so writing them at the HTTP edge first means the repository gets
its contract measured instead of guessed.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from alphacouncil.api.deps import DatabaseConnection

router = APIRouter(prefix="/api/v1/universe", tags=["universe"])


class Membership(BaseModel):
    """One observed interval of one symbol's membership."""

    market: str
    code: str
    name: str = Field(description="The name as the source reported it, at `last_observed_on`.")
    first_observed_on: date
    last_observed_on: date
    #: ⭐ True when this is the roster we know of ⭐ **not** 「currently in the index」 ⭐
    #: because we cannot know that ⭐ **the source's weekly batch means the newest
    #: observation is at most seven days old** ⭐ and it says nothing about later.
    is_latest: bool


class Freshness(BaseModel):
    """⭐ 「我们知道的最后一天」— and it travels with every answer."""

    index_code: str
    latest_grid_point: date | None
    members: int | None
    source: str | None
    #: ⭐ **The resolution as a fact a program can branch on** ⭐ — not the sentence.
    #: ⚠️ The sentence a reader gets about the lag is **product copy**, and
    #: `pyproject.toml:130-132` says display wording has always lived in `frontend/`
    #: ⭐ **referred to rather than quoted here**, because `RUF003` flags a fullwidth comma
    #: even inside corner brackets ⭐ — the same decision `api/errors.py:54-59` records.
    #: ⭐ so the page writes it, beside the boundary line `PoolPage.tsx:574-580` keeps
    #: there. ⭐ A sentence in a Pydantic default is the same wording arriving from a place
    #: nobody reviews as copy.
    resolution: str = "weekly"
    #: ⭐ **False means 「我们从来没取过」, which is not 「名单是空的」** ⭐ and the first
    #: draft said both in one sentence ⭐ **which is the `F-218` shape wearing prose**: a
    #: reader who cannot tell them apart will report the second as the first.
    ever_swept: bool = False


class UniverseRead(BaseModel):
    freshness: Freshness
    members: list[Membership]


_INDEX = "000300"


@router.get("/status", response_model=Freshness)
def status(connection: DatabaseConnection) -> Freshness:
    """How much of the roster we know, and how old it is.

    ⭐ A separate endpoint rather than a field on the list ⭐ because a page that only
    fetches the list still needs the answer, and ⭐ **the two are different requests whose
    freshness differs** ⭐ the roster can be cached while this cannot.
    """
    row = connection.execute(
        "SELECT grid_point, members, source FROM index_universe_sweeps"
        " WHERE index_code = ? ORDER BY grid_point DESC LIMIT 1",
        (_INDEX,),
    ).fetchone()
    if row is None:
        # ⭐ `ever_swept` stays False and the page says so ⭐ **because 「下面没有内容」 on
        # its own is indistinguishable from 「名单是空的」** ⭐ and they are different facts.
        return Freshness(
            index_code=_INDEX, latest_grid_point=None, members=None, source=None
        )
    return Freshness(
        index_code=_INDEX,
        latest_grid_point=date.fromisoformat(row["grid_point"]),
        members=int(row["members"]),
        source=str(row["source"]),
        # ⭐ Said explicitly ⭐ **because the field's default is False, and False means
        # 「我们从来没取过」** ⭐ — leaving it off would claim that about 300 stored rows.
        ever_swept=True,
    )


@router.get("", response_model=UniverseRead)
def members(
    connection: DatabaseConnection,
    q: str | None = None,
) -> UniverseRead:
    """The roster at the newest grid point we hold, with that grid point attached.

    ⭐ ``q`` filters on the **code or the name the source reported** ⭐ and that is the
    only thing it does ⭐ **there is no sort, no score and no way to ask 「which of these
    should I look at」** ⭐ because constitution §802-803 puts a searchable list on the ✅
    side of the line and a shortlist on the ❌ side ⭐ **and the difference between them is
    exactly this parameter.**
    """
    row = connection.execute(
        "SELECT grid_point FROM index_universe_sweeps WHERE index_code = ?"
        " ORDER BY grid_point DESC LIMIT 1",
        (_INDEX,),
    ).fetchone()
    if row is None:
        return UniverseRead(
            freshness=Freshness(
                index_code=_INDEX, latest_grid_point=None, members=None, source=None
            ),
            members=[],
        )
    latest = date.fromisoformat(row["grid_point"])

    sql = (
        "SELECT market, code, name_as_observed, first_observed_on, last_observed_on"
        " FROM index_constituents WHERE index_code = ? AND last_observed_on = ?"
    )
    params: list[object] = [_INDEX, latest.isoformat()]
    if q is not None and q.strip():
        sql += " AND (code LIKE ? OR name_as_observed LIKE ?)"
        pattern = f"%{q.strip()}%"
        params += [pattern, pattern]
    sql += " ORDER BY code"

    rows = connection.execute(sql, params).fetchall()
    fresh = status(connection)
    return UniverseRead(
        freshness=fresh,
        members=[
            Membership(
                market=str(r["market"]),
                code=str(r["code"]),
                name=str(r["name_as_observed"]),
                first_observed_on=date.fromisoformat(r["first_observed_on"]),
                last_observed_on=date.fromisoformat(r["last_observed_on"]),
                is_latest=True,
            )
            for r in rows
        ],
    )


@router.get("/history/{market}/{code}", response_model=list[Membership])
def history(
    market: str, code: str, connection: DatabaseConnection
) -> list[Membership]:
    """⭐ Every interval we observed for one symbol ⭐ **not** only the current one.

    ⭐ This is the endpoint 「出现过的」 actually needs ⭐ and it is the one that cannot be
    reconstructed from the roster: a symbol that left in 2013 and is in the page's own
    `instruments` table has no row in the latest roster ⭐ **and a reader looking at a 2013
    decision needs that row to resolve the name.**
    """
    rows = connection.execute(
        "SELECT market, code, name_as_observed, first_observed_on, last_observed_on"
        " FROM index_constituents WHERE index_code = ? AND market = ? AND code = ?"
        " ORDER BY first_observed_on",
        (_INDEX, market, code),
    ).fetchall()
    newest = status(connection).latest_grid_point
    return [
        Membership(
            market=str(r["market"]),
            code=str(r["code"]),
            name=str(r["name_as_observed"]),
            first_observed_on=date.fromisoformat(r["first_observed_on"]),
            last_observed_on=date.fromisoformat(r["last_observed_on"]),
            is_latest=newest is not None and date.fromisoformat(r["last_observed_on"]) == newest,
        )
        for r in rows
    ]
