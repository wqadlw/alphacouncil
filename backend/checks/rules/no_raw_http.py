"""S-01 — no raw HTTP outside the one construction site.

**Defect guarded:** constitution 7.8 / 4.5. Rate limiting has to be *a function*,
not a note asking everyone to remember to add a sleep. The moment a second call
site reaches for ``httpx.get`` directly, the serialisation, jitter, user agent,
circuit breaker and cache are all silently bypassed — and the symptom is not a
crash, it is an IP ban twenty minutes later.

Anti-pattern (forbidden)::

    # anywhere outside core/http.py
    import httpx
    response = httpx.get(url, timeout=5)          # no UA, no jitter, no breaker

    # even inside core/http.py, the module-level helper skips the shared Client
    response = httpx.get(url, headers=HEADERS)    # a new connection every call

Correct form::

    # core/http.py — the one place a client is constructed
    def build_client(*, user_agent: str, headers=None) -> httpx.Client:
        return httpx.Client(timeout=DEFAULT_TIMEOUT, headers=merged, follow_redirects=True)

    def _fetch(self, symbol: Symbol) -> str:
        with build_client(user_agent=_MARKET_DATA_UA) as client:
            response = client.get(url)

Why a test cannot catch this: a test exercises the calls that exist. It cannot
observe the call that *should not* exist — a second HTTP path is only reachable
through code the test never runs, and it looks perfectly correct in isolation.

⭐ **Why this is a module allowlist and not a directory one (ADR-0031)**

The rule used to allow *any* file under ``providers/``. That conflated two different
things: the directory where market-data egress happens, and the set of places where
building a client is legitimate. The gap between them is not hypothetical — a
notification channel needs an HTTP client and is not a market data source, and
``default_router()`` is a ⭐ **wrong** answer for it (routing, failover and a disk
cache built for 腾讯/新浪/东财, applied to 「一条飞书消息」).

The rewrite is a **tightening**, not a loosening, and the number is countable:

===================================  =========================================
before: every ``.py`` under ``providers/``  4 files today, unbounded tomorrow
after:  ``core/http.py``                     **1**
===================================  =========================================

``providers/sources.py`` no longer constructs a client; it calls the factory. A
directory is not a reason — ⭐ 「the clients live here」 is a reason, and it can be
said in one sentence and reviewed in one diff.

Three rules are enforced, in this order:

1. Outside ``HTTP_AWARE_MODULES``, naming a raw-HTTP module at all is an error.
2. Anywhere, the module-level helpers (``httpx.get``, ``requests.post``,
   ``urlopen`` …) are an error: they take no shared configuration.
3. **Anywhere**, ``httpx.Client(...)`` may only be constructed inside
   ``CONSTRUCTION_SITES`` and only in a factory function.

⭐ **Rules 2 and 3 are unconditional, and that is what makes rule 1's allowlist
safe to widen.** The old rule only checked construction *inside* the allowed
directory, which is precisely how a directory turned into a permission. Now that
construction is caught everywhere, a module may be allowed to *name* ``httpx`` in
order to catch ``httpx.HTTPError`` without any way to build a rogue client — and
that second, weaker permission gets its own list.
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
    title="no raw HTTP outside the single construction site",
    priority="P0",
    code=CODE,
)


#: Modules that talk to the network. Importing any of these outside
#: ``CONSTRUCTION_SITES`` means the single construction site has been bypassed.
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
CLIENT_FACTORY_NAMES = frozenset({"_client", "_make_client", "_http_client", "build_client"})

CLIENT_CONSTRUCTORS = frozenset({"httpx.Client", "httpx.AsyncClient"})

#: Relative to ``ScanContext.product``, which already points at ``src/alphacouncil``.
#: ⭐ Paths, not package names: a package is a neighbourhood, and a neighbourhood's
#: every future file inherits the permission. See ADR-0031.
CONSTRUCTION_SITES: frozenset[Path] = frozenset({Path("core/http.py")})

#: ⭐ **Naming** a raw-HTTP module is a second, weaker permission than **constructing** a
#: client, and the two have different scopes — which the old rule could not express,
#: because it answered the second question with the first one's directory.
#:
#: ``providers/sources.py`` must import ``httpx`` to catch ``httpx.HTTPError`` and to
#: annotate ``httpx.Response``. That is not a bypass; the bypass would be constructing a
#: client or calling a module-level helper, and ⭐ **rules 2 and 3 now catch both
#: unconditionally** — so widening the import permission costs no safety at all.
#:
#: It was free only because the tightening happened first. Had rule 1 been widened before
#: rule 3 stopped being conditional, this would have been a hole.
#:
#: Every entry needs a reason that is not 「it also wants to make requests」.
HTTP_AWARE_MODULES: frozenset[Path] = CONSTRUCTION_SITES | frozenset(
    {
        # catches `httpx.HTTPError` / `TimeoutException`, annotates `httpx.Response`
        Path("providers/sources.py"),
    }
)


def _relative(ctx: ScanContext, path: Path) -> Path | None:
    """``path`` as a product-relative path, or ``None`` if it is outside the product."""
    try:
        return path.resolve().relative_to(ctx.product.resolve())
    except ValueError:
        return None


def run(ctx: ScanContext) -> CheckResult:
    """Scan the product for HTTP access that bypasses the construction site."""
    result = CheckResult()
    for path in ctx.python_files(ctx.product):
        tree = ctx.tree(path)
        if tree is None:
            continue
        result.files.append(path)
        relative = _relative(ctx, path)
        may_import = relative in HTTP_AWARE_MODULES
        may_construct = relative in CONSTRUCTION_SITES

        if not may_import:
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
                    fix="Build the client with `core.http.build_client()` and call a method "
                    "on it, so headers, timeouts and connection reuse live in one place.",
                )
            elif called in CLIENT_CONSTRUCTORS:
                # ⭐ Reported **everywhere**, not only outside a construction site. A
                # client built anywhere else is the same defect whether or not the
                # directory happens to be allowed, and branching on the allowlist here is
                # how the old rule ended up permitting a whole package. This is also what
                # makes widening `HTTP_AWARE_MODULES` above free.
                enclosing = enclosing_function(tree, node)
                if not may_construct or enclosing not in CLIENT_FACTORY_NAMES:
                    where = f"`{enclosing or '<module>'}`"
                    result.error(
                        CODE,
                        f"`{called}(...)` constructed in {where}",
                        target=format_target(ctx, path, node.lineno),
                        fix=(
                            "Call `core.http.build_client(user_agent=..., headers=...)` "
                            "instead of constructing a client here."
                            if not may_construct
                            else f"Construct the client only inside "
                            f"{sorted(CLIENT_FACTORY_NAMES)}; everywhere else take it as "
                            "a parameter."
                        ),
                    )
    return result


def _report_imports(ctx: ScanContext, result: CheckResult, path: Path, tree: ast.Module) -> None:
    """Rule 1: outside an http-aware module, naming a network library is the defect.

    ⭐ The fix text names ``build_client`` **and** ``default_router()``, because the old
    text said only 「call the provider layer」 — which is correct for a caller that wants
    market data and ⭐ **actively wrong for one that does not**: it tells a notification
    channel to route a webhook through three-source failover and a disk cache. A rule
    whose advice is wrong for a real case in this codebase teaches the next reader to
    discount the whole rule.
    """
    fix = (
        "Build the client with `alphacouncil.core.http.build_client(...)`; "
        "if you want market data, call `alphacouncil.providers.default_router()` instead."
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in RAW_HTTP_MODULES:
                    result.error(
                        CODE,
                        f"`import {alias.name}` outside an http-aware module",
                        target=format_target(ctx, path, node.lineno),
                        fix=fix,
                    )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in RAW_HTTP_MODULES
        ):
            result.error(
                CODE,
                f"`from {node.module} import ...` outside an http-aware module",
                target=format_target(ctx, path, node.lineno),
                fix=fix,
            )


__all__ = ["CONSTRUCTION_SITES", "HTTP_AWARE_MODULES", "META", "run"]
