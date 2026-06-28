"""Webhook triggers: launch a workflow from an external HTTP call.

Authenticated by the workflow's server-issued webhook token (no JWT — the caller is
an external system). Only workflows whose trigger is `webhook` can be fired this way.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from ..auth.exceptions import AuthError
from ..config import get_settings
from ..deps import get_session, get_workflow_starter
from ..services import audit as audit_svc
from ..services import executions as exec_svc
from ..services import workflows as wf_svc
from ..services.executions import WorkflowStarter

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.post("/{workflow_id}")
def fire_webhook(
    workflow_id: uuid.UUID,
    token: str = Query(...),
    payload: dict[str, Any] = Body(default_factory=dict),
    session: Session = Depends(get_session),
    starter: WorkflowStarter = Depends(get_workflow_starter),
) -> dict[str, str]:
    workflow = wf_svc.get_workflow(session, workflow_id)  # 404 if missing/deleted
    expected = workflow.trigger_config.get("webhook_token")
    if workflow.trigger_type != "webhook" or not expected or token != expected:
        raise AuthError(401, "invalid_webhook", "invalid webhook token")

    execution = exec_svc.create_execution(
        session,
        workflow.tenant_id,
        workflow.id,
        starter,
        input_context=payload,
        task_queue=get_settings().server_task_queue,
        trigger_source="webhook",
    )
    audit_svc.record(
        session,
        tenant_id=workflow.tenant_id,
        action="execution.webhook",
        target_type="execution",
        target_id=str(execution.id),
        metadata={"workflow_id": str(workflow.id)},
    )
    return {"execution_id": str(execution.id), "status": execution.status}
