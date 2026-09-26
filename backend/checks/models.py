"""The data shapes a static check produces and consumes.

Split out of :mod:`checks.framework` when that module crossed the 400-line
limit in ``.ai/decisions`` (constitution 7.2). This module holds only the
envelope and the result types, and imports nothing from the rest of the
package — so it can never participate in an import cycle.

``.ai/checks/README.md`` §2.1 sketches an ``Issue`` with ``entity`` / ``label``
/ ``available_fixes`` while pointing at ``.ai/error-codes.md`` §1 for the
authoritative shape. The envelope wins: ``entity`` becomes ``target``,
``label`` becomes ``message``, and ``available_fixes`` collapses to ``fix``,
where ``fix=None`` is the "no automatic repair exists" case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover - annotation-only import
    from checks.scan import ScanContext

__all__ = [
    "CheckMeta",
    "CheckResult",
    "Issue",
    "Rule",
    "Severity",
]


class Severity(StrEnum):
    """How loudly a finding should be reported."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Issue:
    """One finding, shaped as the envelope in ``.ai/error-codes.md`` §1.

    ``code`` must be a registered ``CHECK_*`` code; ``S-05`` (and the
    registration half of ``S-12``) keep the document and the enum in step.
    ``fix`` is ``None`` when no automatic repair exists — that is a legal and
    expected value, not an omission.
    """

    severity: Severity
    code: str
    message: str
    target: str | None = None
    fix: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Serialise to exactly the five envelope keys."""
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "fix": self.fix,
        }

    def render(self) -> str:
        """One human-readable block, for the stderr summary."""
        head = f"{self.severity.value}: {self.code}: {self.message}"
        if self.target:
            head += f"\n      at {self.target}"
        if self.fix:
            head += f"\n      fix: {self.fix}"
        return head


@dataclass(frozen=True, slots=True)
class CheckMeta:
    """Identity of a rule. The ``check_id`` must match ``.ai/checks/static/README.md``.

    ``code`` is the ``CHECK_*`` code the rule emits. It lives here as well as in
    the rule module because the framework needs it: an exemption is written
    ``# noqa: S-01``, while a finding carries ``CHECK_RAW_HTTP``, and something
    has to translate between the two.
    """

    check_id: str  # "S-01"
    slug: str  # "no-raw-http"
    title: str
    priority: str  # "P0" | "P1" | "P2"
    code: str = ""  # "CHECK_RAW_HTTP"


@dataclass(slots=True)
class CheckResult:
    """What a rule observed.

    ``skipped`` non-``None`` means the rule **could not run**, which is not the
    same as passing. ``.ai/checks/README.md`` maintenance rule 3 and the
    T-19 decision both rest on that distinction: a check with nothing to scan
    must say so rather than report a clean bill of health.
    """

    issues: list[Issue] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    skipped: str | None = None

    @property
    def scanned(self) -> int:
        """How many files the rule actually opened."""
        return len(self.files)

    def error(
        self, code: str, message: str, *, target: str | None = None, fix: str | None = None
    ) -> None:
        """Append an ``error``-severity finding."""
        self.issues.append(Issue(Severity.ERROR, code, message, target, fix))

    def warn(
        self, code: str, message: str, *, target: str | None = None, fix: str | None = None
    ) -> None:
        """Append a ``warning``-severity finding."""
        self.issues.append(Issue(Severity.WARNING, code, message, target, fix))

    def note(
        self, code: str, message: str, *, target: str | None = None, fix: str | None = None
    ) -> None:
        """Append an ``info``-severity finding — worth listing, not a defect.

        ``info`` exists so that "this is declared and not yet wired up" can be
        reported without training people to ignore warnings.
        """
        self.issues.append(Issue(Severity.INFO, code, message, target, fix))


class Rule(Protocol):
    """The shape every rule module's ``run`` must have."""

    META: CheckMeta

    def run(self, ctx: ScanContext) -> CheckResult: ...
