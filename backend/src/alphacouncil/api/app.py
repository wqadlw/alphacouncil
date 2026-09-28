"""FastAPI application factory.

The app is created through a factory rather than a module-level singleton so
that tests can build isolated instances with their own settings — which matters
more here than usual, because each instance points at its own database file and
runs its own migration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from alphacouncil import __version__
from alphacouncil.api.errors import CODED_ERRORS, domain_failure
from alphacouncil.api.routes import (
    capabilities,
    cards,
    decision_reviews,
    decisions,
    instruments,
    notes,
    reviews,
    today,
    watchlist,
)
from alphacouncil.core.config import Settings, get_settings
from alphacouncil.core.logging import configure_logging, get_logger
from alphacouncil.core.trace import TraceWriter, set_current_trace
from alphacouncil.providers import default_router
from alphacouncil.providers.cache import SqliteCache
from alphacouncil.storage import migrate
from alphacouncil.storage.db import connect_for_migration

logger = get_logger(__name__)


def _prepare_database(settings: Settings) -> migrate.MigrationReport:
    """Bring the schema up to date before a single request is served.

    A desktop application upgrades in place, so this runs on every start and is
    a no-op when the schema is already current. It runs *before* the server
    accepts traffic because serving a request against a half-migrated database
    is the scenario ADR-0012 exists to prevent.

    Raises:
        MigrationError: The database is from a newer build, or the pre-migration
            snapshot failed. Startup is aborted rather than continuing against a
            schema this build does not understand.
    """
    path = settings.database_path
    connection = connect_for_migration(path)
    try:
        report = migrate.apply(connection, database_path=path)
    finally:
        connection.close()

    if report.changed:
        logger.info(
            "schema_migrated",
            from_version=report.from_version,
            to_version=report.to_version,
            applied=list(report.applied),
            snapshot=str(report.snapshot_path) if report.snapshot_path else None,
        )
    else:
        logger.info("schema_up_to_date", version=report.to_version)
    return report


async def _coded_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Render a domain failure in the standard diagnostic envelope.

    Registered for :class:`~alphacouncil.domain.instrument.InstrumentError` and
    :class:`~alphacouncil.domain.watchlist.WatchlistError`. Both subclass
    ``ValueError``, and Starlette picks the most specific handler, so the plain
    ``ValueError`` handler installed below still catches everything else.
    """
    failure = domain_failure(exc)
    logger.warning(
        "domain_error",
        code=failure.body["code"],
        status=failure.status,
        error=str(exc),
    )
    return JSONResponse(status_code=failure.status, content=failure.body)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks.

    Logging is configured here rather than at import time so the configuration
    reflects the settings actually in use.
    """
    settings: Settings = app.state.settings
    configure_logging(level=settings.log_level, json_output=settings.log_json, force=True)
    logger.info(
        "application_started",
        version=__version__,
        env=settings.env,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
    )
    _prepare_database(settings)
    yield
    logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI application.

    Args:
        settings: Optional settings override. Defaults to the cached singleton.

    Returns:
        A ready-to-serve FastAPI instance.
    """
    resolved = settings if settings is not None else get_settings()

    app = FastAPI(
        title="AlphaCouncil",
        version=__version__,
        description=(
            "A stock-market knowledge management system: instruments, the reasons "
            "for following them, and the decisions taken about them. "
            "Not investment advice, and not a source of recommendations."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = resolved
    # One router for the process, because its health bookkeeping — which source
    # refused us and until when — is only worth anything if it accumulates
    # across requests. Built here rather than imported as a module global so a
    # test can replace it on the instance without leaking into the next test.
    # The cache is the disk-backed one (spec 006): the last known good price
    # must survive a restart, which is what "reopen offline and see something"
    # asks for. MemoryCache stays the router tests' lightweight double.
    trace_writer = TraceWriter(resolved.traces_dir or resolved.database_path.parent / "traces")
    app.state.trace_writer = trace_writer
    app.state.market_data = default_router(
        cache=SqliteCache(resolved.database_path), tracer=trace_writer
    )

    @app.middleware("http")
    async def trace_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """One trace per request (spec 011): route, status, duration, plus the
        provider observations the handlers happen to make. Bodies are never
        read — the audit records what was done, not what was said."""
        trace = trace_writer.start(f"{request.method} {request.url.path}")
        set_current_trace(trace)
        try:
            response = await call_next(request)
            with trace.observation(
                "http",
                meta={"path": request.url.path, "http_status": response.status_code},
            ):
                pass
            return response
        finally:
            set_current_trace(None)

    @app.exception_handler(ValueError)
    async def _handle_value_error(_: Request, exc: ValueError) -> JSONResponse:
        """Map an uncoded validation error to 400 rather than 500."""
        logger.warning("request_validation_error", error=str(exc))
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    for coded in CODED_ERRORS:
        app.add_exception_handler(coded, _coded_error_handler)

    app.include_router(watchlist.router)
    app.include_router(instruments.router)
    app.include_router(decisions.router)
    app.include_router(today.router)
    app.include_router(capabilities.router)
    app.include_router(cards.router)
    # Spec 026. The knowledge vault: notes sit **beside** cards, not inside them.
    # Registered after the card router so a reader scanning this list meets the
    # two in the order the product thinks in them — a claim, then a note.
    app.include_router(notes.router)
    # The review queue. `/api/v1/cards/{card_id}` would otherwise shadow
    # `/api/v1/cards/due`, so the queue has its own prefix — see reviews.py.
    app.include_router(reviews.card_router)
    app.include_router(reviews.queue_router)
    # Decision reviews (J3). Imported under its own name because the card queue
    # above already owns "review" — `/api/v1/decision-reviews` cannot be confused
    # with `/api/v1/review`, and the module name says which is which at the call
    # site. Registered after the card routers so a reader scanning this list sees
    # the two queues in the order they were built.
    app.include_router(decision_reviews.router)

    @app.get("/health", tags=["ops"], summary="Liveness and configuration probe")
    async def health() -> dict[str, Any]:
        """Report service health and the effective non-secret configuration."""
        return {
            "status": "ok",
            "version": __version__,
            "env": resolved.env,
            "llm_provider": resolved.llm_provider,
            "llm_model": resolved.llm_model,
        }

    return app


app = create_app()
