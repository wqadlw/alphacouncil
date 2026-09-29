"""S-01 — no raw network egress outside the named sites.

**Defect guarded:** constitution 7.8 / 4.5. Rate limiting has to be *a function*,
not a note asking everyone to remember to add a sleep. The moment a second call
site reaches for ``httpx.get`` directly — or opens its own socket, or its own SMTP
session — the serialisation, jitter, user agent, circuit breaker and cache are all
silently bypassed, and the symptom is not a crash, it is an IP ban twenty minutes later.

Anti-pattern (forbidden)::

    # anywhere outside a named network site
    import httpx
    response = httpx.get(url, timeout=5)          # no UA, no jitter, no breaker

    # even inside a network site, the module-level helper skips the shared Client
    response = httpx.get(url, headers=HEADERS)    # a new connection every call

Correct form::

    # core/http.py — the one place a client is constructed
    def build_client(*, user_agent: str, headers=None) -> httpx.Client:
        return httpx.Client(timeout=DEFAULT_TIMEOUT, headers=merged, follow_redirects=True)

Why a test cannot catch this: a test exercises the calls that exist. It cannot
observe the call that *should not* exist — a second network path is only reachable
through code the test never runs, and it looks perfectly correct in isolation.

⭐ **Why this covers sockets and SMTP, not just HTTP (spec 042)**

It did not, until a real requirement forced the question. BaoStock — the candidate
financial source measured in ``spec 041`` — speaks a **private socket protocol on port
10030**, and ``smtplib`` has been in ``notify/email.py`` since spec 033.

⭐ So for a year the rule's own premise was false. 「唯一入口」 is a claim about *all*
egress, and the rule only enforced it for one transport. ⭐ **A socket opened in
``providers/``'s neighbour would have been invisible** — not flagged, not reviewed,
not rate limited. That is not a loophole to be exploited; it is a hole that was there
waiting for the first requirement that used it.

⭐ **Matching is on the exact dotted module, never the top-level package.**

``urllib`` is the proof that a coarse name cannot stand in for a capability: the same
package ships ``urllib.parse`` (pure string parsing, which ``domain/card.py`` uses to
read a card's ``source_url``) and ``urllib.request`` (an HTTP client). Matching
``name.split(".")[0]`` would flag the parser as an egress path — ⭐ the same mistake
ADR-0031 fixed one layer up, where a *directory* was standing in for a *module*.

Three rules are enforced, in this order:

1. Outside ``NETWORK_AWARE_MODULES``, naming a network module at all is an error.
2. Anywhere, the module-level convenience helpers (``httpx.get``, ``requests.post``,
   ``urlopen`` …) are an error: they take no shared configuration.
3. **Anywhere**, a transport client may only be **constructed** inside
   ``NETWORK_SITES``, and only in a factory function.

⭐ **Rules 2 and 3 are unconditional, and that is what makes rule 1's allowlist safe to
widen.** The old rule only checked construction *inside* the allowed directory, which is
precisely how a directory turned into a permission. Now that construction is caught
everywhere, a module may be allowed to *name* ``httpx`` in order to catch
``httpx.HTTPError`` without any way to build a rogue client — and that second, weaker
permission gets its own list.
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
    title="no raw network egress outside the named sites",
    priority="P0",
    code=CODE,
)


#: ⭐ **Exact dotted module names**, never top-level packages.
#:
#: ``urllib`` is why: it contains both ``urllib.parse`` (string parsing) and
#: ``urllib.request`` (a client). A prefix rule cannot tell them apart, and
#: ``domain/card.py`` legitimately imports the parser to read a card's provenance.
#:
#: ⭐ Written as literals so a static analyser can resolve them — the CWE-73 lesson is
#: that an allowlist expressed in a computed form is an allowlist nothing can check.
NETWORK_MODULES: frozenset[str] = frozenset(
    {
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        # transports the rule did not used to know about (spec 042)
        "socket",
        "ssl",
        "ftplib",
        "imaplib",
        "poplib",
        "smtplib",
        "http.client",
        "urllib.request",
        "urllib.error",
        "xmlrpc.client",
        # ⭐ **`baostock` is here for a different reason than the rest of this list.**
        # It is not a transport; it is a **library that opens one**, over a private
        # socket on port 10030 (spec 043, measured in research.md §4). ⭐ Naming it is
        # the only way this rule can see that socket at all: the `socket.socket(...)`
        # call happens **inside the package**, and the rule only reads this repository's
        # own files.
        "baostock",
        # ⭐ **`urllib.parse` is deliberately absent.** It parses strings and opens
        # nothing. Naming it here would make the rule cry wolf on real provenance code,
        # and a rule that cries wolf is a rule somebody turns off.
    }
)

#: ⚠️⭐ **This list is maintained by hand, and that is a hole that grows.**
#:
#: The rule reads *this repository's* files. A third-party package that opens a socket
#: on our behalf is therefore **invisible to it** — ``baostock`` is in
#: ``NETWORK_MODULES`` because spec 043 named it, and ⭐ nothing would have noticed if
#: it had not been.
#:
#: ⭐ So this is stated rather than designed away: **a guard that claims to be complete
#: and is not is more dangerous than one that says where it ends**, because the first
#: gets trusted for something it does not cover. Every new dependency that opens a
#: transport has to be added by hand; ``test_the_two_network_lists_agree`` is what stops
#: an entry being added to one and forgotten in the other, ⭐ and it cannot stop one
#: being missed from both. That is the honest scope of this rule.
NETWORK_MODULES_ARE_MAINTAINED_BY_HAND = True

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

#: The functions allowed to build a transport client. Named rather than "the first one
#: found" so the rule stays reviewable: there is one factory and it has a name.
#:
#: ⭐ **Adding a name here is the sanctioned way to satisfy this rule. The alternative —
#: renaming the function to match an existing entry — is the mistake the project's own ruff
#: config warns about** (``pyproject.toml``: 「editing a quotation to satisfy a linter is
#: worse than the warning」). ⭐ A descriptive name that is missing here gets added with a
#: reason; a good name never gets bent to fit a proxy.
#:
#: Each entry is a function that **returns a transport and does nothing else**. That is
#: the property the rule actually wants, and this list is only a proxy for it — ⭐ which is
#: why the proxy stays short and every addition carries a sentence.
CLIENT_FACTORY_NAMES = frozenset(
    {
        "_client",  # providers/sources.py, spec 040
        "build_client",  # core/http.py, ADR-0031
        "_make_client",
        "_http_client",
        # SMTP. ⭐ `_smtp` is the obvious name; `notify/email.py` uses `_smtp_session`
        # because what it returns is a *session* — already past `starttls`, and that
        # distinction is the reason the function exists. Spec 042 found this by running
        # the rule over the real tree, so the name is what the code wanted and the list
        # moved to meet it.
        "_smtp",
        "_smtp_session",
    }
)

CLIENT_CONSTRUCTORS = frozenset(
    {
        "httpx.Client",
        "httpx.AsyncClient",
        "smtplib.SMTP",
        "smtplib.SMTP_SSL",
        "socket.socket",
        "ftplib.FTP",
        "imaplib.IMAP4",
        "imaplib.IMAP4_SSL",
        "urllib.request.OpenerDirector",
    }
)

#: Relative to ``ScanContext.product``, which already points at ``src/alphacouncil``.
#: ⭐ Paths, not package names: a package is a neighbourhood, and a neighbourhood's
#: every future file inherits the permission. See ADR-0031.
#:
#: ⭐ **A construction site is named after the transport it opens**, and there are two:
#: an HTTP client and an SMTP session. ⭐ This is the shape ADR-0031 arrived at — named
#: modules, no directory, no exemption — and the reason it can absorb a second transport
#: without becoming the thing it replaced.
CONSTRUCTION_SITES: frozenset[Path] = frozenset(
    {
        Path("core/http.py"),  # the one place an HTTP client is constructed
        Path("notify/email.py"),  # the one place an SMTP session is opened
        # ⭐ `providers/financial.py` (spec 043) is here for a reason the other two are
        # not: it never calls a transport API, it **imports a library that opens one**.
        # `bs.login()` is what opens the socket, and that happens inside BaoStock. Naming
        # the module here is the *only* way the rule can see it at all -- ⭐ and it is a
        # declaration, not a derivation: nothing verified that this file is the sole
        # importer of `baostock`, which is the gap `NETWORK_MODULES_ARE_MAINTAINED_BY_HAND`
        # admits to.
        Path("providers/financial.py"),
    }
)

#: ⭐ A module may **name** a network module — for its exceptions and its types —
#: without being able to **construct** anything. A second, weaker permission with its own
#: list, and a different scope from construction. ⭐ `providers/sources.py` is here and
#: **not** in the set above: it catches `httpx.HTTPError` and annotates
#: `httpx.Response`, and it does not build a client. Putting it in both is the mistake
#: spec 039 removed, and the guard test in the suite is what keeps it gone.
#:
#: It is free only because the tightening happened first: rule 3 is unconditional, so
#: widening this list costs no safety. Had it been widened before rule 3 stopped being
#: conditional, this would have been a hole.
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


def _is_network_module(name: str) -> bool:
    """Whether a dotted module name is one of the network modules.

    ⭐ **Exact match only.** An earlier version compared ``name.split(".")[0]`` against a
    set of top-level names, which cannot tell ``urllib.parse`` from
    ``urllib.request`` — and the first of those is a string parser that
    ``domain/card.py`` imports to read a card's provenance.
    """
    return name in NETWORK_MODULES


def run(ctx: ScanContext) -> CheckResult:
    """Scan the product for network access that bypasses the named sites."""
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
                # directory happens to be allowed.
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
    """Rule 1: outside a network-aware module, naming a transport library is the defect.

    ⭐ The fix text names ``build_client`` **and** ``default_router()``, because the old
    text said only 「go through the provider layer」 — correct for a caller that wants
    market data and ⭐ **actively wrong for one that does not**. A rule whose advice is
    wrong for a real case in this codebase teaches the next reader to discount the rule.
    """
    fix = (
        "Build the client with `alphacouncil.core.http.build_client(...)`; "
        "if you want market data, call `alphacouncil.providers.default_router()` instead."
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_network_module(alias.name):
                    result.error(
                        CODE,
                        f"`import {alias.name}` outside a network-aware module",
                        target=format_target(ctx, path, node.lineno),
                        fix=fix,
                    )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            # ⭐ Two forms, because the coarse package name and the fine capability are
            # different things:
            #
            #   ``from urllib.request import urlopen``  → the module *is* the capability
            #   ``from urllib import request``          → the module is the package, and
            #                                                  the symbol is the capability
            #
            # A prefix rule catches the second by accident and ``urllib.parse`` with it.
            if _is_network_module(node.module):
                result.error(
                    CODE,
                    f"`from {node.module} import ...` outside a network-aware module",
                    target=format_target(ctx, path, node.lineno),
                    fix=fix,
                )
                continue
            for alias in node.names:
                if _is_network_module(f"{node.module}.{alias.name}"):
                    result.error(
                        CODE,
                        f"`from {node.module} import {alias.name}` outside a "
                        "network-aware module",
                        target=format_target(ctx, path, node.lineno),
                        fix=fix,
                    )


__all__ = [
    "CLIENT_CONSTRUCTORS",
    "CONSTRUCTION_SITES",
    "HTTP_AWARE_MODULES",
    "META",
    "NETWORK_MODULES",
    "run",
]
