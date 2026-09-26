"""Structured logging configuration.

Per the project constitution, ``print()`` is forbidden — all output goes through
``structlog`` so that every log line carries machine-readable context.

This module wires structlog into the stdlib logging machinery rather than using
structlog's standalone ``PrintLoggerFactory``. That integration matters for two
reasons:

1. ``structlog.stdlib.add_logger_name`` reads ``logger.name``, which a
   ``PrintLogger`` does not have. Without the stdlib bridge the processor raises
   ``AttributeError`` on every log call.
2. Third-party libraries (uvicorn, sqlalchemy, httpx) log through stdlib. Bridging
   both paths means one renderer, one sink, one consistent output format.

Usage::

    from alphacouncil.core.logging import configure_logging, get_logger

    configure_logging(level="INFO", json_output=False)
    logger = get_logger(__name__)
    logger.info("quote_fetched", code="600519", rows=1250)
"""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO

import structlog
from structlog.typing import Processor

_DEFAULT_LEVEL = "INFO"
_configured = False


def _shared_processors() -> list[Processor]:
    """Processors applied to every record, whatever its origin.

    Used both as the structlog chain prefix and as the stdlib formatter's
    ``foreign_pre_chain``, so stdlib and structlog records render identically.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def _build_renderer(json_output: bool, stream: TextIO | None) -> Processor:
    """Pick a renderer.

    Console output is only colourised when writing to a real terminal; a
    caller-supplied stream (used by tests) must stay free of ANSI escapes.
    """
    if json_output:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=stream is None)


def configure_logging(
    level: str = _DEFAULT_LEVEL,
    *,
    json_output: bool = False,
    stream: TextIO | None = None,
    force: bool = False,
) -> None:
    """Configure structlog and the stdlib logging bridge.

    Args:
        level: Log level name, e.g. ``"INFO"`` or ``"DEBUG"``. Unknown names
            fall back to ``INFO`` rather than raising, so a typo in an
            environment variable cannot take the service down.
        json_output: Emit JSON lines (production) instead of human-readable
            console output (development).
        stream: Destination stream. Defaults to ``sys.stdout``.
        force: Re-configure even if logging was already configured. Intended
            for tests; production code should configure logging exactly once.
    """
    global _configured
    if _configured and not force:
        return

    numeric_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    output = stream if stream is not None else sys.stdout
    renderer = _build_renderer(json_output, stream)

    structlog.configure(
        processors=[
            *_shared_processors(),
            # Hands the record to the stdlib formatter below. Everything after
            # this point is rendered by the handler, not by structlog.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # Disabled so that a later ``configure_logging(force=True)`` takes
        # effect for loggers that were already obtained.
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(output)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    _configured = True


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger.

    Args:
        name: Logger name, typically ``__name__`` of the calling module. It is
            attached to every record as ``logger``, which makes it possible to
            filter output by subsystem.

    Returns:
        A structlog ``BoundLogger``. Typed as ``Any`` because structlog's
        protocol types do not survive mypy ``--strict`` cleanly across versions.
    """
    return structlog.get_logger(name) if name else structlog.get_logger()
