"""`GET /api/v1/metrics` — the vocabulary, per market. (spec 058)

Three groups, in the order they matter:

1. ⭐⭐ **Availability.** The endpoint's whole reason to require a market is that
   「I can compute these 32」 is not unconditionally true — ⭐ measured, `financial` and
   `daily` are both ``pending`` for ``bj``. ⭐ A version that returned all 32 everywhere
   would be correct on sh/sz and lying on bj, ⭐ **and sh/sz is where every other test
   looks**, so this has to be asserted on bj specifically or not at all.
2. **The three wrong examples.** ⭐ The bug was not that a token was missing; ⭐ it was that
   the product's *own* examples were all wrong, and that a test asserting only 「the list is
   non-empty」 would have passed the whole time.
3. **Shape.** ``market`` required, order meaningless, labels present.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.config import Settings
from alphacouncil.metrics import (
    CATALOGUE,
    FINANCIAL_CATALOGUE,
    catalogue_entries,
    catalogue_labels,
)
from alphacouncil.storage import db as dbmod
from alphacouncil.storage import migrate as migmod


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    path = tmp_path / "alphacouncil.db"
    connection = dbmod.connect_for_migration(path)
    try:
        migmod.apply(connection, database_path=path, migrations=migmod.load_migrations())
    finally:
        connection.close()
    return TestClient(create_app(Settings(database_path=path)))


class TestAvailability:
    """⭐⭐ **The reason `market` is a required parameter.**"""

    def test_shanghai_gets_the_whole_vocabulary(self, client: TestClient) -> None:
        body = client.get("/api/v1/metrics?market=sh").json()
        assert body["market"] == "sh"
        assert {cell["token"] for cell in body["metrics"]} == set(catalogue_labels())
        assert body["unavailable"] == []

    def test_shenzhen_gets_the_whole_vocabulary(self, client: TestClient) -> None:
        """⭐ Both A-share venues are the same today, ⭐ and asserting only one of them
        would let a future provider change for `sz` slip past. ⭐ Two lines, ⭐ and the
        asymmetry they encode is a fact about the data layer rather than a guess."""
        body = client.get("/api/v1/metrics?market=sz").json()
        assert len(body["metrics"]) == len(CATALOGUE) + len(FINANCIAL_CATALOGUE)

    def test_beijing_gets_nothing_and_is_told_all_of_it(
        self, client: TestClient
    ) -> None:
        """⭐⭐ **The test this whole design exists for.**

        Measured before the endpoint: `financial` is ``pending`` for ``bj`` — no provider
        declares it for that venue — and so is `daily`. ⇒ **zero** of the 32 are computable
        there, ⭐ and the eight reported figures cannot be produced at all.

        ⭐ So the honest answer is an empty `metrics` and **all 32 in `unavailable`**, ⭐
        rather than 32 offers that would never resolve. ⭐ And empty is a real answer here,
        not an error: ⭐ the reader most needs to be told that nothing on this venue can be
        watched at all.
        """
        body = client.get("/api/v1/metrics?market=bj").json()
        assert body["metrics"] == []
        assert body["unavailable"] == sorted(catalogue_labels())

    def test_the_split_follows_the_capability_matrix_not_a_hardcoded_list(
        self, client: TestClient
    ) -> None:
        """⭐ **Derived, so a provider landing for `bj` fixes this with no code.**

        The alternative — a written-in 「bj gets the 24 price ones」 — would be correct today
        and wrong the day a `bj` daily provider appears, ⭐ and it would be wrong in the
        direction that matters: promising a reader something this build cannot produce.

        ⇒ Asserted against the router's own matrix rather than against a literal, ⭐ so the
        test and the endpoint cannot agree on a wrong answer.
        """
        from alphacouncil.providers import default_router
        from alphacouncil.providers.router import CapabilityState

        matrix = default_router().capability_matrix()
        usable_datasets = {
            cell.dataset
            for cell in matrix
            if cell.market.value == "bj" and cell.state is CapabilityState.USABLE
        }
        expected = [e for e in catalogue_entries() if e.dataset in usable_datasets]
        body = client.get("/api/v1/metrics?market=bj").json()
        assert len(body["metrics"]) == len(expected)

    def test_candidates_does_not_count_as_usable(self) -> None:
        """⭐ No cell is `CANDIDATES` today, ⭐ so this is asserted as a property of the
        filter rather than of the current matrix — ⭐ 「a provider says it might handle
        this」 is not 「this build can compute it」, ⭐ and the sentence a reader gets must
        be true on the day they read it."""
        import inspect

        from alphacouncil.api.routes import metrics as route

        source = inspect.getsource(route.metrics)
        assert "CapabilityState.USABLE" in source
        assert "CapabilityState.CANDIDATES" not in source


class TestTheThreeWrongExamples:
    """⭐ The bug was not a missing token. It was that **the product's own examples were
    all wrong**, and a test asserting 「the list is non-empty」 would have passed throughout."""

    @pytest.mark.parametrize(
        "token",
        ["gross_margin", "revenue_yoy", "price"],
        ids=lambda t: t,
    )
    def test_a_token_the_product_used_to_suggest_is_still_not_computable(
        self, client: TestClient, token: str
    ) -> None:
        """⭐ `DecisionForm`'s placeholder was `gross_margin`; ⭐ the API docstring offered
        `gross_margin` / `revenue_yoy` / `price`. ⭐ None is in either catalogue, ⭐ and the
        domain accepts all three on shape alone, ⭐ so each produced a kill criterion that
        could never be evaluated, silently.

        ⭐ **This is a regression guard on the *examples*, not on the vocabulary** — ⭐ the
        vocabulary is allowed to grow, ⭐ and one of these may legitimately appear later. ⭐
        What may not happen again is the product pointing at a name it does not hold.
        """
        sh = client.get("/api/v1/metrics?market=sh").json()
        tokens = {cell["token"] for cell in sh["metrics"]}
        assert token not in tokens, (
            f"{token} has entered the catalogue — ⭐ if it is now genuinely computable, "
            "delete this test; if it is not, the product is pointing at a name it lacks"
        )

    def test_gross_margin_exists_under_the_token_the_product_actually_holds(
        self, client: TestClient
    ) -> None:
        """⭐⭐ **The fact the whole spec turned on.**

        ⭐ The reader who typed `gross_margin` wanted gross margin, ⭐ **and the product has
        gross margin** — as `gp_margin`, label 「销售毛利率」. ⭐ So the cost was never
        「this build can't do that」; ⭐ it was 「nobody was told what it is called」, ⭐ and
        a product that has a capability and hides its name is not short of capability.
        """
        cells = {c["token"]: c for c in client.get("/api/v1/metrics?market=sh").json()["metrics"]}
        assert "gp_margin" in cells
        assert cells["gp_margin"]["label"] == "销售毛利率"

    def test_the_openapi_description_no_longer_offers_an_uncomputable_example(
        self, client: TestClient
    ) -> None:
        """⭐ **The fix has to include the prose, ⭐ because the prose was part of the bug.**

        `routes/decisions.py`'s `metric` field description offered three tokens as examples
        and **all three were outside both catalogues**. ⭐ A caller reading the OpenAPI page
        had no way to know, ⭐ and the field is the one place a programmatic caller looks.

        ⇒ Asserted against the served schema, not the source file, ⭐ because what a reader
        reads is the served one.

        ⚠️ The schema is named ``KillCriterionRead`` even though ``DecisionCreateRequest``
        uses it for **writes** too. ⭐ That naming oddity predates this spec and is left
        alone; ⭐ renaming a published schema is a breaking change for callers, ⭐ and the
        cost of that is not this spec's to spend.
        """
        schema = client.get("/openapi.json").json()
        described = str(
            schema["components"]["schemas"]["KillCriterionRead"]["properties"]["metric"]
        )
        for stale in ("e.g. gross_margin", "revenue_yoy / price"):
            assert stale not in described, f"the schema still suggests 「{stale}」"
        assert "gp_margin" in described

    def test_the_promise_that_a_criterion_must_be_evaluable_is_gone(
        self, client: TestClient
    ) -> None:
        """⭐⭐ **The same lie, one field below the one I caught first.**

        ``kill_criteria``'s own description read 「At least one, and **it must be
        evaluable**」 ⭐ — ⭐ and nothing enforces that. ⭐ Measured: a criterion naming
        ``gross_margin`` returns **201**. ⭐ So the request body told the caller twice that
        the product would check, ⭐ once by naming a token it does not hold and once by
        promising a validation it does not perform.

        ⭐ **This is why the assertion is on the served text and not on 「did I remember
        to fix it」** — ⭐ the first fix passed its own test while its neighbour still lied.
        """
        schema = client.get("/openapi.json").json()
        described = str(
            schema["components"]["schemas"]["DecisionCreateRequest"]["properties"][
                "kill_criteria"
            ]
        )
        assert "it must be evaluable" not in described
        # ⭐ And it now points at the way to find out, rather than at nothing.
        assert "/api/v1/metrics" in described


class TestShape:
    def test_market_is_required(self, client: TestClient) -> None:
        """⭐⭐ **The rule lives in the signature, not in a convention** (constitution §0.2).

        ⭐ An optional `market` would need a default, ⭐ and every candidate default is
        either 「all 32」 — ⭐ **a lie for `bj`** — or a second code path to keep in step.
        ⭐ Making it required turns the wrong answer into a **422** instead of a silent one.
        """
        assert client.get("/api/v1/metrics").status_code == 422

    def test_an_unknown_market_is_refused(self, client: TestClient) -> None:
        """⭐ `zzz` is not a market, and answering it with a list would be a guess about
        which venue's data layer to use — ⭐ the same rule that makes a bare six-digit
        ticker ambiguous rather than resolved (spec 047)."""
        assert client.get("/api/v1/metrics?market=zzz").status_code == 422

    def test_the_order_carries_no_opinion(self, client: TestClient) -> None:
        """⭐⭐ **Red line 8.**

        ⭐ A list of things the product can watch, ordered by 「usefulness」, is an
        opportunity feed with a technical vocabulary. ⭐ Sorted by token is the cheapest
        guarantee that nobody later decides MA20 goes first because it is more useful — ⭐
        which is the product having an opinion, ⭐ the same thing `DecisionForm` avoids by
        giving its five actions identical weight.
        """
        sh = client.get("/api/v1/metrics?market=sh").json()
        order = [cell["token"] for cell in sh["metrics"]]
        assert order == sorted(order)

    def test_every_cell_carries_a_label_and_says_where_it_comes_from(
        self, client: TestClient
    ) -> None:
        """⭐ A token alone would still be a private vocabulary. ⭐ **And `dataset` is
        exposed** because 「it depends」 is the honest answer: ⭐ a reader is entitled to
        know which of these come from 行情 bars and which from 财报."""
        for cell in client.get("/api/v1/metrics?market=sh").json()["metrics"]:
            assert cell["label"].strip(), f"{cell['token']} has no label"
            assert cell["dataset"] in {"daily", "financial"}

    def test_catalogue_labels_and_the_endpoint_agree(self) -> None:
        """⭐ One resolver for the catalogue's shape (`F-246`).

        ⭐ `catalogue_labels()` used to destructure both dicts itself; ⭐ it now delegates to
        `catalogue_entries()`. ⭐ If it ever goes back to reading them directly, ⭐ the two
        can disagree about a metric that was added to only one of them — ⭐ and the picker
        would offer a label for a token that cannot be read.
        """
        from alphacouncil.metrics import catalogue_entries as entries

        assert catalogue_labels() == {e.token: e.label for e in entries()}
