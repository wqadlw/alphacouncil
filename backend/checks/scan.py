"""What a rule is handed: a repository to inspect, plus its caches.

Split out of :mod:`checks.framework`. A rule reads a **source tree**, never a
running application, so everything it needs is a path and a memoised parse.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from checks.exemptions import Suppressions
from checks.models import CheckMeta

__all__ = [
    "ScanContext",
    "format_target",
]

_SKIP_DIRS = frozenset({"__pycache__", ".venv", ".mypy_cache", ".ruff_cache", "node_modules"})


@dataclass(slots=True)
class ScanContext:
    """A repository to inspect, plus the caches that make it cheap.

    ``repo_root`` is the checkout root (``alphacouncil/``); ``backend`` and
    ``product`` hang off it. Targets are always rendered relative to
    ``repo_root`` so a finding reads the same from any working directory.
    """

    repo_root: Path
    registry: Sequence[CheckMeta] = ()

    _trees: dict[Path, ast.Module | None] = field(default_factory=dict, repr=False)
    _texts: dict[Path, str] = field(default_factory=dict, repr=False)
    _suppressions: dict[Path, Suppressions] = field(default_factory=dict, repr=False)

    @property
    def backend(self) -> Path:
        """``<repo>/backend`` — the Python project root."""
        return self.repo_root / "backend"

    @property
    def product(self) -> Path:
        """``<repo>/backend/src/alphacouncil`` — the shipped code."""
        return self.backend / "src" / "alphacouncil"

    def rel(self, path: Path) -> str:
        """Render a path relative to ``repo_root`` when possible."""
        try:
            return path.resolve().relative_to(self.repo_root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def text(self, path: Path) -> str:
        """File contents, decoded once and cached."""
        cached = self._texts.get(path)
        if cached is None:
            cached = path.read_text(encoding="utf-8", errors="replace")
            self._texts[path] = cached
        return cached

    def tree(self, path: Path) -> ast.Module | None:
        """Parse a module, or ``None`` if it does not parse.

        A syntax error is not this package's business — ``ruff`` already fails
        the build on one — so it is cached as ``None`` rather than raised.
        """
        if path not in self._trees:
            try:
                self._trees[path] = ast.parse(self.text(path), filename=str(path))
            except SyntaxError:
                self._trees[path] = None
        return self._trees[path]

    def suppressions(self, path: Path) -> Suppressions:
        """Parsed ``# noqa`` comments for a file, cached."""
        cached = self._suppressions.get(path)
        if cached is None:
            cached = Suppressions(self.text(path))
            self._suppressions[path] = cached
        return cached

    def python_files(self, *dirs: Path) -> list[Path]:
        """Every ``*.py`` under the given directories, sorted and cache-free."""
        found: list[Path] = []
        for directory in dirs:
            if not directory.exists():
                continue
            found.extend(
                path
                for path in sorted(directory.rglob("*.py"))
                if not _SKIP_DIRS.intersection(path.parts)
            )
        return found

    def files_with_suffix(self, root: Path, suffix: str) -> list[Path]:
        """Every file with a suffix under ``root``, sorted and cache-free."""
        if not root.exists():
            return []
        return [
            path
            for path in sorted(root.rglob(f"*{suffix}"))
            if not _SKIP_DIRS.intersection(path.parts)
        ]

    def doc(self, rel_path: str) -> str | None:
        """Contents of a governed document, or ``None`` when it is absent."""
        path = self.repo_root / rel_path
        return self.text(path) if path.is_file() else None


def format_target(ctx: ScanContext, path: Path, lineno: int | None = None) -> str:
    """``"backend/src/x.py:55"`` — the envelope's ``target`` value."""
    rendered = ctx.rel(path)
    return f"{rendered}:{lineno}" if lineno is not None else rendered
