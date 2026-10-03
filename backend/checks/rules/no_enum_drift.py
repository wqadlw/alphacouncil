"""S-16 · The frontend's hand-written unions against the backend's own enums.

Spec 049. The reasoning is long and lives in
`.ai/specs/049-contract-drift/spec.md`; this docstring says only what a reader
needs in order to run the rule or change it.

The shape of the problem, in one measurement:

    openapi.json publishes 30 enums
    24 of them have a hand-written mirror somewhere under frontend/src
    all 24 match exactly today
    and nothing turns red when that stops being true

That last line is the whole finding. `styleguide.test.ts:1146-1173` already
names the shape: "one concept, one home" fails as *not a bug, only someone
having spelled the same thing a third time*.

Four decisions that are not obvious, and are therefore written down.

1. **The source of truth is `openapi.json`, built here rather than read from a
   running server.** A gate that needs a service up is a gate people skip.
   `openapi.json` is not checked in, so this constructs the app and asks it for
   the schema -- the same thing `tests/unit/test_static_checks.py` does. If the
   app cannot be constructed the rule **skips**, because a broken environment is
   not evidence of drift and a rule that reports it as drift trains people to
   ignore the rule.

2. **`ErrorCode` is out of scope.** It is a 96-value enum, it is *meant* to be
   written out in the frontend's error handling, and `S-05 check-error-codes`
   already governs it. Two rules over one thing means one of them is permanently
   red, and this repository's own judgement is that a permanently red gate trains
   everyone to ignore the summary.

3. **The frontend walk comes from `checks/frontend.py`, not from here.** The
   first version did its own traversal against a `ctx.frontend` attribute that
   does not exist and crashed. The crash was the smaller problem: `S-07/08/09`
   already depend on the framework's answer to "what is a frontend source", so a
   second traversal means two places decide that -- which is the two-homes
   failure this rule exists to catch, committed by the rule that catches it.

4. **It reports both directions**, because both are drift and they fail
   differently:

       backend has it, frontend does not -> the value arrives and falls through
                                             a `switch` default, silently
       frontend has it, backend does not -> the client waits for a value that
                                             can never arrive, and that branch
                                             is dead code which looks correct
"""

from __future__ import annotations

import re
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from checks import frontend as frontend_sources
from checks.framework import CheckMeta, CheckResult, ScanContext, format_target

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

CODE = "CHECK_ENUM_DRIFT"

META = CheckMeta(
    check_id="S-16",
    slug="no-enum-drift",
    title="the frontend's hand-written enums match the backend's published ones",
    priority="P1",
    code=CODE,
)

#: Owned by `S-05 check-error-codes`, which is about registration rather than
#: drift. Named here rather than filtered by size, because "it is big" is a bad
#: reason and a reason that will be re-argued in six months.
OUT_OF_SCOPE = ("ErrorCode",)

#: Unions with no backend counterpart. Each entry is a pair of the concept and
#: the reason it exists, because a reason of "not applicable" is a sentence
#: nobody can argue with -- and this file is read in six months by someone who
#: needs to disagree with it.
FRONTEND_ONLY: dict[str, str] = {
    "IconSize": "the three sizes the icon registry may render at; a glyph is not on the wire",
    "Pane": "whether an indicator is drawn over the chart or in its own pane; a rendering decision",
    "RouteName": (
        "the five entries of ROUTES; a navigation concept, and the server deliberately "
        "sends no URLs"
    ),
    "TimelineTone": (
        "RecordTimeline's own two tones; the timeline renders events, not a backend enum"
    ),
    "Tone": (
        "the up/down/flat convention format.ts applies to a number; direction is "
        "derived, never sent"
    ),
    "View": "the five filters of the knowledge page; a UI-only grouping",
}

#: ⭐⭐ **Backend vocabularies the client deliberately does not mirror.**
#:
#: These are **not** frontend concepts — they are real server enums the client has no
#: reason to hold, and they are kept apart from `FRONTEND_ONLY` because the two want
#: opposite liveness checks:
#:
#: | | 「is it still declared?」 means |
#: |---|---|
#: | `FRONTEND_ONLY` | is the frontend **union** still there? if not, the waiver is dead |
#: | `NOT_MIRRORED` | is the backend **enum** still published? if not, the waiver is dead |
#:
#: ⭐ **The first version put all eleven in one dict**, and the run reported six
#: `is exempted but is no longer declared` errors — because a frontend union can never
#: be found for a backend enum that the frontend deliberately does not hold. The rule
#: was not wrong about anything; **its own data model was**, and it said so loudly
#: enough that the shape was obvious from the output.
#:
#: Naming an absence is what keeps this rule honest: **an unnamed absence is
#: indistinguishable from a forgotten mirror**, and those two need different answers.
NOT_MIRRORED: dict[str, str] = {
    "AssetType": (
        "the client never branches on it; every instrument renders the same way and "
        "`InstrumentPage` shows `display` rather than the asset type. A union the code "
        "does not read is a union that can drift without anyone noticing"
    ),
    "AttentionKind": (
        "one value today (`kill_criterion_due`), and `api.ts` compares against that one "
        "literal rather than holding a union. **If the backend adds a second kind this "
        "stops being exempt automatically**, because it stops being single-valued — "
        "which is exactly what an exemption should do"
    ),
    "CapabilityState": (
        "`GET /capabilities` has no UI at all (recorded as B4 in the 2026-10-02 plan). "
        "Mirroring a three-state vocabulary the client cannot read would be a union that "
        "drifts in silence"
    ),
    "Dataset": (
        "provider-side routing vocabulary (`providers/router.py`); it decides which "
        "source to call and never crosses to a client"
    ),
    "Market": (
        "the client holds `format.ts`'s `Record<string, string>` label map rather than a "
        "union, and `displayCode()` composes the two parts itself — so a union would be a "
        "second home for the same three values"
    ),
    "WatchlistEventKind": (
        "likewise a label map: `timelineAdapters.tsx` holds the one home for the three "
        "kinds. The append-only log is the authority, not a client-side union"
    ),
}

#: Values equal to a backend enum while meaning something else. Same values, and
#: conflating them is exactly the mistake worth writing a name down for.
SAME_VALUES_DIFFERENT_MEANING: dict[str, str] = {
    "QueueName": (
        "the values match DueCount.Queue, but that is the *field* the server sends while "
        "this is the *logical queue* the frontend routes on; api.ts owns it because it is "
        "the leaf of the import graph (it imports nothing), and routing.ts maps it to a "
        "URL rather than re-declaring it. ⚠️ **The spec said routing.ts, and measuring the "
        "import graph said otherwise** — the plan's direction would have made api.ts "
        "import routing.ts, which is a cycle"
    ),
}

#: `type X = 'a' | 'b'`, with or without `export` / `declare`.
#:
#: ⭐⭐ **Multi-line unions are the common case in this codebase, not the edge case.**
#: `api.ts:533` writes `MetricState` one value per line, so the first version of this
#: pattern — single-line, anchored on `$` — did not see it, and the rule reported
#: `CriterionVerdict` as having no mirror while the mirror sat right there under another
#: name. **A drift detector that reports clean on the exact thing it exists to catch is
#: worse than no detector, because it is trusted.**
#:
#: So the body is `[^;]*?` — anything but a semicolon — closed by one of three things: a
#: `;`, a newline **not** followed by `|`, or the end of the file. The middle arm is what
#: lets a continuation line join the body; without it a multi-line union stops at its
#: own first newline.
#:
#: ⭐ And it is probed rather than trusted: `tests/unit/test_static_checks.py` runs it
#: against ten shapes, **two of which it must not match** (`type X = SomethingElse` and
#: an `interface`).
UNION = re.compile(
    r"^[ \t]*(?:export\s+)?(?:declare\s+)?type\s+(\w+)\s*=\s*"
    r"([^;]*?)(?:;|(?=\n(?![ \t]*\|))|\Z)",
    re.M,
)

#: String literals inside a union body. Deliberately not a TypeScript parser: the
#: shape being looked for has exactly one spelling in this codebase, and a rule
#: that can be defeated by reformatting is not a rule.
LITERAL = re.compile(r"'([^']*)'|\"([^\"]*)\"")

#: A reason has to say what the thing *is*. These carry no information, and the
#: first version's exemption table would have been four of them.
EMPTY_REASONS = frozenset(
    {"", "-", "n/a", "na", "not applicable", "none", "tbd", "不适用", "无", "不涉及"}
)


def _sources(ctx: ScanContext) -> list[tuple[str, str]]:
    """Every non-test frontend source, as `(relative path, text)`.

    ⚠️ **Kept because the rule's own tests use it**; `run` inlines the same walk so it
    can hand the paths to `result.files` without walking twice. Two calls, one walk:
    a helper that is only used by tests is a helper nobody reads twice.

    Test files are excluded, and that is a decision rather than an oversight: a
    union written in a test is the test's own fixture vocabulary, and counting
    those would let a test file satisfy a production requirement.
    """
    # ⚠️ has_sources, not skip_reason: the latter always returns a string, so
    # branching on it would make this helper return nothing. S-17 hit exactly that.
    if not frontend_sources.has_sources(ctx):
        return []
    root = frontend_sources.source_root(ctx)
    out: list[tuple[str, str]] = []
    for path in frontend_sources.files(ctx):
        if ".test." in path.name:
            continue
        out.append((str(path.relative_to(root)).replace("\\", "/"), path.read_text("utf-8")))
    return out


def backend_enums() -> dict[str, tuple[str, ...]]:
    """Every enum FastAPI publishes, keyed by schema name.

    A nested enum is published as a property of its parent, and is keyed
    `Parent.property`, which is the same shape `openapi.json` uses for a `$ref`.
    """
    from fastapi.testclient import TestClient

    from alphacouncil.api.app import create_app
    from alphacouncil.core.config import Settings

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(database_path=Path(tmp) / "schema-only.db")
        with TestClient(create_app(settings)) as client:
            spec = client.get("/openapi.json").json()

    found: dict[str, tuple[str, ...]] = {}
    for schema_name, schema in spec.get("components", {}).get("schemas", {}).items():
        if not isinstance(schema, dict):
            continue
        if isinstance(schema.get("enum"), list):
            found[schema_name] = tuple(schema["enum"])
        for prop_name, prop in (schema.get("properties") or {}).items():
            if isinstance(prop, dict) and isinstance(prop.get("enum"), list):
                found[f"{schema_name}.{prop_name}"] = tuple(prop["enum"])
    return found


def _without_comment_lines(text: str) -> str:
    """Drop whole-line comments, leaving string literals intact.

    ⭐⭐ **A union with a comment inside it used to parse as truncated**, which made
    `S-16` report a matching union as absent — a finding that reads like a code defect and is
    about the scanner. The body pattern closes on 「a newline not followed by `|`」, and a
    `//` line satisfies that, so everything after the first comment was invisible.

    ⚠️ **Whole-line comments, and that turns out to be enough.** A *trailing*
    # comment on a value’s own line (| 'a' // why) does not truncate the body either,
    # because the literals are read out of the quoted text rather than by splitting on
    # |. An earlier version of this docstring claimed the opposite and the claim was
    # wrong; 	est_a_trailing_comment_is_not_a_hazard exists so it cannot come back.

    ⚠️ String state is tracked because `//` inside a string is not a comment and a naive
    stripper would delete the rest of the line — turning a passing file into one that looks
    clean because it was truncated (`0003`).
    """
    out: list[str] = []
    quote: str | None = None
    for line in text.splitlines():
        stripped = line.strip()

        # ⭐⭐ **The prefix test comes first, and that ordering is the whole fix.**
        # A line that opens with `//` or `#` is a comment, and nothing inside a comment can
        # change the scanner's state — a backtick in prose is a backtick, not a delimiter.
        # Testing it after the string scan is what made this miss: a comment containing
        # backticks left `quote` set, and from there every line counted as inside a string
        # (`0025`).
        if stripped.startswith(("//", "#")):
            # ⭐ **Dropped, not blanked.** Blanking leaves an empty line, and the union
            # pattern closes on 「a newline not followed by `|`」 — so a *blank* line
            # truncates the body exactly as a comment does. ⭐ That is why the first version
            # of this helper looked like it worked and did not: it was only ever exercised
            # after the comment had been moved out of the union by hand, so the fix itself
            # was never tested. `regressions/0025`.
            continue

        j = 0
        while j < len(line):
            char = line[j]
            if quote is not None:
                if char == "\\":
                    j += 2
                    continue
                if char == quote:
                    quote = None
            elif char in "'\"`":
                quote = char
            j += 1
        out.append(line)
    return "\n".join(out)


def frontend_unions(
    sources: Iterable[tuple[str, str]],
) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """Every `type X = 'a' | 'b'` as `X -> [(file, values)]`.

    A union with fewer than two literals is skipped, because a one-value union is
    indistinguishable from a plain alias and there is nothing to compare.
    """
    found: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for rel, text in sources:
        for match in UNION.finditer(_without_comment_lines(text)):
            values = tuple(
                value
                for literal in LITERAL.finditer(match.group(2))
                for value in literal.groups()
                if value is not None
            )
            if len(values) < 2:
                continue
            found.setdefault(match.group(1), []).append((rel, values))
    return found


def _reason_is_real(reason: str) -> bool:
    return reason.strip().lower() not in EMPTY_REASONS and len(reason.strip()) >= 16


def _site_of(unions: dict[str, list[tuple[str, tuple[str, ...]]]], values: tuple[str, ...]) -> str:
    for hits in unions.values():
        for rel, declared in hits:
            if declared == values:
                return rel
    return ""


def run(ctx: ScanContext) -> CheckResult:
    """Compare what the backend publishes against what the frontend wrote down."""
    result = CheckResult()
    root = frontend_sources.source_root(ctx)

    # ⭐ **Files, never the directory.** `apply_exemptions` reads every entry of
    # `result.files` looking for `# noqa`, so a directory here is a PermissionError —
    # raised *after* the rule had already decided it was clean, which is the worst
    # moment for it. Second crash of this rule, and the same verdict both times: a
    # check that crashes is indistinguishable from a check that passes.
    scanned = [path for path in frontend_sources.files(ctx) if ".test." not in path.name]
    result.files = scanned

    if not scanned:
        result.skipped = "no frontend sources found -- nothing to compare against"
        return result
    sources = [
        (str(path.relative_to(root)).replace("\\", "/"), path.read_text("utf-8"))
        for path in scanned
    ]

    try:
        server = backend_enums()
    except Exception as exc:
        result.skipped = f"could not read the app's schema: {type(exc).__name__}: {exc}"
        return result

    published_enums = {name: values for name, values in server.items() if name not in OUT_OF_SCOPE}
    if not published_enums:
        result.skipped = "the app published no enums -- nothing to compare against"
        return result

    unions = frontend_unions(sources)

    # Indexed by value-set rather than by name, because the frontend has renamed a
    # mirror before: the backend calls it CriterionVerdict and `api.ts` calls it
    # MetricState. Matching by name would report that as drift forever.
    by_values: dict[tuple[str, ...], list[str]] = {}
    for union_name, hits in unions.items():
        for _rel, values in hits:
            by_values.setdefault(tuple(sorted(values)), []).append(union_name)

    waived = {*FRONTEND_ONLY, *NOT_MIRRORED, *SAME_VALUES_DIFFERENT_MEANING}
    seen_values: set[tuple[str, ...]] = set()

    for schema_name, values in sorted(published_enums.items()):
        key = tuple(sorted(values))
        if by_values.get(key):
            seen_values.add(key)
            continue
        # A strict subset is drift in the dangerous direction: the value the
        # server will send has nowhere to land.
        superset = next(
            (
                other
                for other, other_values in published_enums.items()
                if values and set(values) < set(other_values)
            ),
            None,
        )
        if superset is not None:
            missing = sorted(set(published_enums[superset]) - set(values))
            where = _site_of(unions, values)
            result.error(
                CODE,
                f"the frontend's union for `{superset}` is missing {missing}",
                target=format_target(ctx, root / where) if where else format_target(ctx, root),
                fix=f"Add {missing}, or exempt the union with a reason that says why the "
                f"client never sees `{superset}`.",
            )
            seen_values.add(key)
            continue
        if key in by_values:
            continue
        # ⭐ **The three waivers match by three different keys, and that is not
        # inelegance — it is the difference between them.**
        #
        #   NOT_MIRRORED                by NAME, against the published enum. It says
        #                               「this server enum has no client mirror」, and
        #                               there is by definition no union to match against.
        #   FRONTEND_ONLY               by VALUE-SET, against the frontend unions.
        #   SAME_VALUES_DIFFERENT_MEANING by NAME, against the frontend unions.
        #
        # The first version matched all three by value-set against `unions`, which is
        # why all six `NOT_MIRRORED` entries were reported as drift on a clean tree:
        # **a waiver that cannot match anything is not a waiver.**
        if schema_name in NOT_MIRRORED:
            continue
        if _waived_union_holds(values, {*FRONTEND_ONLY, *SAME_VALUES_DIFFERENT_MEANING}, unions):
            continue
        result.error(
            CODE,
            f"`{schema_name}` = {list(values)} has no matching union in frontend/src",
            target=format_target(ctx, root),
            fix="Add a union with exactly these values, or list it in NOT_MIRRORED / "
            "FRONTEND_ONLY with a reason that says what the concept is. Spec 049 §2.3.",
        )

    # The reverse direction. `seen_values` is skipped so a union already reported
    # as a subset is not also reported as holding values the backend lacks -- one
    # defect, one finding.
    everything_published = {value for values in published_enums.values() for value in values}
    for union_name, hits in sorted(unions.items()):
        for rel, values in hits:
            if union_name in waived:
                continue
            if tuple(sorted(values)) in seen_values:
                continue
            extra = sorted(set(values) - everything_published)
            if extra:
                result.error(
                    CODE,
                    f"`{union_name}` in {rel} holds values the backend never publishes: {extra}",
                    target=format_target(ctx, root / rel),
                    fix="Either the client is waiting for a value that cannot arrive (a "
                    "dead branch), or the union belongs in FRONTEND_ONLY with a reason.",
                )

    for name, reason in sorted(FRONTEND_ONLY.items()):
        if name not in unions:
            result.error(
                CODE,
                f"`{name}` is exempted from S-16 but is no longer declared in frontend/src",
                target=format_target(ctx, root),
                fix="Delete the exemption. An exemption for a type that does not exist is "
                "a hole with a comment on it, and the next reader cannot tell it from a rule.",
            )
        elif not _reason_is_real(reason):
            result.error(
                CODE,
                f"the exemption for `{name}` carries no reason",
                target=format_target(ctx, Path(__file__)),
                fix="Say what the concept *is*. A reason nobody can argue with is not a "
                "reason, and this file is read in six months by someone who needs to.",
            )

    # ⭐ **Two liveness checks, and keeping them apart is the whole point of the split.**
    # A frontend concept's waiver dies when its *union* disappears; a backend enum's
    # waiver dies when the *enum* stops being published. One dict and one check cannot
    # say both, and the run said so by reporting six `no longer declared` errors for
    # enums that had never been frontend unions at all.
    for name, reason in sorted(NOT_MIRRORED.items()):
        if name not in published_enums:
            result.error(
                CODE,
                f"`{name}` is listed in NOT_MIRRORED but the app no longer publishes it",
                target=format_target(ctx, Path(__file__)),
                fix="Delete the entry, or say why the client still does not mirror it. An "
                "exemption for an enum that no longer exists is a hole with a comment on it.",
            )
        elif not _reason_is_real(reason):
            result.error(
                CODE,
                f"the NOT_MIRRORED entry for `{name}` carries no reason",
                target=format_target(ctx, Path(__file__)),
                fix="Say what the concept *is*. A reason nobody can argue with is not a "
                "reason, and this file is read in six months by someone who needs to.",
            )

    for name in sorted(SAME_VALUES_DIFFERENT_MEANING):
        if name not in unions:
            result.error(
                CODE,
                f"`{name}` is listed in SAME_VALUES_DIFFERENT_MEANING but is not declared",
                target=format_target(ctx, root),
                fix="Delete the entry; it describes a union that no longer exists.",
            )

    return result


def _waived_union_holds(
    values: tuple[str, ...],
    waived: set[str],
    unions: dict[str, list[tuple[str, tuple[str, ...]]]],
) -> bool:
    """Whether some exempted frontend union holds exactly these values.

    ⭐ **A waiver is about *pairing*, never about drift.** A frontend-only union whose
    values change is still compared against the backend, because the alternative is a
    hole that widens silently — and this repository has now met that shape four times
    (0012, 0018, 0019, 0020).

    ⚠️ `NOT_MIRRORED` is deliberately **not** consulted here. It is matched by name
    in `run`, because it makes a claim about a server enum that has no union to find.
    """
    key = tuple(sorted(values))
    return any(
        tuple(sorted(declared)) == key
        for name, hits in unions.items()
        if name in waived
        for _rel, declared in hits
    )
