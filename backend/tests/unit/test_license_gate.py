"""The licence gate's judgement, tested (spec 031).

## ⭐ These tests did not exist and the gate was running anyway

``scripts/check_licenses.py`` had **no test file at all** — the only mention of
``classify`` anywhere in ``tests/`` was incidental. So the function that decides whether
this project may ship a dependency had never been asserted against anything, while the
gate ran it on every commit. ⭐ A guard is not the thing that is tested; the **judgement
inside** the guard is, and that was the untested part.

## The test the mutation check turns on

``test_or_and_disagree_for_one_pair`` is the only assertion here that a table written
upside down cannot survive: it states both operators over **the same** permissive/copyleft
pair in one place. Every other expression test passes with ``OR`` and ``AND`` reversed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_licenses import (
    Verdict,
    _iter_installed,
    _licence_field,
    _production_closure,
    _scan_npm,
    classify,
)


class TestClassifySingleTerm:
    """One licence, no expression operators."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("MIT", Verdict.OK),
            ("Apache-2.0", Verdict.OK),
            ("BSD-3-Clause", Verdict.OK),
            ("ISC", Verdict.OK),
            ("0BSD", Verdict.OK),
            # Weak copyleft warns — it is real, and it is not this project's problem yet.
            ("LGPL-3.0-only", Verdict.WARN),
            ("MPL-2.0", Verdict.WARN),
            # The inherited ordering, which a refactor must not "tidy":
            # LGPL contains no bare GPL, and AGPL does.
            ("GPL-3.0-only", Verdict.FAIL),
            ("AGPL-3.0-only", Verdict.FAIL),
        ],
    )
    def test_verdict(self, text: str, expected: Verdict) -> None:
        assert classify(text) is expected

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "UNKNOWN", "NONE", "UNLICENSED", "SEE LICENSE IN LICENSE.txt"],
    )
    def test_unreadable_warns_and_is_never_ok(self, text: str) -> None:
        """⭐ 'We could not determine the licence' is not 'the licence is fine'.

        WARN rather than OK is the whole point — an undeterminable licence that passes
        quietly is how an unknown dependency becomes a known problem after release.
        """
        assert classify(text) is Verdict.WARN


class TestClassifyExpressions:
    """SPDX expressions, where one mistake blocks a legitimate dependency."""

    def test_or_and_disagree_for_one_pair(self) -> None:
        """⭐ The assertion a reversed severity table cannot survive.

        ``OR`` is a **choice**: pick MIT and every obligation is discharged at once, so
        ``(MIT OR GPL-3.0-only)`` is fine. ``AND`` **stacks** obligations: choosing the
        permissive branch does not cancel the other one, so it is not an exemption.

        Real packages ship this exact string — ``dompurify`` is
        ``(MPL-2.0 OR Apache-2.0)`` — and a substring scan blocks it. ⭐ A guardrail that
        cries wolf gets switched off, so this case is the difference between a gate that
        survives contact with the ecosystem and one that gets deleted.
        """
        assert classify("(MIT OR GPL-3.0-only)") is Verdict.OK
        assert classify("(MIT AND GPL-3.0-only)") is Verdict.FAIL

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("MIT OR GPL-3.0-or-later", Verdict.OK),
            ("AGPL-3.0-only OR MIT", Verdict.OK),
            ("GPL-3.0-only OR AGPL-3.0-only", Verdict.FAIL),
            ("MIT AND MIT", Verdict.OK),
            ("MIT AND AGPL-3.0-only", Verdict.FAIL),
            ("LGPL-3.0-only OR MIT", Verdict.OK),
        ],
    )
    def test_operator_semantics(self, expression: str, expected: Verdict) -> None:
        assert classify(expression) is expected

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            # An exception **relaxes** the base terms, so the base decides. Deliberate
            # simplification (spec 031 §4): treating an exception as aggravating would
            # make a very permissive combination a false positive.
            ("Apache-2.0 WITH LLVM-exception", Verdict.OK),
            ("GPL-3.0-only WITH Classpath-exception-2.0", Verdict.FAIL),
        ],
    )
    def test_with_exception_uses_the_base_licence(self, expression: str, expected: Verdict) -> None:
        assert classify(expression) is expected

    @pytest.mark.parametrize(
        ("blob", "expected"),
        [
            # ⭐ The `|` join is **several candidates**, not one expression — the fields
            # `License`, `License-Expression` and the trove classifiers are alternatives,
            # and the strictest one wins because a copyleft claim among them still has to
            # be answered.
            ("MIT | License :: OSI Approved :: MIT License", Verdict.OK),
            ("MIT | GPL-3.0-only", Verdict.FAIL),
            ("MPL-2.0 | MIT", Verdict.WARN),
        ],
    )
    def test_field_join_takes_the_strictest_candidate(self, blob: str, expected: Verdict) -> None:
        assert classify(blob) is expected

    @pytest.mark.parametrize("expression", ["(MIT", "MIT)", "()", "MIT OR"])
    def test_malformed_expressions_degrade_rather_than_raise(self, expression: str) -> None:
        """⭐ A malformed field must produce a verdict, not an exception.

        The gate's job is to report. Crashing on a package.json typo would report nothing
        while *looking* like a gate failure, which is the worst of both.
        """
        assert isinstance(classify(expression), Verdict)


def _manifest(name: str, version: str, licence: object, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {"name": name, "version": version}
    if licence is not None:
        body["license"] = licence
    body.update(extra)
    return body


def _write(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")


class TestNpmScan:
    """The npm half, over a tree this test builds, so the numbers are checkable."""

    @pytest.fixture()
    def frontend(self, tmp_path: Path) -> Path:
        root = tmp_path / "frontend"
        _write(
            root / "package.json",
            {
                "name": "alphacouncil-frontend",
                "private": True,
                "dependencies": {"shipped-lib": "1.0.0"},
                "devDependencies": {"build-tool": "2.0.0"},
            },
        )
        modules = root / "node_modules"
        # A production dependency, plus the dependency **of** that dependency — the walk
        # has to be transitive, because a transitive dep ships even when only its parent
        # was declared.
        _write(modules / "shipped-lib" / "package.json", _manifest("shipped-lib", "1.0.0", "MIT"))
        _write(
            modules / "shipped-lib" / "node_modules" / "inner" / "package.json",
            _manifest("inner", "0.1.0", "ISC", dependencies={"missing-lib": "1.0.0"}),
        )
        # A devDependency and its own transitive dependency. Neither ships.
        _write(modules / "build-tool" / "package.json", _manifest("build-tool", "2.0.0", "MIT"))
        _write(
            modules / "build-tool" / "node_modules" / "helper" / "package.json",
            _manifest("helper", "0.0.1", "MIT"),
        )
        # A scoped package — ⭐ the shape a `*/package.json` glob cannot match.
        _write(
            modules / "@scope" / "scoped-lib" / "package.json",
            _manifest("@scope/scoped-lib", "1.1.0", "Apache-2.0"),
        )
        # npm's leftover temporary directories: dot-prefixed, not packages.
        _write(
            modules / ".chai-abc123" / "package.json",
            _manifest("chai-temp", "9.9.9", "GPL-3.0-only"),
        )
        return root

    def test_production_closure_is_transitive_not_top_level(self, frontend: Path) -> None:
        """⭐ Transitive dependencies ship even when only their parent was declared.

        ``helper`` is declared nowhere — it is reachable only through ``build-tool`` — so
        it must be outside the closure. ``inner`` is reachable through a declared
        dependency, so it must be inside. **Top-level counting gets this backwards**,
        which is why the gate walks rather than reading the manifest once.
        """
        closure, _ = _production_closure(frontend)
        assert "shipped-lib" in closure
        assert "inner" in closure
        assert "build-tool" not in closure
        assert "helper" not in closure

    def test_unresolvable_dependency_is_reported_not_dropped(self, frontend: Path) -> None:
        """⭐ A declared-but-uninstalled dependency becomes a WARN finding.

        Silently dropping it would make the scan's failure mode indistinguishable from
        success: the counts would look right and the gap would be invisible. That is
        exactly what a broken `npm ci` looks like.
        """
        closure, unresolved = _production_closure(frontend)
        assert unresolved == ["missing-lib"]
        findings, _ = _scan_npm(frontend)
        gaps = [f for f in findings if f.name == "missing-lib"]
        assert len(gaps) == 1
        assert gaps[0].verdict is Verdict.WARN
        assert gaps[0].shipped is True
        assert "missing-lib" not in closure

    def test_scoped_packages_are_found_and_leftovers_are_not(self, frontend: Path) -> None:
        """⭐ 127 of this project's packages are ``@scope/name``.

        They live two levels deep, so a ``node_modules/*/package.json`` glob misses every
        one of them — and ``@milkdown/*`` and ``@playwright/*`` are **direct** dependencies.
        The dot-prefixed temporary directory is the opposite case: it is not a package and
        carries a GPL licence that must not be reported.
        """
        names = {name for name, _ in _iter_installed(frontend / "node_modules")}
        assert "@scope/scoped-lib" in names
        assert "chai-temp" not in names
        findings, _ = _scan_npm(frontend)
        assert {f.name for f in findings if f.verdict is Verdict.FAIL} == set()

    def test_dev_only_copyleft_is_reported_but_not_shipped(self, frontend: Path) -> None:
        """⭐ A GPL build tool is visible without blocking.

        The distinction is not a technicality: a build tool is never in the bundle, so it
        creates no distribution obligation — which is why the ecosystem's own scanner has
        a ``--production`` flag. But "not shipped" expires the moment someone moves a
        dependency into ``dependencies``, so the finding still has to be on the page.
        """
        _write(
            frontend / "node_modules" / "gpl-tool" / "package.json",
            _manifest("gpl-tool", "3.0.0", "GPL-3.0-only"),
        )
        findings, _ = _scan_npm(frontend)
        tool = next(f for f in findings if f.name == "gpl-tool")
        assert tool.verdict is Verdict.FAIL
        assert tool.shipped is False
        assert tool.ecosystem == "npm"

        # And once it *is* declared as a runtime dependency, it ships and blocks.
        manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
        deps = dict(manifest["dependencies"])
        deps["gpl-tool"] = "3.0.0"
        (frontend / "package.json").write_text(
            json.dumps({**manifest, "dependencies": deps}), encoding="utf-8"
        )
        findings, _ = _scan_npm(frontend)
        assert next(f for f in findings if f.name == "gpl-tool").shipped is True

    def test_one_package_two_versions_is_two_findings(self, frontend: Path) -> None:
        """Each installed version is a licence to read; the same version twice is one."""
        _write(
            frontend / "node_modules" / "shipped-lib" / "package.json",
            _manifest("shipped-lib", "1.2.0", "MIT"),
        )
        _write(
            frontend / "node_modules" / "dup" / "node_modules" / "shipped-lib" / "package.json",
            _manifest("shipped-lib", "1.0.0", "GPL-3.0-only"),
        )
        findings, _ = _scan_npm(frontend)
        versions = sorted(f.version for f in findings if f.name == "shipped-lib")
        assert versions == ["1.0.0", "1.2.0"]

    def test_no_metadata_is_warn_not_ok(self, frontend: Path) -> None:
        _write(
            frontend / "node_modules" / "bare" / "package.json",
            _manifest("bare", "1.0.0", None),
        )
        findings, _ = _scan_npm(frontend)
        bare = next(f for f in findings if f.name == "bare")
        assert bare.verdict is Verdict.WARN
        assert bare.licence == "(no licence metadata)"


class TestLicenceField:
    """npm enforces no shape for ``license``; all of these are real."""

    def test_object_form(self) -> None:
        assert _licence_field({"license": {"type": "MIT", "url": "https://x/y"}}) == "MIT"

    def test_legacy_array_form(self) -> None:
        assert _licence_field({"licenses": [{"type": "ISC"}, {"type": "MIT"}]}) == "ISC | MIT"

    def test_expression_survives_verbatim(self) -> None:
        """⭐ The `|` join must not mangle a parenthesis expression.

        ``dompurify`` is ``(MPL-2.0 OR Apache-2.0)``. If the join happened inside the
        parentheses the expression would parse as two separate terms and the ``OR`` would
        be lost — turning a legitimate dual licence into two independent claims.
        """
        assert _licence_field({"license": "(MPL-2.0 OR Apache-2.0)"}) == "(MPL-2.0 OR Apache-2.0)"

    def test_absent(self) -> None:
        assert _licence_field({}) == "(no licence metadata)"

    def test_unparseable_manifest_is_empty(self, tmp_path: Path) -> None:
        broken = tmp_path / "package.json"
        broken.write_text("{not json", encoding="utf-8")
        from check_licenses import _read_manifest

        assert _read_manifest(broken) == {}
