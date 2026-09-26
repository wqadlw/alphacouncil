"""S-05 — every error code in the code is registered in the document.

**Defect guarded:** ``.ai/error-codes.md`` maintenance rules 1 and 4. An error
code is a stable identifier that callers match on. The failure mode is not a
crash: it is a code that reaches a user, gets screenshotted into a bug report,
and cannot be looked up — or two names for one condition, so nothing can be
counted reliably.

Anti-pattern (forbidden)::

    # emitted but never registered — nobody can look it up
    return DataResult.error("DATA_SOURCE_RATE_LIMITTED", ...)   # typo, and unregistered

    # in product code: a bare string where the enum exists
    if result.error_code == "DATA_SOURCE_FORBIDDEN": ...

Correct form::

    from alphacouncil.core.error_codes import ErrorCode
    return DataResult.error(ErrorCode.DATA_SOURCE_RATE_LIMITED, ...)
    if result.error_code is ErrorCode.DATA_SOURCE_FORBIDDEN: ...

Why a test cannot catch this: a test asserts on the code the implementation
actually emits, so a typo becomes the expectation and the suite stays green.
The document is the only thing that knows what the code was supposed to be.

Four comparisons, because each direction is a different defect:

============================  ==========  ============================================
condition                     severity    what it means
============================  ==========  ============================================
used, not documented          error       it can reach a user and cannot be looked up
bare string in product code   error       it slipped past the enum, so nothing checks it
documented, not in the enum   warning     the document describes a code that is gone
in the enum, nothing uses it  info        declared ahead of the feature that emits it
============================  ==========  ============================================

**Why bare strings are only an error in ``src/``:** the check scripts under
``checks/`` are forbidden from importing the product (``README.md`` §4.5), so
they *must* name their codes as literals. The distinction is real, and it is the
same one ``S-10`` draws for ``print``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_UNREGISTERED_CODE"

META = CheckMeta(
    check_id="S-05",
    slug="check-error-codes",
    title="error codes are registered in .ai/error-codes.md",
    priority="P0",
    code=CODE,
)

DOC_PATH = ".ai/error-codes.md"
ENUM_PATH = Path("src", "alphacouncil", "core", "error_codes.py")
ENUM_CLASS = "ErrorCode"

#: The namespace prefixes from `.ai/error-codes.md` §2. Order matters twice:
#: `DATA_SOURCE` precedes `DATA` so the alternation cannot stop short on
#: `DATA_SOURCE_RATE_LIMITED`, and the list is otherwise alphabetical so a
#: missing prefix is visible rather than lost in the middle.
CODE_PATTERN = re.compile(
    r"\b(?:AGENT|CHECK|CONTRACT|DATA_SOURCE|DATA|DECISION|INSTRUMENT|MIGRATION|STORAGE|WATCHLIST)"
    r"_[A-Z0-9_]+\b"
)
_BACKTICKED = re.compile(r"`([^`\n]+)`")


def registered_codes(document: str) -> set[str]:
    """Every code named in the document, inside backticks.

    Backticks are required on purpose: the document also *discusses* prefixes
    (``DATA_SOURCE_*``) and formats, and prose should not be able to register a
    code by accident.
    """
    return {
        match.group(1).strip()
        for match in _BACKTICKED.finditer(document)
        if CODE_PATTERN.fullmatch(match.group(1).strip())
    }


def declared_codes(ctx: ScanContext) -> set[str]:
    """Members of the ``ErrorCode`` enum — the code-side source of truth."""
    tree = ctx.tree(ctx.backend / ENUM_PATH)
    if tree is None:
        return set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == ENUM_CLASS:
            return {
                target.id
                for statement in node.body
                if isinstance(statement, ast.Assign)
                for target in statement.targets
                if isinstance(target, ast.Name)
            }
    return set()


def referenced_codes(
    ctx: ScanContext,
) -> tuple[dict[str, list[tuple[Path, int]]], dict[str, list[tuple[Path, int]]]]:
    """Codes named in code, split into ``ErrorCode.X`` uses and bare literals.

    The enum module itself is skipped: its members *are* string literals equal
    to their own names, so counting those as "used" would make every declared
    code look emitted and silently disable the "nothing emits it" report.
    """
    attributes: dict[str, list[tuple[Path, int]]] = {}
    literals: dict[str, list[tuple[Path, int]]] = {}
    enum_file = (ctx.backend / ENUM_PATH).resolve()
    roots = (ctx.product, ctx.backend / "checks", ctx.backend / "scripts")

    for path in ctx.python_files(*roots):
        if path.resolve() == enum_file:
            continue
        tree = ctx.tree(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == ENUM_CLASS
            ):
                attributes.setdefault(node.attr, []).append((path, node.lineno))
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and CODE_PATTERN.fullmatch(node.value)
            ):
                literals.setdefault(node.value, []).append((path, node.lineno))
    return attributes, literals


def _in_product(ctx: ScanContext, path: Path) -> bool:
    """Whether a file is shipped product code rather than developer tooling."""
    try:
        path.resolve().relative_to(ctx.product.resolve())
    except ValueError:
        return False
    return True


def run(ctx: ScanContext) -> CheckResult:
    """Compare the document, the enum, and every reference in the code."""
    result = CheckResult()
    document = ctx.doc(DOC_PATH)
    if document is None:
        result.skipped = f"{DOC_PATH} not found — nothing to compare against"
        return result

    doc_codes = registered_codes(document)
    enum_codes = declared_codes(ctx)
    attributes, literals = referenced_codes(ctx)
    used = set(attributes) | set(literals)
    touched = {path for sites in (*attributes.values(), *literals.values()) for path, _ in sites}
    result.files = [ctx.backend / ENUM_PATH, *sorted(touched)]

    # Declared counts as present: a member of the enum is a code that exists,
    # whether or not anything emits it yet. An unregistered member is
    # unregistered, and the doc is the registry.
    for name in sorted((used | enum_codes) - doc_codes):
        sites = attributes.get(name) or literals.get(name) or []
        target = (
            format_target(ctx, *sites[0]) if sites else format_target(ctx, ctx.backend / ENUM_PATH)
        )
        result.error(
            CODE,
            f"`{name}` is used in code but not registered in {DOC_PATH}",
            target=target,
            fix=f"Add a row for `{name}` to the matching table in {DOC_PATH} "
            "(prefix + severity + meaning + `fix` form). Maintenance rule 1.",
        )

    for name, sites in sorted(literals.items()):
        for path, lineno in sites:
            if not _in_product(ctx, path):
                continue
            result.error(
                CODE,
                f"`{name}` appears as a bare string instead of `ErrorCode.{name}`",
                target=format_target(ctx, path, lineno),
                fix=f"Import `ErrorCode` and use `ErrorCode.{name}` — a string literal "
                "cannot be checked, renamed, or completed by an editor.",
            )

    for name in sorted(doc_codes - enum_codes):
        result.warn(
            CODE,
            f"`{name}` is registered in {DOC_PATH} but absent from `{ENUM_CLASS}`",
            target=DOC_PATH,
            fix=f"Either add it to `{ENUM_CLASS}` in {ENUM_PATH.as_posix()} or remove the row.",
        )

    for name in sorted(enum_codes - used):
        result.note(
            CODE,
            f"`{name}` is declared in `{ENUM_CLASS}` but nothing emits it yet",
            target=format_target(ctx, ctx.backend / ENUM_PATH),
            fix="Wire it up when the feature lands. Listed as `info` rather than a "
            "defect because the namespace was specified before the code, on purpose.",
        )
    return result


__all__ = ["META", "run"]
