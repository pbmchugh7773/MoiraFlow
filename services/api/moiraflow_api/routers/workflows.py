"""Workflow endpoints: validation (stateless) + CRUD with immutable versioning.

RBAC (docs 04 §A.8): viewers/operators can read; developers (and admins) create
and edit workflows.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from ..deps import get_current_tenant, get_current_user, get_session, require_roles
from ..schemas.validation import ValidateRequest, ValidateResponse
from ..schemas.workflows import CreateWorkflowRequest, WorkflowOut, WorkflowVersionOut
from ..services import workflows as svc
from ..workflow import validate_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


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


@router.post("", status_code=201, response_model=WorkflowOut)
def create_workflow(
    request: CreateWorkflowRequest,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    _: models.User = Depends(require_roles("developer")),
) -> WorkflowOut:
    workflow = svc.create_workflow(session, tenant.id, request.content, request.format)
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
    _: models.User = Depends(require_roles("developer")),
) -> WorkflowOut:
    return WorkflowOut.model_validate(svc.activate_version(session, workflow_id, version))
