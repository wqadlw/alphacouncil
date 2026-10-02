"""The ordered list of rules.

Order is the order they run, and it is the order findings of **equal severity**
are reported in. ⭐ It is **not** a severity order, and it did not used to claim
to be: this docstring said 「P0 first, so the build fails on a red-line breach
before it reports a stray print」 ⭐ - ⭐ which was never what the list did ⭐
(``S-13`` is P0 and sits in the P2 block, deliberately, per
``.ai/checks/static/README.md`` §3.3) ⭐ and is not what enforces the promise
either. ⭐ ``checks/__main__.py`` sorts the **findings** by severity, ⭐ so a P0
breach is reported first whatever order its rule is in, ⭐ and the list order only
decides the sequence within one severity. ⭐ Both halves of that are asserted in
``test_static_checks.py``.

**Naming contract:** a rule's ``slug`` is the stem of its module, so
``check-append-only-triggers`` lives in ``checks/rules/check_append_only_triggers.py``.
:data:`MODULE_BY_ID` derives that mapping, and a test imports every module and
confirms its ``META`` is the one bound here — which is what stops a copy-paste
error in this file from silently disabling a rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from checks.framework import CheckMeta, CheckResult, ScanContext
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
    no_enum_drift,
    no_mojibake,
    no_prediction_field,
    no_print,
    no_raw_http,
    no_route_drift,
    time_cost_in_stop_loss,
    tool_encoding,
)


@dataclass(frozen=True, slots=True)
class Rule:
    """A rule module, bound explicitly.

    Explicit rather than discovered by scanning the package: the registry is
    then readable in one screen, and a rule accidentally left out shows up as a
    diff rather than as silence. ``S-12`` compares this list against
    ``.ai/checks/static/README.md`` in both directions.
    """

    meta: CheckMeta
    run: Callable[[ScanContext], CheckResult]


#: Seventeen rules, matching `.ai/checks/static/README.md` §3.
RULES: tuple[Rule, ...] = (
    Rule(no_raw_http.META, no_raw_http.run),
    Rule(no_boolean_state.META, no_boolean_state.run),
    Rule(no_prediction_field.META, no_prediction_field.run),
    Rule(check_append_only_triggers.META, check_append_only_triggers.run),
    Rule(check_error_codes.META, check_error_codes.run),
    Rule(no_client_supplied_id.META, no_client_supplied_id.run),
    Rule(home_no_return_rate.META, home_no_return_rate.run),
    Rule(immature_outcome_blank.META, immature_outcome_blank.run),
    Rule(time_cost_in_stop_loss.META, time_cost_in_stop_loss.run),
    Rule(no_mojibake.META, no_mojibake.run),
    Rule(no_print.META, no_print.run),
    Rule(no_bare_except.META, no_bare_except.run),
    Rule(check_doc_sync.META, check_doc_sync.run),
    Rule(tool_encoding.META, tool_encoding.run),
    # S-16 (spec 049). ★ Placed before S-14 because it **constructs the app** to read
    # `openapi.json`, so a syntax error in the app would make it skip rather than mask
    # anything — and a rule that skips silently is the failure mode its own docstring
    # warns about.
    Rule(no_enum_drift.META, no_enum_drift.run),
    # S-17 (spec 050). Also constructs the app, for the same reason as S-16 and with the
    # same guard: it **skips** rather than reports when the app cannot be built.
    Rule(no_route_drift.META, no_route_drift.run),
    # S-14 (spec 032). Last because it is the only rule that reads git rather
    # than the working tree, and it should not mask a syntax error.
    Rule(git_tracked.META, git_tracked.run),
)

#: Rule id -> the module that must implement it.
MODULE_BY_ID: dict[str, str] = {
    rule.meta.check_id: f"checks.rules.{rule.meta.slug.replace('-', '_')}" for rule in RULES
}


def registry_meta() -> tuple[CheckMeta, ...]:
    """The metadata of every rule, for ``ScanContext`` and for ``S-12``."""
    return tuple(rule.meta for rule in RULES)


__all__ = ["MODULE_BY_ID", "RULES", "Rule", "registry_meta"]
