"""S-11 — no bare ``except:`` and no silently swallowed exception.

**Defect guarded:** constitution 7.3. A bare ``except`` catches ``KeyboardInterrupt``
and ``SystemExit`` along with everything else, so Ctrl-C stops working. An
``except Exception: pass`` is worse in a different way: it converts a crash into
a wrong answer, and the user gets a plausible number instead of an error.

Anti-pattern (forbidden)::

    try:
        quote = fetch(code)
    except:                       # swallows Ctrl-C
        pass

    try:
        score = compute(decision)
    except Exception:
        pass                      # the failure is now invisible

Correct form::

    try:
        quote = fetch(code)
    except httpx.TimeoutException as exc:
        logger.warning("quote_fetch_timeout", code=code, error=str(exc))
        raise DataUnavailableError(code) from exc

Why a test cannot catch this: the swallowing path is only reachable when
something *else* fails, so tests written against working code never enter it.
The one test that would enter it — a failure-injection test — is precisely the
test nobody writes for the ``except`` clause they added "just to be safe".

What this rule does **not** check, on purpose: whether a caught exception is
handled *well*. Constitution 7.3 asks for logging or re-raising, but a static
rule cannot tell a deliberate degraded return from a swallowed bug, and a rule
that guesses would be turned off. That judgement stays in review.
"""

from __future__ import annotations

import ast

from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

CODE = "CHECK_BARE_EXCEPT"

META = CheckMeta(
    check_id="S-11",
    slug="no-bare-except",
    title="no bare except and no silently swallowed exception",
    priority="P2",
    code=CODE,
)


#: Exception types that, when caught and ignored, hide a real failure.
BROAD_TYPES = frozenset({"Exception", "BaseException"})

#: Statements that do nothing at all.
_NO_OPS = (ast.Pass, ast.Continue)


def run(ctx: ScanContext) -> CheckResult:
    """Find handlers that catch everything, and handlers that catch nothing."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                result.error(
                    CODE,
                    "bare `except:` also catches KeyboardInterrupt and SystemExit",
                    target=format_target(ctx, path, node.lineno),
                    fix="Name the exceptions you expect, e.g. "
                    "`except (httpx.HTTPError, OSError) as exc:`.",
                )
            elif _is_broad(node.type) and _is_silent(node.body):
                result.error(
                    CODE,
                    f"`except {_render(node.type)}` with an empty body hides the failure",
                    target=format_target(ctx, path, node.lineno),
                    fix='Either log it (`logger.warning("event", error=str(exc))`) or '
                    "re-raise it (`raise SomeError(...) from exc`). A swallowed "
                    "exception becomes a wrong number, not a visible absence.",
                )
    return result


def _is_broad(node: ast.expr) -> bool:
    """Whether the handler catches one of the very wide exception types."""
    if isinstance(node, ast.Name):
        return node.id in BROAD_TYPES
    if isinstance(node, ast.Tuple):
        return any(_is_broad(element) for element in node.elts)
    return False


def _is_silent(body: list[ast.stmt]) -> bool:
    """Whether a handler body consists only of no-ops."""
    if not body:
        return True
    return all(isinstance(statement, _NO_OPS) for statement in body)


def _render(node: ast.expr) -> str:
    return ast.unparse(node)


__all__ = ["META", "run"]
