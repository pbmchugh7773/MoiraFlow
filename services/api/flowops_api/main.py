"""FlowOps API application factory.

API First: every capability is exposed here; the UI and the future Architect are
pure consumers of this contract. State lives in Postgres/Temporal/MinIO/Redis —
this layer is stateless.
"""

from __future__ import annotations

from fastapi import FastAPI

from .routers import catalog, workflows

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="FlowOps API",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.include_router(workflows.router, prefix=API_PREFIX)
    app.include_router(catalog.router, prefix=API_PREFIX)
    return app


app = create_app()
