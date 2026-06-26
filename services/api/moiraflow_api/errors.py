"""Map service-layer exceptions to the API error envelope {error:{code,message,details}}."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .auth.exceptions import AuthError
from .services import executions as ex
from .services import secrets as sec
from .services import workflows as wf


def _envelope(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(wf.WorkflowValidationError)
    async def _validation(_: Request, exc: wf.WorkflowValidationError) -> JSONResponse:
        return _envelope(422, "validation_error", str(exc), [asdict(e) for e in exc.errors])

    @app.exception_handler(wf.WorkflowExistsError)
    async def _exists(_: Request, exc: wf.WorkflowExistsError) -> JSONResponse:
        return _envelope(409, "workflow_exists", str(exc))

    @app.exception_handler(wf.NameMismatchError)
    async def _mismatch(_: Request, exc: wf.NameMismatchError) -> JSONResponse:
        return _envelope(409, "name_mismatch", str(exc))

    @app.exception_handler(wf.WorkflowNotFoundError)
    async def _wf_missing(_: Request, exc: wf.WorkflowNotFoundError) -> JSONResponse:
        return _envelope(404, "not_found", str(exc))

    @app.exception_handler(wf.VersionNotFoundError)
    async def _ver_missing(_: Request, exc: wf.VersionNotFoundError) -> JSONResponse:
        return _envelope(404, "not_found", str(exc))

    @app.exception_handler(ex.ExecutionNotFoundError)
    async def _exec_missing(_: Request, exc: ex.ExecutionNotFoundError) -> JSONResponse:
        return _envelope(404, "not_found", str(exc))

    @app.exception_handler(ex.WorkflowNotReadyError)
    async def _not_ready(_: Request, exc: ex.WorkflowNotReadyError) -> JSONResponse:
        return _envelope(409, "workflow_not_ready", str(exc))

    @app.exception_handler(AuthError)
    async def _auth(_: Request, exc: AuthError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message)

    @app.exception_handler(sec.SecretNotFoundError)
    async def _secret_missing(_: Request, exc: sec.SecretNotFoundError) -> JSONResponse:
        return _envelope(404, "not_found", str(exc))
