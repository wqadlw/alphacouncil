"""Unit tests for `S-17`'s scanner, one per mistake it is known to make.

Not a copy of the mutation run. ⭐ **A mutation proves the gate bites; a unit test proves
*why*, in milliseconds, and names the mistake.** Six real defects got through this scanner
during spec 050, and every one was an off-by-one or a stale index that still produced
something shaped like a path — so a test asserting only 「the gate went red」 would not have
told anyone which one came back.

The four query shapes are lifted verbatim from the three client files, because they are the
thing most likely to change shape next and the thing a reader will most need explained.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ⚠️ **No suppression directive on these imports, and `RUF100` is what proved it.**
# The `sys.path.insert` above does push them below a statement, so a suppression looked
# correct — `E402` simply is not enabled for `tests/`. ⭐ **A suppression written
# from a rule's name rather than from its enablement is a claim, and `RUF100` is the
# thing that checks it** (`F-210`).
#
# ⚠️ And this comment had to be reworded to drop the literal directive text: ruff
# scans comments for one, so **explaining the absence of a directive in prose that
# contains one is enough to trip it**. ⭐ The tooling cannot tell 「mentioning」
# from 「using」 — which is the same lesson one level up, and it is the third time
# today a sentence written to explain a fix became the bug.
from checks.rules.no_route_drift import (
    CALL,
    PLAUSIBILITY_FLOOR,
    WRAPPER,
    path_of,
    reachable,
    read_argument,
)

#: The shape `openapi.json` publishes, which is what `reachable` compares against.
BACKEND = "/api/v1/notes/{note_id}"


# --------------------------------------------------------------- argument reading
def test_a_closer_ends_the_argument_without_belonging_to_it() -> None:
    # ⭐ `read_argument` used to return `text[begin : i + 1]`, so every single-quoted path
    # kept its quote and 20 of 46 call sites came out as `/api/v1/watchlist'`.
    text = "request<WatchlistEntry[]>('/api/v1/watchlist')"
    argument, _after = read_argument(text, text.index("(") + 1)
    assert argument == "'/api/v1/watchlist'"


def test_a_nested_template_comes_back_whole() -> None:
    # The multiline shape at `notes.ts:175`: a call inside a call inside `${}`.
    text = """request<Note>(
    `/api/v1/notes/${encodeURIComponent(id)}/links/${encodeURIComponent(
      link.to_kind,
    )}/${link.id}`,
    { method: 'DELETE' },
  )"""
    argument, _after = read_argument(text, text.index("(") + 1)
    assert argument.startswith("`/api/v1/notes/")
    assert argument.endswith("`")
    assert "link.to_kind" in argument


def test_the_second_argument_is_read_on_its_own() -> None:
    # ⭐ `method:` used to be searched 400 characters ahead, which reached into the *next*
    # call — six GETs were reported as POSTs.
    text = """request<Note[]>('/api/v1/notes/due')
export function other() {
  return request('/api/v1/notes', { method: 'POST' })
}"""
    _first, after = read_argument(text, text.index("(") + 1)
    second, _end = read_argument(text, after)
    assert "method" not in second


# ------------------------------------------------------------------- path shapes
@pytest.mark.parametrize(
    ("argument", "expected", "why"),
    [
        ("'/api/v1/notes'", "/api/v1/notes", "the plain literal case"),
        # ⚠️ `lessons.ts` writes its paths with **no leading slash**. The scanner adds one
        # rather than requiring it, because requiring it would have missed every lesson
        # endpoint on the day it was written.
        ("'api/v1/lessons'", "/api/v1/lessons", "a leading slash is added, not assumed"),
        (
            "`/api/v1/notes/${id}`",
            "/api/v1/notes/*",
            "a template segment becomes one wildcard",
        ),
        (
            "`/api/v1/decisions?limit=${limit}`",
            "/api/v1/decisions",
            "a literal `?` before the placeholder ends the path",
        ),
        (
            "`/api/v1/cards${query ? `?${query}` : ''}`",
            "/api/v1/cards",
            "a `?` nested inside a template expression ends the path",
        ),
        (
            "`/api/v1/instruments/resolve?ticker=${encodeURIComponent(t)}`",
            "/api/v1/instruments/resolve",
            "a literal `?` plus a nested call",
        ),
    ],
)
def test_the_four_query_shapes_and_the_slash_rule(argument: str, expected: str, why: str) -> None:
    assert path_of(argument, "")[0] == expected, why


def test_a_const_holding_a_query_is_followed_not_guessed() -> None:
    # ⚠️ `api.ts:1072` builds `const suffix = search.size > 0 ? `?${...}` : ''`, so the
    # placeholder contains no `?` at all. The two easy answers were both wrong: letting a
    # trailing wildcard vanish loosens every path shape, and reading the variable's *name*
    # guesses.
    source = "const suffix = search.size > 0 ? `?${search.toString()}` : ''\n"
    path, unknown = path_of("`/api/v1/instruments/${market}/${code}/daily${suffix}`", source)
    assert path == "/api/v1/instruments/*/*/daily"
    assert unknown is None


def test_a_parameter_is_a_segment_and_not_an_unknown() -> None:
    # ⚠️ The first version filed 15 of 46 call sites as 「unverifiable」 — every one of them
    # `cardId`, `id`, `limit` — because a name with no local declaration was treated as
    # unknown. A parameter is a path segment, and a bucket that fires on ordinary code is a
    # bucket that means nothing.
    path, unknown = path_of("`/api/v1/cards/${cardId}/schedule`", "")
    assert path == "/api/v1/cards/*/schedule"
    assert unknown is None


def test_a_path_built_by_a_call_is_reported_as_unknown() -> None:
    # The bucket's one legitimate use: something computed, which could be either.
    _path, unknown = path_of("`/api/v1/cards/${buildSegment()}`", "")
    assert unknown is not None


def test_a_non_literal_first_argument_is_unknown_rather_than_skipped() -> None:
    # ⚠️ A skipped call site is a blind spot, and this rule exists to remove blind spots.
    path, unknown = path_of("somePathVariable", "")
    assert path is None
    assert unknown == "somePathVariable"


# ---------------------------------------------------------------------- matching
def test_one_wildcard_matches_exactly_one_segment() -> None:
    assert reachable("/api/v1/notes/*", "/api/v1/notes/{note_id}")
    assert not reachable("/api/v1/notes/*", "/api/v1/notes/{note_id}/tags")
    # ⚠️ Not 「a trailing wildcard may vanish」 — that would have made every shape pass.
    assert not reachable("/api/v1/notes", "/api/v1/notes/{note_id}")
    assert not reachable("/api/v1/notes/*/extra", "/api/v1/notes/{note_id}")


# --------------------------------------------------------------- the two patterns
def test_the_wrapper_declaration_is_recognised_despite_the_generic() -> None:
    # ⭐ `export async function request<T>(...)` puts `<T>` between the name and the paren,
    # so an exclusion written as `function\s+request\s*$` never matched and the declaration
    # was reported as `` `? ` is called from api.ts:458 ``.
    declaration = "export async function request<T>(path: string, init?: RequestInit) {"
    assert WRAPPER.search(declaration[: declaration.index("request")])
    assert CALL.search(declaration)


def test_an_ordinary_call_is_not_mistaken_for_the_declaration() -> None:
    call = "  return request<Note[]>('/api/v1/notes')"
    assert not WRAPPER.search(call[: call.index("request")])


# ----------------------------------------------------------------- the self-check
def test_the_floor_is_a_share_not_a_count() -> None:
    # It has to survive a frontend that grows: a count would start skipping on a large
    # codebase and never trip on a small one.
    assert 0 < PLAUSIBILITY_FLOOR < 1


def test_the_backend_path_form_the_rule_actually_sees() -> None:
    # `openapi.json` spells parameters with braces, which is what `reachable` compares
    # against; if FastAPI ever changes that spelling this is the test that says so.
    assert reachable(BACKEND, BACKEND)
