"""FastAPI application factory.

Error handling here has one rule: a response never carries a stack trace. An
unexpected exception is logged in full on the server and answered with a generic
500, because a traceback in an HTTP body tells a caller the file layout, the ORM in
use and often the SQL.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import engine
from app.routes import ROUTERS
from app.services import device_health, simulator

logger = logging.getLogger("cylinguard")

DESCRIPTION = """
Smart LPG cylinder monitoring and safety.

An ESP32 with a load cell and an MQ-6 gas sensor reports to this API, which stores
the history, derives consumption, estimates depletion and raises alerts.

**This is a prototype.** The MQ-6 is not a certified gas analyser, and buzzer and
relay fields report only what the backend commanded or the device reported - never
a confirmed physical gas shutoff.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to serve with the shipped placeholder JWT secret. Anyone who has read
    # the repository would be able to mint valid tokens, so this is a hard stop
    # outside debug rather than a warning that scrolls past.
    if settings.is_default_secret:
        message = (
            "JWT_SECRET is still the shipped placeholder. Run "
            "scripts/bootstrap_mysql.py (which generates one) or set JWT_SECRET in .env."
        )
        if settings.debug:
            logger.warning("%s Continuing because DEBUG is on.", message)
        else:
            raise RuntimeError(message)

    # Fail at startup rather than on the first request if the database is unreachable.
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("database reachable")
    except SQLAlchemyError as exc:
        raise RuntimeError(
            f"cannot reach the database on startup: {exc.orig if hasattr(exc, 'orig') else exc}"
        ) from exc

    # Background loops. Both are cancelled on shutdown; neither runs under the test
    # client, which does not execute the lifespan, so tests drive them directly.
    simulator.start()
    sweep = asyncio.create_task(_sweep_forever(), name="device-offline-sweep")

    yield

    sweep.cancel()
    try:
        await sweep
    except asyncio.CancelledError:
        pass
    await simulator.stop()
    engine.dispose()


async def _sweep_forever() -> None:
    """Mark devices offline that have stopped reporting (spec §33)."""
    interval = max(5, settings.device_sweep_seconds)
    logger.info("device offline sweep started, every %ss", interval)
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                raised = await run_in_threadpool(device_health.sweep_once)
                if raised:
                    logger.info("offline sweep raised %d alert(s)", raised)
            except Exception:
                # One failed sweep must not end the loop for the process lifetime.
                logger.exception("device offline sweep failed")
    except asyncio.CancelledError:
        logger.info("device offline sweep stopped")
        raise


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in ROUTERS:
        app.include_router(router)

    @app.get("/health", tags=["meta"], summary="Liveness and database reachability")
    def health() -> dict:
        """Unauthenticated, so a load balancer or NGINX can poll it."""
        database_ok = True
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            # Logged, not returned: the reason could name the host and user.
            logger.exception("health check could not reach the database")
            database_ok = False
        return {
            "status": "ok" if database_ok else "degraded",
            "app": settings.app_name,
            "database": "up" if database_ok else "down",
        }

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        """422 with field errors only.

        Two things are stripped from pydantic's raw error list. `input` echoes the
        submitted value, which on a failed registration would send the password
        straight back in the response body. `ctx` can hold the original exception
        *object* for errors raised inside a field_validator, which is not JSON
        serialisable and would turn a bad email into a 500.
        """
        if request.url.path.startswith("/api/iot/"):
            # Spec §53: a rejected sensor packet is logged, not silently dropped - it
            # is usually the first sign of a miscalibrated load cell or a bad device
            # clock. Field names and messages only, never the payload.
            logger.warning(
                "rejected packet on %s: %s",
                request.url.path,
                [
                    f"{'.'.join(str(part) for part in error.get('loc', ()))}: {error.get('msg')}"
                    for error in exc.errors()
                ],
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": [
                    {
                        "type": error.get("type"),
                        "loc": [str(part) for part in error.get("loc", ())],
                        "msg": str(error.get("msg")),
                    }
                    for error in exc.errors()
                ]
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_handler(request: Request, exc: SQLAlchemyError):
        logger.exception("database error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "A database error occurred"},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    return app


app = create_app()
