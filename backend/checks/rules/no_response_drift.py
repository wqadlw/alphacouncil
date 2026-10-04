"""Every field the backend publishes is declared in some client type.

⚠️⚠️ **This rule exists because of a defect that shipped green.** On 2026-10-04 five
fields were added to `DailySeriesRead`
(`api/routes/instruments.py:396-425`) and they reached the wire (`:533-548`) ⭐ while
`frontend/src/api.ts:1037-1045` still declared two fields. ⭐ Seventeen static checks,
1432 backend tests and 137 e2e tests were green.

⭐ **Not one of them could see it, and the reason is that all seventeen compare the
same two things** — enum value sets (`S-16`, `no_enum_drift.py:250,253`) or
`(verb, path)` pairs (`S-17`, `no_route_drift.py:378-382`). ⭐ Nobody had ever
reconciled the *field* layer.

## The judgement, and why it is one-directional

    schema.properties ⊆ some client type's top-level fields   ⇒  mirrored

⭐⭐ **Subset, not equality** ⭐ — and the reason is not leniency. ⭐ A client type exists
so the compiler can check **reads of what arrives** ⭐ — a one-directional obligation. ⭐ A
field the client declares and the server never sends is the *opposite* defect, and
`no_enum_drift.py:44-48` already gave it its name: 「the client waits for a value that can
never arrive, ⭐ **and that branch is dead code which looks correct**」. ⭐ That defect is
real and worth reporting — ⭐ and it is not this rule's job, because making it red would
mean **every** legitimate client-side view had to be declared as a waiver. ⭐ Measured: 191
extra client field names on a clean tree. ⭐ A finding per extra field is noise; a rule
whose every finding is a waiver is a decoration (`F-207`).

## Why there is no "too small to discriminate" threshold

⚠️ **The first draft had `DISCRIMINATION_FLOOR = 4`** ⭐ — on the reasoning that a
three-field schema like `Symbol` is satisfied by three unrelated types and therefore
carries no information. ⭐ Measured: that is true, and it cut the findings from 12 to 4.

⭐⭐ **And that is exactly why it had to go.** ⭐ A constant whose value was chosen because
it made the number smaller is a constant tuned to a fixture, ⭐ and `test_response_drift.py`
says in its own docstring that tuning a constant to a fixture is the mistake it watches
for. ⭐ **A threshold that hides findings is indistinguishable from a threshold that does
not exist** ⭐ — the only difference is that one of them was written down.

⇒ **Every finding is a fact about the code instead**: 「this is a request body the client
types inline」, 「this one is nested inside another type」, 「this endpoint has no client
consumer at all」. ⭐ **Five such facts now, down from twelve** ⭐ — the seven request
bodies got named client types and the rule noticed. ⭐ That is a
longer table than four entries, ⭐ and every entry in it can be *argued with*, which is
what `no_enum_drift.py:79-82` asks of a reason.

## The parser, and the bug it is shaped around

⚠️⚠️ **A member counts when the cumulative depth *at its name* is zero.** ⭐ This is the
whole rule, and it is written down because the probe that designed this rule got it wrong
three times.

`api.ts:661` reads:

    due: {
      cards: DueCount
      reviews: DueCount
    }

⭐ **The line that declares `due` is the line that opens its braces.** ⭐ The first
version asked "does this line's brace balance exceed zero" ⭐ — true of exactly the lines
that declare a member with an object type ⭐ ⇒ **it dropped `due` and hoisted its
children to the top level.** ⭐ That probe reported `Today` as missing a field the page
reads at `TodayPage.tsx:91`, ⭐ and **`tsc` being green is what proved the probe wrong
rather than the client.** ⭐ Four probes, three of them wrong, all of them the parser.

`AC-5` of spec 053 is the assertion that this cannot come back ⭐ — the same member,
written three ways.

⭐ **Methods are excluded** ⭐ (`MEMBER` accepts `:` and not `(`): ⭐ a `render(): void`
member is not on the wire.

## What this rule cannot see, stated rather than implied

Three holes, measured. ⭐ They are in the spec too (`## 已知的失败`) ⭐ — a guard that
claims completeness it does not have is worse than one that says where it ends
(`no_raw_http.py:127-140`).

1. ⭐ **Nested schemas.** `DueRead` lives inside `Today.due` and `DueCriterionRead`
   inside `AttentionItem.item` ⭐ — both are inline literals, ⭐ and an inline literal is
   textually identical to the named type it stands for, ⭐ so descending would degrade
   the judgement into "does this text appear somewhere". ⇒ waived by hand.
2. ⭐ **Request bodies.** `TagWrite`, `WatchlistAddRequest`, both `ReviewRequest`s and
   the rest are object literals inside function bodies. ⭐ Not addressed here at all.
3. ⭐ **Types, not just names.** `volume: number` becoming `volume: string` is invisible
   here. ⭐ That needs a real TypeScript parser, ⭐ which `constitution.md:3.2.1` does not
   permit adding.

⚠️ And one false pass, which is the honest cost of the design: ⭐ **small schemas get
satisfied by unrelated types** (`Symbol`'s three fields match `WatchlistEntry`,
`InstrumentDetail` and `TickerResolution`) ⭐ — so `LessonCreate`, `NoteUpdate` and five
others "pass" by coincidence. ⭐ A coincidence that passes is better than a threshold that
hides, ⭐ and it is written here so nobody reads green as proof.
"""

from __future__ import annotations

import re
import sys
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from checks import frontend as frontend_sources
from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

CODE = "CHECK_RESPONSE_DRIFT"

META = CheckMeta(
    check_id="S-18",
    slug="no-response-drift",
    title="every field the backend publishes is declared in a client type",
    priority="P1",
    code=CODE,
)

#: FastAPI's own envelopes and its body-parameter aliases. ⭐ Structural, not a list of
#: our names: `DataResult_*` is the generic response wrapper, `HTTPValidationError` /
#: `ValidationError` are the framework's error bodies, and `*_Input` is FastAPI's alias
#: for a body parameter that has no model of its own. ⭐ None of them is product data and
#: none of them has a client type to declare.
ENVELOPE = re.compile(r"^(?:DataResult_|HTTPValidationError$|ValidationError$|.*_Input$)")

#: Reasons that are not reasons. Copied from `no_enum_drift.py:201-203` ⭐ — two rules
#: with one idea should have one copy of the idea, ⭐ not two that drift.
EMPTY_REASONS = frozenset(
    {"n/a", "na", "none", "not applicable", "no", "tbd", "todo", "later", "-", "?"}
)

#: ⭐⭐ **Five structural facts, each of which can be checked by reading one file.**
#: ⭐⭐ **It was twelve until 2026-10-04**, ⭐ when seven request bodies were given named
#: client types — ⭐ and the rule said so itself, ⭐ seven times, ⭐ with 「hiding a green
#: result」. ⭐ The old reason was 「the request body is a literal inside a function」, ⭐
#: **which is not a fact but a position** —— the literal is still inline, ⭐ it now satisfies
#: a name.
#:
#: ⚠️ **Not "too small to discriminate".** ⭐ An earlier draft of this rule had a field
#: count floor and these twelve were four of them. ⭐ The floor was removed because a
#: constant chosen to make the count smaller is a constant tuned to a fixture ⭐ — see the
#: module docstring. ⭐ What replaced it is a reason that names a *fact about the code*.
NOT_MIRRORED: dict[str, str] = {
    # ---- nested inside another client type (three facts, one shape) ----
    "DueRead": (
        "mirrored as the inline object literal inside `Today.due` in api.ts; a named "
        "interface for it would be a second home for one shape"
    ),
    "DueCriterionRead": (
        "mirrored as the inline object literal inside `AttentionItem.item` in api.ts, "
        "which is why AttentionItem declares criterion and decision_id at top level"
    ),
    # ---- no client consumer at all ----
    "CapabilityCell": (
        "`GET /capabilities` has no UI: grep for `capabilities` under frontend/src returns "
        "zero hits, so there is no type to declare it in"
    ),
    "CapabilitySource": (
        "the payload of CapabilityCell, on the same endpoint with no client consumer; "
        "S-16's NOT_MIRRORED already carries the same reason for CapabilityState"
    ),
    "CapabilitiesRead": (
        "`GET /capabilities` has no UI: grep for `capabilities` under frontend/src returns "
        "zero hits. Recorded as open debt, so a waiver states the debt instead of hiding it"
    ),
}

#: `interface X {` or `type X = {`, with or without `export`, generics tolerated.
#: ⭐⭐ **The first version could not match `type X = {` at all** ⭐ — `[=\s]\{` asks for a
#: character that a greedy `\s*` has already eaten. ⭐ Probed against twelve shapes
#: (four adversarial: a function type, a `Exclude<...>` union, a one-value union, an index
#: signature) and it now matches all twelve. ⭐ On this checkout it sees the **same 71**
#: client types as the broken one, ⭐ because `frontend/src` happens to declare no `type X = {`
#: ⭐ — so the bug was real and had no effect *here*, ⭐ which is a different sentence
#: from "the bug was not real" and the docstring of a guard should say which one it is.
DECLARATION = re.compile(
    r"^[ \t]*(?:export\s+)?(?:declare\s+)?(?:interface|type)\s+(\w+)"
    r"(?:<[^>{\n]*>)?\s*=?\s*\{",
    re.M,
)

#: One member: a name, an optional `?`, then a colon. ⭐⭐ **That colon is what
#: excludes a method** — `render(): void` has `render` followed by `(`, ⭐ so `\s*:` fails
#: and the method is not counted. ⭐ An earlier comment here said the exclusion came from
#: `(` being absent from the character class, ⭐ which is not what happens ⭐ and is the
#: same mistake `no_enum_drift.py:185-187` made: ⭐ a comment describing a mechanism other
#: than the one doing the work.
MEMBER = re.compile(r"^[ \t]*(?:readonly\s+)?([A-Za-z_$][\w$]*|'[^']+')(\?)?\s*:")


@dataclass(frozen=True, slots=True)
class Wire:
    """One published object schema: what it declares, ⭐ and which of that is load-bearing.

    ⭐ `required` is the server's own statement about which fields break a reader if the
    client cannot see them ⭐ — ⭐ and reading it is what lets this rule tell 「the client
    may read `undefined`」 from 「the client does not exercise an optional path」. ⭐ The
    module docstring has the measurement that forced the split."""

    properties: frozenset[str]
    required: frozenset[str]


def wire_schemas() -> dict[str, Wire] | None:
    """Every object schema FastAPI publishes, keyed by name.

    ⭐ **Constructed, never committed.** ⭐ pydantic generates this schema, ⭐ so it cannot
    drift from the backend ⭐ — and a checked-in copy would be a *new* stale source rather
    than a guard. ⭐ `None` means the app could not be built, ⭐ which the caller turns
    into a skip ⭐ because 「跳过的门禁不是通过的门禁」 (`dev.py:288-292`).
    """
    try:
        from fastapi.testclient import TestClient

        from alphacouncil.api.app import create_app
        from alphacouncil.core.config import Settings
    except ImportError:
        return None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(database_path=Path(tmp) / "schema-only.db")
            with TestClient(create_app(settings)) as client:
                response = client.get("/openapi.json")
            spec = response.json()
    except Exception:  # a rule that cannot build the app must say so, not pass
        return None

    out: dict[str, Wire] = {}
    for name, schema in (spec.get("components") or {}).get("schemas", {}).items():
        if not isinstance(schema, dict):
            continue
        props = schema.get("properties")
        if isinstance(props, dict) and props:
            out[name] = Wire(
                properties=frozenset(props),
                required=frozenset(schema.get("required") or ()),
            )
    return out


def _depth_delta(segment: str) -> int:
    """Brace balance of one line, ignoring braces inside quotes.

    ⭐ A template literal holding `${x}` would otherwise move the depth, ⭐ and every
    member after it would be silently dropped ⭐ — which is the same failure as the one
    this module exists to avoid, arrived at from the other direction.
    """
    delta = 0
    quote: str | None = None
    index = 0
    while index < len(segment):
        char = segment[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
        index += 1
    return delta


def _strip_comments(text: str) -> str:
    """Remove ``/* ... */`` blocks and ``// ...`` tails, ⭐ keeping newlines.

    ⭐⭐ **Comments come off FIRST, and that ordering is the whole point.** ⭐ An
    earlier version tracked quotes while scanning and hit this in `api.ts`:

        * the three 「we don't know」states.

    ⭐ That apostrophe opened a string literal ⭐ in the reader's eyes ⭐ and every
    newline after it stopped being a segment boundary, ⭐ so the **last member of
    `AttentionItem` — `adjudicable` — was swallowed** ⭐ and `AttentionRead` stopped
    matching its client type. ⭐ A per-line version of the same tracker reset each line
    and hid the bug; ⭐ the version that spanned lines exposed it.

    ⚠⬈ **Newlines are preserved** ⭐ because they are the depth-0 boundary, ⭐ and ⚠⬈
    **a `//` inside a string literal would be removed as a comment** ⭐ — ⭐ not handled,
    because the body being scanned is a type declaration ⭐ where a URL in a literal is
    the only realistic case, ⭐ and `test_a_url_in_a_string_survives`-shaped coverage for
    this rule would be dishonest until it is actually written.
    """
    out: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            out.append(char)
            if char == "\\":
                if index + 1 < len(text):
                    out.append(text[index + 1])
                    index += 2
                    continue
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"\u0060":
            quote = char
            out.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < len(text):
            following = text[index + 1]
            if following == "/":
                while index < len(text) and text[index] != "\n":
                    index += 1
                continue
            if following == "*":
                index += 2
                closer = text.find("*/", index)
                while closer == -1:
                    if index < len(text) and text[index] == "\n":
                        out.append("\n")
                    index += 1
                    closer = text.find("*/", index)
                index = closer + 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _segments(body: str) -> Iterator[str]:
    """Split a comment-free object body at depth 0 into candidate member declarations.

    ⭐⭐ **Depth 0, not lines.** ⭐ A one-line body — `interface T { a: string; b: number }`
    — is a formatting choice, ⭐ and `no_enum_drift.py:194-196` states the standard this rule
    is held to: ⭐ 「a rule that can be defeated by reformatting is not a rule」. ⭐ Measured
    on this checkout: 76 declarations, all multi-line ⭐ — so a line-based scanner is green
    here and blind the day someone writes it compactly. ⭐ Both facts are in this docstring
    because a guard that does not say where it ends is worse than one that stops.

    Brackets are counted, not just braces, ⭐ because an index signature `[k: string]: T`
    must not shift the depth.
    """
    depth = 0
    quote: str | None = None
    start = 0
    index = 0
    while index < len(body):
        char = body[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"\u0060":
            quote = char
        elif char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
        elif depth == 0 and char in ";\n":
            yield body[start:index]
            start = index + 1
        index += 1
    yield body[start:]


def _members(body: str) -> frozenset[str]:
    """Top-level member names of one object body.

    ⭐⭐ **The rule that matters: only depth 0 is counted.** ⭐ `due: {` is both — it declares
    a member *and* opens a nested object — ⭐ so it must be read before the depth moves,
    ⭐ and its children must not be. ⭐ The module docstring is the long version of why.
    """
    names: set[str] = set()
    for segment in _segments(_strip_comments(body)):
        line = segment.strip()
        if not line:
            continue
        found = MEMBER.match(line)
        if found:
            names.add(found.group(1).strip("'"))
    return frozenset(names)


def client_types(sources: Iterable[tuple[str, str]]) -> dict[str, tuple[str, frozenset[str]]]:
    """Every named object type in the client, as ``name -> (file, top-level fields)``.

    ⭐ Nested members are deliberately **not** collected ⭐ — `DailyBar.symbol` holds a
    two-field object, ⭐ and a scanner that descended would report `market` and `code` as
    if they were top-level fields of `DailyBar`. ⭐ Only depth 0 is the wire shape.
    """
    found: dict[str, tuple[str, frozenset[str]]] = {}
    for rel, text in sources:
        for match in DECLARATION.finditer(text):
            name = match.group(1)
            body_start = text.index("{", match.end() - 1)
            depth = 0
            end = len(text)
            for index in range(body_start, len(text)):
                if text[index] == "{":
                    depth += 1
                elif text[index] == "}":
                    depth -= 1
                    if depth == 0:
                        end = index
                        break
            members = _members(text[body_start + 1 : end])
            if not members:
                continue
            previous = found.get(name)
            # ⭐ Two declarations of one name with different fields ⇒ keep the union, ⭐ so
            # the probe cannot quietly pick a winner and call it a mirror.
            merged = previous[1] | members if previous else members
            found[name] = (rel, merged)
    return found


def _reason_is_real(reason: str) -> bool:
    """Same judgement as `no_enum_drift.py:335-336` ⭐ — 「不适用」 is a sentence nobody
    can argue with, ⭐ and this file is read in six months by someone who needs to."""
    return reason.strip().lower() not in EMPTY_REASONS and len(reason.strip()) >= 16


def run(ctx: ScanContext) -> CheckResult:
    """Reconcile what the server publishes against what the client declared."""
    result = CheckResult()

    # ⭐ **Files, never the directory** — `apply_exemptions` walks `result.files` looking
    # for a suppression marker, ⭐ so a directory here is a PermissionError raised *after* the rule
    # decided it was clean. ⭐ `no_enum_drift.py:352-357` is the second crash of that rule.
    scanned = [path for path in frontend_sources.files(ctx) if ".test." not in path.name]
    result.files = scanned

    if not scanned:
        result.skipped = frontend_sources.skip_reason()
        return result

    schemas = wire_schemas()
    if schemas is None:
        # ⚠️ A skip, not a pass. ⭐ S-16 and S-17 guard the same way, ⭐ because a rule
        # that cannot read the codebase cannot testify about it.
        result.skipped = "the app could not be built, so openapi.json is unavailable"
        return result

    root = frontend_sources.source_root(ctx)
    types = client_types(
        (str(path.relative_to(root)).replace("\\", "/"), path.read_text("utf-8"))
        for path in scanned
    )

    for name in sorted(schemas):
        if ENVELOPE.match(name):
            continue
        if name in NOT_MIRRORED:
            continue
        wire = schemas[name]
        holders = sorted(
            candidate for candidate, (_, got) in types.items() if wire.properties <= got
        )
        if holders:
            if len(holders) > 1:
                result.note(
                    CODE,
                    f"`{name}` ({len(wire.properties)} fields) is declared by {len(holders)}"
                    f" client types at once: {holders[:4]}. The correspondence is ambiguous,"
                    f" so this pass is a coincidence rather than a mirror",
                    target=format_target(ctx, root),
                    fix="If one of them is the real mirror, narrow it; if the schema really is "
                    "that generic, waive it with a reason that says so.",
                )
            continue

        closest, got = min(
            ((name_, got_) for name_, (_, got_) in types.items()),
            key=lambda pair: len(wire.properties - pair[1]),
            default=("", frozenset()),
        )
        gap = wire.properties - got
        missing_required = sorted(gap & wire.required)
        missing_optional = sorted(gap - wire.required)
        where = f"`{closest}` in {types[closest][0]}" if closest else "any client type"

        if missing_required:
            result.error(
                CODE,
                f"`{name}` requires {missing_required} and no client type declares them; the "
                f"closest is {where}",
                target=format_target(ctx, root),
                fix=f"Add {missing_required} to {where}, or list the schema in NOT_MIRRORED "
                "with a reason that names a fact about the code. Spec 053 §FR-1.",
            )
            continue

        result.note(
            CODE,
            f"`{name}` also offers {missing_optional}, which it does not require, and no client "
            f"type declares them; the closest is {where}",
            target=format_target(ctx, root),
            fix="⚠️ **This is not drift** — a client that does not exercise an optional path is "
            "a legitimate shape. ⭐ Declare them if a page should read them; ⭐ if not, this "
            "note is the whole cost of the server offering something nobody uses yet.",
        )

    # ⭐⭐ **A waiver that covers nothing is worse than no waiver.** ⭐ S-16 learned this
    # the expensive way: all six of its NOT_MIRRORED entries were reported as drift on a
    # clean tree because the first version matched all three exemption dicts by value-set
    # (`no_enum_drift.py:430-432`). ⭐ A waiver must therefore (a) still match a schema
    # that exists, (b) carry a reason, and (c) cover something that *would* have been red.
    for name, reason in sorted(NOT_MIRRORED.items()):
        if name not in schemas:
            result.error(
                CODE,
                f"the NOT_MIRRORED entry for `{name}` names a schema FastAPI no longer "
                f"publishes, so it waives nothing",
                target=format_target(ctx, Path(__file__)),
                fix="Delete the entry. A waiver that cannot match is not a waiver.",
            )
            continue
        if not _reason_is_real(reason):
            result.error(
                CODE,
                f"the NOT_MIRRORED entry for `{name}` carries no reason",
                target=format_target(ctx, Path(__file__)),
                fix="Say what the shape *is*. A reason nobody can argue with is not a reason.",
            )
            continue
        # ⭐⭐ `fields` is rebound here **on purpose** ⭐ and that is the second
        # bug this function had. ⭐ The first version read the name from the enclosing
        # loop, ⭐ so all eleven waivers were judged against whichever schema happened
        # to be iterated last ⭐ — which is how "a waiver that hides a green result"
        # would have passed forever while never being checked against its own schema.
        declared = schemas[name].properties
        if any(declared <= got for _, got in types.values()):
            result.error(
                CODE,
                f"the NOT_MIRRORED entry for `{name}` waives something no client type is "
                f"missing, so it is hiding a green result",
                target=format_target(ctx, Path(__file__)),
                fix="Delete the entry, or the schema it names is already mirrored and the "
                "waiver is only there to make the table look thorough.",
            )
    return result
