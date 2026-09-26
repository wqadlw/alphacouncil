"""Shared machinery for the static checks — the single import face.

The static checks catch a class of defect that tests structurally *cannot*:
**code that should not exist**. A test can prove that the paths it exercises
behave correctly; it can never prove that nobody added a second HTTP client.

Design rules, from ``.ai/checks/static/README.md`` §4:

1. **AST, never regex.** A regex over source text is defeated by a string
   literal, a comment, or a line break. Every Python rule in this package walks
   a parse tree. (The one exception is parsing ``# noqa`` comments — that *is*
   comment text, so there is nothing else to parse.)
2. **Every rule has its own test** — one fixture that must be reported, one that
   must stay silent. Without that, a rule is indistinguishable from a rule that
   never runs; this repository has already paid for that lesson once (see
   ``.ai/logs/changes/2026-09-26-s1-data-layer.md``).
3. **One diagnostic envelope** (``.ai/error-codes.md`` §1):
   ``{severity, code, message, target, fix}``. ``fix`` may be ``None`` — not
   every problem can be repaired automatically, and pretending otherwise is
   worse than admitting it.
4. **Exemptions are explicit and reasoned**: ``# noqa: S-01 -- <reason>``. The
   reason is mandatory; an unreasoned exemption is itself a finding, otherwise
   "explicit exemption" degrades into "silent suppression".
5. **A rule never imports the code it inspects.** Rules read a source tree, not
   a running application.

Two shape decisions worth knowing about:

* ``.ai/checks/README.md`` §2.1 sketches an ``Issue`` with ``entity`` / ``label``
  / ``available_fixes`` while pointing at the envelope in ``.ai/error-codes.md``
  for the authoritative shape. The envelope wins: ``entity`` becomes ``target``,
  ``label`` becomes ``message``, and ``available_fixes`` collapses to ``fix``,
  where ``fix=None`` is the "no automatic repair exists" case.
* ``.ai/error-codes.md`` §3 says exit code ``0`` means "ran to completion —
  *including* when problems were found". That is right for an inspector and
  unusable as a CI gate, so gate mode is opt-in via ``--strict`` rather than a
  change to the documented contract.

**This module is a facade.** It used to hold all of the above itself and grew
past the 400-line ceiling (constitution 7.2), so the implementation now lives in
four siblings and this file only re-exports:

============================ ====================================================
:mod:`checks.models`         the envelope: ``Issue`` / ``CheckMeta`` /
                             ``CheckResult`` / ``Severity`` / ``Rule``
:mod:`checks.scan`           ``ScanContext`` and ``format_target``
:mod:`checks.exemptions`     ``# noqa`` parsing and application
:mod:`checks.ast_utils`      the tree helpers
============================ ====================================================

Rule modules import from here and do not need to care which sibling a name came
from. The import surface is frozen by ``__all__``; adding a name to it is the
only way to widen it.
"""

from __future__ import annotations

from checks.ast_utils import (
    annotation_idents,
    call_target,
    contains_token,
    declared_fields,
    dotted,
    enclosing_function,
    parent_map,
    snake_tokens,
)
from checks.exemptions import (
    Exemption,
    Suppressions,
    apply_exemptions,
    rule_id_for,
    split_target,
)
from checks.models import (
    CheckMeta,
    CheckResult,
    Issue,
    Rule,
    Severity,
)
from checks.scan import (
    ScanContext,
    format_target,
)

#: Sorted (RUF022), because a hand-maintained order drifts. Which sibling each
#: name comes from is the table in the module docstring above.
__all__ = [
    "CheckMeta",
    "CheckResult",
    "Exemption",
    "Issue",
    "Rule",
    "ScanContext",
    "Severity",
    "Suppressions",
    "annotation_idents",
    "apply_exemptions",
    "call_target",
    "contains_token",
    "declared_fields",
    "dotted",
    "enclosing_function",
    "format_target",
    "parent_map",
    "rule_id_for",
    "snake_tokens",
    "split_target",
]
