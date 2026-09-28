"""Tests for the red-line evaluation runner (`scripts/eval.py`).

The runner's whole value is that its number is *believable*. Three things can
make a number like "5 / 15" worthless, and each has a test here:

1. **The registry drifts from the constitution** — a red line is quietly
   dropped, or its id renumbered, and the denominator quietly shrinks.
   (`TestTheRegistryMatchesTheConstitution`)
2. **A declared verifier rots** — the E2E test it names is deleted, or its gate
   is removed from ``CHECK``, and the registry keeps claiming the red line is
   covered. (`TestDeclaredVerifiersCannotRot`)
3. **The number is edited instead of earned** — someone raises the baseline
   without adding a check. (`TestTheBaselineIsEarned`)

And one behavioural property that is the point of the whole thing:

- **A ``partial`` red line never passes.** Counting it would make the number
   prettier and the document a lie. (`TestPartialNeverPasses`)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import dev
import pytest

import eval as runner

BACKEND = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND.parent
REGISTRY_PATH = REPO_ROOT / ".ai" / "eval" / "redlines.json"
CONSTITUTION = REPO_ROOT / ".ai" / "constitution.md"

VALID_COVERAGE = frozenset({"full", "partial", "none"})


@pytest.fixture
def registry() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return loaded


class TestTheRegistryMatchesTheConstitution:
    def test_all_fifteen_red_lines_are_present_once_each(
        self, registry: dict[str, Any]
    ) -> None:
        ids = [entry["id"] for entry in registry["redlines"]]
        assert ids == list(range(1, 16)), "the constitution declares exactly 15 red lines"
        assert len(set(ids)) == 15

    def test_the_constitution_still_declares_fifteen(self) -> None:
        """If the constitution changes, this test fails before the registry lies."""
        text = CONSTITUTION.read_text(encoding="utf-8")
        start = text.index("## 第一条")
        end = text.index("## 第二条")
        section = text[start:end]
        rows = re.findall(r"^\|\s*(\d+)\s*\|", section, flags=re.MULTILINE)
        assert [int(n) for n in rows] == list(range(1, 16))

    def test_every_coverage_value_is_one_of_three(
        self, registry: dict[str, Any]
    ) -> None:
        for entry in registry["redlines"]:
            assert entry["coverage"] in VALID_COVERAGE, entry["id"]

    def test_coverage_and_verifier_agree(self, registry: dict[str, Any]) -> None:
        """`none` means no verifier; `full`/`partial` mean one. A mismatch is a lie."""
        for entry in registry["redlines"]:
            has = entry.get("verifier") is not None
            if entry["coverage"] == "none":
                assert not has, f"red line {entry['id']} is 'none' but names a verifier"
                assert entry.get("gap"), f"red line {entry['id']} is unguarded but explains nothing"
            else:
                assert has, f"red line {entry['id']} claims {entry['coverage']} with no verifier"
                if entry["coverage"] == "partial":
                    assert entry.get("gap"), f"red line {entry['id']} is partial but names no gap"

    def test_a_full_red_line_records_evidence(self, registry: dict[str, Any]) -> None:
        for entry in registry["redlines"]:
            if entry["coverage"] == "full":
                assert entry.get("evidence"), f"red line {entry['id']} claims full with no evidence"

    def test_static_verifiers_name_a_registered_rule(self, registry: dict[str, Any]) -> None:
        import checks.registry as reg

        registered = set(reg.MODULE_BY_ID)
        for entry in registry["redlines"]:
            for verifier in _all_verifiers(entry):
                if verifier["kind"] == "static":
                    assert verifier["check"] in registered, (
                        f"red line {entry['id']} names {verifier['check']}, "
                        "which is not a registered rule"
                    )

    def test_every_red_line_states_its_title_and_gap(
        self, registry: dict[str, Any]
    ) -> None:
        for entry in registry["redlines"]:
            assert entry["title"].strip()
            assert entry["enforcement"].strip()


class TestDeclaredVerifiersCannotRot:
    def test_gate_verifiers_name_a_gate_that_actually_runs(self, registry: dict[str, Any]) -> None:
        for entry in registry["redlines"]:
            for verifier in _all_verifiers(entry):
                if verifier["kind"] != "gate":
                    continue
                assert verifier["gate"] in dev.GATES, entry["id"]
                assert verifier["gate"] in dev.CHECK, (
                    f"red line {entry['id']} leans on gate {verifier['gate']}, "
                    "which is not in CHECK — a gate that never runs is not a gate"
                )

    def test_gate_verifiers_name_a_file_that_exists(self, registry: dict[str, Any]) -> None:
        for entry in registry["redlines"]:
            for verifier in _all_verifiers(entry):
                if verifier["kind"] != "gate":
                    continue
                assert (REPO_ROOT / verifier["file"]).is_file(), verifier["file"]

    def test_gate_verifiers_name_a_test_that_still_exists(
        self, registry: dict[str, Any]
    ) -> None:
        for entry in registry["redlines"]:
            for verifier in _all_verifiers(entry):
                if verifier["kind"] != "gate":
                    continue
                text = (REPO_ROOT / verifier["file"]).read_text(encoding="utf-8")
                assert verifier["selector"] in text, (
                    f"red line {entry['id']} names a test that is no longer in "
                    f"{verifier['file']}: {verifier['selector']!r}"
                )


class TestStaticVerdictRules:
    """`_static_ok`'s branches, pinned individually.

    Found by mutation check M3: flipping "a skipped rule is a failure" to "a
    skipped rule is a pass" turned **no test red**, because every static
    verifier in the registry happens to run on a repo where nothing is skipped.
    The branch was correct and completely unpinned — the exact state S-09 sat in
    for three days before a check was written for it.
    """

    def test_a_skipped_rule_is_not_a_pass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `rules_ran` must be non-zero on purpose: `_static_ok` tests `ran == 0`
        # first, so a report with both zero *and* skipped never reaches the
        # skipped branch. An earlier version of this test got that wrong and the
        # mutation check caught it (M3) — the branch was correct and unpinned.
        report = {"summary": {"rules_ran": 1, "rules_skipped": 1, "rules_crashed": 0}, "issues": []}
        monkeypatch.setattr(runner, "_run_rule", lambda _check_id: report)
        ok, why = runner._static_ok("S-09")
        assert ok is False
        assert "skipped" in why

    def test_a_crashed_rule_is_not_a_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        report = {"summary": {"rules_ran": 1, "rules_skipped": 0, "rules_crashed": 1}, "issues": []}
        monkeypatch.setattr(runner, "_run_rule", lambda _check_id: report)
        ok, why = runner._static_ok("S-09")
        assert ok is False
        assert "crash" in why

    def test_an_error_finding_is_not_a_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        report = {
            "summary": {"rules_ran": 1, "rules_skipped": 0, "rules_crashed": 0},
            "issues": [{"severity": "error", "code": "CHECK_TIME_COST_MISSING"}],
        }
        monkeypatch.setattr(runner, "_run_rule", lambda _check_id: report)
        ok, why = runner._static_ok("S-09")
        assert ok is False
        assert "CHECK_TIME_COST_MISSING" in why

    def test_an_info_finding_still_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`info` is the "declared but not wired yet" severity and is not a defect."""
        report = {
            "summary": {"rules_ran": 1, "rules_skipped": 0, "rules_crashed": 0},
            "issues": [{"severity": "info", "code": "CHECK_UNREGISTERED_CODE"}],
        }
        monkeypatch.setattr(runner, "_run_rule", lambda _check_id: report)
        ok, _why = runner._static_ok("S-09")
        assert ok is True

    def test_a_rule_the_registry_invented_is_not_a_pass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner, "_run_rule", lambda _check_id: {"__unknown_rule__": True})
        ok, why = runner._static_ok("S-99")
        assert ok is False
        assert "not a registered rule" in why

    def test_a_rule_that_ran_and_found_nothing_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = {"summary": {"rules_ran": 1, "rules_skipped": 0, "rules_crashed": 0}, "issues": []}
        monkeypatch.setattr(runner, "_run_rule", lambda _check_id: report)
        ok, _why = runner._static_ok("S-09")
        assert ok is True


class TestGateVerdictRules:
    """`_gate_ok`'s branches, pinned by calling it.

    The same mistake as `TestStaticVerdictRules`, found by mutation check M4:
    `TestDeclaredVerifiersCannotRot` re-implemented the staleness check on the
    test side, so the runner's own copy could be deleted and nothing went red.
    A test that re-implements the rule is a second rule, and it rots separately.
    """

    def test_a_gate_outside_check_is_rejected(self) -> None:
        ok, why = runner._gate_ok({"gate": "check-data", "file": "frontend/e2e/pool.spec.ts"})
        assert ok is False
        assert "CHECK" in why or "does not exist" in why

    def test_an_unknown_gate_is_rejected(self) -> None:
        ok, _why = runner._gate_ok({"gate": "no-such-gate", "file": "frontend/e2e/pool.spec.ts"})
        assert ok is False

    def test_a_missing_file_is_rejected(self) -> None:
        ok, why = runner._gate_ok({"gate": "e2e", "file": "frontend/e2e/gone.spec.ts"})
        assert ok is False
        assert "does not exist" in why

    def test_a_test_that_is_no_longer_there_is_rejected(self) -> None:
        """The staleness check itself. Deleting an E2E test must fail `eval`."""
        ok, why = runner._gate_ok(
            {
                "gate": "e2e",
                "file": "frontend/e2e/pool.spec.ts",
                "selector": "a test title that was deleted in a refactor",
            }
        )
        assert ok is False
        assert "no longer in" in why

    def test_a_live_declaration_passes(self) -> None:
        ok, why = runner._gate_ok(
            {
                "gate": "e2e",
                "file": "frontend/e2e/pool.spec.ts",
                "selector": "the page states its own no-returns rule",
            }
        )
        assert ok is True, why


class TestTheTestTier:
    """`test` verifiers are executed, so they have to be honest about failure.

    The distinction from `gate` matters: `gate` proves a declaration has not
    rotted, `test` proves the red line holds *now*. That only counts if the
    failure modes are all failures — including the quiet one.
    """

    def test_a_live_node_passes(self) -> None:
        ok, why = runner._test_ok({"node": "tests/unit/test_reviews.py::TestTheModelHoldsNoFigure"})
        assert ok is True, why

    def test_a_node_that_collects_nothing_is_a_failure(self) -> None:
        """The dangerous case: nothing ran, so nothing failed.

        A verdict built on "did anything fail?" would call a deleted red line
        green — the `0002` failure mode (a ledger nothing parses) in a new hat.
        Note the exit code is **not** asserted here: pytest 9.1.1 uses 4
        (`USAGE_ERROR`) for a missing node, not the 5 older versions used. The
        implementation reads the test count instead of trusting a constant, and
        this test checks the behaviour that makes that necessary.
        """
        ok, why = runner._test_ok(
            {"node": "tests/unit/test_reviews.py::AClassThatWasRenamed"}
        )
        assert ok is False
        assert "did not pass" in why

    def test_a_failing_node_is_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulated rather than real: there is no failing test to point at.

        Writing one on purpose would mean committing a red test, and the `test`
        gate runs the whole unit suite. Patched on `subprocess.run` itself rather
        than on ``runner.subprocess`` — reaching through the module would need a
        re-export the type checker rightly refuses to grant.
        """

        class Result:
            returncode = 1
            stdout = "1 failed, 3 passed in 0.10s"

        def fake_run(*_args: object, **_kwargs: object) -> Result:
            return Result()

        monkeypatch.setattr("subprocess.run", fake_run)
        ok, why = runner._test_ok({"node": "tests/unit/test_reviews.py::Whatever"})
        assert ok is False
        assert "1 failed" in why

    def test_a_run_that_reports_nothing_is_rejected_even_on_exit_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The precise trap: exit 0, no failures, and no tests.

        This is why the count is read from the output rather than inferred from
        the exit code. A fake exit 0 with an empty summary must not be a pass.
        """

        class Result:
            returncode = 0
            stdout = "no tests ran in 0.01s"

        def fake_run(*_args: object, **_kwargs: object) -> Result:
            return Result()

        monkeypatch.setattr("subprocess.run", fake_run)
        ok, _ = runner._test_ok({"node": "tests/unit/test_reviews.py::Gone"})
        assert ok is False

    def test_a_verifier_with_no_node_is_rejected(self) -> None:
        ok, why = runner._test_ok({})
        assert ok is False
        assert "no node id" in why

    def test_the_registry_uses_the_test_tier_for_red_lines_5_and_10(self) -> None:
        """The tier is only worth having if something actually declares it."""
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        by_id = {entry["id"]: entry for entry in data["redlines"]}
        for redline_id in (5, 10):
            entry = by_id[redline_id]
            assert entry["verifier"]["kind"] == "test", redline_id
            assert entry["verifier"]["node"], redline_id


class TestPartialNeverPasses:
    def test_a_partial_entry_is_forced_to_fail(self, registry: dict[str, Any]) -> None:
        """The invariant, exercised directly rather than through the whole run.

        `evaluate()` reads the real registry, so the cheapest honest way to test
        this rule is to assert it on the entries that exist: a `partial` red
        line must be a `fail`, whatever its verifier says.
        """
        results, _ = runner.evaluate()
        for result in results:
            if result.coverage == "partial":
                assert result.verdict == "fail", result.redline_id

    def test_the_counts_add_up(self) -> None:
        results, _ = runner.evaluate()
        counts = runner._summary(results)
        assert counts["total"] == len(results)
        assert counts["pass"] + counts["fail"] == counts["total"]
        assert counts["full"] + counts["partial"] + counts["none"] == counts["total"]
        assert counts["pass"] == counts["full"], "only a 'full' red line may pass"


class TestTheBaselineIsEarned:
    def test_the_live_run_matches_the_recorded_baseline(
        self, registry: dict[str, Any]
    ) -> None:
        """Anti-drift: the number may only move by doing the work.

        If this fails, either a verifier started or stopped working, or the
        registry was edited. Both deserve a deliberate baseline bump in
        `redlines.json` — never a quiet edit to make the build green.
        """
        results, _ = runner.evaluate()
        counts = runner._summary(results)
        baseline = registry["baseline"]
        assert counts["pass"] == baseline["pass"], (
            f"guarded count is {counts['pass']}, baseline says {baseline['pass']} "
            f"({baseline['date']}). If that is progress, update the baseline "
            "deliberately; if it is a break, fix the verifier."
        )
        assert counts["total"] == baseline["total"]
        # The coverage breakdown used to go unchecked, and it rotted: the baseline
        # said `partial 2 / none 8` while the measurement said `4 / 6`, and the
        # only reason it was ever noticed is that someone read the numbers. A
        # number nobody checks is a number that drifts (constitution 8.3).
        for key in ("full", "partial", "none"):
            assert counts[key] == baseline[key], (
                f"{key} is {counts[key]}, baseline says {baseline[key]} "
                f"({baseline['date']}) — bump the baseline deliberately"
            )

    def test_the_baseline_is_not_a_claim_of_completion(self) -> None:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        assert data["policy"]["unguarded_counts_as_failure"] is True
        assert data["policy"]["threshold"] == 1.0

    def test_a_guarded_below_threshold_run_exits_non_zero(self) -> None:
        """`main()` must fail while any red line is unguarded (T-19)."""
        assert runner.main([]) == 1

    def test_json_mode_emits_one_parseable_document(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        runner.main(["--json"])
        captured = capsys.readouterr()
        document = json.loads(captured.out)
        assert document["counts"]["total"] == 15
        assert 0.0 <= document["pass_rate"] <= 1.0
        assert len(document["redlines"]) == 15


def _all_verifiers(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """The primary verifier plus any ``also`` entries."""
    found: list[dict[str, Any]] = []
    if entry.get("verifier"):
        found.append(entry["verifier"])
    found.extend(entry.get("also", []))
    return found
