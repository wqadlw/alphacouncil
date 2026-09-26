"""Unit tests for :mod:`alphacouncil.core.config`."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from alphacouncil.core.config import Settings, get_settings

pytestmark = pytest.mark.unit


def _settings(**overrides: Any) -> Settings:
    """Construct settings without reading a ``.env`` file."""
    return Settings(_env_file=None, **overrides)


class TestDefaults:
    """Default values must match the documented contract in ``.env.example``."""

    def test_defaults_are_development_friendly(self) -> None:
        settings = _settings()

        assert settings.env == "development"
        assert settings.is_development is True
        assert settings.is_production is False

    def test_default_recall_exceeds_rerank(self) -> None:
        settings = _settings()

        assert settings.recall_top_k == 50
        assert settings.rerank_top_k == 8
        assert settings.recall_top_k > settings.rerank_top_k

    def test_credentials_are_absent_by_default(self) -> None:
        settings = _settings()

        assert settings.openai_api_key is None
        assert settings.anthropic_api_key is None
        assert settings.langfuse_secret_key is None


class TestValidation:
    """Guards that turn silent misconfiguration into loud failures."""

    def test_rerank_above_recall_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not exceed"):
            _settings(recall_top_k=5, rerank_top_k=10)

    def test_api_port_range_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            _settings(api_port=70000)

    def test_temperature_range_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            _settings(llm_temperature=3.0)

    def test_urls_are_normalised(self) -> None:
        settings = _settings(qdrant_url="http://localhost:6333/", langfuse_host="http://x:3001/")

        assert settings.qdrant_url == "http://localhost:6333"
        assert settings.langfuse_host == "http://x:3001"


class TestProductionGuards:
    """Production must fail fast rather than at the first LLM call."""

    def test_missing_provider_key_fails_in_production(self) -> None:
        with pytest.raises(ValidationError, match="require credentials"):
            _settings(env="production", llm_provider="openai")

    def test_provider_key_satisfies_production_guard(self) -> None:
        settings = _settings(env="production", llm_provider="openai", openai_api_key="sk-test")

        assert settings.is_production is True

    def test_langfuse_enabled_without_keys_fails_in_production(self) -> None:
        with pytest.raises(ValidationError, match="LANGFUSE_PUBLIC_KEY"):
            _settings(
                env="production",
                llm_provider="openai",
                openai_api_key="sk-test",
                langfuse_enabled=True,
            )

    def test_anthropic_provider_requires_anthropic_key(self) -> None:
        with pytest.raises(ValidationError, match="require credentials"):
            _settings(env="production", llm_provider="anthropic", openai_api_key="sk-test")


class TestEnvironmentBinding:
    """Environment variables must override defaults, and secrets must stay wrapped."""

    def test_prefixed_variable_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALPHACOUNCIL_LLM_MODEL", "claude-sonnet-4")

        assert _settings().llm_model == "claude-sonnet-4"

    def test_unprefixed_secret_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
        settings = _settings()

        assert settings.openai_api_key is not None
        assert settings.openai_api_key.get_secret_value() == "sk-secret-value"

    def test_secret_is_not_leaked_by_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-appear")
        settings = _settings()

        assert "sk-must-not-appear" not in repr(settings)
        assert "sk-must-not-appear" not in str(settings)

    def test_unknown_variables_are_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALPHACOUNCIL_TOTALLY_UNKNOWN", "value")

        assert _settings().env == "development"


class TestSingleton:
    """``get_settings`` is cached; tests rely on clearing it."""

    def test_get_settings_returns_same_instance(self) -> None:
        assert get_settings() is get_settings()

    def test_cache_clear_produces_new_instance(self) -> None:
        first = get_settings()
        get_settings.cache_clear()
        second = get_settings()

        assert first is not second
