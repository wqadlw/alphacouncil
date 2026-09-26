"""Command-line entry point.

Runs the API server. Kept deliberately thin — all behaviour lives in
:func:`alphacouncil.api.app.create_app`.
"""

from __future__ import annotations

import sys

import uvicorn

from alphacouncil.core.config import get_settings
from alphacouncil.core.logging import configure_logging, get_logger


def main() -> int:
    """Start the API server using settings from the environment.

    Returns:
        Process exit code.
    """
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json, force=True)
    logger = get_logger(__name__)
    logger.info("starting_server", host=settings.api_host, port=settings.api_port)

    uvicorn.run(
        "alphacouncil.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
        reload=settings.is_development,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
