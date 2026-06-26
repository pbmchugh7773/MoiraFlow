"""Observability (ADR-0018): liveness/readiness probes + Prometheus metrics.

OpenTelemetry tracing plugs in via the Temporal runtime + a FastAPI OTel
instrumentor once a collector is deployed (Phase 2 wiring); this module covers the
self-contained, always-on parts.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.requests import Request

from .deps import get_session

_REQUESTS = Counter("moiraflow_http_requests_total", "HTTP requests", ["method", "status"])
_LATENCY = Histogram(
    "moiraflow_http_request_duration_seconds", "HTTP request latency (s)", ["method"]
)

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(session: Session = Depends(get_session)) -> Response:
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        return Response(
            content='{"status":"not_ready"}', status_code=503, media_type="application/json"
        )
    return Response(content='{"status":"ready"}', status_code=200, media_type="application/json")


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def add_metrics_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _record(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        _LATENCY.labels(request.method).observe(time.perf_counter() - start)
        _REQUESTS.labels(request.method, str(response.status_code)).inc()
        return response
