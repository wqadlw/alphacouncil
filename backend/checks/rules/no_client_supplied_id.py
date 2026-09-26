"""S-06 — request schemas must not let the client supply server-assigned fields.

**Defect guarded:** constitution 5.2 rules 9/10 and product red line 4. A
decision record's primary key *is* the millisecond at which the server accepted
it. If a client can post its own id, it can post an id that sorts before a
review it was supposed to predate — and the single property that makes the
journal evidence, "this was written before the outcome was known", becomes
forgeable. Not by an attacker: by anyone who edits the request body to fix a
timestamp that looked wrong.

Anti-pattern (forbidden)::

    class DecisionCreate(BaseModel):
        id: int                  # the client decides when this happened
        recorded_at: datetime    # and what time it happened
        rationale: str

Correct form::

    class DecisionCreate(BaseModel):
        rationale: str                       # the only thing the client owns
        counter_evidence: str
        kill_criteria: list[Predicate]

    # the server stamps identity and time
    recorded_at = now_utc()
    decision_id = to_millis(recorded_at)

Why a test cannot catch this: a test posts a body *with* an id and asserts the
record round-trips. It passes — the hole is open the whole time, and closing it
later is a breaking API change. The defect is that the field exists in the
schema, which no execution path reveals.

Scope: classes named like inbound payloads (``*Create`` / ``*Request`` / ``*In``
/ ``*New``). Update-shaped schemas are deliberately exempt: there, a ``*_id`` is
a *reference* to the record being amended, not a claim about when it was made —
and 5.2 rule 10 says amending means appending a new record anyway.
"""

from __future__ import annotations

import ast
import re

from checks.framework import (
    CheckMeta,
    CheckResult,
    ScanContext,
    declared_fields,
    format_target,
)

CODE = "CHECK_CLIENT_SUPPLIED_ID"

META = CheckMeta(
    check_id="S-06",
    slug="no-client-supplied-id",
    title="request schemas do not accept server-assigned ids or timestamps",
    priority="P0",
    code=CODE,
)


#: Suffixes that mark a class as an inbound payload.
REQUEST_SUFFIXES = ("Create", "Request", "In", "New")

#: Suffixes that mark a class as an outbound payload — never flagged.
RESPONSE_SUFFIXES = ("Response", "Out", "Read", "View", "Detail", "Summary")

#: Fields the server always owns, regardless of the model.
SERVER_ASSIGNED = frozenset(
    {
        "id",
        "pk",
        "uuid",
        "created_at",
        "updated_at",
        "recorded_at",
        "appended_at",
        "logged_at",
        "timestamp",
        "server_time",
        "server_timestamp",
    }
)

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _is_request_schema(name: str) -> bool:
    """Whether a class name reads as an inbound payload rather than a response."""
    if name.endswith(RESPONSE_SUFFIXES):
        return False
    return name.endswith(REQUEST_SUFFIXES)


def _own_identity_fields(class_name: str) -> set[str]:
    """``DecisionCreate`` → ``{"decision_id"}`` — the PK the client must not name."""
    stem = class_name
    for suffix in REQUEST_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if not stem:
        return set()
    snake = _CAMEL_BOUNDARY.sub("_", stem).lower()
    return {f"{snake}_id"}


def run(ctx: ScanContext) -> CheckResult:
    """Scan inbound schemas for client-suppliable identity and time."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_request_schema(node.name):
                continue
            forbidden = SERVER_ASSIGNED | _own_identity_fields(node.name)
            for name, lineno, _annotation in declared_fields(node):
                if name.lower() not in forbidden:
                    continue
                result.error(
                    CODE,
                    f"`{node.name}.{name}` lets the client supply a server-assigned value",
                    target=format_target(ctx, path, lineno),
                    fix="Drop the field and assign it in the handler from the server "
                    "clock. A client-supplied primary key makes `recorded before the "
                    "outcome was known` forgeable (constitution 5.2 rule 9).",
                )
    return result


__all__ = ["META", "run"]
