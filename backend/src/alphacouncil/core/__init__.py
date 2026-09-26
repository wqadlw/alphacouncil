"""Core infrastructure: configuration, logging, observability.

Modules in this package must not import from ``agents``, ``graph``, ``retrieval``,
``tools`` or ``api``. ``core`` sits at the bottom of the dependency graph.
"""

from __future__ import annotations

__all__: list[str] = []
