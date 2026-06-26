"""Execution endpoints: launch on Temporal (idempotent) + query."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..auth.security import TokenError, decode_access_token
from ..config import get_settings
from ..db import models
from ..deps import (
    get_current_tenant,
    get_current_user,
    get_session,
    get_workflow_starter,
    require_roles,
)
from ..live import manager
from ..schemas.executions import CreateExecutionRequest, ExecutionEventOut, ExecutionOut
from ..services import events as events_svc
from ..services import executions as svc
from ..services.executions import WorkflowStarter

router = APIRouter(prefix="/executions", tags=["executions"])


@router.post("", status_code=201, response_model=ExecutionOut)
def create_execution(
    request: CreateExecutionRequest,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    starter: WorkflowStarter = Depends(get_workflow_starter),
    actor: models.User = Depends(require_roles("operator", "developer")),
) -> ExecutionOut:
    execution = svc.create_execution(
        session,
        tenant.id,
        request.workflow_id,
        starter,
        input_context=request.input_context,
        version=request.version,
        idempotency_key=request.idempotency_key,
        triggered_by=actor.id,
        task_queue=get_settings().server_task_queue,
    )
    return ExecutionOut.model_validate(execution)


@router.get("", response_model=list[ExecutionOut])
def list_executions(
    workflow_id: uuid.UUID | None = None,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
) -> list[ExecutionOut]:
    rows = svc.list_executions(session, tenant.id, workflow_id)
    return [ExecutionOut.model_validate(e) for e in rows]


@router.get("/{execution_id}", response_model=ExecutionOut)
def get_execution(
    execution_id: uuid.UUID,
    session: Session = Depends(get_session),
    _: models.User = Depends(get_current_user),
) -> ExecutionOut:
    return ExecutionOut.model_validate(svc.get_execution(session, execution_id))


@router.get("/{execution_id}/events", response_model=list[ExecutionEventOut])
def get_execution_events(
    execution_id: uuid.UUID,
    session: Session = Depends(get_session),
    _: models.User = Depends(get_current_user),
) -> list[ExecutionEventOut]:
    svc.get_execution(session, execution_id)  # 404 if missing
    rows = events_svc.list_events(session, execution_id)
    return [ExecutionEventOut.model_validate(e) for e in rows]


@router.websocket("/{execution_id}/stream")
async def stream_execution(
    websocket: WebSocket, execution_id: uuid.UUID, token: str = Query(...)
) -> None:
    """Live event stream for an execution. Auth via `?token=<jwt>` (WebSockets
    can't carry an Authorization header from the browser)."""
    try:
        decode_access_token(token, get_settings().jwt_secret)
    except TokenError:
        await websocket.close(code=4401)
        return
    await manager.connect(str(execution_id), websocket)
    try:
        while True:
            await websocket.receive_text()  # keep the socket open; ignore input
    except WebSocketDisconnect:
        manager.disconnect(str(execution_id), websocket)
