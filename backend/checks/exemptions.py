"""The ``# noqa: S-01 -- <reason>`` exemption mechanism.

Split out of :mod:`checks.framework`. Two forms, both documented in
``.ai/checks/static/README.md`` §4.4:

* **line-level** — a trailing comment on a line of code, silencing a finding
  reported against *that* line;
* **file-level** — a comment on a line of its own within the first
  :attr:`Suppressions.FILE_SCOPE_LINES` lines, silencing the rule for the whole
  file.

The distinction is "is the comment alone on its line", not "is it before any
code". The positional version was the first attempt and it made a line-1
trailing comment silently behave like a file-level one — a difference nobody
would ever guess. "Standalone comment near the top" is a rule a reader can
apply without knowing the implementation.

This is the one place in the package where a regex *is* correct: a ``# noqa``
is comment text, so there is no parse tree to walk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from checks.models import CheckResult, Issue, Severity

if TYPE_CHECKING:  # pragma: no cover - annotation-only import
    from checks.scan import ScanContext

__all__ = [
    "Exemption",
    "Suppressions",
    "apply_exemptions",
    "rule_id_for",
    "split_target",
]

_NOQA_RE = re.compile(
    r"#\s*noqa:\s*"
    r"(?P<ids>[A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)"
    r"(?:\s*--\s*(?P<reason>.*?))?"
    r"\s*$"
)


@dataclass(frozen=True, slots=True)
class Exemption:
    """One ``# noqa`` for one rule on one line."""

    check_id: str
    lineno: int
    reason: str | None
    file_scope: bool = False


class Suppressions:
    """The ``# noqa`` exemptions declared in a single file."""

    FILE_SCOPE_LINES = 12

    def __init__(self, source: str) -> None:
        self._exemptions: list[Exemption] = []
        for lineno, line in enumerate(source.splitlines(), start=1):
            match = _NOQA_RE.search(line)
            if match is None:
                continue
            reason = (match.group("reason") or "").strip() or None
            standalone = line.lstrip().startswith("#")
            for raw in match.group("ids").split(","):
                self._exemptions.append(
                    Exemption(
                        raw.strip(),
                        lineno,
                        reason,
                        file_scope=standalone and lineno <= self.FILE_SCOPE_LINES,
                    )
                )

    def unreasoned(self) -> tuple[Exemption, ...]:
        """Exemptions that did not state why. These are findings, not passes."""
        return tuple(item for item in self._exemptions if item.reason is None)

    def covers(self, check_id: str, lineno: int | None) -> bool:
        """Whether an exemption silences ``check_id`` at ``lineno``."""
        for item in self._exemptions:
            if item.check_id != check_id:
                continue
            if item.file_scope:
                return True
            if lineno is not None and item.lineno == lineno:
                return True
        return False


def split_target(target: str | None) -> tuple[str | None, int | None]:
    """Split ``"backend/src/x.py:55"`` into its path and line parts."""
    if not target:
        return None, None
    path, _, line = target.rpartition(":")
    if not path:
        return target, None
    return (path, int(line)) if line.isdigit() else (target, None)


def rule_id_for(ctx: ScanContext, code: str) -> str | None:
    """Translate a finding's ``CHECK_*`` code into the rule id exemptions use.

    An exemption reads ``# noqa: S-01`` because that is what the document calls
    the rule; a finding carries ``CHECK_RAW_HTTP`` because that is what a log
    line and a bug report need. The registry is the bridge, which is why it is
    threaded through the scan context.
    """
    for meta in ctx.registry:
        if meta.code == code:
            return meta.check_id
    return None


def apply_exemptions(ctx: ScanContext, result: CheckResult) -> CheckResult:
    """Drop exempted findings and surface unreasoned exemptions.

    Runs *after* a rule has produced its raw findings, so a rule never needs to
    know that exemptions exist.

    An exemption **still works** when its reason is missing — the code is not
    left both broken and unsilenceable — but the missing reason is itself
    reported as an error. That combination is what makes "the reason is
    mandatory" a rule rather than a wish.

    Called once per rule, so a file containing an unreasoned exemption yields
    one copy of that finding per rule that opened it. The runner deduplicates
    before reporting, and attributes counts by error code rather than by
    accumulation, so the duplication never reaches a reader.
    """
    kept: list[Issue] = []
    for issue in result.issues:
        path_part, lineno = split_target(issue.target)
        path = ctx.repo_root / path_part if path_part else None
        if path is None or not path.is_file():
            kept.append(issue)
            continue
        rule_id = rule_id_for(ctx, issue.code) or issue.code
        if ctx.suppressions(path).covers(rule_id, lineno):
            continue
        kept.append(issue)

    for path in result.files:
        for item in ctx.suppressions(path).unreasoned():
            kept.append(
                Issue(
                    Severity.ERROR,
                    "CHECK_EXEMPTION_UNREASONED",
                    f"`# noqa: {item.check_id}` states no reason",
                    f"{ctx.rel(path)}:{item.lineno}",
                    "Write it as `# noqa: S-01 -- <why this is not the defect>`; "
                    "an exemption without a reason cannot be reviewed later.",
                )
            )

    result.issues = kept
    return result
