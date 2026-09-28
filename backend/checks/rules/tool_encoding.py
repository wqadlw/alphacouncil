"""S-13 — a developer tool that prints must own its output encoding.

**Defect guarded:** regression ``0004``, and its immediate recurrence.

``dev.py`` prints a tick and a cross to mark a verdict. On a Chinese Windows
console ``sys.stdout.encoding`` is ``gbk``, which has neither character, and
``sys.stdout``'s default ``errors='strict'`` turns that into a
``UnicodeEncodeError`` *part-way through the report* — so ``dev.py check``
printed "ran 10 · passed 10 · failed 0" and then exited **1**. A gate that
cannot say "green" is the same as no gate.

The fix was ``use_utf8()`` in three ``main()`` functions. Three call sites is
not a mechanism. **On the same day, a fourth tool was written without it** —
``scripts/eval.py`` — and its ``--json`` output came out in GBK, truncating a
Chinese string mid-document. That is what this rule exists for.

Anti-pattern (forbidden)::

    # scripts/something.py
    def main() -> int:
        print("  ✓ every gate passed")      # ← crashes on a cp936 console
        return 0

Correct form::

    from _console import use_utf8

    def main() -> int:
        use_utf8()                          # ← before anything is printed
        print("  ✓ every gate passed")
        return 0

Why a test cannot catch this: a test that reads its own output back through a
UTF-8 pipe sees a correct file, because the *writer* is fine when the console
happens to be UTF-8. The defect only exists on a machine whose stdout is a
legacy codepage, and the CI runner's is not. The check that does catch it is
``PYTHONIOENCODING=gbk`` in a subprocess — which is a behavioural test, so this
rule deliberately does **not** try to replace it; it closes the cheap gap so
that writing a new tool without the call is a build failure rather than a
discovery on someone else's machine.

Scope: ``scripts/*.py`` and ``checks/__main__.py`` — the developer tools whose
*interface* is human-readable output. ``_console.py`` itself is exempt: it is
the implementation, and it must not call itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_TOOL_ENCODING_UNGUARDED"

META = CheckMeta(
    check_id="S-13",
    slug="tool-encoding",
    title="a printing developer tool must call use_utf8()",
    priority="P0",
    code=CODE,
)

#: The helper's own module. It defines the call, so requiring it to make the
#: call is a self-reference.
_EXEMPT_FILES = frozenset({"_console.py"})


def run(ctx: ScanContext) -> CheckResult:
    """Find developer tools that print without taking ownership of encoding."""
    result = CheckResult()
    backend = ctx.backend

    for path in _tool_files(backend):
        if path.name in _EXEMPT_FILES:
            continue
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        if _calls_use_utf8(tree):
            continue
        result.error(
            CODE,
            f"`{path.name}` prints human output but never calls `use_utf8()`",
            target=format_target(ctx, path, 1),
            fix="Add `from _console import use_utf8` and call it as the first "
            "statement of `main()`. Without it, a cp936 console raises "
            "UnicodeEncodeError mid-report and the process exits 1 on a green "
            "run (regression 0004).",
        )
    return result


def _tool_files(backend: Path) -> list[Path]:
    """The modules whose interface is human-readable output.

    ``scripts/`` and ``checks/__main__.py``. Deliberately a fixed list rather
    than "anything that prints": the rule is about the *tools a human runs*, and
    a heuristic would flag test files and fixtures that legitimately print.
    """
    found: list[Path] = []
    scripts = backend / "scripts"
    if scripts.is_dir():
        found.extend(sorted(scripts.glob("*.py")))
    checks_main = backend / "checks" / "__main__.py"
    if checks_main.is_file():
        found.append(checks_main)
    return found


def _calls_use_utf8(tree: ast.Module) -> bool:
    """Whether the module calls ``use_utf8()`` anywhere at module or function scope.

    Deliberately not "inside ``main`` specifically": a module may route its
    entry through a helper, and a rule that insisted on one exact shape would
    push people to satisfy the letter of the check rather than its intent. What
    must not happen is a tool that never calls it at all.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name == "use_utf8":
            return True
    return False


__all__ = ["META", "run"]
