"""Unit tests for :mod:`alphacouncil.api.app`."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphacouncil import __version__
from alphacouncil.api.app import create_app
from alphacouncil.core.config import Settings

pytestmark = pytest.mark.unit


def _client(**overrides: Any) -> TestClient:
    """Build a TestClient backed by isolated settings."""
    settings = Settings(_env_file=None, **overrides)
    return TestClient(create_app(settings))


class TestHealthEndpoint:
    """``/health`` is the operational contract; its shape must stay stable."""

    def test_returns_ok_with_version(self) -> None:
        with _client() as client:
            response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["version"] == __version__

    def test_reports_effective_configuration(self) -> None:
        with _client(llm_model="claude-sonnet-4") as client:
            body = client.get("/health").json()

        assert body["llm_model"] == "claude-sonnet-4"

    def test_the_abandoned_retrieval_layer_is_not_reported(self) -> None:
        """ADR-0006 retired the v1 retrieval layer; /health reporting it made
        the service describe capabilities it does not have. This is the guard
        that keeps it dead (spec 009)."""
        with _client() as client:
            body = client.get("/health").json()

        assert "retrieval" not in body

    def test_never_leaks_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-leak")
        with _client() as client:
            raw = client.get("/health").text

        assert "sk-must-not-leak" not in raw


class TestRemovedRoutes:
    """v1 endpoints that were removed must stay removed (spec 009).

    A 404, not a 501: the route does not exist, and pretending otherwise
    would advertise a pipeline the product has explicitly abandoned.
    """

    def test_the_research_endpoint_is_gone(self) -> None:
        with _client() as client:
            response = client.post("/api/v1/research", json={"query": "Is margin expanding?"})

        assert response.status_code == 404


class TestAppFactory:
    """The factory must produce independent, correctly configured apps."""

    def test_openapi_schema_is_available(self) -> None:
        with _client() as client:
            schema = client.get("/openapi.json").json()

        assert schema["info"]["title"] == "AlphaCouncil"
        assert "/health" in schema["paths"]
        assert "/api/v1/watchlist" in schema["paths"]
        assert "/api/v1/research" not in schema["paths"]

    def test_separate_instances_do_not_share_state(self) -> None:
        first = create_app(Settings(_env_file=None, llm_model="model-a"))
        second = create_app(Settings(_env_file=None, llm_model="model-b"))

        assert first.state.settings.llm_model == "model-a"
        assert second.state.settings.llm_model == "model-b"

    def test_value_error_maps_to_400(self) -> None:
        app = create_app(Settings(_env_file=None))

        @app.get("/boom")
        async def boom() -> None:
            msg = "domain rule violated"
            raise ValueError(msg)

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom")

        assert response.status_code == 400
        assert response.json()["detail"] == "domain rule violated"
