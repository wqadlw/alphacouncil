"""S-14 — every source file is tracked by git.

**Defect guarded:** a source file that exists on disk and is not in the
repository. It works on the machine that wrote it and is **absent from every
clone** — including CI, and including your own next machine.

The dangerous case is not the one you would see in ``git status``. An
over-broad ignore rule (``data/`` with no leading slash, which this
repository's own ``.gitignore`` does) makes a source file *untracked **and**
ignored*, and ⭐ ``git status`` does not show ignored files. That is a defect
whose main property is that it cannot be seen by the command people actually
run.

Anti-pattern (forbidden)::

    backend/src/alphacouncil/whatever/module.py   # written, never `git add`ed
    .gitignore: data/                             # …and it also matches any depth

Correct form::

    git add backend/src/alphacouncil/whatever/module.py

Why a test cannot catch this: nothing is broken. Every test passes, every
import resolves, every gate is green — on the machine that has the file. The
defect is a disagreement between the working tree and the repository, and no
test runs against the repository.

Scope: ``backend/`` and ``frontend/src`` / ``frontend/e2e``, minus the framework's
skip directories. ⭐ The scope is what makes the warning usable: ``.venv``,
``node_modules`` and ``__pycache__`` are all correctly ignored, so without a
narrow walk this rule would warn on every build. With it, a warning here can
only mean an ignore rule is covering source.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from checks.framework import CheckMeta, CheckResult, ScanContext
from checks.scan import SKIP_DIRS

UNTRACKED = "CHECK_UNTRACKED_SOURCE"
IGNORED = "CHECK_IGNORED_SOURCE"

#: The conventional module-level name every rule exports, and the one the
#: registry test reads. Kept as an alias so the two names cannot drift.
CODE = UNTRACKED

META = CheckMeta(
    check_id="S-14",
    slug="git-tracked",
    title="every source file is tracked by git",
    priority="P2",
    code=UNTRACKED,
)

#: Files worth tracking. Not a general-purpose ignore list: the walk below already skips
#: build directories, so this is only 「what is a source file」.
SOURCE_SUFFIXES = frozenset(
    {
        ".py", ".pyi", ".ts", ".tsx", ".js", ".mjs", ".css", ".scss",
        ".sql", ".json", ".toml", ".yml", ".yaml", ".html", ".md",
    }
)

#: Generated and never meant to be tracked even inside the walked trees.
_NOT_SOURCE = frozenset({"package-lock.json"})


def _roots(ctx: ScanContext) -> list[Path]:
    """The trees this rule speaks about."""
    return [
        ctx.backend,
        ctx.repo_root / "frontend" / "src",
        ctx.repo_root / "frontend" / "e2e",
    ]


def _git(ctx: ScanContext, *args: str) -> str | None:
    """Run one git command, or return ``None`` if git cannot answer.

    Three calls for the whole repository, rather than one ``--error-unmatch``
    per file: this rule runs in the gate on every commit, and 198 subprocesses
    is a different kind of slow.
    """
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=ctx.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _git_paths(ctx: ScanContext, *args: str) -> set[str] | None:
    """One ``-z`` git listing as a set of repo-relative POSIX paths."""
    raw = _git(ctx, *args, "-z")
    if raw is None:
        return None
    return {entry for entry in raw.split("\0") if entry}


def _source_files(ctx: ScanContext) -> list[Path]:
    """Every source file under the walked trees, sorted."""
    found: list[Path] = []
    for root in _roots(ctx):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name in _NOT_SOURCE or path.suffix not in SOURCE_SUFFIXES:
                continue
            if path.is_file():
                found.append(path)
    return sorted(found)


def run(ctx: ScanContext) -> CheckResult:
    """Report source files git does not have, and source files git ignores."""
    result = CheckResult()
    if not (ctx.repo_root / ".git").exists():
        result.skipped = (
            f"{ctx.rel(ctx.repo_root)} is not a git repository \u2014 nothing to compare against"
        )
        return result

    tracked = _git_paths(ctx, "ls-files")
    untracked = _git_paths(ctx, "ls-files", "--others", "--exclude-standard")
    ignored = _git_paths(ctx, "ls-files", "--others", "--ignored", "--exclude-standard")
    if tracked is None or untracked is None or ignored is None:
        result.skipped = "git produced no usable listing here"
        return result

    for path in _source_files(ctx):
        result.files.append(path)
        try:
            relative = path.resolve().relative_to(ctx.repo_root.resolve()).as_posix()
        except ValueError:  # pragma: no cover - a file outside the repo is not ours
            continue
        if relative in tracked:
            continue
        if relative in untracked:
            result.error(
                UNTRACKED,
                f"{relative} exists on disk but git does not have it",
                target=ctx.rel(path),
                fix=f"git add {relative}",
            )
        elif relative in ignored:
            result.warn(
                IGNORED,
                f"{relative} is a source file that git is ignoring",
                target=ctx.rel(path),
                fix="check the .gitignore rule covering it \u2014 a bare directory name "
                "matches at every depth",
            )
    return result
