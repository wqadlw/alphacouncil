"""The capability matrix over HTTP (spec 008) — shape, order, honesty.

Marked ``unit``: the matrix reads declarations and health bookkeeping only,
so the real production router is safe to use here — no stub, no network.
The point of exercising the *real* one through the API is that the endpoint
must never filter or reshuffle what the router reports.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app

pytestmark = pytest.mark.unit

CAPABILITIES = "/api/v1/capabilities"

EXPECTED_CELLS = 15  # 5 datasets x 3 venues, every one of them present.


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A client over the real production router — the matrix never fetches."""
    with TestClient(create_app()) as test_client:
        yield test_client


def test_the_matrix_travels_whole_and_in_a_stable_order(client: TestClient) -> None:
    """15 cells, sorted by dataset then venue — nothing filtered, nothing hidden.

    A `pending` cell dropped here would let a page mistake a missing feature
    for a broken one; the endpoint's contract is to carry all of them.
    """
    response = client.get(CAPABILITIES)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generated_at"].endswith("Z")
    cells = body["capabilities"]
    assert len(cells) == EXPECTED_CELLS

    keys = [(cell["dataset"], cell["market"]) for cell in cells]
    assert keys == sorted(keys)
    assert len(set(keys)) == EXPECTED_CELLS


def test_every_cell_states_its_state_from_the_closed_vocabulary(client: TestClient) -> None:
    response = client.get(CAPABILITIES)

    body = response.json()
    assert {cell["state"] for cell in body["capabilities"]} <= {
        "usable",
        "candidates",
        "pending",
    }
    pending = [cell for cell in body["capabilities"] if cell["state"] == "pending"]
    assert all(cell["reason"] for cell in pending)
    usable = [cell for cell in body["capabilities"] if cell["state"] == "usable"]
    assert all(cell["reason"] is None for cell in usable)


def test_healthy_sources_carry_no_cooldown_number(client: TestClient) -> None:
    """`cooldown_remaining_s` is only for sources actually cooling — a null
    field on a healthy source would let a client render a countdown that
    does not exist. (The candidates path itself is covered, with forged
    cooldowns, in test_capability_matrix.py.)"""
    response = client.get(CAPABILITIES)

    body = response.json()
    for cell in body["capabilities"]:
        for source in cell["sources"]:
            if source["healthy"]:
                assert source["cooldown_remaining_s"] is None
