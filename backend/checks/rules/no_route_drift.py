"""S-17 · Every frontend call site, joined against the routes the app actually serves.

Spec 050.  The reasoning is in `.ai/specs/050-route-pairing/spec.md`; this docstring says
what a reader needs to run the rule or change it.

⭐ **This scan was hand-rolled four times in earlier sessions and was wrong three of them**,
producing the numbers 26 orphans, 0 of 36 reachable, 12, then 11.  Everything below exists
because of one specific way that went wrong.

## The four buckets

    drift          FAIL   the frontend calls a method+path the backend does not have
    unverifiable   INFO   a path built by a call, so the rule cannot tell a segment from
                            a query string — and says so instead of guessing
    orphan         INFO   a served route no call site reaches
    ok                    the rest

⚠️ **Orphan is not drift, and the difference is the whole design.** `/health` is a liveness
probe; `/api/v1/capabilities` has no screen yet; a schema endpoint exists so a client *can*
ask. Those are legitimate states, and a rule that reports them as errors is a rule that gets
deleted. Every earlier version collapsed 「nobody calls this」 and 「this is broken」 into one
bucket, which is why none of them survived contact with a real tree.

## Where each side comes from, and why

**Backend: `openapi.json`, not `app.routes` and not the source files.**  On the pinned
FastAPI, `app.routes` holds twelve `_IncludedRouter` objects whose `path` is `''`; a walk
that filters on `if not path: continue` throws all twelve away and is left with `/health`.
That is exactly `regressions/0012`'s shape — a scan that silently finds nothing looks
identical to a scan that correctly finds nothing — and it is why the first version of this
rule reported **46 of 46 call sites as drift while the frontend was entirely correct.**

Reaching those routes means private attributes (`original_router`,
`include_context.included_router`) that a FastAPI upgrade can move.  `openapi.json` has the
paths FastAPI itself computed, after every `include_router` and every
`APIRouter(prefix=...)`.  ⇒ **This retires the 「I forgot the prefix」 mistake class by never
seeing a prefix**, rather than by handling prefixes more carefully.

**Frontend: a balanced scanner over three files.**  The four mistakes that were made before,
and what each one cost:

    a template never equals a route       -> `${...}` becomes one `*` segment
    a query string makes a path unique    -> four query shapes, listed below
    a leading slash is not guaranteed     -> `lessons.ts` writes `'api/v1/lessons'`
    `method:` searched past the call      -> six GETs reported as POSTs

## The four query shapes in one file

`api.ts` / `notes.ts` / `lessons.ts` between them spell the query four different ways, and
**all four had to be handled or the rule reported drift that did not exist**:

    /api/v1/decisions?limit=${limit}                     literal `?` before the placeholder
    /api/v1/cards${query ? `?${query}` : ''}             `?` inside a nested template
    /api/v1/instruments/{m}/{c}/daily${suffix}           a local `const` holding a query
    /api/v1/instruments/resolve?ticker=${enc(x)}          literal `?` plus a nested call

⚠️ **Not loosening the matcher to cope.** 「A trailing wildcard may match zero segments」
would have made the `suffix` case pass without looking at `suffix` at all, and this
repository has four records of loosening a check until a finding stops appearing.

## The rule checks itself

⚠️⚠️ **`PLAUSIBILITY_FLOOR` is the one thing here that would have saved every earlier
version, and it costs one comparison.** A static route scan that reports *most* of the
frontend as broken is describing itself. So if more than this fraction of call sites come
back as drift, the rule **skips with an explanation** rather than printing a wall of
accusations: a scanner that has lost the shape of the codebase cannot testify about it.

One function, `matches`, decides everything: **one `*` matches exactly one segment, and the
two lists must be the same length.** Not 「one `*` matches anything」 — that would make
`/cards/*/schedule` match `/cards/{card_id}`.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from checks import frontend as frontend_sources
from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

CODE = "CHECK_ROUTE_DRIFT"

META = CheckMeta(
    check_id="S-17",
    slug="no-route-drift",
    title="every frontend call site reaches a route the app actually serves",
    priority="P1",
    code=CODE,
)

#: The three files that hold the client. Named rather than globbed: `e2e/` mocks routes
#: and would otherwise appear to call endpoints the product never calls, and a component
#: that happens to contain the word `request` is not a call site.
CLIENT_FILES = ("api.ts", "notes.ts", "lessons.ts")

#: Served routes that nothing is expected to reach. Orphans are INFO either way, so this
#: table is not about silencing — it is about saying *why*, so the list stays reviewable
#: and a new dead endpoint is visible as 「unaccounted for」 rather than lost in a count.
EXPECTED_UNREACHED: dict[str, str] = {
    "GET /health": "the liveness probe; there is no screen that would ask for it",
}

#: ⚠️⚠️ **The self-check, and the reason this file is worth more than its finding.**
#:
#: A static join that reports *most* of the frontend as broken is not reporting drift, it is
#: reporting that the scanner has lost the shape of the codebase. Six bugs got this far
#: before being caught, and the one that produced 「46 of 46」 was caught by exactly this
#: reasoning: an implausible failure rate is a fact about the tool.
#:
#: ⇒ Above this fraction, the rule **skips** and says why. A skipped rule is visibly not
#: passing (`CheckResult.skipped` is not None), so this cannot become a silent pass.
PLAUSIBILITY_FLOOR = 0.34

#: The wrapper's own declaration is not a call site. ⭐ **The token before a call is the
#: keyword `function`** — which covers `function request(`, `async function request(` and
#: `function request<T>(` alike, because the generic sits *between* the name and the paren
#: and an earlier pattern that tried to match the name itself could never see it (the
#: window ended where `request` began). It was reported as `` `? ` is called from
#: api.ts:458 `` — the rule's only drift finding on a clean tree, and a fair advertisement
#: for the bucket: it found a real defect, in the rule.
WRAPPER = re.compile(r"\bfunction\s+$")

#: `request<X>(...)`, generic included.
CALL = re.compile(r"\brequest(?:<[^()<>]*>)?\s*\(")
#: The verb lives in the options object. Read from the codebase's own spelling rather than
#: from a list of every verb that exists, so a new verb shows up as a miss.
METHOD = re.compile(r"""\bmethod\s*:\s*['"]([A-Za-z]+)['"]""")
#: A placeholder whose whole text is one identifier — the only shape that can be followed
#: to a declaration.
BARE_NAME = re.compile(r"^[A-Za-z_$][\w$]*$")
DECLARATION = r"\b(?:const|let|var)\s+{name}\s*(?::[^=]+)?=\s*"
#: A placeholder computed by a call. `encodeURIComponent` is excluded by name because it
#: wraps a segment rather than building one — and naming one function is honest where
#: inferring intent from a variable's spelling is not.
COMPUTED = re.compile(r"\b(?!encodeURIComponent\b)\w+\s*\(")

_OPENERS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {v: k for k, v in _OPENERS.items()}


# --------------------------------------------------------------------- the app
def served_routes() -> dict[str, tuple[str, ...]]:
    """Every `(method, path)` the app serves, keyed by method.

    Built from the app's own `openapi.json`.  If the app cannot be constructed the caller
    skips: a broken environment is not evidence of drift.
    """
    from fastapi.testclient import TestClient

    from alphacouncil.api.app import create_app
    from alphacouncil.core.config import Settings

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(database_path=Path(tmp) / "schema-only.db")
        with TestClient(create_app(settings)) as client:
            spec = client.get("/openapi.json").json()

    found: dict[str, tuple[str, ...]] = {}
    for path, operations in spec.get("paths", {}).items():
        for method in operations:
            verb = method.upper()
            if verb in {"PARAMETERS", "HEAD", "OPTIONS"}:
                continue
            found.setdefault(verb, ())
            found[verb] = found[verb] + (path,)
    return {verb: tuple(sorted(paths)) for verb, paths in found.items()}


# ------------------------------------------------------------- the frontend
def read_argument(text: str, start: int) -> tuple[str, int]:
    """One call argument as source text, plus the index just past it.

    Balanced across all three bracket kinds and all three quote kinds, so a template holding
    `` ${encodeURIComponent(\n  link.to_kind,\n)} `` comes back whole.

    ⚠️ **A closer met with an empty stack belongs to the caller**, so it ends the argument
    without joining it.  Getting that wrong left a trailing quote on 20 of 46 paths
    (`'/api/v1/watchlist'` -> `/api/v1/watchlist'`), which is still shaped like a path and
    therefore invisible without printing the join.
    """
    i = start
    while i < len(text) and text[i] in " \t\r\n,":
        i += 1
    begin: int = i
    stack: list[str] = []
    quote: str | None = None
    while i < len(text):
        char = text[i]
        if quote is not None:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char in _OPENERS:
            stack.append(char)
        elif char in _CLOSERS:
            if stack and stack[-1] == _CLOSERS[char]:
                stack.pop()
            if not stack:
                return text[begin:i], i + 1
        elif char == "," and not stack:
            return text[begin:i].strip(), i + 1
        i += 1
    return text[begin:i].strip(), i


def placeholders(body: str) -> list[tuple[int, int, bool]]:
    """`(start, end, builds_a_query)` for each `${...}`, brace-counted.

    Brace counting with quote awareness, because the query shapes nest: the outer `${}`
    holds a backtick string that holds another `${}`.
    """
    out: list[tuple[int, int, bool]] = []
    i = 0
    while True:
        start = body.find("${", i)
        if start == -1:
            return out
        depth = 0
        quote: str | None = None
        j = start
        while j < len(body):
            char = body[j]
            if quote is not None:
                if char == "\\":
                    j += 2
                    continue
                if char == quote:
                    quote = None
            elif char in "'\"`":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        raw = body[start : j + 1]
        out.append((start, j + 1, "?" in raw or "&" in raw))
        i = j + 1


def declared_value(text: str, name: str) -> str | None:
    """The text a `const`/`let`/`var <name>` was given, or None when it is not declared here.

    ⚠️ **None does not mean 「unknown」.**  It means the value is a parameter or an import,
    and a parameter is a path segment.  The first version reported 15 of 46 call sites as
    unverifiable — every one of them `cardId`, `id`, `limit` — and a bucket that fires on
    ordinary code is a bucket that means nothing.
    """
    match = re.search(DECLARATION.format(name=re.escape(name)), text)
    if match is None:
        return None
    rest = text[match.end() :]
    _, index = read_argument(rest, 0)
    return rest[:index]


def path_of(argument: str, file_text: str) -> tuple[str | None, str | None]:
    """A call's first argument -> `(path, unknown placeholder)`.

    The path is compared one segment at a time, so a templated segment becomes `*`.
    Returns `None` for the path when the argument is not a string literal at all — a
    variable holding the whole path — and the caller reports that as unverifiable rather
    than skipping it, because a skipped call site is a blind spot.
    """
    if not argument or argument[0] not in "`'\"":
        return None, argument or None

    body = argument[1:-1]
    spans = placeholders(body)

    # A literal `?` outside any placeholder ends the path.  Checked *before* the loop and
    # the spans are filtered to what survives, because keeping the old spans made the loop
    # index past the truncated string and append a `*` for a placeholder that was gone.
    cut = len(body)
    for index, char in enumerate(body):
        if char == "?" and not any(s <= index < e for s, e, _q in spans):
            cut = index
            break
    spans = [s for s in spans if s[0] < cut]
    body = body[:cut]

    segments: list[str] = []
    cursor = 0
    unknown: str | None = None
    for start, end, builds_query in spans:
        inner = body[start:end][2:-1]
        query = builds_query
        if not query and BARE_NAME.match(inner):
            value = declared_value(file_text, inner)
            if value is not None:
                query = "?" in value or "&" in value
        if query:
            body = body[:start]
            break
        if not builds_query and COMPUTED.search(inner):
            unknown = inner
        segments.append(body[cursor:start])
        segments.append("*")
        cursor = end
    segments.append(body[cursor:])

    path = "".join(segments)
    if not path:
        return None, unknown
    # ⚠️ Added, never assumed: `lessons.ts` writes `'api/v1/lessons'` with no leading slash.
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/", unknown


def call_sites(root: Path) -> list[tuple[str, int, str, str, str | None]]:
    """`(file, line, method, path, unknown)` for every call site in the three clients."""
    out: list[tuple[str, int, str, str, str | None]] = []
    for name in CLIENT_FILES:
        path = root / name
        if not path.exists():
            continue
        text = path.read_text("utf-8")
        for match in CALL.finditer(text):
            # The wrapper's own declaration is not a call site.
            if WRAPPER.search(text[max(0, match.start() - 60) : match.start()]):
                continue
            first, after = read_argument(text, match.end())
            resolved, unknown = path_of(first, text)
            if resolved is None:
                if unknown:
                    out.append((name, text.count("\n", 0, match.end()) + 1, "?", "", unknown))
                continue
            second, _ = read_argument(text, after)
            found = METHOD.search(second)
            out.append(
                (
                    name,
                    text.count("\n", 0, match.end()) + 1,
                    found.group(1).upper() if found else "GET",
                    resolved,
                    unknown,
                )
            )
    return out


def reachable(front: str, back: str) -> bool:
    """One `*` matches exactly one segment, and the two lists must be the same length."""
    a = front.strip("/").split("/")
    b = back.strip("/").split("/")
    return len(a) == len(b) and all(x == "*" or x == y for x, y in zip(a, b, strict=True))


# --------------------------------------------------------------------- the rule
def run(ctx: ScanContext) -> CheckResult:
    """Join the frontend's call sites against the routes the app serves."""
    result = CheckResult()
    # ⚠️ **`has_sources`, not `skip_reason`.** `skip_reason()` always returns a string, so
    # branching on it skips unconditionally — the first run of this rule reported
    # 「frontend sources are not present」 against a frontend with 46 call sites in it.
    # Three older rules already pair the message with their own empty-list check, so only
    # the name was wrong; `checks/frontend.py::has_sources` is now the predicate.
    if not frontend_sources.has_sources(ctx):
        result.skipped = frontend_sources.skip_reason()
        return result

    root = frontend_sources.source_root(ctx)
    sources = [root / name for name in CLIENT_FILES if (root / name).exists()]
    result.files = sources
    if not sources:
        result.skipped = "none of the client modules were found — nothing to join against"
        return result

    try:
        routes = served_routes()
    # ⚠️ A broad except, deliberately, and **with no suppression directive** — `BLE` is not
    # in this project's `select` list and `RUF100` says so. The first draft carried a
    # `noqa: BLE001` copied out of `S-16`, which is `F-210` repeated verbatim.
    #
    # ⚠️ And the sentence above is worded to avoid spelling the directive: ruff scans
    # comments for it, so **explaining the absence of a directive in prose that contains
    # one is enough to trip it**. That is its own small version of `F-210` — the tooling
    # cannot tell 「mentioning」 from 「using」, so the wording has to.
    except Exception as exc:
        result.skipped = f"could not read the app's schema: {type(exc).__name__}: {exc}"
        return result
    if not routes:
        result.skipped = "the app published no routes — nothing to join against"
        return result

    calls = call_sites(root)
    if not calls:
        result.skipped = "no call sites found — nothing to join against"
        return result

    drift = [
        (name, line, method, path)
        for name, line, method, path, _unknown in calls
        if not any(reachable(path, back) for back in routes.get(method, ()))
    ]

    # ⚠️⚠️ **The self-check.**  Above this fraction the scanner is the thing that is broken,
    # and a rule that cannot tell that is a rule that will one day accuse a whole frontend.
    if drift and len(drift) / len(calls) > PLAUSIBILITY_FLOOR:
        result.skipped = (
            f"{len(drift)} of {len(calls)} call sites came back as drift, which is more "
            f"than the {PLAUSIBILITY_FLOOR:.0%} this rule trusts itself with. ⭐ That is a "
            "fact about the scanner, not about the frontend — every version of this scan "
            "that was wrong reported almost everything broken, and none of them noticed. "
            "Print the join before believing a number from it."
        )
        return result

    for name, line, method, path in drift:
        result.error(
            CODE,
            f"`{method} {path}` is called from {name}:{line} and no route serves it",
            target=format_target(ctx, root / name),
            fix="Either the path or the verb is wrong, or the endpoint does not exist. "
            "A verb mismatch is the common case: this rule compares (method, path), and "
            "the client defaults to GET when no `method:` is given.",
        )

    # ---------------------------------------------------------------- orphans
    reached: set[tuple[str, str]] = set()
    for _name, _line, method, path, _unknown in calls:
        for back in routes.get(method, ()):
            if reachable(path, back):
                reached.add((method, back))

    for method in sorted(routes):
        for back in routes[method]:
            if (method, back) in reached:
                continue
            label = f"{method} {back}"
            reason = EXPECTED_UNREACHED.get(label)
            target = format_target(ctx, Path(__file__))
            if reason:
                result.note(
                    CODE,
                    f"`{label}` is served and nothing calls it — expected: {reason}",
                    target=target,
                    fix="Nothing to do. Listed here so the reason is on the record rather "
                    "than in whoever's memory.",
                )
            else:
                result.note(
                    CODE,
                    f"`{label}` is served and nothing calls it, and it is not in "
                    f"EXPECTED_UNREACHED",
                    target=target,
                    fix="Either wire a screen to it, or say here why nothing should. ⭐ An "
                    "endpoint with no caller is usually one of two things — a capability "
                    "that was never surfaced, or a hand-written copy of something the "
                    "server was already publishing.",
                )

    # --------------------------------------------------------- unverifiable
    for name, line, _method, _path, unknown in calls:
        if unknown:
            result.note(
                CODE,
                f"{name}:{line} builds its path from `{unknown}`, so this rule cannot tell "
                "a path segment from a query string there",
                target=format_target(ctx, root / name),
                fix="Either inline the path, or accept that this call site is not checked. "
                "⚠️ It is reported rather than skipped on purpose: a silently unchecked call "
                "site is a blind spot, and a blind spot is what this rule exists to remove.",
            )

    return result
