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


def has_sources(ctx: ScanContext) -> bool:
    """Whether there is any frontend source to look at.

    ⭐ **This is the predicate. `skip_reason` is a message, not one** — and reading it as a
    predicate makes every caller skip unconditionally, because it always returns a string.
    `S-17` did exactly that on its first run and reported 「frontend sources are not present」
    against a frontend that has 46 call sites in it.

    ⇒ `S-07` / `S-08` / `S-09` were already branching on `if not pages:` / `if not files:`
    and using `skip_reason()` only for the wording, which is why they were never affected.
    The function's *name* was the trap, not its behaviour — and this repository has four
    records of a name being wider than the thing it describes (`0011`, `F-208`, `F-210`,
    `F-211`).
    """
    return bool(files(ctx))


def skip_reason() -> str:
    """Why the UI rules cannot run — phrased so it reads as a gap, not a pass.

    ⚠️ **This always returns text; it is not a test.**  Pair it with `has_sources`, or with
    the caller's own empty-list check — never branch on this value alone.
    """
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
