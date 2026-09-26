"""S-01 — no raw HTTP outside the one entry point.

**Defect guarded:** constitution 7.8 / 4.5. Rate limiting has to be *a function*,
not a note asking everyone to remember to add a sleep. The moment a second call
site reaches for ``httpx.get`` directly, the serialisation, jitter, user agent,
circuit breaker and cache are all silently bypassed — and the symptom is not a
crash, it is an IP ban twenty minutes later.

Anti-pattern (forbidden)::

    # anywhere outside providers/
    import httpx
    response = httpx.get(url, timeout=5)          # no UA, no jitter, no breaker

    # even inside providers/, the module-level helper skips the shared Client
    response = httpx.get(url, headers=HEADERS)    # a new connection every call

Correct form::

    # providers/sources.py — the single entry point
    def _client(headers: dict[str, str] | None = None) -> httpx.Client:
        return httpx.Client(timeout=_TIMEOUT, headers=merged, follow_redirects=True)

    def _fetch(self, symbol: Symbol) -> str:
        with _client() as client:
            response = client.get(url)

Why a test cannot catch this: a test exercises the calls that exist. It cannot
observe the call that *should not* exist — a second HTTP path is only reachable
through code the test never runs, and it looks perfectly correct in isolation.

Three rules are enforced, in this order:

1. Outside ``providers/``, naming a raw-HTTP module at all is an error.
2. Anywhere, the module-level helpers (``httpx.get``, ``requests.post``,
   ``urlopen`` …) are an error: they take no shared configuration.
3. Inside ``providers/``, ``httpx.Client(...)`` may only be constructed in a
   factory function, so there is exactly one place where headers and timeouts
   are decided.
"""

from __future__ import annotations

import ast
from pathlib import Path

from checks.framework import (
    CheckMeta,
    CheckResult,
    ScanContext,
    call_target,
    enclosing_function,
    format_target,
)

CODE = "CHECK_RAW_HTTP"

META = CheckMeta(
    check_id="S-01",
    slug="no-raw-http",
    title="no raw HTTP outside the single entry point",
    priority="P0",
    code=CODE,
)


#: Modules that talk to the network. Importing any of these outside
#: ``providers/`` means the single entry point has been bypassed.
RAW_HTTP_MODULES = frozenset({"httpx", "requests", "aiohttp", "urllib3"})

#: Module-level convenience helpers that skip connection reuse entirely.
CONVENIENCE_CALLS = frozenset(
    {
        "httpx.get",
        "httpx.post",
        "httpx.put",
        "httpx.delete",
        "httpx.patch",
        "httpx.head",
        "httpx.options",
        "httpx.request",
        "httpx.stream",
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.patch",
        "requests.head",
        "requests.request",
        "urlopen",
    }
)

#: The functions allowed to build a client. Named rather than "the first one
#: found" so the rule stays reviewable: there is one factory and it has a name.
CLIENT_FACTORY_NAMES = frozenset({"_client", "_make_client", "_http_client"})

CLIENT_CONSTRUCTORS = frozenset({"httpx.Client", "httpx.AsyncClient"})

#: Relative to ``ScanContext.product``, which already points at ``src/alphacouncil``.
_PROVIDERS_REL = Path("providers")


def _inside_providers(ctx: ScanContext, path: Path) -> bool:
    """Whether ``path`` lives in the provider package — the one allowed place."""
    try:
        relative = path.resolve().relative_to(ctx.product.resolve())
    except ValueError:
        return False
    return relative.parts[:1] == _PROVIDERS_REL.parts


def run(ctx: ScanContext) -> CheckResult:
    """Scan the product for HTTP access that bypasses the entry point."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        allowed = _inside_providers(ctx, path)

        if not allowed:
            _report_imports(ctx, result, path, tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = call_target(node)
            if called is None:
                continue
            if called in CONVENIENCE_CALLS:
                result.error(
                    CODE,
                    f"`{called}()` bypasses the shared client",
                    target=format_target(ctx, path, node.lineno),
                    fix="Build the client with the `_client()` factory and call a method "
                    "on it, so headers, timeouts and connection reuse live in one place.",
                )
            elif allowed and called in CLIENT_CONSTRUCTORS:
                enclosing = enclosing_function(tree, node)
                if enclosing not in CLIENT_FACTORY_NAMES:
                    result.error(
                        CODE,
                        f"`{called}(...)` constructed in `{enclosing or '<module>'}`",
                        target=format_target(ctx, path, node.lineno),
                        fix=f"Construct the client only inside {sorted(CLIENT_FACTORY_NAMES)}; "
                        "everywhere else take it as a parameter.",
                    )
    return result


def _report_imports(
    ctx: ScanContext, result: CheckResult, path: Path, tree: ast.Module
) -> None:
    """Rule 1: outside ``providers/``, importing a network library is the defect."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in RAW_HTTP_MODULES:
                    result.error(
                        CODE,
                        f"`import {alias.name}` outside the providers package",
                        target=format_target(ctx, path, node.lineno),
                        fix="Call the provider layer instead — "
                        "`alphacouncil.providers.default_router()`.",
                    )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in RAW_HTTP_MODULES
        ):
            result.error(
                CODE,
                f"`from {node.module} import ...` outside the providers package",
                target=format_target(ctx, path, node.lineno),
                fix="Call the provider layer instead — "
                "`alphacouncil.providers.default_router()`.",
            )


__all__ = ["META", "run"]
