"""S-10 — no ``print()`` in the product.

**Defect guarded:** constitution 7.4. ``print`` writes to stdout, which in a
packaged desktop app is a console nobody is looking at. The line "succeeds",
the operator sees nothing, and the only trace of the failure is gone when the
process exits. ``structlog`` output goes to a file the user can attach to a bug
report.

Anti-pattern (forbidden)::

    print(f"fetching {code}")                 # invisible in a packaged app

Correct form::

    logger.info("quote_fetch_started", code=code)

Why a test cannot catch this: ``print`` is not an error. It has no failure mode,
no return value anyone asserts on, and no exception. Deleting a ``print`` breaks
no test; adding one breaks no test. Only a rule that looks for the call itself
can see it.

Scope: ``src/alphacouncil/`` — the shipped product, **except the files whose interface
is stdout**. ``scripts/`` and ``__main__.py`` are CLI entry points, and a command's output
is its product; ``ruff``'s ``T201`` already exempts them for exactly this reason.
Keeping the scope identical to the linter's means there is one rule about ``print``, not
two that disagree.

⭐ **That sentence is the reason :data:`CLI_ENTRY_POINTS` exists.** The scope above was
written down before the implementation, ⭐ and the implementation scanned every ``*.py``
under the package — ⭐ so for as long as no entry point used ``print``, the drift was
invisible. ⭐ ``notify/__main__.py`` (spec 044) is the first file to need one, ⭐ and it
exposed a rule that documented an exemption it did not have.

⭐ The exemption is a **filename**, not a comment: ⭐ a per-call ``noqa`` would need three
of them and would be reviewable line by line, ⭐ while 「the entry point is the file Python
runs with ``-m``」 is one sentence and cannot be applied by accident in the middle of a
module.
"""

from __future__ import annotations

import ast

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_PRINT_STATEMENT"

META = CheckMeta(
    check_id="S-10",
    slug="no-print",
    title="no print() in the product",
    priority="P2",
    code=CODE,
)


#: `print` under an alias, and the `builtins.` form.
_BANNED_CALLS = frozenset({"print", "builtins.print"})

#: ⭐ Files whose stdout **is** the interface. ⭐ Named by filename because that is the one
#: thing that makes the exemption reviewable: ``python -m alphacouncil`` runs
#: ``__main__.py``, ⭐ so a `print` in it reaches the person who typed the command — ⭐ which
#: is the whole difference between a report and an invisible line.
#:
#: ⚠️ **And a `print` in any *other* file still fails**, ⭐ including a module the entry
#: point calls. ⭐ Otherwise 「the output is mine」 would grow into 「the output is anything
#: on the way out」, ⭐ and that is the rule this whole project exists to prevent.
CLI_ENTRY_POINTS = frozenset({"__main__.py"})


def run(ctx: ScanContext) -> CheckResult:
    """Find ``print`` calls in the shipped package."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        if path.name in CLI_ENTRY_POINTS:
            continue
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name not in _BANNED_CALLS:
                continue
            result.error(
                CODE,
                f"`{name}()` in the product writes to a console nobody reads",
                target=format_target(ctx, path, node.lineno),
                fix='Use `structlog`: `logger.info("event_name", key=value)`. '
                "A packaged app has no visible stdout (constitution 7.4). "
                "The one exception is a file named `__main__.py`, whose stdout *is* "
                "the interface.",
            )
    return result


def _call_name(node: ast.Call) -> str | None:
    """Dotted name of the callee, for `print` and `builtins.print`."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


__all__ = ["META", "run"]
