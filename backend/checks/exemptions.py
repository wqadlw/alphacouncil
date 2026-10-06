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


def apply_exemptions(
    ctx: ScanContext, result: CheckResult, check_id: str
) -> CheckResult:
    """Drop exempted findings and surface unreasoned exemptions.

    Runs *after* a rule has produced its raw findings, so a rule never needs to
    know that exemptions exist.

    An exemption **still works** when its reason is missing — the code is not
    left both broken and unsilenceable — but the missing reason is itself
    reported as an error. That combination is what makes "the reason is
    mandatory" a rule rather than a wish.

    ⭐⭐⭐ **`check_id` is required, and it was previously *guessed* from the finding's
    code ⭐⭐⭐ — which is unsound, and silently so.** ⭐⭐ An exemption reads
    ``# noqa: D-22`` because that is what the document calls the rule; ⭐⭐ a finding
    carries ``CHECK_DATA_INTEGRITY`` because that is what a bug report needs. ⭐⭐⭐

    ⭐⭐ **But all four data rules share that one code** ⭐⭐ (S-05 requires a code to be a
    registered *category*, ⭐⭐ so a code can never identify a rule ⭐⭐ — ⭐⭐ and
    ⭐⭐ `rule_id_for` returned the **first** registry entry whose code matched ⭐⭐ —
    ⭐⭐ so a ``# noqa: D-22`` in `decision_orphan.py` would have silenced D-02's finding
    ⭐⭐ and left D-22's untouched). ⭐⭐⭐

    ⭐⭐⭐ **Measured consequence:** the old `_write_human` mis-attributed D-02's finding
    ⭐⭐⭐ to `D-22` ⭐⭐⭐ — ⭐⭐ **the same wrong answer, from the same wrong premise, in
    ⭐⭐⭐ the second place that asked a shared code to name a rule.** ⭐⭐⭐ The guessing
    ⭐⭐⭐ function is deleted rather than fixed ⭐⭐⭐ because every caller now has the real
    ⭐⭐⭐ id in hand ⭐⭐⭐ and leaving it exported would leave the trap armed.
    """
    kept: list[Issue] = []
    for issue in result.issues:
        path_part, lineno = split_target(issue.target)
        path = ctx.repo_root / path_part if path_part else None
        if path is None or not path.is_file():
            kept.append(issue)
            continue
        if ctx.suppressions(path).covers(check_id, lineno):
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
