"""Tests for the static checks in ``backend/checks/``.

``.ai/checks/static/README.md`` §4.2 requires every rule to have its own test:
one fixture that **must be reported** and one that **must stay silent**. The
reason is not coverage — it is that without the first fixture, a rule is
indistinguishable from a rule that never runs. This repository has already paid
for that lesson once: ``pytest -m unit`` reported "54 passed, 47 deselected"
while 47 tests silently did not run.

The "must be reported" half is therefore the important half. A rule whose
positive case is missing is not a guard; it is a comment.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from checks import framework
from checks.__main__ import main
from checks.framework import (
    CheckMeta,
    ScanContext,
    Severity,
    Suppressions,
    apply_exemptions,
    contains_token,
)
from checks.registry import MODULE_BY_ID, RULES, registry_meta
from checks.rules import (
    check_append_only_triggers,
    check_doc_sync,
    check_error_codes,
    git_tracked,
    home_no_return_rate,
    immature_outcome_blank,
    no_bare_except,
    no_boolean_state,
    no_client_supplied_id,
    no_prediction_field,
    no_print,
    no_raw_http,
    time_cost_in_stop_loss,
    tool_encoding,
)

from alphacouncil.core.error_codes import ErrorCode

#: ``backend/tests/unit/test_static_checks.py`` → ``<repo>``
REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ctx(
    tmp_path: Path,
    files: Mapping[str, str],
    registry: Sequence[CheckMeta] | None = None,
) -> ScanContext:
    """Build a throwaway repository from ``{relative path: contents}``.

    The registry defaults to the real one, because the framework needs it to
    translate a finding's ``CHECK_*`` code back into the ``S-xx`` id an
    exemption is written with. A fixture without it would test a context the
    runner never builds.
    """
    for relative, content in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return ScanContext(
        repo_root=tmp_path,
        registry=registry_meta() if registry is None else registry,
    )


def codes(result: framework.CheckResult) -> list[str]:
    """The codes reported by a rule, for terse assertions."""
    return [issue.code for issue in result.issues]


def errors(result: framework.CheckResult) -> list[framework.Issue]:
    """Only the error-severity findings."""
    return [issue for issue in result.issues if issue.severity is Severity.ERROR]


# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------


class TestEnvelope:
    """The diagnostic envelope must have exactly the documented five keys."""

    def test_issue_serialises_to_the_envelope(self) -> None:
        issue = framework.Issue(Severity.ERROR, "CHECK_RAW_HTTP", "msg", "a.py:1", None)
        assert set(issue.as_dict()) == {"severity", "code", "message", "target", "fix"}

    def test_a_missing_fix_is_legal(self) -> None:
        """``.ai/error-codes.md`` §1: not every problem can be repaired."""
        issue = framework.Issue(Severity.ERROR, "CHECK_RAW_HTTP", "msg")
        assert issue.as_dict()["fix"] is None

    def test_render_includes_the_target_and_the_fix(self) -> None:
        issue = framework.Issue(Severity.ERROR, "CHECK_RAW_HTTP", "msg", "a.py:1", "do this")
        rendered = issue.render()
        assert "a.py:1" in rendered
        assert "do this" in rendered


class TestSuppressions:
    """`# noqa: S-01 -- reason` is the only way to silence a rule."""

    def test_a_trailing_exemption_covers_that_line(self) -> None:
        suppressions = Suppressions("x = 1  # noqa: S-01 -- the entry point itself\n")
        assert suppressions.covers("S-01", 1)

    def test_a_trailing_exemption_does_not_cover_another_line(self) -> None:
        source = "x = 1  # noqa: S-01 -- reason\n" + "y = 2\n" * 40
        suppressions = Suppressions(source)
        assert not suppressions.covers("S-01", 30)

    def test_a_standalone_comment_near_the_top_covers_the_file(self) -> None:
        source = "# noqa: S-01 -- this module is the entry point\n" + "y = 2\n" * 40
        suppressions = Suppressions(source)
        assert suppressions.covers("S-01", 30)

    def test_a_standalone_comment_far_down_does_not_cover_the_file(self) -> None:
        """Otherwise a stray comment on line 90 would silence the whole module."""
        source = "y = 2\n" * 40 + "# noqa: S-01 -- local\n"
        suppressions = Suppressions(source)
        assert not suppressions.covers("S-01", 30)

    def test_an_exemption_for_one_rule_does_not_silence_another(self) -> None:
        suppressions = Suppressions("x = 1  # noqa: S-01 -- reason\n")
        assert not suppressions.covers("S-10", 1)

    def test_an_exemption_without_a_reason_is_reported(self) -> None:
        """The reason is mandatory, otherwise "explicit" means "silent"."""
        suppressions = Suppressions("x = 1  # noqa: S-01\n")
        assert [item.check_id for item in suppressions.unreasoned()] == ["S-01"]

    def test_a_reasoned_exemption_is_not_reported(self) -> None:
        suppressions = Suppressions("x = 1  # noqa: S-01 -- because\n")
        assert suppressions.unreasoned() == ()


class TestApplyExemptions:
    """Exemptions are applied by the framework, not by each rule."""

    def test_an_exempted_finding_disappears(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"backend/src/alphacouncil/api/app.py": "x = 1  # noqa: S-10 -- CLI shim\n"},
        )
        result = framework.CheckResult(
            issues=[
                framework.Issue(
                    Severity.ERROR,
                    "CHECK_PRINT_STATEMENT",
                    "m",
                    "backend/src/alphacouncil/api/app.py:1",
                )
            ],
            files=[tmp_path / "backend/src/alphacouncil/api/app.py"],
        )
        assert apply_exemptions(ctx, result).issues == []

    def test_an_unreasoned_exemption_becomes_a_finding(self, tmp_path: Path) -> None:
        path = tmp_path / "backend/src/alphacouncil/api/app.py"
        ctx = make_ctx(tmp_path, {"backend/src/alphacouncil/api/app.py": "x = 1  # noqa: S-10\n"})
        result = framework.CheckResult(files=[path])
        assert codes(apply_exemptions(ctx, result)) == ["CHECK_EXEMPTION_UNREASONED"]


class TestContainsToken:
    """Word-run matching, so a rule does not cry wolf."""

    def test_a_token_matches_a_whole_word_run(self) -> None:
        assert contains_token("consensus_target_price", ("target_price",)) == "target_price"

    def test_a_token_does_not_match_inside_a_word(self) -> None:
        assert contains_token("migrating", ("rating",)) is None

    def test_a_token_does_not_match_a_partial_run(self) -> None:
        assert contains_token("target_prices", ("target_price",)) is None


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


class TestRegistry:
    """The registry is the contract between the document and the code."""

    def test_fourteen_rules_in_order(self) -> None:
        """The id list is a statement about how many rules there are.

        It breaks when a rule is added, which is the point: ⭐ a renamed count that kept
        its old number would be a test describing something other than what it checks.
        """
        assert [rule.meta.check_id for rule in RULES] == [f"S-{n:02d}" for n in range(1, 15)]

    @pytest.mark.parametrize("check_id", sorted(MODULE_BY_ID))
    def test_each_rule_resolves_to_the_module_that_declares_it(self, check_id: str) -> None:
        """Guards against a copy-paste error in ``registry.py``."""
        module = importlib.import_module(MODULE_BY_ID[check_id])
        bound = next(rule for rule in RULES if rule.meta.check_id == check_id)
        assert module.META is bound.meta
        assert module.META.check_id == check_id

    @pytest.mark.parametrize("check_id", sorted(MODULE_BY_ID))
    def test_each_rule_emits_a_registered_error_code(self, check_id: str) -> None:
        module = importlib.import_module(MODULE_BY_ID[check_id])
        assert module.CODE in set(ErrorCode)

    def test_the_documented_rule_list_matches_the_registry(self) -> None:
        """S-12 against the real repository — the whole point of the rule."""
        ctx = ScanContext(repo_root=REPO_ROOT, registry=registry_meta())
        assert errors(check_doc_sync.run(ctx)) == []


# ---------------------------------------------------------------------------
# S-01 no-raw-http
# ---------------------------------------------------------------------------


class TestS01NoRawHttp:
    """⭐ The predicate is **module paths**, not a directory (ADR-0031)."""

    def test_importing_httpx_outside_an_http_aware_module_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, {"backend/src/alphacouncil/api/app.py": "import httpx\n"})
        assert codes(no_raw_http.run(ctx)) == ["CHECK_RAW_HTTP"]

    def test_a_convenience_call_is_reported_even_in_an_http_aware_module(
        self, tmp_path: Path
    ) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/sources.py": (
                    "import httpx\n\n\ndef fetch(url: str) -> str:\n"
                    "    return httpx.get(url).text\n"
                )
            },
        )
        assert codes(no_raw_http.run(ctx)) == ["CHECK_RAW_HTTP"]

    def test_a_client_built_outside_the_factory_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/http.py": (
                    "import httpx\n\n\ndef fetch(url: str) -> str:\n"
                    "    with httpx.Client(timeout=5) as client:\n"
                    "        return client.get(url).text\n"
                )
            },
        )
        assert codes(no_raw_http.run(ctx)) == ["CHECK_RAW_HTTP"]

    def test_the_construction_site_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/http.py": (
                    "import httpx\n\n\n"
                    "def build_client() -> httpx.Client:\n"
                    "    return httpx.Client(timeout=5)\n"
                )
            },
        )
        assert no_raw_http.run(ctx).issues == []

    # -- the tightening: a module may *name* httpx but never *build* a client --------

    def test_a_module_may_name_httpx_to_catch_its_exceptions(self, tmp_path: Path) -> None:
        """⭐ ``providers/sources.py`` needs ``httpx.HTTPError`` and nothing more.

        Rule 1 answers a different question from rule 3, so it gets its own list. Before
        the rewrite the only way to express this was a directory allowlist, which is how
        ``providers/`` acquired the power to construct clients anywhere.
        """
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/sources.py": (
                    "import httpx\n\n\n"
                    "def fetch(client: httpx.Client, url: str) -> str:\n"
                    "    try:\n"
                    "        return client.get(url).text\n"
                    "    except httpx.HTTPError:\n"
                    "        return ''\n"
                )
            },
        )
        assert no_raw_http.run(ctx).issues == []

    def test_that_same_module_may_not_construct_a_client(self, tmp_path: Path) -> None:
        """⭐ The whole point: the import permission does not carry a construction one."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/sources.py": (
                    "import httpx\n\n\n"
                    "def fetch(url: str) -> str:\n"
                    "    return httpx.Client(timeout=5).get(url).text\n"
                )
            },
        )
        assert codes(no_raw_http.run(ctx)) == ["CHECK_RAW_HTTP"]

    def test_a_factory_named_function_in_the_wrong_file_is_still_reported(
        self, tmp_path: Path
    ) -> None:
        """⭐⭐ Written because a mutation survived, and this is the shape it missed.

        The construction rule has **two** conditions — right file *and* right function
        name. A fixture that only breaks one of them cannot tell them apart: with the
        function called ``fetch``, both conditions are violated at once and the test goes
        red whether or not the file check exists.

        Deleting the file condition from the rule leaves this fixture green. ⭐ That is
        the exact form of 「a rule that passes its own tests and catches nothing」, and the
        only reason it was found is that the mutation was run at all.
        """
        ctx = make_ctx(
            tmp_path,
            {
                # A permitted name, in a file that is not a construction site.
                "backend/src/alphacouncil/providers/sources.py": (
                    "import httpx\n\n\n"
                    "def _client() -> httpx.Client:\n"
                    "    return httpx.Client(timeout=5)\n"
                )
            },
        )
        assert codes(no_raw_http.run(ctx)) == ["CHECK_RAW_HTTP"]

    def test_the_construction_site_is_a_single_named_file(self, tmp_path: Path) -> None:
        """⭐ A test, not a comment: the count is what makes 「改紧」 checkable.

        The rewrite tightened this from 「every .py under providers/」 to one file. Nothing
        else records that, so nothing would notice it quietly widening again.
        """
        assert frozenset({Path("core/http.py")}) == no_raw_http.CONSTRUCTION_SITES

    def test_every_http_aware_module_is_a_construction_site_or_explains_itself(
        self, tmp_path: Path
    ) -> None:
        """⭐ A widened import allowlist must be justified by types, not by wanting HTTP."""
        for path in no_raw_http.HTTP_AWARE_MODULES - no_raw_http.CONSTRUCTION_SITES:
            assert path.parts[0] in {"providers"}, f"{path} may name httpx for no stated reason"

    def test_a_new_file_beside_an_allowed_one_gets_nothing(self, tmp_path: Path) -> None:
        """⭐ The directory that used to be allowed is no longer allowed."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/anything_new.py": (
                    "import httpx\n\n\ndef f(url: str) -> str:\n"
                    "    return httpx.Client(timeout=5).get(url).text\n"
                )
            },
        )
        # Two findings: the import, and the construction.
        assert codes(no_raw_http.run(ctx)) == ["CHECK_RAW_HTTP", "CHECK_RAW_HTTP"]


# ---------------------------------------------------------------------------
# S-02 no-boolean-state
# ---------------------------------------------------------------------------


class TestS02NoBooleanState:
    def test_two_lifecycle_booleans_are_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/models/domain.py": (
                    "class Review:\n    reviewed: bool = False\n    outcome_filled: bool = False\n"
                )
            },
        )
        assert codes(no_boolean_state.run(ctx)) == ["CHECK_BOOLEAN_STATE"]

    def test_two_is_prefixes_are_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/models/domain.py": (
                    "class Card:\n    is_suspended: bool = False\n    has_lapsed: bool = False\n"
                )
            },
        )
        assert codes(no_boolean_state.run(ctx)) == ["CHECK_BOOLEAN_STATE"]

    def test_one_boolean_is_a_real_binary_and_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/models/domain.py": (
                    "class Card:\n"
                    "    state: CardState = CardState.NEW\n"
                    "    is_active: bool = True\n"
                )
            },
        )
        assert no_boolean_state.run(ctx).issues == []

    def test_an_enum_state_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"backend/src/alphacouncil/models/domain.py": "class Card:\n    state: str\n"},
        )
        assert no_boolean_state.run(ctx).issues == []


# ---------------------------------------------------------------------------
# S-03 no-prediction-field
# ---------------------------------------------------------------------------


class TestS03NoPredictionField:
    def test_a_target_price_field_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/models/domain.py": (
                    "class ResearchReport:\n    target_price: float\n"
                )
            },
        )
        assert codes(no_prediction_field.run(ctx)) == ["CHECK_PREDICTION_FIELD"]

    def test_a_recommendation_route_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/api/app.py": (
                    "app = object()\n\n\n"
                    '@app.get("/api/v1/recommendations")\n'
                    "def handler() -> None:\n    ...\n"
                )
            },
        )
        assert codes(no_prediction_field.run(ctx)) == ["CHECK_PREDICTION_FIELD"]

    def test_a_chinese_ui_phrase_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"backend/src/alphacouncil/api/app.py": 'LABEL = "目标价"\n'},
        )
        assert codes(no_prediction_field.run(ctx)) == ["CHECK_PREDICTION_FIELD"]

    def test_facts_and_kill_criteria_stay_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/models/domain.py": (
                    "class ResearchReport:\n"
                    "    facts: list[str]\n"
                    "    open_questions: list[str]\n"
                    "    kill_criteria: list[str]\n"
                )
            },
        )
        assert no_prediction_field.run(ctx).issues == []


# ---------------------------------------------------------------------------
# S-04 check-append-only-triggers
# ---------------------------------------------------------------------------


class TestS04AppendOnlyTriggers:
    def test_an_unguarded_append_only_table_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"backend/migrations/0001_init.sql": "CREATE TABLE decisions (id INTEGER);\n"},
        )
        assert codes(check_append_only_triggers.run(ctx)) == ["CHECK_MISSING_TRIGGER"]

    def test_only_the_missing_trigger_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/migrations/0001_init.sql": (
                    "CREATE TABLE decisions (id INTEGER);\n"
                    "CREATE TRIGGER decisions_no_update BEFORE UPDATE ON decisions\n"
                    "BEGIN SELECT RAISE(ABORT, 'append-only'); END;\n"
                )
            },
        )
        result = check_append_only_triggers.run(ctx)
        assert len(result.issues) == 1
        assert "BEFORE DELETE" in result.issues[0].message

    def test_a_commented_out_trigger_does_not_count(self, tmp_path: Path) -> None:
        """The exact failure the comment-stripping step exists for."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/migrations/0001_init.sql": (
                    "CREATE TABLE decisions (id INTEGER);\n"
                    "-- CREATE TRIGGER decisions_no_update BEFORE UPDATE ON decisions\n"
                    "-- CREATE TRIGGER decisions_no_delete BEFORE DELETE ON decisions\n"
                )
            },
        )
        assert len(check_append_only_triggers.run(ctx).issues) == 1

    def test_a_guarded_table_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/migrations/0001_init.sql": (
                    "CREATE TABLE decisions (id INTEGER);\n"
                    "CREATE TRIGGER decisions_no_update BEFORE UPDATE ON decisions\n"
                    "BEGIN SELECT RAISE(ABORT, 'append-only'); END;\n"
                    "CREATE TRIGGER decisions_no_delete BEFORE DELETE ON decisions\n"
                    "BEGIN SELECT RAISE(ABORT, 'append-only'); END;\n"
                )
            },
        )
        assert check_append_only_triggers.run(ctx).issues == []

    def test_a_non_log_table_is_not_reported(self, tmp_path: Path) -> None:
        """`instruments` is not a log table, so no trigger is demanded of it."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/migrations/0001_init.sql": (
                    "CREATE TABLE instruments (code TEXT);\n"
                    "CREATE TABLE decisions (id TEXT);\n"
                    "CREATE TRIGGER decisions_no_update BEFORE UPDATE ON decisions\n"
                    "BEGIN SELECT RAISE(ABORT, 'append-only'); END;\n"
                    "CREATE TRIGGER decisions_no_delete BEFORE DELETE ON decisions\n"
                    "BEGIN SELECT RAISE(ABORT, 'append-only'); END;\n"
                )
            },
        )
        assert check_append_only_triggers.run(ctx).issues == []

    def test_the_watchlist_event_log_is_guarded_too(self, tmp_path: Path) -> None:
        """A watchlist reason is user-written, so red line 15 keeps agents out of it."""
        ctx = make_ctx(
            tmp_path,
            {"backend/migrations/0001_init.sql": "CREATE TABLE watchlist_events (id INTEGER);\n"},
        )
        assert codes(check_append_only_triggers.run(ctx)) == ["CHECK_MISSING_TRIGGER"]

    def test_a_schema_without_append_only_tables_is_skipped_not_passed(
        self, tmp_path: Path
    ) -> None:
        """The hole this rule had: nothing to guard was reported as clean.

        The first version intersected the declared tables with the append-only
        set and reported an error per element. An empty intersection therefore
        produced no findings — so the day a schema landed without the decision
        journal, the rule returned "clean" while having examined nothing. It is
        the same distinction the runner already draws for ``skipped``: *nothing
        observed* is not *nothing wrong*.
        """
        ctx = make_ctx(
            tmp_path,
            {"backend/migrations/0001_init.sql": "CREATE TABLE instruments (code TEXT);\n"},
        )
        result = check_append_only_triggers.run(ctx)
        assert result.issues == []
        assert result.skipped is not None

    def test_no_schema_files_is_skipped_not_passed(self, tmp_path: Path) -> None:
        """T-19: nothing to scan is not the same as clean."""
        ctx = make_ctx(tmp_path, {"backend/README.md": "hi\n"})
        assert check_append_only_triggers.run(ctx).skipped is not None


# ---------------------------------------------------------------------------
# S-05 check-error-codes
# ---------------------------------------------------------------------------

_ENUM_HEADER = "from enum import StrEnum\n\n\nclass ErrorCode(StrEnum):\n"



def _codes_doc(*prefixes: str, rows: str = "") -> str:
    """A minimal ``.ai/error-codes.md`` carrying the §2 headings the rule reads.

    ⭐ Since spec 030 the rule **derives** its namespace prefixes from §2's headings
    rather than keeping a second hand-maintained list — a list already forgotten
    three times (``REVIEW_*``, ``NOTE_*``, ``LESSON_*``), the last twenty minutes after
    reading the comment that predicted it.

    So a document that is only a table row no longer registers anything, and the six
    S-05 tests that used one had to start saying which namespace they are about. The
    rule has no fallback on purpose: a fallback would fail in the direction where a
    namespace is half-recognised, which is the silent one.
    """
    headings = "".join(
        f"### 2.{number} `{prefix}_*`\n\n" for number, prefix in enumerate(prefixes, 1)
    )
    return f"## 二、错误码命名空间\n\n{headings}{rows}"

class TestS05ErrorCodes:
    # ── the derivation itself (spec 030) ──────────────────────────────────

    def test_the_prefixes_come_from_the_documents_own_headings(self, tmp_path: Path) -> None:
        """A namespace with no §2 heading is not registered, and that is reported.

        The rule used to carry a hardcoded prefix list, so this was impossible to
        state. It is the property that makes the single-place edit possible: add a
        §2 heading in ``.ai/error-codes.md`` and the code is recognised, with no second
        file to update and nothing to forget.
        """
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/error_codes.py": _ENUM_HEADER
                + '    SOMETHING_NEW = "SOMETHING_NEW"\n',
                ".ai/error-codes.md": _codes_doc(
                    "CARD", rows="| `CARD_CONTENT_REQUIRED` | error | x |\n"
                ),
            },
        )
        messages = [issue.message for issue in errors(check_error_codes.run(ctx))]
        assert any("SOMETHING_NEW" in message for message in messages)

    def test_both_prefixes_are_extracted_and_both_families_match(self, tmp_path: Path) -> None:
        """The ``DATA_SOURCE_*`` heading has to yield a token, and it did not.

        ⭐ **The load-bearing assertion is the first one.** With ``[A-Z0-9]*`` as the
        prefix class, the heading ``` `DATA_SOURCE_*` ``` produced *no* token — so
        ``DATA_SOURCE`` never entered the alternation at all, and every
        ``DATA_SOURCE_*`` code was recognised only by accident, through the shorter
        ``DATA`` heading sharing its first word. A namespace that documents itself,
        registers itself nowhere, and whose codes nevertheless pass is a wrong answer
        reached by coincidence, which is the shape that survives review.

        The order is asserted because it is the list's contract, **not** because it
        would break anything today: the suffix class is greedy, so either alternation
        order fullmatches a real code. The comment in the rule says so too, now.
        """
        document = _codes_doc("DATA", "DATA_SOURCE")
        prefixes = check_error_codes.documented_prefixes(document)
        assert prefixes == ("DATA_SOURCE", "DATA")

        pattern = check_error_codes.code_pattern(document)
        assert pattern.fullmatch("DATA_SOURCE_RATE_LIMITED")
        assert pattern.fullmatch("DATA_MISSING")
        # ★ And a namespace name on its own is **not** a code: the pattern demands a
        # `_`-prefixed suffix. This is what keeps §2's headings from counting as
        # codes, since `registered_codes` reads every backticked token in the document.
        assert pattern.fullmatch("DATA") is None

    def test_a_heading_may_carry_two_prefixes(self, tmp_path: Path) -> None:
        """§2.8 is `` `MIGRATION_*` `` / `` `STORAGE_*` `` — one heading, two namespaces.

        A "take the first backticked token" reading of the heading would register
        ``MIGRATION_*`` and silently drop ``STORAGE_*``, and then every
        ``STORAGE_*`` code would be reported as unregistered forever with nothing
        pointing at the cause. Asserted because the derivation reads a heading rather
        than a line, and that is the only place the two can diverge.
        """

        document = "### 2.8 `MIGRATION_*` / `STORAGE_*`\n"
        assert set(check_error_codes.documented_prefixes(document)) == {"MIGRATION", "STORAGE"}
        pattern = check_error_codes.code_pattern(document)
        assert pattern.fullmatch("STORAGE_NO_SUCH_TABLE")
        assert pattern.fullmatch("MIGRATION_UNKNOWN_VERSION")

    def test_a_document_with_no_section_two_registers_nothing(self, tmp_path: Path) -> None:
        """⭐ And it fails **loudly**, which is the reason there is no fallback.

        A pattern derived from a document with no headings matches nothing, so every
        declared code is reported. That is a false alarm on a broken document rather
        than a silent pass — and a fallback to the old hardcoded list would restore
        precisely the quiet version, which is what the rule change was for.
        """

        empty = "# codes\n\nnothing here\n"
        assert check_error_codes.documented_prefixes(empty) == ()
        assert check_error_codes.code_pattern(empty).fullmatch("CARD_NOT_FOUND") is None

    def test_a_code_missing_from_the_document_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/error_codes.py": _ENUM_HEADER
                + '    DATA_SOURCE_UNREACHABLE = "DATA_SOURCE_UNREACHABLE"\n',
                ".ai/error-codes.md": _codes_doc("DATA_SOURCE"),
            },
        )
        result = check_error_codes.run(ctx)
        assert len(errors(result)) == 1
        assert "DATA_SOURCE_UNREACHABLE" in errors(result)[0].message

    def test_a_bare_string_code_in_product_code_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/error_codes.py": _ENUM_HEADER
                + '    DATA_SOURCE_FORBIDDEN = "DATA_SOURCE_FORBIDDEN"\n',
                "backend/src/alphacouncil/providers/sources.py": (
                    'CODE = "DATA_SOURCE_FORBIDDEN"\n'
                ),
                ".ai/error-codes.md": _codes_doc(
                    "DATA_SOURCE",
                    rows="| `DATA_SOURCE_FORBIDDEN` | error | x |\n",
                ),
            },
        )
        result = check_error_codes.run(ctx)
        assert any("bare string" in issue.message for issue in errors(result))

    def test_a_bare_string_in_the_check_scripts_is_allowed(self, tmp_path: Path) -> None:
        """`checks/` may not import the product, so its codes must be literals."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/error_codes.py": _ENUM_HEADER
                + '    CHECK_RAW_HTTP = "CHECK_RAW_HTTP"\n',
                "backend/checks/rules/no_raw_http.py": 'CODE = "CHECK_RAW_HTTP"\n',
                ".ai/error-codes.md": _codes_doc(
                    "CHECK", rows="| `CHECK_RAW_HTTP` | error | x |\n"
                ),
            },
        )
        assert errors(check_error_codes.run(ctx)) == []

    def test_a_registered_and_declared_code_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/error_codes.py": _ENUM_HEADER
                + '    DATA_NO_DATA = "DATA_NO_DATA"\n',
                "backend/src/alphacouncil/providers/sources.py": (
                    "from alphacouncil.core.error_codes import ErrorCode\n\n"
                    "CODE = ErrorCode.DATA_NO_DATA\n"
                ),
                ".ai/error-codes.md": _codes_doc(
                    "DATA", rows="| `DATA_NO_DATA` | info | 确实没有 |\n"
                ),
            },
        )
        assert errors(check_error_codes.run(ctx)) == []

    def test_a_documented_code_with_no_enum_member_is_a_warning(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/error_codes.py": _ENUM_HEADER
                + '    DATA_NO_DATA = "DATA_NO_DATA"\n',
                ".ai/error-codes.md": _codes_doc(
                    "DATA",
                    rows="| `DATA_NO_DATA` | info | x |\n| `DATA_GONE` | info | x |\n",
                ),
            },
        )
        result = check_error_codes.run(ctx)
        warnings = [issue for issue in result.issues if issue.severity is Severity.WARNING]
        assert any("DATA_GONE" in issue.message for issue in warnings)

    def test_a_declared_but_unemitted_code_is_only_info(self, tmp_path: Path) -> None:
        """The namespace was specified before the code, on purpose."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/core/error_codes.py": _ENUM_HEADER
                + '    AGENT_WRITE_DENIED = "AGENT_WRITE_DENIED"\n',
                ".ai/error-codes.md": _codes_doc(
                    "AGENT", rows="| `AGENT_WRITE_DENIED` | error | x |\n"
                ),
            },
        )
        result = check_error_codes.run(ctx)
        assert errors(result) == []
        assert result.issues[0].severity is Severity.INFO

    def test_a_missing_document_is_skipped(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, {"backend/README.md": "hi\n"})
        assert check_error_codes.run(ctx).skipped is not None


# ---------------------------------------------------------------------------
# S-06 no-client-supplied-id
# ---------------------------------------------------------------------------


class TestS06ClientSuppliedId:
    def test_an_id_in_a_create_schema_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/api/schemas.py": (
                    "class DecisionCreate:\n    id: int\n    rationale: str\n"
                )
            },
        )
        assert codes(no_client_supplied_id.run(ctx)) == ["CHECK_CLIENT_SUPPLIED_ID"]

    def test_a_client_supplied_timestamp_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/api/schemas.py": (
                    "class DecisionCreate:\n    recorded_at: str\n"
                )
            },
        )
        assert codes(no_client_supplied_id.run(ctx)) == ["CHECK_CLIENT_SUPPLIED_ID"]

    def test_a_reference_id_in_an_update_schema_stays_silent(self, tmp_path: Path) -> None:
        """An update names the record it amends; that is a reference, not a claim."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/api/schemas.py": (
                    "class DecisionUpdate:\n    decision_id: int\n    counter_evidence: str\n"
                )
            },
        )
        assert no_client_supplied_id.run(ctx).issues == []

    def test_a_response_model_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/api/schemas.py": (
                    "class DecisionResponse:\n    id: int\n    recorded_at: str\n"
                )
            },
        )
        assert no_client_supplied_id.run(ctx).issues == []


# ---------------------------------------------------------------------------
# S-07 / S-08 / S-09 — the UI layer
# ---------------------------------------------------------------------------


class TestS07HomeNoReturnRate:
    def test_a_return_figure_on_the_home_page_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"frontend/src/pages/Home.tsx": '<Stat label="今年收益率" value="+18%" />\n'},
        )
        assert codes(home_no_return_rate.run(ctx)) == ["CHECK_RETURN_RATE_LEAK"]

    def test_facts_on_the_home_page_stay_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"frontend/src/pages/Home.tsx": '<Stat label="在场天数" value="412" />\n'},
        )
        assert home_no_return_rate.run(ctx).issues == []

    def test_no_frontend_is_skipped_not_passed(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, {"backend/README.md": "hi\n"})
        assert home_no_return_rate.run(ctx).skipped is not None


class TestS08ImmatureOutcomeBlank:
    def test_a_zero_fallback_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"frontend/src/components/OutcomeCard.tsx": "{review.resultScore ?? 0}\n"},
        )
        assert codes(immature_outcome_blank.run(ctx)) == ["CHECK_IMMATURE_OUTCOME"]

    def test_an_em_dash_fallback_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"frontend/src/components/OutcomeCard.tsx": "{review.resultScore ?? '—'}\n"},
        )
        assert codes(immature_outcome_blank.run(ctx)) == ["CHECK_IMMATURE_OUTCOME"]

    def test_a_blank_fallback_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"frontend/src/components/OutcomeCard.tsx": "{review.resultScore ?? ''}\n"},
        )
        assert immature_outcome_blank.run(ctx).issues == []

    def test_a_process_score_of_zero_stays_silent(self, tmp_path: Path) -> None:
        """A process score of zero is meaningful; only result scores cannot be 0."""
        ctx = make_ctx(
            tmp_path,
            {"frontend/src/components/ProcessCard.tsx": "{review.processScore ?? 0}\n"},
        )
        assert immature_outcome_blank.run(ctx).issues == []


class TestS09TimeCostInStopLoss:
    def test_a_stop_loss_prompt_without_the_time_cost_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {"frontend/src/components/StopLossDialog.tsx": "<p>当前亏损 32%</p>\n"},
        )
        assert codes(time_cost_in_stop_loss.run(ctx)) == ["CHECK_TIME_COST_MISSING"]

    def test_a_stop_loss_prompt_with_the_time_cost_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "frontend/src/components/StopLossDialog.tsx": (
                    "<p>当前亏损 32%</p>\n<p>恢复所需年数：约 2.3 年</p>\n"
                )
            },
        )
        assert time_cost_in_stop_loss.run(ctx).issues == []

    def test_no_stop_loss_component_is_skipped(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, {"frontend/src/pages/Home.tsx": "<p>hello</p>\n"})
        assert time_cost_in_stop_loss.run(ctx).skipped is not None


# ---------------------------------------------------------------------------
# S-10 no-print
# ---------------------------------------------------------------------------


class TestS10NoPrint:
    def test_a_print_call_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, {"backend/src/alphacouncil/api/app.py": 'print("hello")\n'})
        assert codes(no_print.run(ctx)) == ["CHECK_PRINT_STATEMENT"]

    def test_structured_logging_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/api/app.py": (
                    "logger = object()\n\n\ndef handler() -> None:\n"
                    '    logger.info("started", code="600519")\n'
                )
            },
        )
        assert no_print.run(ctx).issues == []

    def test_scripts_are_out_of_scope(self, tmp_path: Path) -> None:
        """`scripts/` is CLI tooling; stdout is its interface (matches ruff T201)."""
        ctx = make_ctx(tmp_path, {"backend/scripts/dev.py": 'print("gate")\n'})
        assert no_print.run(ctx).issues == []


# ---------------------------------------------------------------------------
# S-13 tool-encoding
# ---------------------------------------------------------------------------


class TestS13ToolEncoding:
    """A printing tool must own its output encoding (regression 0004).

    The fixture that matters most is the last one: it is the exact shape of
    `scripts/eval.py` as it was first written — a new tool, on the same day the
    fix landed, missing the call — and it is why this rule exists rather than
    three careful call sites.
    """

    def test_a_tool_that_prints_without_use_utf8_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/scripts/thing.py": (
                    "def main() -> int:\n"
                    '    print("  \\u2713 every gate that ran, passed")\n'
                    "    return 0\n"
                )
            },
        )
        assert codes(tool_encoding.run(ctx)) == ["CHECK_TOOL_ENCODING_UNGUARDED"]

    def test_a_tool_that_calls_use_utf8_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/scripts/thing.py": (
                    "from _console import use_utf8\n\n\n"
                    "def main() -> int:\n"
                    "    use_utf8()\n"
                    '    print("  \\u2713 every gate that ran, passed")\n'
                    "    return 0\n"
                )
            },
        )
        assert tool_encoding.run(ctx).issues == []

    def test_a_qualified_call_also_counts(self, tmp_path: Path) -> None:
        """`console.use_utf8()` is the same promise written differently."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/scripts/thing.py": (
                    "import _console as console\n\n\n"
                    "def main() -> int:\n"
                    "    console.use_utf8()\n"
                    "    return 0\n"
                )
            },
        )
        assert tool_encoding.run(ctx).issues == []

    def test_the_helper_itself_is_exempt(self, tmp_path: Path) -> None:
        """`_console.py` defines the call; requiring it to make the call is a loop."""
        source = "def use_utf8() -> None:\n    return\n"
        ctx = make_ctx(tmp_path, {"backend/scripts/_console.py": source})
        assert tool_encoding.run(ctx).issues == []

    def test_checks_main_is_in_scope(self, tmp_path: Path) -> None:
        source = "def main(argv=None) -> int:\n    print('ran')\n    return 0\n"
        ctx = make_ctx(tmp_path, {"backend/checks/__main__.py": source})
        assert codes(tool_encoding.run(ctx)) == ["CHECK_TOOL_ENCODING_UNGUARDED"]

    def test_the_product_is_out_of_scope(self, tmp_path: Path) -> None:
        """Product code must not print at all (S-10); this rule is about tools."""
        ctx = make_ctx(
            tmp_path,
            {"backend/src/alphacouncil/api/app.py": 'print("hello")\n'},
        )
        assert tool_encoding.run(ctx).issues == []


# ---------------------------------------------------------------------------
# S-11 no-bare-except
# ---------------------------------------------------------------------------


class TestS11NoBareExcept:
    def test_a_bare_except_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/router.py": (
                    "def go() -> None:\n    try:\n        pass\n    except:\n        pass\n"
                )
            },
        )
        assert codes(no_bare_except.run(ctx)) == ["CHECK_BARE_EXCEPT"]

    def test_an_empty_except_exception_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/router.py": (
                    "def go() -> None:\n"
                    "    try:\n        pass\n"
                    "    except Exception:\n        pass\n"
                )
            },
        )
        assert codes(no_bare_except.run(ctx)) == ["CHECK_BARE_EXCEPT"]

    def test_a_named_handler_that_re_raises_stays_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/router.py": (
                    "def go() -> None:\n"
                    "    try:\n"
                    "        pass\n"
                    "    except ValueError as exc:\n"
                    "        raise RuntimeError('wrapped') from exc\n"
                )
            },
        )
        assert no_bare_except.run(ctx).issues == []

    def test_a_broad_handler_that_logs_stays_silent(self, tmp_path: Path) -> None:
        """Constitution 7.3 allows handling; only silence is a defect."""
        ctx = make_ctx(
            tmp_path,
            {
                "backend/src/alphacouncil/providers/router.py": (
                    "logger = object()\n\n\ndef go() -> None:\n"
                    "    try:\n"
                    "        pass\n"
                    "    except Exception as exc:\n"
                    '        logger.warning("failed", error=str(exc))\n'
                )
            },
        )
        assert no_bare_except.run(ctx).issues == []


# ---------------------------------------------------------------------------
# S-12 check-doc-sync
# ---------------------------------------------------------------------------

_README = "| **S-01** | `no-raw-http` | 禁止裸 HTTP | 7.8 |\n"
_META_01 = CheckMeta("S-01", "no-raw-http", "t", "P0")


class TestS12DocSync:
    def test_a_documented_rule_with_no_implementation_is_reported(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {
                ".ai/checks/static/README.md": _README
                + "| **S-99** | `no-imaginary-thing` | 禁止想象 | 7.9 |\n"
            },
            registry=[_META_01],
        )
        result = check_doc_sync.run(ctx)
        assert any("S-99" in issue.message for issue in errors(result))

    def test_an_implemented_rule_missing_from_the_document_is_reported(
        self, tmp_path: Path
    ) -> None:
        ctx = make_ctx(
            tmp_path,
            {".ai/checks/static/README.md": _README},
            registry=[_META_01, CheckMeta("S-02", "no-boolean-state", "t", "P0")],
        )
        result = check_doc_sync.run(ctx)
        assert any("S-02" in issue.message for issue in errors(result))

    def test_a_slug_mismatch_is_a_warning(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {".ai/checks/static/README.md": "| **S-01** | `no-raw-http-old` | x | 7.8 |\n"},
            registry=[_META_01],
        )
        result = check_doc_sync.run(ctx)
        assert errors(result) == []
        assert any(issue.severity is Severity.WARNING for issue in result.issues)

    def test_matching_lists_stay_silent(self, tmp_path: Path) -> None:
        ctx = make_ctx(
            tmp_path,
            {".ai/checks/static/README.md": _README},
            registry=[_META_01],
        )
        assert check_doc_sync.run(ctx).issues == []

    def test_a_missing_document_is_skipped(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, {"backend/README.md": "hi\n"}, registry=[_META_01])
        assert check_doc_sync.run(ctx).skipped is not None


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BrokenRule:
    """A rule that raises, to prove a crash is reported rather than swallowed."""

    meta: CheckMeta
    run: Callable[[ScanContext], framework.CheckResult]


class TestRunner:
    """The runner's contract: exit codes, stream routing, and crash handling."""

    def test_a_clean_repo_exits_zero_without_strict(self, tmp_path: Path) -> None:
        (tmp_path / "backend").mkdir()
        assert main(["--root", str(tmp_path)]) == 0

    def test_a_skipped_rule_fails_under_strict(self, tmp_path: Path) -> None:
        """T-19: a skipped rule has not passed, it has not run."""
        (tmp_path / "backend").mkdir()
        assert main(["--root", str(tmp_path), "--strict"]) == 1

    def test_an_unknown_rule_id_is_a_usage_error(self, tmp_path: Path) -> None:
        (tmp_path / "backend").mkdir()
        assert main(["--root", str(tmp_path), "--only", "S-99"]) == 2

    def test_only_runs_the_selected_rule(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "backend").mkdir()
        assert main(["--root", str(tmp_path), "--only", "S-10"]) == 0
        reported = capsys.readouterr().err
        assert "S-10" in reported
        assert "S-11" not in reported

    def test_a_missing_backend_directory_is_a_usage_error(self, tmp_path: Path) -> None:
        assert main(["--root", str(tmp_path)]) == 2

    def test_json_mode_writes_one_document_to_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`.ai/error-codes.md` §1.1: stdout carries the document and nothing else."""
        (tmp_path / "backend").mkdir()
        assert main(["--root", str(tmp_path), "--json"]) == 0
        captured = capsys.readouterr()
        document = json.loads(captured.out)
        # ⭐ Derived from the registry rather than written out, so adding a rule does not
        # require finding this number to change it too — and, more importantly, so the
        # number here cannot quietly disagree with the one the runner actually reports.
        assert document["summary"]["rules_selected"] == len(RULES)
        assert document["summary"]["rules_skipped"] >= 1
        assert "AlphaCouncil" not in captured.out

    def test_a_crashing_rule_is_reported_and_fails_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rule that crashes must not look like a rule that passed."""
        (tmp_path / "backend").mkdir()

        def explode(_ctx: ScanContext) -> framework.CheckResult:
            raise RuntimeError("boom")

        broken = _BrokenRule(_META_01, explode)
        monkeypatch.setattr("checks.__main__.RULES", (broken,))
        assert main(["--root", str(tmp_path), "--only", "S-01"]) == 1

# ---------------------------------------------------------------------------
# S-14 git-tracked
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=60,
    )


def git_repo(tmp_path: Path, files: dict[str, str], gitignore: str | None = None) -> Path:
    """A real git repository, because the rule's whole subject is git."""
    for relative, content in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if gitignore is not None:
        (tmp_path / ".gitignore").write_text(gitignore, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    return tmp_path


class TestS14GitTracked:
    """A source file git does not have works here and nowhere else.

    Nothing about this defect is a failure: every test passes, every import
    resolves, every other gate is green — **on the machine that has the file**.
    That is why the rule exists and why a test cannot catch it.
    """

    def test_an_untracked_source_file_is_reported(self, tmp_path: Path) -> None:
        repo = git_repo(
            tmp_path,
            {"backend/src/alphacouncil/thing.py": "VALUE = 1\n"},
        )
        # ⭐ The tracked file is added **first**. Without this the fixture's own file is
        # untracked too, and the assertion gets two findings — correct about the rule,
        # wrong about which defect was being tested.
        _git(repo, "add", "-A")
        (repo / "backend" / "src" / "alphacouncil" / "late.py").write_text(
            "LATE = 1\n", encoding="utf-8"
        )
        ctx = make_ctx(repo, {})
        result = git_tracked.run(ctx)
        assert codes(result) == ["CHECK_UNTRACKED_SOURCE"]
        assert "late.py" in result.issues[0].message
        assert result.issues[0].fix == "git add backend/src/alphacouncil/late.py"

    def test_a_tracked_source_file_stays_silent(self, tmp_path: Path) -> None:
        repo = git_repo(
            tmp_path,
            {"backend/src/alphacouncil/thing.py": "VALUE = 1\n"},
        )
        _git(repo, "add", "-A")
        ctx = make_ctx(repo, {})
        assert git_tracked.run(ctx).issues == []

    def test_an_ignored_source_file_is_reported_as_a_warning(self, tmp_path: Path) -> None:
        """⭐ The defect `git status` cannot show.

        `.gitignore` holding `data/` with **no leading slash** matches at every
        depth, so it covers `backend/src/.../data/` — spec 025 §7.1's recorded
        hazard. The file is untracked *and* ignored, and `git status` does not
        list ignored files, so this is the instance most likely to survive.

        A warning rather than an error, because `.venv` and `node_modules` are
        also correctly ignored: ⭐ a guardrail that cries wolf gets switched off.
        What keeps the warning quiet is the walk's scope, not the severity.
        """
        repo = git_repo(
            tmp_path,
            {"backend/src/alphacouncil/data/thing.py": "VALUE = 1\n"},
            gitignore="data/\n",
        )
        _git(repo, "add", "-A")
        ctx = make_ctx(repo, {})
        result = git_tracked.run(ctx)
        assert codes(result) == ["CHECK_IGNORED_SOURCE"]
        assert result.issues[0].severity is Severity.WARNING

    def test_ignored_build_directories_do_not_warn(self, tmp_path: Path) -> None:
        """⭐ The reason the walk has a skip list at all.

        `backend/.pytest_cache/README.md` is a real file, ends in a source
        extension, and is correctly ignored — so without `SKIP_DIRS` this rule
        warned about it the first time it ran against the real repository, which
        is how the spec's own claim that a warning 「can only mean an ignore rule
        is covering source」 turned out to be false.

        ⭐ **The `.gitignore` is the load-bearing part.** The first version of this
        fixture ran ``git add -A``, which made every one of these files *tracked* —
        so the rule stayed silent because the file was tracked and the skip list
        was never consulted. The test asserted a true statement about the wrong
        thing, and mutation 3 (removing `.pytest_cache` from `SKIP_DIRS`) survived
        because of it.
        """
        repo = git_repo(
            tmp_path,
            {
                "backend/src/alphacouncil/thing.py": "VALUE = 1\n",
                "backend/.pytest_cache/README.md": "# cache\n",
                "backend/.venv/lib/thing.py": "V = 1\n",
                "frontend/node_modules/pkg/index.js": "//\n",
            },
            gitignore=".pytest_cache/\n.venv/\nnode_modules/\n",
        )
        _git(repo, "add", "backend/src/alphacouncil/thing.py")
        ctx = make_ctx(repo, {})
        assert git_tracked.run(ctx).issues == []

    def test_source_outside_the_shipped_package_is_still_covered(self, tmp_path: Path) -> None:
        """⭐ 「The trees this rule is about」 needs a file outside the obvious one.

        Every other fixture puts its source under `backend/src/alphacouncil/`, and
        that directory **is** `ctx.product`. So a rule that stopped looking at
        `backend/checks/` and `frontend/e2e/` entirely would still pass all of
        them — which is exactly what mutation 6 did, and it survived.
        """
        repo = git_repo(
            tmp_path,
            {
                "backend/checks/rules/late_rule.py": "META = None\n",
                "frontend/e2e/late.spec.ts": "export default {}\n",
            },
        )
        ctx = make_ctx(repo, {})
        result = git_tracked.run(ctx)
        assert codes(result) == ["CHECK_UNTRACKED_SOURCE", "CHECK_UNTRACKED_SOURCE"]
        reported = {issue.message.split(" exists")[0] for issue in result.issues}
        assert reported == {"backend/checks/rules/late_rule.py", "frontend/e2e/late.spec.ts"}

    def test_a_non_repository_is_skipped_not_passed(self, tmp_path: Path) -> None:
        """⭐ 「Skipped is not passed」 — a tarball has no `.git`.

        Reporting zero issues there would be a lie that looks exactly like a
        clean run, which is what `CheckResult.skipped` exists to prevent.
        """
        ctx = make_ctx(tmp_path, {"backend/src/alphacouncil/thing.py": "VALUE = 1\n"})
        result = git_tracked.run(ctx)
        assert result.issues == []
        assert result.skipped is not None
        assert "not a git repository" in result.skipped

    def test_git_failing_inside_a_repository_is_skipped_with_a_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ The other skip branch, which mutation 5 found untested.

        ``_git`` returning ``None`` is what git does when it cannot run — a
        sandbox without it, a permissions problem, a repository that is being
        rewritten. The rule must say so rather than fall through to three empty
        listings and report every source file as untracked, ⭐ which is the
        spectacular failure mode: a clean checkout and a broken git become the
        same 200 errors.
        """
        repo = git_repo(
            tmp_path,
            {"backend/src/alphacouncil/thing.py": "VALUE = 1\n"},
        )
        monkeypatch.setattr(git_tracked, "_git", lambda *_args, **_kwargs: None)
        ctx = make_ctx(repo, {})
        result = git_tracked.run(ctx)
        assert result.issues == []
        assert result.skipped == "git produced no usable listing here"
