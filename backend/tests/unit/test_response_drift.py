r"""The parser, and the decision `run()` makes — both tested, which S-16 and S-17 are not.

## Why this file exists at all

⚠️ **Measured 2026-10-04: `tests/unit/test_enum_drift.py` and `tests/unit/test_route_drift.py`
between them have 22 tests and not one of them calls `run()`.** ⭐ Nine tests of a scanner
and none of the decision, ⭐ while `no_enum_drift.py:185-187` claimed a probe that did not
exist. ⭐ Spec 053's `AC-6` is this file.

## The parser tests that matter, and the three bugs they pin

Three defects got into the parser while this rule was being written, ⭐ and **every one of
them was invisible on this checkout** ⭐ — which is why each has a test that constructs the
shape directly rather than trusting a green run.

**1. A member counted only when the *line*'s brace balance was zero.**
⭐ `due: {` is both a declaration and an opening brace, ⭐ so `due` was dropped and its
children were hoisted to the top level.
⭐ *Invisible because:* the probe reported `Today` as missing a field that
`TodayPage.tsx:91` reads — ⭐ **`tsc` being green is what proved the probe wrong, not the
client.**

**2. `DECLARATION` could not match `type X = {` at all.**
⭐ `[=\s]\{` asks for a character a greedy `\s*` has already eaten.
⭐ *Invisible because:* 76 declarations on this checkout, **all multi-line** — the
broken regex and the fixed one both see the same 71 types.

**3. Members were read line by line, so a one-line body yielded nothing.**
⭐ `interface T { a: string; b: number }` → zero fields.
⭐ *Invisible because:* ⭐ **zero single-line declarations exist in `frontend/src`.**

⭐ Bug 3 is the one that matters for the long run: ⭐ `no_enum_drift.py:194-196` states the
standard this rule is held to — 「a rule that can be defeated by reformatting is not a rule」
⭐ — ⭐ and a scanner that reads lines is defeated by a formatting choice.

## What `run()` is tested against

⭐ A fake `wire_schemas`, not the real app. ⭐ The real one constructs FastAPI and migrates
a database, ⭐ which makes a unit test slow and couples this file to the route table. ⭐ What
is under test here is the **decision** ⭐ — which bucket, which message, which waiver
complaint ⭐ — and the real schema surface is covered by `test_the_real_tree_is_green` below
plus `test_static_checks.py` running the rule for real.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from checks import frontend as frontend_sources
from checks.framework import CheckResult
from checks.rules import no_response_drift as rule
from checks.scan import ScanContext

pytestmark = pytest.mark.unit


def _fields(source: str, name: str = "T") -> frozenset[str]:
    """The top-level members of one named client type."""
    return rule.client_types([("api.ts", source)])[name][1]


def _all_names(source: str) -> set[str]:
    return set(rule.client_types([("api.ts", source)]))


# ------------------------------------------------------------------ the parser


class TestTheMemberIsFoundWhereItsNameIs:
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param(
                "export interface T { due: { cards: A }; other: string }",
                id="one-line",
            ),
            pytest.param(
                "export interface T {\n  due: {\n    cards: A\n  }\n  other: string\n}",
                id="two-line",
            ),
            pytest.param(
                "export interface T {\n        due: {\n                cards: A\n        }\n"
                "        other: string\n}",
                id="reindented",
            ),
            pytest.param(
                "export interface T {\n"
                "  // a comment between the members\n"
                "  due: {\n    cards: A\n  }\n\n  other: string\n}",
                id="comment-and-blank-line",
            ),
            pytest.param(
                "export interface T {\n  due: {\n    cards: A\n    deep: { x: B }\n  }\n"
                "  other: string\n}",
                id="two-levels-of-nesting",
            ),
        ],
    )
    def test_the_same_member_survives_five_spellings(self, source: str) -> None:
        """⭐ **`due` is declared and `cards` is nested inside it** ⭐ — so the answer is
        ``{'due', 'other'}`` in all five cases, ⭐ and neither `cards` nor `x` may appear.

        ⭐⭐ This is `AC-5`, and the five spellings are the point: ⭐ the bug this pins was
        invisible on a clean tree, ⭐ so the only way to hold it is to **write the shape**
        rather than to run the rule and read the summary.
        """
        assert _fields(source) == frozenset({"due", "other"}), (
            "nested members must not be hoisted to the top level"
        )


class TestTheDeclarationIsFoundInEverySpelling:
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("export interface T {\n  a: string\n}", id="export-interface"),
            pytest.param("interface T {\n  a: string\n}", id="bare-interface"),
            pytest.param("declare interface T {\n  a: string\n}", id="declare-interface"),
            pytest.param("export type T = {\n  a: string\n}", id="export-type-equals"),
            pytest.param("type T = {\n  a: string\n}", id="bare-type-equals"),
        ],
    )
    def test_five_spellings_of_a_declaration(self, source: str) -> None:
        r"""⭐⭐ **`type X = {` is the one that was broken** ⭐ — `[=\s]\{` asks for a character
        a greedy `\\s*` has already eaten. ⭐ Zero such declarations exist in
        `frontend/src` today, ⭐ which is exactly why it survived being written.
        """
        assert _fields(source) == frozenset({"a"})

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            pytest.param("type Handler = (x: string) => void", set(), id="function-type"),
            pytest.param(
                "type ViewName = Exclude<Route['name'], 'instrument'>", set(), id="exclude-union"
            ),
            pytest.param("type Mode = 'a'", set(), id="one-value-union"),
            pytest.param("type Pair = A & B", set(), id="intersection"),
        ],
    )
    def test_four_shapes_that_are_not_object_declarations(
        self, source: str, expected: set[str]
    ) -> None:
        """⭐ The adversarial set. ⭐ A rule that claims to read client types has to say what
        it refuses to read, ⭐ and these four are the ones that would silently widen a
        field set if it accepted them."""
        assert _all_names(source) == expected


class TestWhatIsNotAField:
    def test_a_method_is_not_a_wire_field(self) -> None:
        r"""**The colon is what excludes it**, ⭐ not the character class: `render` is
        followed by `(`, so `\\s*:` cannot match. ⭐ A wire field has a name and a colon and
        nothing else ⭐ — and a comment in the rule once credited the wrong mechanism."""
        source = "export interface T {\n  a: string\n  render(): void\n  b: number\n}"
        assert _fields(source) == frozenset({"a", "b"})

    def test_an_index_signature_is_not_a_named_member(self) -> None:
        """⭐ The wire has named fields. ⭐ A bag that accepts anything cannot be reconciled
        with any schema, ⭐ and accepting it would make every schema match every bag."""
        source = "export interface Bag {\n  [key: string]: unknown\n  a: string\n}"
        assert _fields(source, "Bag") == frozenset({"a"})

    def test_braces_inside_a_template_literal_do_not_move_the_depth(self) -> None:
        """⭐ The mirror image of the hoisting bug ⭐ — one `${x}` would push the depth up
        and **every member after it would vanish silently**."""
        source = "export interface T {\n  a: string\n  b: `${x}`\n  c: number\n}"
        assert _fields(source) == frozenset({"a", "b", "c"})

    def test_an_optional_marker_is_not_part_of_the_name(self) -> None:
        """⭐ `b?` and `b` are the same field on the wire. ⭐ The `?` is the client's claim
        about nullability, ⭐ and folding it into the name would make every optional field
        look like drift."""
        source = "export type T = {\n  a: string\n  b?: number\n}"
        assert _fields(source) == frozenset({"a", "b"})

    def test_a_readonly_modifier_is_not_part_of_the_name(self) -> None:
        source = "export interface T {\n  readonly a: string\n  b: number\n}"
        assert _fields(source) == frozenset({"a", "b"})

    def test_two_declarations_of_one_name_are_unioned_not_overwritten(self) -> None:
        """⭐ Otherwise the scanner quietly picks a winner ⭐ and calls it a mirror."""
        found = rule.client_types(
            [
                ("a.ts", "export interface T {\n  a: string\n}"),
                ("b.ts", "export interface T {\n  b: string\n}"),
            ]
        )
        assert found["T"][1] == frozenset({"a", "b"}), "a second home must widen, not replace"

    def test_a_declaration_with_no_members_is_not_recorded(self) -> None:
        """⭐ An empty interface has no field set, ⭐ so it cannot be a mirror of anything
        ⭐ — and recording it as an empty set would let it satisfy an empty schema."""
        assert _all_names("export interface T {\n}") == set()


# ------------------------------------------------------------------ the decision


def _only(
    monkeypatch: pytest.MonkeyPatch,
    schemas: dict[str, frozenset[str]],
    waivers: dict[str, str] | None = None,
) -> None:
    """Pin both halves of what `run()` reads.

    ⭐ The waiver table has to be emptied too, and forgetting that is instructive: ⭐ with a
    one-schema wire and the real twelve waivers, every waiver correctly reads as stale ⭐ —
    ⭐ which is the rule working, on the wrong subject. ⭐ Hence the explicit parameter
    instead of a blanket wipe.
    """
    monkeypatch.setattr(rule, "wire_schemas", lambda: schemas)
    monkeypatch.setattr(rule, "NOT_MIRRORED", waivers if waivers is not None else {})


def _repo(tmp_path: Path, api_ts: str) -> ScanContext:
    src = tmp_path / "frontend" / "src"
    src.mkdir(parents=True)
    (src / "api.ts").write_text(api_ts, encoding="utf-8")
    return ScanContext(repo_root=tmp_path)


FOUR = "export interface T { a: string; b: string; c: string; d: string }"
FIVE = frozenset({"a", "b", "c", "d", "e"})


def _errors(result: CheckResult) -> list[str]:
    return [i.message for i in result.issues if i.severity.value == "error"]


def _fixes(result: CheckResult) -> list[str]:
    return [i.fix or "" for i in result.issues if i.severity.value == "error"]


def _notes(result: CheckResult) -> list[str]:
    return [i.message for i in result.issues if i.severity.value == "info"]


class TestTheDecision:
    def test_a_field_nobody_declared_is_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ **The regression, in one assertion** ⭐ — and it is the shape that shipped
        green on 2026-10-04: ⭐ four of the server's fields are declared, ⭐ the fifth is
        not, ⭐ and nothing anywhere said so."""
        _only(monkeypatch, {"ThingRead": FIVE})
        result = rule.run(_repo(tmp_path, FOUR))
        (message,) = _errors(result)
        assert "`ThingRead`" in message
        assert "'e'" in message, "the missing field must be named, not just counted"

    def test_the_fix_says_which_file_and_which_type(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ 「同步一下」 is not a repair instruction. ⭐ A finding that cannot be acted on
        is a complaint, ⭐ and this is the difference between the two."""
        _only(monkeypatch, {"ThingRead": FIVE})
        result = rule.run(_repo(tmp_path, FOUR))
        (fix,) = _fixes(result)
        assert "`T`" in fix and "api.ts" in fix

    def test_being_declared_twice_is_a_note_not_a_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Ambiguity has to be said out loud ⭐ — a correspondence that resolves to two
        candidates is a coincidence, ⭐ and reading it as a mirror is how a hole survives."""
        _only(monkeypatch, {"ThingRead": frozenset({"a", "b"})})
        source = "export interface One { a: string; b: string }\n"
        source += "export interface Two { a: string; b: string }"
        result = rule.run(_repo(tmp_path, source))
        assert _errors(result) == []
        (note,) = _notes(result)
        assert "ambiguous" in note and "One" in note and "Two" in note

    def test_a_fastapi_envelope_is_not_the_products_business(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ `ValidationError` is FastAPI's error body and `DataResult_*` is its generic
        wrapper. ⭐ Neither has a client type, ⭐ and requiring one would mean declaring
        the framework's shapes ⭐ — which is the opposite of this rule's purpose."""
        _only(monkeypatch, {"ValidationError": frozenset({"loc", "msg"})})
        result = rule.run(_repo(tmp_path, FOUR))
        assert _errors(result) == [] and _notes(result) == []


class TestTheWaiverTable:
    def test_a_waived_schema_is_not_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _only(monkeypatch, {"TagWrite": frozenset({"tag"})}, {"TagWrite": "a real reason here"})
        result = rule.run(_repo(tmp_path, FOUR))
        assert _errors(result) == [], f"{_errors(result)}"

    def test_a_waiver_that_names_a_gone_schema_is_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ S-16 learned this the expensive way ⭐ — all six of its waivers were reported as
        drift on a clean tree because the first version matched them wrongly ⭐
        (`no_enum_drift.py:430-432`). ⭐ **A waiver that cannot match is not a waiver.**"""
        monkeypatch.setattr(rule, "wire_schemas", lambda: {"TagWrite": frozenset({"tag"})})
        monkeypatch.setattr(rule, "NOT_MIRRORED", dict(rule.NOT_MIRRORED))
        gone = "a shape that no longer exists here at all"
        monkeypatch.setattr(rule, "NOT_MIRRORED", {**rule.NOT_MIRRORED, "GoneRead": gone})
        result = rule.run(_repo(tmp_path, FOUR))
        assert any("`GoneRead`" in m for m in _errors(result))

    def test_a_waiver_without_a_reason_is_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ 「不适用」 is a sentence nobody can argue with ⭐ — ⭐ and this file is read in
        six months by someone who needs to disagree with it."""
        monkeypatch.setattr(rule, "wire_schemas", lambda: {"TagWrite": frozenset({"tag"})})
        monkeypatch.setattr(rule, "NOT_MIRRORED", {"TagWrite": "n/a"})
        result = rule.run(_repo(tmp_path, FOUR))
        assert any("carries no reason" in m for m in _errors(result))

    def test_a_waiver_over_something_already_green_is_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐⭐ **This is the tightening that replaced the threshold the rule used to
        have.** ⭐ A waiver whose schema *is* mirrored is not a waiver ⭐ — it is a green
        result somebody wanted hidden, ⭐ and it is the shape a waiver table grows into
        when nobody reads it. ⭐ Measured on the first draft: a field-count floor cut the
        findings from 12 to 4, ⭐ ⭐ and a constant chosen because it makes the number
        smaller is a constant tuned to a fixture."""
        monkeypatch.setattr(rule, "wire_schemas", lambda: {"TagWrite": frozenset({"tag"})})
        monkeypatch.setattr(rule, "NOT_MIRRORED", dict(rule.NOT_MIRRORED))
        mirrored = "export interface TagWrite { tag: string; extra: string }"
        result = rule.run(_repo(tmp_path, mirrored))
        assert any("hiding a green result" in m for m in _errors(result))

    def test_every_waiver_on_the_real_table_has_a_reason(self) -> None:
        """⭐ The table is asserted as a whole, ⭐ because ⭐ **the failure this rule exists
        to prevent is a table that grew without anyone reading it.** ⭐ `run()` cannot
        check this — with an empty wire every entry reads as stale — so the property is
        asserted on the table itself, ⭐ and `test_a_waiver_without_a_reason_is_an_error`
        holds the `run()` half."""
        bad = [
            name
            for name, reason in rule.NOT_MIRRORED.items()
            if not rule._reason_is_real(reason)
        ]
        assert bad == [], f"waivers with no reason: {bad}"

    def test_no_waiver_names_an_envelope(self) -> None:
        """⭐ A waiver for something the rule already skips is a dead entry ⭐ — ⭐ and
        `no_enum_drift.py:430-432` records what a table of those does: ⭐ it reported six
        waivers as drift on a clean tree."""
        overlapped = [n for n in rule.NOT_MIRRORED if rule.ENVELOPE.match(n)]
        assert overlapped == [], f"waived envelopes: {overlapped}"


class TestTheRuleRefusesToPretend:
    def test_no_frontend_sources_is_a_skip_not_a_pass(self, tmp_path: Path) -> None:
        """⭐ `dev.py:288-292` — ⭐ 「a skipped gate is not a passing gate」 ⭐ — ⭐ and this is
        the same distinction one level down, inside one rule."""
        result = rule.run(ScanContext(repo_root=tmp_path))
        assert result.skipped, "a rule with nothing to scan must say so"
        assert result.issues == []

    def test_an_unbuildable_app_is_a_skip_not_a_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ S-16 and S-17 guard the same way ⭐ — ⭐ a rule that cannot read the codebase
        cannot testify about it, ⭐ and the first version of this one crashed instead ⭐
        which the runner reported as `CHECK_RUNNER_ERROR` ⭐ — ⭐ correctly, ⭐ and then the
        two bugs it had were worth reading."""
        monkeypatch.setattr(rule, "wire_schemas", lambda: None)
        result = rule.run(_repo(tmp_path, FOUR))
        assert result.skipped
        assert result.issues == []

    def test_the_real_tree_is_green(self) -> None:
        """⭐ **And the assertion nobody can fake: on this checkout, zero errors.** ⭐ The
        `info` findings are the ambiguity notes, ⭐ and their existence is the point ⭐ —
        they are the cases where a green result is a coincidence, ⭐ written down."""
        root = Path(__file__).resolve().parents[3]
        if not frontend_sources.has_sources(ScanContext(repo_root=root)):
            pytest.skip("no frontend sources in this checkout")
        result = rule.run(ScanContext(repo_root=root))
        assert result.skipped is None
        assert result.scanned > 0
        assert _errors(result) == [], f"the real tree must be green: {_errors(result)}"
