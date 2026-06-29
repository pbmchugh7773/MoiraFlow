"""MoiraFlow API application factory.

API First: every capability is exposed here; the UI and the future Architect are
pure consumers of this contract. State lives in Postgres/Temporal/MinIO/Redis —
this layer is stateless.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .deps import session_factory
from .errors import register_error_handlers
from .live import run_event_subscriber
from .observability import add_metrics_middleware
from .observability import router as system_router
from .routers import (
    agents,
    audit,
    auth,
    catalog,
    executions,
    hooks,
    overview,
    secrets,
    users,
    workflows,
)

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    task: asyncio.Task[None] | None = None
    if settings.event_subscriber_enabled:
        task = asyncio.create_task(run_event_subscriber(session_factory(), settings.redis_url))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    app = FastAPI(
        title="MoiraFlow API",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(workflows.router, prefix=API_PREFIX)
    app.include_router(executions.router, prefix=API_PREFIX)
    app.include_router(hooks.router, prefix=API_PREFIX)
    app.include_router(secrets.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(agents.router, prefix=API_PREFIX)
    app.include_router(audit.router, prefix=API_PREFIX)
    app.include_router(catalog.router, prefix=API_PREFIX)
    app.include_router(overview.router, prefix=API_PREFIX)
    app.include_router(system_router)  # /healthz, /readyz, /metrics (root, no auth)
    add_metrics_middleware(app)
    register_error_handlers(app)
    return app


app = create_app()
