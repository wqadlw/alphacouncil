"""HTTP routes. One module per resource, each a thin translation layer.

Constitution 7.5: a route validates input, calls the domain, calls a repository,
and returns. Any branch here that decides *what should happen* is a bug in the
placement of the logic, not a shortcut — the rule exists because business logic
in a route cannot be tested without a server and cannot be reused by the CLI.
"""

from __future__ import annotations

__all__: list[str] = []
