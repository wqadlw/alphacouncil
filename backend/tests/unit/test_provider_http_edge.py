"""A source failure has to arrive as a sentence, not as a 500 (spec 052 · §12.2).

Marked ``unit``: the route used here is mounted by the test, because ⭐ **as of this
commit no product endpoint raises a ``ProviderError``** ⭐ the universe provider is the
next step and this file is what tells that step's author the edge already works.

## The gap this file exists because of

Measured 2026-10-03, before the change: ``providers/sources.py:97-125`` is the **only**
place a ``ProviderError`` becomes something with a status, it is on the market path, and
``providers/__init__.py:75-78`` says in as many words that the router has no fetch entry
point for the other protocols. ⇒ A financial or universe provider raising produced
**Starlette's default 500**, with none of the five-field envelope.

⭐ **And a 500 with no body is the specific failure constitution §4.6 names**: 「确实没有
数据」 and 「接口坏了」 arriving as the same silence, which is how a product fails without
telling anyone.

## Why the route is mounted here rather than used

⭐ Because the thing that was broken is the **handler**, not any endpoint. ⭐ A test that
waited for the endpoint would leave the handler untested until the endpoint existed ⭐
and `test_financial_provider.py:140-142` already records the cost of that habit in this
package: a fixture that quietly stops resetting state, and every test after it passes for
the wrong reason.

## What each case pins

1. ⭐ **The code survives to the body.** Not 「it did not 500」 ⭐ **a bare 400 would also
   not 500**, and that is the fifth-time failure this file's neighbours have recorded.
2. ⭐ **The two siblings stay apart.** ``base.py:106-108`` says ``ProviderRateLimitedError``
   and ``ProviderIpBlockedError`` are **siblings, not subclasses**, 「so that no
   ``isinstance`` chain can reach the wrong code by ordering luck」 ⭐ and registration by
   base class is exactly such a chain ⭐ so this asserts the two do not land alike.
3. ⭐ **A refusal is not the reader's fault.** 502, never 403 ⭐ because 403 is a sentence
   about the person using the product produced by a fact about a socket.
4. ⭐ **An unrecognised upstream code is 502, not 500** ⭐ because the request was
   well-formed and the fault is upstream.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alphacouncil.api.app import create_app
from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.providers.base import (
    ProviderBlockedError,
    ProviderEmptyError,
    ProviderError,
    ProviderIpBlockedError,
    ProviderProtocolError,
    ProviderRateLimitedError,
    ProviderUnreachableError,
)

pytestmark = pytest.mark.unit

#: The five keys `.ai/error-codes.md` §1 fixes, and no more ⭐ **the runner's ``--json``
#: output is asserted to have exactly these**, so an extra one here would be a second
#: place the envelope differs.
ENVELOPE_KEYS = {"severity", "code", "message", "target", "fix"}

PROBE = "/probe/provider"


class _Raiser:
    """A route body that raises whatever it was handed.

    ⭐ A real endpoint is not used because none exists yet ⭐ and a fake one is only
    honest if it is **obvious** that it is a fake, hence the name.
    """

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __call__(self) -> None:
        raise self.error


@pytest.fixture
def app() -> FastAPI:
    """A fresh application, so a probe route installed by one test cannot leak.

    ⭐ **Two fixtures rather than one**, copied from ``test_pool_quotes_api.py:82-92`` ⭐
    because ``TestClient.app`` is typed as the ASGI protocol rather than as
    :class:`FastAPI`, so handing it to ``add_api_route`` fails the type check ⭐ **and a
    test that needs to configure the app should be given the app.**
    """
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client over the isolated database, with migrations already applied."""
    with TestClient(app) as test_client:
        yield test_client


def raise_from(app: FastAPI, error: Exception) -> None:
    """Mount a route that raises ``error``, replacing any previous probe."""
    app.router.routes = [
        route for route in app.router.routes if getattr(route, "path", "") != PROBE
    ]
    app.add_api_route(PROBE, _Raiser(error), methods=["GET"])


#: Every provider failure, the status it now deserves, and the code the body must carry.
#: ⭐ **All seven**, not a sample ⭐ because `test_financial_provider.py:104-117` records
#: what happened the first time a list of columns was sampled instead of enumerated: a
#: fourth one slipped past, which is the whole reason that list exists.
CASES: tuple[tuple[type[ProviderError], int, str], ...] = (
    (ProviderRateLimitedError, 429, ErrorCode.DATA_SOURCE_RATE_LIMITED.value),
    (ProviderIpBlockedError, 503, ErrorCode.DATA_SOURCE_IP_BLOCKED.value),
    (ProviderBlockedError, 502, ErrorCode.DATA_SOURCE_FORBIDDEN.value),
    (ProviderUnreachableError, 503, ErrorCode.DATA_SOURCE_UNREACHABLE.value),
    (ProviderProtocolError, 502, ErrorCode.DATA_UNVERIFIABLE.value),
    (ProviderEmptyError, 404, ErrorCode.DATA_NO_DATA.value),
    (ProviderError, 502, ErrorCode.DATA_FETCH_ERROR.value),
)


class TestAProviderFailureArrivesAsItsOwnSentence:
    @pytest.mark.parametrize(("error", "status", "code"), CASES)
    def test_it_carries_its_code_and_the_status_it_implies(
        self, app: FastAPI, client: TestClient, error: type[ProviderError], status: int, code: str
    ) -> None:
        raise_from(app, error("the source said no"))
        response = client.get(PROBE)

        assert response.status_code == status, response.text
        body = response.json()
        assert body["code"] == code
        assert set(body) == ENVELOPE_KEYS
        assert body["severity"] == "error"
        assert body["message"] == "the source said no"

    @pytest.mark.parametrize(("error", "status", "code"), CASES)
    def test_no_provider_failure_is_a_bare_five_hundred(
        self, app: FastAPI, client: TestClient, error: type[ProviderError], status: int, code: str
    ) -> None:
        """⭐ The assertion that would have caught the gap this file exists for.

        Before the change every one of these returned 500 with FastAPI's ``{"detail": …}``
        ⭐ **which is a 500 that a client cannot act on** ⭐ and §4.6's four states never ran
        on that path at all.
        """
        raise_from(app, error("the source said no"))
        response = client.get(PROBE)

        assert response.status_code != 500, response.text
        assert "detail" not in response.json(), "⭐ FastAPI's own shape leaked through"


class TestTheTwoSiblingsStayApart:
    def test_a_rate_limit_is_not_reported_as_a_refusal(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """⭐ ``base.py:106-108`` keeps these two as siblings 「so that no ``isinstance``
        chain can reach the wrong code by ordering luck」 ⭐ **and registering a base class
        is such a chain**, so the claim needs a test rather than a comment."""
        raise_from(app, ProviderRateLimitedError("slow down"))
        limited = client.get(PROBE)

        raise_from(app, ProviderBlockedError("no")
                   )
        refused = client.get(PROBE)

        assert limited.json()["code"] != refused.json()["code"]
        assert limited.status_code == 429
        assert refused.status_code == 502

    def test_a_ban_is_not_reported_as_a_rate_limit(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """⭐ §4.5: 「限流」 and 「封 IP」 have different recoveries ⭐ **20 hours against five
        minutes** ⭐ so a client that cannot tell them apart cannot plan."""
        raise_from(app, ProviderIpBlockedError("banned"))
        banned = client.get(PROBE)

        raise_from(app, ProviderRateLimitedError("slow down"))
        limited = client.get(PROBE)

        assert banned.json()["code"] != limited.json()["code"]


class TestTheStatusesAreTheOnesTheReasoningArguesFor:
    def test_a_refusal_is_never_the_readers_fault(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """⭐ 403 would be a sentence about the person using the product, produced by a fact
        about a socket ⭐ **which is ``metrics.py:38-41``'s named failure** ⭐ the program
        speaking for the reader."""
        raise_from(app, ProviderBlockedError("no"))
        assert client.get(PROBE).status_code != 403

    def test_an_unrecognised_upstream_code_is_not_a_server_error(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """⭐ ``classify`` returns ``None`` for a code it does not know ⭐ **and unknown is a
        real answer**, so the fallback is the bare ``ProviderError`` ⭐ which must still be
        502 ⭐ **the request was well-formed and the fault is upstream.**"""
        raise_from(app, ProviderError("baostock error 99999999: 新码"))
        response = client.get(PROBE)

        assert response.status_code == 502, response.text
        assert response.json()["code"] == ErrorCode.DATA_FETCH_ERROR.value

    def test_the_message_is_the_providers_own_sentence_verbatim(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """⭐ The client's contract (``api.ts:731-736``) is that ``message`` is the
        server's sentence, untranslated ⭐ **and the source's wording is the only one that
        knows which recovery applies.** ⭐ A wrapper that reworded it would be the fifth
        copy of the error vocabulary, and there is no gate that keeps a fifth copy honest."""
        sentence = "baostock banned this address: IP 已加入黑名单"
        raise_from(app, ProviderIpBlockedError(sentence))
        assert client.get(PROBE).json()["message"] == sentence
