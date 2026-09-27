"""Shared pytest fixtures.

Design rule (constitution §3): tests must run **without network access**. Any
external client is injected and stubbed, never instantiated against the network.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from alphacouncil.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Prevent the developer's real ``.env`` from leaking into tests.

    Every test starts from a clean slate; tests that need a specific variable
    set it explicitly via ``monkeypatch.setenv``.
    """
    for key in list(os.environ):
        if key.startswith("ALPHACOUNCIL_") or key in {
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY",
        }:
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolated_database(
    _isolate_environment: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point every test at its own database file.

    The application factory runs the schema migration during startup, so any
    test that builds an app touches whatever ``Settings.database_path`` resolves
    to — and the default is the real per-user location
    (``%LOCALAPPDATA%/AlphaCouncil/alphacouncil.db`` on Windows). The obvious
    test, ``TestClient(create_app(Settings()))``, therefore migrates the
    developer's own database. That is not hypothetical: it happened on
    2026-09-26, and this fixture is the fix.

    Setting it in the environment rather than in each test is what makes it
    forgettable-proof — a test added later inherits the isolation without
    knowing it exists.

    Depends on ``_isolate_environment`` explicitly rather than relying on
    fixture order: that fixture *deletes* every ``ALPHACOUNCIL_*`` variable, so
    if it ever ran second it would remove this one and the test would silently
    fall back to the real path — reintroducing the very bug this prevents.
    """
    monkeypatch.setenv("ALPHACOUNCIL_DATABASE_PATH", str(tmp_path / "alphacouncil.db"))
    get_settings.cache_clear()


@pytest.fixture
def dev_settings() -> Settings:
    """Settings for a plain development environment with no credentials."""
    return Settings(_env_file=None)


@pytest.fixture
def fixed_now() -> datetime:
    """A deterministic timestamp so assertions on ``fetched_at`` are stable."""
    return datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only."""
    return "asyncio"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply each test's category marker from the directory it lives in.

    A test's category is decided by **where the file lives**, not by whether
    someone remembered a decorator.

    This is not a hypothetical: on 2026-09-26, `pytest tests/unit -m unit`
    reported **"54 passed, 47 deselected"** — 47 tests were being skipped in
    silence while the suite still showed green. Adding a decorator to every file
    would have fixed that instance; deriving the marker from the path fixes the
    class of bug.
    """
    for item in items:
        parts = Path(str(item.fspath)).parts
        if "tests" not in parts:
            continue
        category = parts[parts.index("tests") + 1]
        marker = _CATEGORY_MARKERS.get(category)
        if marker is not None:
            item.add_marker(getattr(pytest.mark, marker))


# Directory name -> marker name. `eval/` maps to `live` because the directory
# predates the rename and an empty directory is not worth a migration.
_CATEGORY_MARKERS = {"unit": "unit", "integration": "integration", "eval": "live"}


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers so ``--strict-markers`` does not fail."""
    for marker, description in (
        ("unit", "unit tests, no external dependencies"),
        ("integration", "integration tests, may use containers or mocks"),
        ("live", "hits the real network — never run in CI"),
    ):
        config.addinivalue_line("markers", f"{marker}: {description}")


def make_settings(**overrides: Any) -> Settings:
    """Build settings with explicit overrides, ignoring any ``.env`` file.

    Helper for tests that need a non-default configuration without touching
    the process environment.
    """
    return Settings(_env_file=None, **overrides)
