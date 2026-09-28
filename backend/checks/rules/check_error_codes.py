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
#:
#: ⚠️ **Adding a prefix here is a two-place edit**, and getting it wrong is quiet:
#: a new `REVIEW_*` code that is declared and documented but absent from this
#: pattern simply does not match, so the document row is invisible and the check
#: reports all four codes as unregistered (2026-09-28, spec 020). The failure is
#: loud, at least — which is the only reason it was found the same day.
#:
#: ⭐ It happened again on 2026-09-28 with `NOTE_*` (spec 026), and the comment
#: above had already predicted it verbatim. The eight codes were declared in the
#: enum, given a documented table in `.ai/error-codes.md`, and still reported as
#: unregistered — because the pattern, not the document, is what recognises a
#: code. **A rule that says "this is a two-place edit" and is still got wrong is
#: a rule that wants to be a single-place edit**, so: the fix below is to add the
#: prefix, and the maintenance rule in `.ai/error-codes.md` §五 now says the two
#: places by name.
#: A §2 subsection heading: three hashes, then ``2.`` and a number, then a
#: backticked ``PREFIX_*`` token, then whatever the heading says after it — which
#: in every current case is Chinese prose, hence ``title`` rather than the whole
#: line.
#:
#: ⭐ Described rather than reproduced on purpose. The earlier comment pasted a real
#: heading verbatim, which made it a quotation of a document that gets renumbered
#: every time a subsection is inserted, and it tripped RUF003 — a reminder that
#: this project's per-file exemptions are for quoting *rules*, not for quoting
#: layout, and a rule that gets stretched stops meaning anything.
#:
#: Deliberately loose about the number (a ``b`` suffix counts) and strict about the
#: level, so inserting a subsection between two existing ones needs no edit here.
_SECTION_HEADING = re.compile(r"^#{3}\s+2\.[0-9a-z]*\s+(?P<title>.*)$", re.MULTILINE)

#: A namespace token inside such a heading.
#:
#: ⭐ The character class includes ``_``, and that is not decoration. With
#: ``[A-Z0-9]*`` the heading ``` `DATA_SOURCE_*` ``` yielded **no token at all** — and
#: the bug stayed latent only because ``` `DATA_*` ``` also exists, so every
#: ``DATA_SOURCE_*`` code still matched as ``DATA`` + ``_SOURCE_...``. A prefix that
#: documents its namespace, is registered by nobody, and whose codes are recognised
#: anyway because a shorter prefix happens to share its first word: that is a wrong
#: answer reached by accident, which is the shape that survives review. Delete
#: ``` `DATA_*` ``` from the document and the whole namespace goes unregistered.
#:
#: §2.8 carries **two** of them
#: (`` `MIGRATION_*` `` / `` `STORAGE_*` ``), so every match in the heading counts —
#: a "take the first" reading would quietly drop `STORAGE` and then report every
#: `STORAGE_*` code as unregistered, which is this rule failing in the direction it
#: exists to prevent.
_PREFIX_TOKEN = re.compile(r"`([A-Z][A-Z0-9_]*)_\*`")

_BACKTICKED = re.compile(r"`([^`\n]+)`")


def documented_prefixes(document: str) -> tuple[str, ...]:
    """The namespace prefixes, read out of the document that documents them.

    ⭐ **This function is the whole fix.** The prefix list used to be a second,
    hand-maintained copy of §2's headings, and the rule's own comment records it
    being forgotten twice (``REVIEW_*`` in spec 020, ``NOTE_*`` in spec 026) and
    then a third time (``LESSON_*``, spec 030, twenty minutes after reading that
    comment). A list that has to be updated in the same breath as its source is
    one that eventually is not, and the failure is silent from the document's side:
    the row is there, the code is declared, and the check says no.

    Length-descending so the list reads deterministically — longest first, then
    alphabetically — rather than depending on the iteration order of a ``set``.

    ⭐ **The ordering is not what makes this work, and an earlier version of this
    comment claimed it was.** It said the sort stops ``DATA`` matching part of
    ``DATA_SOURCE_RATE_LIMITED`` and leaving the rest dangling. It does not: the
    suffix class is ``[A-Z0-9_]+``, which is greedy, so either order fullmatches a
    real code. What makes it work is the **prefix class** in ``_PREFIX_TOKEN`` — the
    comment above — which is why the bug that was actually here (a heading yielding
    no token at all) lived next to a justification about ordering and was invisible.
    """
    found: set[str] = set()
    for match in _SECTION_HEADING.finditer(document):
        found.update(_PREFIX_TOKEN.findall(match.group("title")))
    return tuple(sorted(found, key=lambda prefix: (-len(prefix), prefix)))


def code_pattern(document: str) -> re.Pattern[str]:
    """A pattern matching any code in any namespace §2 documents.

    Derived rather than hardcoded, and with **no fallback**: a document with no
    §2 headings yields a pattern that matches nothing, so every code is reported.
    That is the correct direction to fail — loud, and pointing at the document.
    """
    prefixes = documented_prefixes(document)
    if not prefixes:
        return re.compile(r"(?!)")
    return re.compile(
        r"\b(?:" + "|".join(prefixes) + r")_[A-Z0-9_]+\b"
    )


def registered_codes(
    document: str, pattern: re.Pattern[str] | None = None
) -> set[str]:
    """Every code named in the document, inside backticks.

    Backticks are required on purpose: the document also *discusses* prefixes
    (``DATA_SOURCE_*``) and formats, and prose should not be able to register a
    code by accident.
    """
    known = pattern if pattern is not None else code_pattern(document)
    return {
        match.group(1).strip()
        for match in _BACKTICKED.finditer(document)
        if known.fullmatch(match.group(1).strip())
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
    pattern: re.Pattern[str],
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
                and pattern.fullmatch(node.value)
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

    pattern = code_pattern(document)
    doc_codes = registered_codes(document, pattern)
    enum_codes = declared_codes(ctx)
    attributes, literals = referenced_codes(ctx, pattern)
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
