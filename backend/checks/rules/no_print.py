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

Scope: ``src/alphacouncil/`` — the shipped product. ``scripts/`` and
``__main__.py`` are CLI entry points whose *interface is stdout*, and they are
already exempt from ``ruff``'s ``T201`` for the same reason. Keeping the scope
identical to the linter's means there is one rule about ``print``, not two that
disagree.
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


def run(ctx: ScanContext) -> CheckResult:
    """Find ``print`` calls in the shipped package."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
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
                fix="Use `structlog`: `logger.info(\"event_name\", key=value)`. "
                "A packaged app has no visible stdout (constitution 7.4).",
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
