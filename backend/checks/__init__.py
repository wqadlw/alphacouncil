"""Static checks for the defects tests structurally cannot catch.

The rules live in :mod:`checks.rules`, the shared machinery in
:mod:`checks.framework`, and the runner in :mod:`checks.__main__`.

Run it with::

    python -m checks            # human summary on stderr
    python -m checks --strict   # exit 1 when anything is not clean
    python -m checks --json     # one JSON document on stdout

This module deliberately re-exports nothing. An eager import of
:mod:`checks.registry` here would pull in every rule module, and the rule
modules import :mod:`checks.frontend` and :mod:`checks.framework` — a cycle that
only works by accident of import order. Import the submodule you want.

The machinery itself is layered, lowest first, and the layers only point
downwards: :mod:`checks.models` (no package imports) → :mod:`checks.exemptions`
→ :mod:`checks.scan`; :mod:`checks.ast_utils` stands alone; and
:mod:`checks.framework` re-exports all four as the one face the rules import.

See ``.ai/checks/static/README.md`` for the rule list, and the four things every
rule module's docstring must state.
"""

from __future__ import annotations
