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

import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import distributions

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
    """One distribution and what we made of its licence."""

    name: str
    version: str
    licence: str
    verdict: Verdict


def classify(text: str) -> Verdict:
    """Classify a licence blob.

    Order matters: AGPL is checked before GPL because ``AGPL`` contains the
    substring ``GPL``, and ``LGPL`` must not be caught by the plain-GPL rule.
    """
    upper = text.upper().strip()
    if not upper or upper in {"UNKNOWN", "NONE"}:
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


def scan() -> list[Finding]:
    """Return one finding per installed distribution, sorted by name."""
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
            )
        )
    return sorted(findings, key=lambda f: f.name.lower())


def main() -> int:
    """Print the report and return a process exit code."""
    findings = scan()
    failures = [f for f in findings if f.verdict is Verdict.FAIL]
    warnings = [f for f in findings if f.verdict is Verdict.WARN]

    print(f"scanned {len(findings)} installed distributions")

    for finding in failures:
        print(f"  FAIL  {finding.name} {finding.version}  ->  {finding.licence[:90]}")
    for finding in warnings:
        print(f"  warn  {finding.name} {finding.version}  ->  {finding.licence[:90]}")

    ok = len(findings) - len(failures) - len(warnings)
    print(f"  ok={ok}  warn={len(warnings)}  fail={len(failures)}")

    if failures:
        print("")
        print("✗ copyleft dependency detected — see ADR-0024 (L-06)")
        print("  Do not ship this. Replace the dependency or re-implement the mechanism.")
        return 1
    if warnings:
        print("")
        print("note: warnings do not fail the gate, but 'unknown' is not 'fine'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
