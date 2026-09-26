"""One module per rule. See ``.ai/checks/static/README.md`` §3 for the list.

Every module exposes ``META: CheckMeta`` and ``run(ctx) -> CheckResult``, and
its docstring states the four things §1 requires: the defect guarded, the
anti-pattern, the correct form, and why a test cannot catch it.
"""

from __future__ import annotations
