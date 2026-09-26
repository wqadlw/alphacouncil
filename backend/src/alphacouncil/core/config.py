"""Application configuration.

All runtime configuration is loaded from environment variables (or a ``.env``
file) and validated at import time. Per the project constitution, **no module
may hardcode configuration values** — model names, thresholds, paths and URLs
all flow through :class:`Settings`.

Usage::

    from alphacouncil.core.config import get_settings

    settings = get_settings()
    print(settings.llm_model)
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LlmProvider = Literal["openai", "anthropic", "deepseek", "azure_openai"]


def default_database_path() -> Path:
    """Return where the SQLite file lives by default (constitution 5.3).

    The database must not sit next to the executable: a packaged app installed
    under ``Program Files`` cannot write there, so saving would fail on a user's
    machine while working on the developer's. ``%LOCALAPPDATA%`` is the
    documented location for per-user application data on Windows, and the XDG
    data directory is its equivalent on the platforms used for development and
    CI.

    Returns:
        An absolute path. The parent directory is **not** created here — that is
        the storage layer's job, so constructing settings never touches disk.
    """
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / "AlphaCouncil" / "alphacouncil.db"


class Settings(BaseSettings):
    """Validated runtime settings.

    Prefixed settings read ``ALPHACOUNCIL_*`` environment variables. Provider
    credentials are declared with an explicit alias so they read the
    conventional unprefixed names (``OPENAI_API_KEY`` and friends).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ALPHACOUNCIL_",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    # ---- application -------------------------------------------------------
    env: Environment = "development"
    log_level: LogLevel = "INFO"
    log_json: bool = False
    api_host: str = "0.0.0.0"  # noqa: S104 - containers must bind all interfaces
    api_port: int = Field(default=8000, ge=1, le=65535)

    # ---- llm ---------------------------------------------------------------
    llm_provider: LlmProvider = "openai"
    llm_model: str = Field(default="gpt-4o-mini", min_length=1)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=1, le=200_000)

    # ---- embedding ---------------------------------------------------------
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = Field(default=1024, ge=1)
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # ---- vector store ------------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "alphacouncil_docs"

    # ---- relational store --------------------------------------------------
    # The database must not sit next to the executable: a packaged app under
    # Program Files cannot write there, so the first save would fail on a user's
    # machine while working on the developer's (constitution 5.3). The default
    # is derived from %LOCALAPPDATA% by `default_database_path()`.
    #
    # This replaced `sqlite+aiosqlite:///./alphacouncil.db`, which was a path
    # relative to the *current working directory*: it broke 5.3 and pointed at a
    # different file depending on how the program was launched. The field was
    # never read anywhere (verified 2026-09-26: grep found only its declaration),
    # so removing it breaks no caller.
    database_path: Path = Field(default_factory=default_database_path)

    # ---- observability -----------------------------------------------------
    langfuse_enabled: bool = False
    langfuse_host: str = "http://localhost:3001"

    # ---- agent runtime guards ---------------------------------------------
    max_agent_steps: int = Field(default=25, ge=1, le=500)
    max_cost_usd_per_run: float = Field(default=0.50, gt=0.0)
    request_timeout_seconds: int = Field(default=120, ge=1, le=3600)

    # ---- retrieval tuning --------------------------------------------------
    recall_top_k: int = Field(default=50, ge=1, le=1000)
    rerank_top_k: int = Field(default=8, ge=1, le=100)
    enable_graph_retrieval: bool = True
    enable_text2sql: bool = True

    # ---- credentials (unprefixed aliases) ---------------------------------
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    deepseek_api_key: SecretStr | None = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    langfuse_public_key: SecretStr | None = Field(
        default=None, validation_alias="LANGFUSE_PUBLIC_KEY"
    )
    langfuse_secret_key: SecretStr | None = Field(
        default=None, validation_alias="LANGFUSE_SECRET_KEY"
    )

    # ---- validators --------------------------------------------------------
    @field_validator("qdrant_url", "langfuse_host")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Normalise URLs so downstream joins never produce a double slash."""
        return value.rstrip("/")

    @model_validator(mode="after")
    def _check_rerank_not_exceeding_recall(self) -> Settings:
        """Guard against a silent misconfiguration that would return nothing."""
        if self.rerank_top_k > self.recall_top_k:
            msg = (
                f"rerank_top_k ({self.rerank_top_k}) must not exceed "
                f"recall_top_k ({self.recall_top_k})"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _require_provider_credentials(self) -> Settings:
        """Fail fast in production rather than at the first LLM call."""
        if self.env != "production":
            return self

        credentials: dict[LlmProvider, SecretStr | None] = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "deepseek": self.deepseek_api_key,
            "azure_openai": self.openai_api_key,
        }
        if credentials[self.llm_provider] is None:
            msg = (
                f"llm_provider is '{self.llm_provider}' but the matching API key "
                "is not set; production runs require credentials"
            )
            raise ValueError(msg)

        if self.langfuse_enabled and not (self.langfuse_public_key and self.langfuse_secret_key):
            msg = "langfuse_enabled is true but LANGFUSE_PUBLIC_KEY/SECRET_KEY are missing"
            raise ValueError(msg)

        return self

    # ---- derived helpers ---------------------------------------------------
    @property
    def is_production(self) -> bool:
        """Whether the application runs in production mode."""
        return self.env == "production"

    @property
    def is_development(self) -> bool:
        """Whether the application runs in development mode."""
        return self.env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that repeated calls do not re-read the environment. Tests that
    need different settings should call :func:`get_settings.cache_clear`.
    """
    return Settings()
