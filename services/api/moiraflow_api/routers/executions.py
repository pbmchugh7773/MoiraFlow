"""Execution endpoints: launch on Temporal (idempotent) + query."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models
from ..deps import (
    get_current_tenant,
    get_current_user,
    get_session,
    get_workflow_starter,
    require_roles,
)
from ..schemas.executions import CreateExecutionRequest, ExecutionOut
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
