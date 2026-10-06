"""The ordered list of data checks.

# Why a second registry and not a second process

`dev.py` runs eleven gates, ⭐ and each one is **one command with one exit code**. ⭐ A second
runner would mean a second command, ⭐ and two exit codes for one question ⭐ — ⭐ and
`constitution.md:160-165` says the definition of done is a single `make check`.

⇒ ⭐ **Same process, second registry, one flag.** `python -m checks --data` reads
`DATA_RULES`; ⭐ `python -m checks` still reads `RULES` and nothing else. ⭐ Putting the data
rules into `RULES` itself would have made `check-static` open a database, ⭐ and
`check-static` is documented as 「静态检查 S-01..S-14」⭐ — ⭐ a gate whose name says *static*
has no business reading the reader's rows.

# The naming contract, enforced on this side too

`registry.py` binds each rule's `META` explicitly ⭐ "so a rule accidentally left out shows up
as a diff rather than as silence". ⭐ That silence is exactly what `status.md` B4 records for
the whole `data/` side ⭐ — ⭐ so this registry exists, ⭐ **and `test_response_drift.py` and
`test_data_rules.py` both import every module and confirm its `META` is the one bound here.**
⭐ A registry nothing checks is how twelve entries came to sit in `APPEND_ONLY_TABLES` for a
# table no migration creates.

# Why one `CHECK_*` code and not three

D-01, D-07 and D-22 are three instances of one thing ⭐ — an invariant the schema does not
enforce ⭐ — ⭐ and a data finding has no fixed shape to describe: ⭐ a static finding is a
*file*, ⭐ and a data finding is a *set of rows*. ⭐ The code therefore says what kind of thing
happened, ⭐ and the check id in the message says which invariant.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from checks.data_rules import (
    audit_detail_length,
    counter_evidence_blank,
    dangling_target,
    orphan_reference,
)
from checks.framework import CheckMeta, CheckResult, ScanContext


@dataclass(frozen=True, slots=True)
class DataRule:
    """A data check, bound explicitly. ⭐ The parallel of ``checks.registry.Rule`` ⭐ —
    ⭐ and it is spelled out rather than inherited ⭐ because the two registries are read by
    # different runners ⭐ and ⭐ a shared base for two modules with one user each ⭐ is the
    # kind of abstraction ``constitution.md:145`` tells you not to build."""

    meta: CheckMeta
    run: Callable[[ScanContext], CheckResult]


#: ⭐ Five, not twenty-four. ⭐ Measured 2026-10-04 ⭐ — ⭐ only two of the declared checks are
#: implementable as written, ⭐ and D-01 becomes a third once its sentence is corrected.
#:
#: ⭐⭐ **D-25 was added 2026-10-06 (spec 060)** ⭐⭐ — ⭐⭐ *not* `D-02`, ⭐⭐ which the
#: ⭐⭐ README already declares as 「孤儿实体 · 没有对应标的的持仓记录」 ⭐⭐ and which has no
#: ⭐⭐ table to read ⭐⭐ (measured: ⭐⭐ no `position`/`holding`/`portfolio` table exists ⭐⭐
#: ⭐⭐ in any migration). ⭐⭐ D-01 guards `decisions → instruments`; ⭐⭐
#: ⭐⭐ `decision_review_state → decisions` had no guard at all, ⭐⭐ and the rows were there.
DATA_RULES: tuple[DataRule, ...] = (
    DataRule(dangling_target.META, dangling_target.run),
    DataRule(orphan_reference.META, orphan_reference.run),
    DataRule(counter_evidence_blank.META, counter_evidence_blank.run),
    DataRule(audit_detail_length.META, audit_detail_length.run),
)

DATA_MODULE_BY_ID: dict[str, str] = {
    rule.meta.check_id: f"checks.data_rules.{rule.meta.slug.replace('-', '_')}"
    for rule in DATA_RULES
}
