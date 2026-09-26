"""Locating and reading frontend sources, for the UI-layer rules (S-07 … S-09).

The three UI rules are text-level, and that is a deliberate exception to
"AST, never regex" — the same exception ``S-04`` makes for SQL. The reason is
different in each case and worth stating:

* ``S-01``/``S-02``/``S-03``/``S-06`` ask about **code structure** (is there a
  second HTTP client? is this a state machine?). Structure must be read from a
  parse tree, because a regex cannot tell a call from a comment.
* ``S-07``/``S-08``/``S-09`` ask about **what the user will read and what the
  fallback value is**. That is string content. A text scan is the correct
  granularity; the risk it carries is false positives, not false negatives, and
  each rule is written to tolerate those (reporting a warning where it is
  unsure) rather than to be maximally aggressive.

``.ai/checks/static/README.md`` §3.2 already says these three are only the first
line of defence and that E2E assertions are the real guarantee.
"""

from __future__ import annotations

from pathlib import Path

from checks.framework import ScanContext

#: Where the frontend lives. `frontend/src` is preferred; a bare `frontend/`
#: is accepted so a Vite-less layout still gets scanned.
_SOURCE_ROOT = "frontend/src"
_FALLBACK_ROOT = "frontend"

SUFFIXES = (".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".html", ".astro")

_SKIP_PARTS = frozenset({"node_modules", "dist", "build", ".vite", "coverage"})


def source_root(ctx: ScanContext) -> Path:
    """The directory to scan, preferring ``frontend/src``."""
    preferred = ctx.repo_root / _SOURCE_ROOT
    return preferred if preferred.is_dir() else ctx.repo_root / _FALLBACK_ROOT


def files(ctx: ScanContext) -> list[Path]:
    """Every frontend source file, sorted, with build output excluded."""
    root = source_root(ctx)
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if _SKIP_PARTS.intersection(path.parts):
            continue
        found.append(path)
    return found


def skip_reason() -> str:
    """Why the UI rules cannot run — phrased so it reads as a gap, not a pass."""
    return (
        f"no frontend sources under `{_SOURCE_ROOT}` or `{_FALLBACK_ROOT}` yet — "
        "the UI-layer rule cannot observe anything until S2 lands the frontend"
    )


#: Names a home page is likely to have, in the order they should be preferred.
HOME_PAGE_STEMS = ("home", "index", "app", "dashboard", "today")


def home_pages(ctx: ScanContext) -> list[Path]:
    """Files that plausibly render the first screen a user sees.

    Matching is by stem rather than by an exact path because the routing layout
    is not decided yet, and a rule that silently finds nothing is worse than one
    that checks a couple of extra candidates.
    """
    candidates = [path for path in files(ctx) if path.stem.lower() in HOME_PAGE_STEMS]
    root_index = source_root(ctx) / "index.html"
    if root_index.is_file() and root_index not in candidates:
        candidates.append(root_index)
    return candidates
