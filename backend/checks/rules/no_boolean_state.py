"""S-02 — no boolean state tracking.

**Defect guarded:** constitution 7.7 and product red line 5. A boolean can be
reinterpreted after the fact; an enumerated string cannot. Three booleans on one
row compose into eight combinations, five of which have no name and no meaning —
and the bug that follows is not a crash, it is a row that is
``reviewed=false, outcome_filled=true, result_scored=false`` and nobody can say
what that means.

Anti-pattern (forbidden)::

    class Review(BaseModel):
        reviewed: bool = False
        outcome_filled: bool = False
        result_scored: bool = False
        # 8 combinations, 5 of them meaningless

Correct form::

    class ReviewState(StrEnum):
        DRAFT = "draft"
        OPEN = "open"
        AWAITING_OUTCOME = "awaiting_outcome"
        REVIEWED = "reviewed"
        ARCHIVED = "archived"

    class Review(BaseModel):
        state: ReviewState = ReviewState.DRAFT
        # 5 states, every one of them has a name

Why a test cannot catch this: the eight combinations are *reachable*, so every
test you write passes. The defect is that five of them should never have been
expressible — which is a property of the type, not of any execution path.

The threshold is two, taken straight from 7.7: one boolean is a genuine binary,
two booleans about the same object is a state machine wearing a disguise.
"""

from __future__ import annotations

import ast

from checks.framework import (
    CheckMeta,
    CheckResult,
    ScanContext,
    annotation_idents,
    declared_fields,
    format_target,
)

CODE = "CHECK_BOOLEAN_STATE"

META = CheckMeta(
    check_id="S-02",
    slug="no-boolean-state",
    title="no boolean state tracking (use an enum)",
    priority="P0",
    code=CODE,
)


#: Names that read as "a flag tracking where this object is in a lifecycle".
STATE_PREFIXES = ("is", "has", "was", "should", "can")

STATE_SUFFIXES = (
    "done",
    "filled",
    "scored",
    "reviewed",
    "recorded",
    "archived",
    "locked",
    "deleted",
    "draft",
    "open",
    "closed",
    "resolved",
    "complete",
    "completed",
    "pending",
    "dirty",
    "confirmed",
    "settled",
    "matured",
)

#: Two is a state machine; below that, it is a real binary.
THRESHOLD = 2

_FIX = (
    "Replace the booleans with one enumerated `state` column "
    "(e.g. `state IN ('draft','open','awaiting_outcome','reviewed','archived')`) "
    "and drive transitions from a `{current: {event: next}}` table."
)


def _looks_like_state(name: str) -> bool:
    """Whether a field name reads as lifecycle state rather than configuration."""
    words = name.lower().split("_")
    if len(words) >= 2 and words[0] in STATE_PREFIXES:
        return True
    return words[-1] in STATE_SUFFIXES


def _is_boolean_annotation(annotation: ast.expr) -> bool:
    return "bool" in annotation_idents(annotation)


def _is_boolean_column(call: ast.Call) -> bool:
    """``Column(Boolean, ...)`` / ``mapped_column(Boolean)`` — unannotated ORM form."""
    for sub in ast.walk(call):
        if isinstance(sub, ast.Name) and sub.id in {"Boolean", "Bool"}:
            return True
    return False


def run(ctx: ScanContext) -> CheckResult:
    """Find classes carrying two or more lifecycle booleans."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            flags = _boolean_state_fields(node)
            if len(flags) < THRESHOLD:
                continue
            names = ", ".join(f"`{name}`" for name, _ in flags)
            result.error(
                CODE,
                f"`{node.name}` tracks state with {len(flags)} booleans: {names}",
                target=format_target(ctx, path, flags[0][1]),
                fix=_FIX,
            )
    return result


def _boolean_state_fields(node: ast.ClassDef) -> list[tuple[str, int]]:
    """Annotated *and* unannotated boolean lifecycle fields of one class."""
    found: list[tuple[str, int]] = []
    for name, lineno, annotation in declared_fields(node):
        if _looks_like_state(name) and _is_boolean_annotation(annotation):
            found.append((name, lineno))
    for statement in node.body:
        if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
            continue
        if not _is_boolean_column(statement.value):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name) and _looks_like_state(target.id):
                found.append((target.id, target.lineno))
    return found


__all__ = ["META", "run"]
