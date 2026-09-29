"""Dependency licence gate (ADR-0024 · L-06).

Scans **installed** distributions for copyleft licences.

Why this is a gate and not a review step: a licence mistake is not found by
reading code. It is found later, by someone else, usually with a lawyer. The
knowledge-management projects we studied are all AGPL/GPL for exactly this
reason — the licence is the moat — so this is a live risk for us, not a
theoretical one.

Verdicts:

* **fail** — AGPL, or GPL proper. Copyleft that would reach our own source.
* **warn** — LGPL (weak copyleft), MPL, or **an undeterminable licence**.
  ⚠️ "We could not determine the licence" is *not* the same as "the licence is
  fine", so it warns rather than passing quietly.
* **ok** — MIT, Apache-2.0, BSD, ISC, PSF, Zlib, CC0, Unlicense, public domain.

⚠️ **Scope limit, stated rather than hidden**: this scans what is *installed*.
A declared-but-not-installed dependency is invisible here.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import distributions
from pathlib import Path

from _console import use_utf8

PERMISSIVE = (
    "MIT",
    "APACHE",
    "BSD",
    "ISC",
    "PSF",
    "PYTHON SOFTWARE FOUNDATION",
    "ZLIB",
    "CC0",
    "PUBLIC DOMAIN",
    "UNLICENSE",
    "0BSD",
)

# Weak copyleft: worth knowing about, not worth failing the build over.
WEAK_COPYLEFT = ("LGPL", "MOZILLA PUBLIC", "MPL-2", "MPL 2")

_SELF = "alphacouncil"


class Verdict(StrEnum):
    """Outcome of classifying one distribution's licence."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Finding:
    """One distribution and what we made of its licence.

    ``ecosystem`` and ``shipped`` exist because the exit code depends on them: ⭐ only a
    copyleft finding among **shipped** packages may fail the gate (spec 031 §2.1), and a
    reader has to be able to tell which world a finding came from.
    """

    name: str
    version: str
    licence: str
    verdict: Verdict
    ecosystem: str = "python"
    shipped: bool = True
    #: ``False`` for a declared dependency with nothing on disk. It still occupies a slot
    #: that would ship, so it is counted as shipping — ⭐ but it is not a package, and
    #: adding it to the package total would print a number nobody can reconcile.
    installed: bool = True


#: **Strictness**, lowest first, so 「least strict branch」 is ``min`` and 「most strict
#: branch」 is ``max``. That lets ``OR`` and ``AND`` be one line each instead of a
#: hand-written if-chain over three verdicts.
#:
#: ⭐ **The direction of this table is load-bearing and nothing checks it.** Written the
#: other way round it looks identical, ``min``/``max`` still return a well-typed
#: ``Verdict``, and both operators silently invert — which is exactly what happened the
#: first two times this was written. The guard is a test that asserts *both* operators on
#: one permissive/copyleft pair: ``(MIT OR GPL-3.0-only)`` is ``ok`` while
#: ``(MIT AND GPL-3.0-only)`` is ``fail``. ⭐ Any test checking only one of them passes
#: with the table upside down.
_STRICTNESS: dict[Verdict, int] = {Verdict.OK: 0, Verdict.WARN: 1, Verdict.FAIL: 2}

#: Fields ``_licence_text`` joins into one string. **Not** an SPDX separator and must
#: never be read as one: the joined value is *several candidates*.
_FIELD_SPLIT = re.compile(r"\s*\|\s*")

#: ``OR`` / ``AND`` outside parentheses. Inside them the split would cut a nested
#: expression in half, which is why the alternatives are peeled outermost-first.
_SPLIT_OR = re.compile(r"\s+OR\s+", re.IGNORECASE)
_SPLIT_AND = re.compile(r"\s+AND\s+", re.IGNORECASE)

#: ``<licence> WITH <exception>``. The exception is kept out of the classification and
#: left in the reported text, so a human can still see it.
_STRIP_WITH = re.compile(r"\s+WITH\s+.*$", re.IGNORECASE)


def _unwrap(expression: str) -> str:
    """Drop one layer of surrounding parentheses.

    Peeling outermost-first, and only while the parentheses actually pair, means a
    malformed field like ``(MIT`` degrades to ``MIT`` rather than to nothing.
    """
    text = expression.strip()
    while text.startswith("(") and text.endswith(")"):
        inner = text[1:-1].strip()
        # Only unwrap when the leading "(" is closed by that final ")".
        if inner.count("(") != inner.count(")"):
            return text
        text = inner
    return text


def _classify_term(term: str) -> Verdict:
    """Classify one licence term — no expression operators.

    The ordering is inherited unchanged and is load-bearing: ``AGPL`` contains the
    substring ``GPL`` and ``LGPL`` must not be caught by the plain-GPL rule. ⭐ It is
    deliberately not part of the expression work; a refactor that 「tidied」 this order
    would silently start passing LGPL.
    """
    upper = _STRIP_WITH.sub("", term).upper().strip()
    if not upper or upper in {"UNKNOWN", "NONE", "UNLICENSED"}:
        return Verdict.WARN
    if "AGPL" in upper:
        return Verdict.FAIL
    # A bare GPL, but not LGPL: the character before G decides it.
    if re.search(r"(?<!L)GPL", upper):
        return Verdict.FAIL
    if any(marker in upper for marker in WEAK_COPYLEFT):
        return Verdict.WARN
    if any(marker in upper for marker in PERMISSIVE):
        return Verdict.OK
    return Verdict.WARN


def _classify_expression(expression: str) -> Verdict:
    """Classify an SPDX expression, recursing innermost-first.

    ``AND`` is tested before ``OR`` and both before falling through to a single term.
    ⭐ That order is what makes ``MIT AND GPL`` and ``MIT OR GPL`` **different answers**,
    which is the entire point: a parser that only ever reported 「is any branch
    permissive」 would satisfy every single-term test and still be wrong here.
    """
    text = _unwrap(expression)
    for splitter, pick in ((_SPLIT_AND, max), (_SPLIT_OR, min)):
        parts = splitter.split(text)
        if len(parts) > 1:
            verdicts = [_classify_expression(part) for part in parts]
            # ⭐ The key is load-bearing and easy to drop. `Verdict` is a `StrEnum`, so
            # min/max without it would order by *string value* — "fail" < "ok" < "warn"
            # — silently inverting both operators: `OR` would take the strictest branch
            # and `AND` the loosest. That is legal, well-typed, and exactly backwards.
            return pick(verdicts, key=_STRICTNESS.__getitem__)
    return _classify_term(text)


def classify(text: str) -> Verdict:
    """Classify a licence blob.

    ⭐ **Field separator first, operators second.** A blob joined with ``" | "`` is
    several *candidates* (``License``, ``License-Expression``, trove classifiers), not
    one expression — treating it as an expression asks whether the whole join contains
    GPL, which is a question with no answer. When several candidates are present the
    **strictest wins**, mirroring what ``AND`` means: every field that states a licence
    is a claim about the distribution, and a copyleft claim among them is a claim that
    has to be answered. ⭐ Swapping this order raises nothing — the result is merely
    wrong — which is why the order is stated here and not left to be rediscovered.
    """
    candidates = [part for part in _FIELD_SPLIT.split(text.strip()) if part]
    if len(candidates) > 1:
        # ⭐ The same `key` as in `_classify_expression`, and for the same reason: this
        # was written first *without* it, so the join below reported `ok` for
        # `MIT | GPL-3.0-only` while every operator case was already correct. ⭐ Fixing
        # one call site of `min`/`max` on a `StrEnum` and leaving the second is how a
        # bug survives a fix — **grep for the pattern, not for the mistake.**
        return max(
            (_classify_expression(part) for part in candidates),
            key=_STRICTNESS.__getitem__,
        )
    return _classify_expression(text)


def _licence_text(dist_metadata: object) -> str:
    """Collect every licence-ish field a distribution may expose.

    Metadata is inconsistent across tools: some write ``License``, newer ones
    write ``License-Expression``, and many only expose a trove classifier.
    Reading just one of them would miss licences.
    """
    get = dist_metadata.get  # type: ignore[attr-defined]
    parts: list[str] = []
    for key in ("License", "License-Expression"):
        value = get(key)
        if isinstance(value, str):
            parts.append(value)
    classifiers = get("Classifier") or []
    if isinstance(classifiers, str):
        classifiers = [classifiers]
    parts.extend(c for c in classifiers if isinstance(c, str) and c.startswith("License"))
    return " | ".join(parts)


#: Where the frontend lives, derived from this file rather than from the cwd: the gate runs
#: from ``backend/`` and the tests do too, and a scan that only works from one directory is
#: a scan that will be skipped.
_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

_SELF_NPM = "alphacouncil-frontend"


def _iter_installed(node_modules: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(name, manifest_path)`` for every installed package, scoped ones included.

    ⭐ **The trap this exists to avoid**: ``node_modules.glob('*/package.json')`` finds 153
    packages and misses every one of the 127 ``@scope/name`` ones, because a scoped
    package's directory is two levels deep. Scoping is not cosmetic here — ``@milkdown/*``
    and ``@playwright/*`` are direct dependencies. Entries beginning with ``.`` are skipped
    too: npm leaves temporary directories behind (``. chai-jmrcRiVS``) that are not
    installable packages.

    Nested ``node_modules`` — version conflicts, 8 of them here — are recursed into, because
    a package that received its own copy is a package that will be bundled.
    """
    if not node_modules.is_dir():
        return
    for entry in sorted(node_modules.iterdir()):
        if entry.name.startswith(".") or entry.is_symlink():
            # A symlink points at something already scanned; a dot-name is npm's leftover.
            continue
        if entry.name.startswith("@"):
            for scoped in sorted(entry.iterdir()):
                if not scoped.name.startswith(".") and (scoped / "package.json").is_file():
                    yield f"{entry.name}/{scoped.name}", scoped / "package.json"
        elif entry.is_dir() and (entry / "package.json").is_file():
            yield entry.name, entry / "package.json"
        yield from _iter_installed(entry / "node_modules")


def _read_manifest(path: Path) -> dict[str, object]:
    """Parse one ``package.json``, treating anything unparseable as empty.

    ⭐ A malformed manifest must not stop the scan. The gate's job is to report, and a
    crash reports nothing at all while looking like a failure.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _licence_field(manifest: dict[str, object]) -> str:
    """Read npm's several licence-ish fields into one ``" | "`` blob.

    npm enforces no shape here. ``license`` is usually a string but may legally be
    ``{"type": ..., "url": ...}``; ``licenses`` is an array; ``private: true`` packages may
    have none. ⭐ All of them are joined with ``" | "``, which is what ``classify`` already
    takes the strictest view of.
    """
    parts: list[str] = []
    field = manifest.get("license")
    if isinstance(field, str):
        parts.append(field)
    elif isinstance(field, dict) and isinstance(field.get("type"), str):
        parts.append(field["type"])
    legacy = manifest.get("licenses")
    if isinstance(legacy, list):
        parts.extend(
            entry["type"]
            for entry in legacy
            if isinstance(entry, dict) and isinstance(entry.get("type"), str)
        )
    return " | ".join(parts) if parts else "(no licence metadata)"


def _string_keys(value: object) -> list[str]:
    """Return the string keys of a mapping-typed metadata field, or nothing.

    `_read_manifest` returns ``dict[str, object]``, so ``mypy`` is right that ``.get()``
    may hand back something with no ``__iter__``. Narrowing lives here, once, because it
    is needed in two places inside the closure walk — ⭐ and a mistake like that, fixed at
    one of its two call sites, is how the other one survives.
    """
    return [key for key in value if isinstance(key, str)] if isinstance(value, dict) else []


def _production_closure(frontend: Path) -> tuple[set[str], list[str]]:
    """Return ``(names that ship, names that could not be resolved)``.

    Walks ``dependencies`` transitively. ⭐ Not the top-level list: a package reachable
    only through a ``devDependency`` does not ship either, and neither do its own
    dependencies — which is the whole reason ``--production`` exists in the ecosystem's
    tooling (spec 031 §2.1).
    """
    root = _read_manifest(frontend / "package.json")
    manifests: dict[str, dict[str, object]] = {}
    locations: dict[str, list[Path]] = {}
    for name, path in _iter_installed(frontend / "node_modules"):
        manifests.setdefault(name, _read_manifest(path))
        locations.setdefault(name, []).append(path)

    closure: set[str] = set()
    unresolved: set[str] = set()
    queue = _string_keys(root.get("dependencies"))
    while queue:
        name = queue.pop()
        if name in closure or name in unresolved:
            continue
        manifest = manifests.get(name)
        if manifest is None:
            # ⭐ Reported, never dropped (spec 031 §5): a declared dependency with no
            # manifest on disk is exactly what a failed `npm ci` leaves behind, and
            # dropping it silently would make the scan's failure mode indistinguishable
            # from success.
            unresolved.add(name)
            continue
        closure.add(name)
        # ⭐ Every package admitted expands its own declarations, **whichever signal
        # admitted it**. An earlier version expanded only on the declared path, so a
        # package pulled in by nesting had its dependencies silently skipped — and the
        # report looked exactly as healthy as it had always looked.
        queue.extend(_string_keys(manifest.get("dependencies")))
        # ⭐ **Second signal: a copy physically inside a shipped package ships.** npm nests
        # a package because its parent needs it, so the directory is evidence — and a
        # directory is a fact where a `dependencies` field is a claim (spec 031 §8).
        #
        # Needed *and* insufficient alone: nesting cannot see a hoisted transitive
        # dependency, and declarations cannot see an undeclared nested copy. Each covers
        # the other's blind spot, which is why both are here.
        #
        # `.parent`, because `is_relative_to` compares **path components**, not string
        # prefixes: one file is never relative to another file in the same directory, and
        # `node_modules/a/...` is correctly not relative to `node_modules/ab`.
        mine = [path.parent for path in locations.get(name, [])]
        for other, paths in locations.items():
            if other not in closure and any(
                inner.is_relative_to(outer) for inner in paths for outer in mine
            ):
                queue.append(other)
    return closure, sorted(unresolved)


def _scan_npm(frontend: Path) -> tuple[list[Finding], int]:
    """Return ``(findings per installed npm package, size of the production closure)``."""
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    closure, unresolved = _production_closure(frontend)
    for name, path in _iter_installed(frontend / "node_modules"):
        if not name or name == _SELF_NPM:
            continue
        manifest = _read_manifest(path)
        raw = manifest.get("version")
        version = raw if isinstance(raw, str) and raw else "?"
        # ⭐ Dedupe on name **and** version: one package at two versions is two licences to
        # read; the same version listed twice is one.
        if (name, version) in seen:
            continue
        seen.add((name, version))
        text = _licence_field(manifest)
        findings.append(
            Finding(
                name=name,
                version=version,
                licence=text,
                verdict=classify(text),
                ecosystem="npm",
                shipped=name in closure,
            )
        )
    for name in unresolved:
        # ⭐ Reported, never dropped — a name in `dependencies` with no manifest on disk is
        # exactly what a broken install hides, and dropping it silently would make the
        # scan's failure mode indistinguishable from success.
        findings.append(
            Finding(
                name=name,
                version="?",
                licence="(in dependencies but not installed)",
                verdict=Verdict.WARN,
                ecosystem="npm",
                shipped=True,
                installed=False,
            )
        )
    return sorted(findings, key=lambda f: (f.name.lower(), f.version)), len(closure)


def scan_python() -> list[Finding]:
    """Return one finding per installed Python distribution, sorted by name."""
    findings: list[Finding] = []
    for dist in distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if not name or name.lower().replace("-", "_") == _SELF:
            continue
        text = _licence_text(dist.metadata)
        findings.append(
            Finding(
                name=name,
                version=dist.version or "?",
                licence=text or "(no licence metadata)",
                verdict=classify(text),
                ecosystem="python",
                shipped=True,
            )
        )
    return sorted(findings, key=lambda f: f.name.lower())


def scan() -> list[Finding]:
    """Return one finding per dependency, in **both** ecosystems.

    ⭐ Python and npm go through the same ``classify``, so 「is this licence acceptable」
    has one implementation. A second scanner with its own vocabulary would give the
    project two verdicts for one question, and the one nobody remembers is the one that
    eventually gets edited.

    ⭐ **This is the seam.** ``main()`` reads the world through this function and through
    nothing else, which is what lets ``TestTheLicenceGate`` substitute a finding instead
    of installing a copyleft package. A ``main()`` that reaches for the subsystems
    directly has no seam, and the tests that depend on it start asserting against
    whatever is really installed.
    """
    npm, _ = _scan_npm(_FRONTEND)
    return scan_python() + npm


def main() -> int:
    """Print the report and return a process exit code.

    ⭐ **Only copyleft among packages that actually ship fails the gate** (spec 031
    §2.1). A GPL build tool, test runner or linter never reaches the bundle, so it
    creates no distribution obligation — the reason the ecosystem's own scanner has a
    ``--production`` flag. Those findings are still printed, because "not shipped" is a
    fact that expires: moving one dependency into ``dependencies`` is all it takes, and
    this line is what will notice.
    """
    # Before anything is printed, and on the branch that matters: the `✗` below
    # is only reached when a copyleft dependency is found, and on a cp936
    # console it raised `UnicodeEncodeError` there — so the tool meant to report
    # a licensing problem would instead report an encoding one
    # (`regressions/0004`).
    use_utf8()
    # ⭐ `scan()` is the only way this function learns anything. See its docstring.
    findings = scan()
    python_findings = [f for f in findings if f.ecosystem == "python"]
    npm_findings = [f for f in findings if f.ecosystem == "npm"]
    failures = [f for f in findings if f.verdict is Verdict.FAIL]
    warnings = [f for f in findings if f.verdict is Verdict.WARN]
    blocking = [f for f in failures if f.shipped]
    shipped = {f.name for f in npm_findings if f.shipped and f.installed}

    print(
        f"scanned {len(findings)} installed packages "
        f"({len(python_findings)} python, {len(npm_findings)} npm; "
        f"{len(shipped)} npm ship in the production closure)"
    )

    for finding in failures:
        note = "" if finding.shipped else "   <- dev only, does not ship"
        print(f"  FAIL  {finding.name} {finding.version}  ->  {finding.licence[:76]}{note}")
    for finding in warnings:
        print(f"  warn  {finding.name} {finding.version}  ->  {finding.licence[:76]}")

    ok = len(findings) - len(failures) - len(warnings)
    print(f"  ok={ok}  warn={len(warnings)}  fail={len(failures)}")

    if blocking:
        print("")
        print(f"\u2717 {len(blocking)} copyleft dependency would ship \u2014 ADR-0024 (L-06)")
        for finding in blocking:
            print(f"  {finding.name} {finding.version}: {finding.licence[:100]}")
        print("  Do not ship this. Replace the dependency or re-implement it.")
        return 1
    if failures:
        print("")
        print("note: copyleft exists in dev-only dependencies; none of them ship.")
    if warnings:
        print("")
        print("note: warnings do not fail the gate, but 'unknown' is not 'fine'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
