"""Workflow endpoints: validation (stateless) + CRUD with immutable versioning.

RBAC (docs 04 §A.8): viewers/operators can read; developers (and admins) create
and edit workflows.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models
from ..deps import (
    get_current_tenant,
    get_current_user,
    get_schedule_manager,
    get_session,
    require_roles,
)
from ..schemas.simulation import SimulateResponse
from ..schemas.validation import ValidateRequest, ValidateResponse
from ..schemas.workflows import (
    CreateWorkflowRequest,
    WorkflowOut,
    WorkflowVersionDetailOut,
    WorkflowVersionOut,
)
from ..services import audit as audit_svc
from ..services import simulation as sim_svc
from ..services import workflows as svc
from ..services.schedules import ScheduleManager, schedule_id_for
from ..workflow import validate_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _sync_schedule(session: Session, sched: ScheduleManager, workflow: models.Workflow) -> None:
    """Reconcile the workflow's Temporal Schedule with its cron trigger (ADR-0015)."""
    if workflow.trigger_type != "cron":
        return
    schedule_id = schedule_id_for(workflow.id)
    cron = workflow.trigger_config.get("cron")
    if workflow.is_enabled and workflow.active_version_id and cron:
        version = session.get(models.WorkflowVersion, workflow.active_version_id)
        if version is not None:
            sched.upsert(
                schedule_id=schedule_id,
                cron=str(cron),
                timezone=workflow.trigger_config.get("timezone"),
                definition=version.definition,
                input_context={},
                task_queue=get_settings().server_task_queue,
                meta={
                    "tenant_id": str(workflow.tenant_id),
                    "workflow_id": str(workflow.id),
                    "workflow_version_id": str(version.id),
                },
            )
    else:
        sched.pause(schedule_id)


@router.post("/validate", response_model=ValidateResponse)
def validate(
    request: ValidateRequest, _: models.User = Depends(get_current_user)
) -> ValidateResponse:
    """Validate a workflow definition. Always returns 200; problems are in `errors`.

    A 200-with-errors contract (rather than 4xx) keeps the endpoint machine-friendly
    for the UI editor and the future MoiraFlow Architect, which expect a structured
    report, not an HTTP error.
    """
    result = validate_workflow(request.content, request.format)
    return ValidateResponse.from_result(result)


@router.post("/simulate", response_model=SimulateResponse)
def simulate(
    request: ValidateRequest,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
) -> SimulateResponse:
    """Dry-run: resolve the DAG + check secret:// refs and routing without executing."""
    result = sim_svc.simulate(session, tenant.id, request.content, request.format)
    return SimulateResponse.from_result(result)


@router.post("", status_code=201, response_model=WorkflowOut)
def create_workflow(
    request: CreateWorkflowRequest,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    sched: ScheduleManager = Depends(get_schedule_manager),
    actor: models.User = Depends(require_roles("developer")),
) -> WorkflowOut:
    workflow = svc.create_workflow(session, tenant.id, request.content, request.format)
    _sync_schedule(session, sched, workflow)
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="workflow.create",
        actor_user_id=actor.id,
        target_type="workflow",
        target_id=str(workflow.id),
        metadata={"name": workflow.name},
    )
    return WorkflowOut.model_validate(workflow)


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
) -> list[WorkflowOut]:
    return [WorkflowOut.model_validate(w) for w in svc.list_workflows(session, tenant.id)]


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    _: models.User = Depends(get_current_user),
) -> WorkflowOut:
    return WorkflowOut.model_validate(svc.get_workflow(session, workflow_id))


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
def list_versions(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    _: models.User = Depends(get_current_user),
) -> list[WorkflowVersionOut]:
    svc.get_workflow(session, workflow_id)  # 404 if missing
    versions = session.scalars(
        select(models.WorkflowVersion)
        .where(models.WorkflowVersion.workflow_id == workflow_id)
        .order_by(models.WorkflowVersion.version)
    )
    return [WorkflowVersionOut.model_validate(v) for v in versions]


@router.get("/{workflow_id}/versions/{version}", response_model=WorkflowVersionDetailOut)
def get_version(
    workflow_id: uuid.UUID,
    version: int,
    session: Session = Depends(get_session),
    _: models.User = Depends(get_current_user),
) -> WorkflowVersionDetailOut:
    return WorkflowVersionDetailOut.model_validate(svc.get_version(session, workflow_id, version))


@router.post("/{workflow_id}/versions", status_code=201, response_model=WorkflowVersionOut)
def add_version(
    workflow_id: uuid.UUID,
    request: CreateWorkflowRequest,
    session: Session = Depends(get_session),
    _: models.User = Depends(require_roles("developer")),
) -> WorkflowVersionOut:
    version = svc.add_version(session, workflow_id, request.content, request.format)
    return WorkflowVersionOut.model_validate(version)


@router.post("/{workflow_id}/activate/{version}", response_model=WorkflowOut)
def activate_version(
    workflow_id: uuid.UUID,
    version: int,
    session: Session = Depends(get_session),
    sched: ScheduleManager = Depends(get_schedule_manager),
    _: models.User = Depends(require_roles("developer")),
) -> WorkflowOut:
    workflow = svc.activate_version(session, workflow_id, version)
    _sync_schedule(session, sched, workflow)
    return WorkflowOut.model_validate(workflow)


@router.post("/{workflow_id}/enable", response_model=WorkflowOut)
def enable_workflow(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    sched: ScheduleManager = Depends(get_schedule_manager),
    _: models.User = Depends(require_roles("developer")),
) -> WorkflowOut:
    workflow = svc.set_enabled(session, workflow_id, True)
    _sync_schedule(session, sched, workflow)
    return WorkflowOut.model_validate(workflow)


@router.post("/{workflow_id}/disable", response_model=WorkflowOut)
def disable_workflow(
    workflow_id: uuid.UUID,
    session: Session = Depends(get_session),
    sched: ScheduleManager = Depends(get_schedule_manager),
    _: models.User = Depends(require_roles("developer")),
) -> WorkflowOut:
    workflow = svc.set_enabled(session, workflow_id, False)
    _sync_schedule(session, sched, workflow)
    return WorkflowOut.model_validate(workflow)
