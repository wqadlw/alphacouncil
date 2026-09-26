"""AST helpers shared by the rules.

Split out of :mod:`checks.framework`. **AST, never regex** is the first design
rule of this package (``.ai/checks/static/README.md`` §4.1): a regex over source
text is defeated by a string literal, a comment, or a line break.

Nothing here imports the rest of the package, so it is always safe to import
from a rule module.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence

__all__ = [
    "annotation_idents",
    "call_target",
    "contains_token",
    "declared_fields",
    "dotted",
    "enclosing_function",
    "parent_map",
    "snake_tokens",
]


def dotted(node: ast.expr) -> str | None:
    """Render ``httpx.Client`` as ``"httpx.Client"``; ``None`` for anything else."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def call_target(node: ast.Call) -> str | None:
    """The dotted name being called, e.g. ``"httpx.get"`` or ``"print"``."""
    return dotted(node.func)


def annotation_idents(node: ast.expr) -> set[str]:
    """Every bare identifier appearing in an annotation.

    ``Mapped[bool]`` yields ``{"Mapped", "bool"}``, so a rule can ask "is this a
    boolean?" without caring whether the author wrote ``bool``,
    ``Mapped[bool]`` or ``Optional[bool]``.
    """
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


def declared_fields(node: ast.ClassDef) -> Iterator[tuple[str, int, ast.expr]]:
    """Annotated class attributes: ``name, lineno, annotation``.

    Covers pydantic ``x: bool = Field(...)``, dataclass ``x: bool`` and
    SQLAlchemy ``x: Mapped[bool] = mapped_column(...)`` with one reader, which
    is the point — the rule should not care which ORM is in play.
    """
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            yield statement.target.id, statement.target.lineno, statement.annotation


def snake_tokens(name: str) -> tuple[str, ...]:
    """Split a snake_case identifier into its words."""
    return tuple(part for part in name.split("_") if part)


def contains_token(name: str, tokens: Sequence[str]) -> str | None:
    """Whether ``name`` contains any of ``tokens`` as a whole underscore-word run.

    Word-run matching rather than substring matching: ``target_price`` fires on
    ``target_price`` and on ``consensus_target_price``, but ``rating`` does not
    fire on ``migrating``. A rule that cries wolf on ``migrating`` gets deleted
    within a month, which is a worse outcome than the defect it was guarding.
    """
    words = snake_tokens(name.lower())
    for token in tokens:
        parts = token.split("_")
        width = len(parts)
        for start in range(len(words) - width + 1):
            if list(words[start : start + width]) == parts:
                return token
    return None


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Child → parent, so a rule can ask "what encloses this?" in one pass."""
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def enclosing_function(tree: ast.AST, node: ast.AST) -> str | None:
    """Name of the innermost function containing ``node``, or ``None`` at module level."""
    parents = parent_map(tree)
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(current)
    return None
