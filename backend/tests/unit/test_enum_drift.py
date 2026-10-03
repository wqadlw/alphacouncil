"""`S-16`'s scanner, tested — because twice now it was wrong and neither time was tested.

The rule had **no unit test file at all**, and that absence is why two defects reached
`main`: a union with a comment inside it parsed as truncated (`0023`), and a comment containing
a backtick defeated the fix for the first (`0025`).

⭐ **Both were only ever exercised by accident.** In each case the finding came from running the
gate against a file I happened to be editing — and in each case the *fix* was verified by the
finding disappearing, not by a test of the fix. ⭐ **「the symptom is gone」 and 「the cause is
handled」 are different claims, and only the second survives the next shape.**
"""

from pathlib import Path

import pytest
from checks.rules.no_enum_drift import UNION, _without_comment_lines, frontend_unions

pytestmark = pytest.mark.unit

# parents[2] is ackend; one more level up is the repository root.
FRONTEND = Path(__file__).resolve().parents[2].parent / "frontend" / "src" / "api.ts"


def values(source: str) -> list[str]:
    """The literal values of the first union in ``source``, after comment removal."""
    stripped = _without_comment_lines(source)
    match = next(UNION.finditer(stripped), None)
    assert match is not None, f"no union was found in:\n{source}"
    body = match.group(2)
    return [
        literal
        for literal in (part.split(chr(39))[1] for part in body.split("|") if chr(39) in part)
        if literal
    ]


class TestTheScannerLearnedTwoShapes:
    def test_a_plain_union(self) -> None:
        assert values("export type S =\n  | 'a'\n  | 'b'\n") == ["a", "b"]

    def test_a_comment_block_inside_the_union(self) -> None:
        """`0023`: the comment used to end the body, so the values after it vanished."""
        assert values(
            "export type S =\n  | 'a'\n  // why 'b' exists\n  | 'b'\n"
        ) == ["a", "b"]

    def test_a_comment_containing_a_backtick(self) -> None:
        """⭐ `0025`: the shape that defeated the *fix* for the shape above.

        The first version tracked quote state across lines, so a backtick inside prose put the
        scanner 「inside a string」 and it never came out — after which **no** later comment was
        stripped. And this comment is the kind a person writes: the value named in backticks.
        """
        assert values(
            "export type S =\n  | 'a'\n  // `b` is here because `a` is not enough\n  | 'b'\n"
        ) == ["a", "b"]

    def test_two_comment_blocks_and_a_multi_byte_comment(self) -> None:
        assert values(
            "export type S =\n"
            "  // first\n"
            "  | 'a'\n"
            "  // \u2b50\u2b50 second, with an em-dash and \u300cquotes\u300d\n"
            "  | 'b'\n"
            "  // third\n"
            "  | 'c'\n"
        ) == ["a", "b", "c"]


class TestWhyCommentsAreDroppedRatherThanBlanked:
    """⭐ The mechanism, so the next reader does not 「simplify」 it back into a blank line."""

    def test_a_blank_line_inside_a_union_truncates_it(self) -> None:
        """So blanking a comment to `""` would have kept the original bug alive."""
        match = next(UNION.finditer("export type S =\n  | 'a'\n\n  | 'b'\n"), None)
        assert match is not None
        assert "'b'" not in match.group(0), (
            "a blank line no longer truncates, so dropping comments is no longer necessary"
        )

    def test_dropping_a_comment_joins_its_neighbours(self) -> None:
        lines = ["export type S =", "  | 'a'", "  // note", "  | 'b'"]
        assert _without_comment_lines("\n".join(lines)).splitlines() == [
            "export type S =",
            "  | 'a'",
            "  | 'b'",
        ]


class TestASlashInsideAStringIsNotAComment:
    """`0003`'s concern: a naive stripper eats a legitimate line."""

    def test_a_url_in_a_string_survives(self) -> None:
        stripped = _without_comment_lines(
            "export const u = 'https://example.com/api';\nexport type S =\n  | 'a'\n  | 'b'\n"
        )
        assert "https://example.com/api" in stripped
        assert values("export type S =\n  | 'a'\n  | 'b'\n") == ["a", "b"]

    def test_a_trailing_comment_is_not_a_hazard(self) -> None:
        """⚠️ The helper's docstring used to claim this *was* a hazard. It is not, and measured."""
        assert values("export type S =\n  | 'a' // trailing\n  | 'b'\n") == ["a", "b"]


class TestTheRealFrontendStillParses:
    """⭐ The rules above are about snippets; this is about the file that actually exists.

    It is the only test here that would catch a **new** shape, because it is the only one that
    reads code nobody wrote for the test.
    """

    def test_it_reads_when_the_checkout_has_one(self) -> None:
        if not FRONTEND.exists():  # pragma: no cover - a source-only install
            pytest.skip("frontend/src/api.ts is not in this checkout")

        unions = frontend_unions([("api.ts", FRONTEND.read_text(encoding="utf-8"))])

        assert "MetricState" in unions, "the frontend mirror is missing or unreadable"
        found = unions["MetricState"][0][1]
        for value in ("crossed", "not_crossed", "warming", "undetermined", "no_bars"):
            assert value in found, value
        assert "not_announced" in found
        assert "not_reported" in found
