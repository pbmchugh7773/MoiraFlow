"""Workflow CRUD + immutable versioning (Workflow as Code).

A workflow's name comes from `metadata.name` and is unique per tenant. Every
saved definition becomes an immutable, content-hashed `workflow_versions` row
(never updated or deleted). The active version is an explicit pointer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models
from ..workflow import (
    WorkflowDefinition,
    WorkflowError,
    canonical_dict,
    definition_hash,
    parse_definition,
    validate_workflow,
)
from ..workflow.parser import SourceFormat


class WorkflowServiceError(Exception):
    """Base for workflow service errors (mapped to HTTP codes in the router)."""


class WorkflowValidationError(WorkflowServiceError):
    def __init__(self, errors: list[WorkflowError]) -> None:
        super().__init__("workflow definition is invalid")
        self.errors = errors


class WorkflowExistsError(WorkflowServiceError):
    def __init__(self, name: str) -> None:
        super().__init__(f"workflow '{name}' already exists")
        self.name = name


class WorkflowNotFoundError(WorkflowServiceError):
    pass


class VersionNotFoundError(WorkflowServiceError):
    pass


class NameMismatchError(WorkflowServiceError):
    pass


def _parse_or_raise(content: str, source_format: SourceFormat) -> WorkflowDefinition:
    result = validate_workflow(content, source_format)
    if not result.valid:
        raise WorkflowValidationError(result.errors)
    return parse_definition(content, source_format)


def _next_version_number(session: Session, workflow_id: uuid.UUID) -> int:
    current = session.scalar(
        select(func.max(models.WorkflowVersion.version)).where(
            models.WorkflowVersion.workflow_id == workflow_id
        )
    )
    return (current or 0) + 1


def _add_version(
    session: Session,
    workflow: models.Workflow,
    definition: WorkflowDefinition,
    source_format: SourceFormat,
    created_by: uuid.UUID | None,
) -> models.WorkflowVersion:
    version = models.WorkflowVersion(
        tenant_id=workflow.tenant_id,
        workflow_id=workflow.id,
        version=_next_version_number(session, workflow.id),
        definition=canonical_dict(definition),
        definition_hash=definition_hash(definition),
        source_format=source_format,
        created_by=created_by,
    )
    session.add(version)
    session.flush()
    return version


def create_workflow(
    session: Session,
    tenant_id: uuid.UUID,
    content: str,
    source_format: SourceFormat = "yaml",
    created_by: uuid.UUID | None = None,
) -> models.Workflow:
    definition = _parse_or_raise(content, source_format)
    name = definition.metadata.name

    existing = session.scalar(
        select(models.Workflow).where(
            models.Workflow.tenant_id == tenant_id,
            models.Workflow.name == name,
            models.Workflow.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise WorkflowExistsError(name)

    workflow = models.Workflow(
        tenant_id=tenant_id,
        name=name,
        description=definition.metadata.description,
        trigger_type=definition.spec.trigger.type,
        trigger_config=definition.spec.trigger.model_dump(exclude_none=True, exclude={"type"}),
        created_by=created_by,
    )
    session.add(workflow)
    session.flush()

    version = _add_version(session, workflow, definition, source_format, created_by)
    workflow.active_version_id = version.id
    session.flush()
    return workflow


def add_version(
    session: Session,
    workflow_id: uuid.UUID,
    content: str,
    source_format: SourceFormat = "yaml",
    created_by: uuid.UUID | None = None,
) -> models.WorkflowVersion:
    workflow = get_workflow(session, workflow_id)
    definition = _parse_or_raise(content, source_format)
    if definition.metadata.name != workflow.name:
        raise NameMismatchError(
            f"definition name '{definition.metadata.name}' != workflow name '{workflow.name}'"
        )
    return _add_version(session, workflow, definition, source_format, created_by)


def activate_version(
    session: Session, workflow_id: uuid.UUID, version_number: int
) -> models.Workflow:
    workflow = get_workflow(session, workflow_id)
    version = session.scalar(
        select(models.WorkflowVersion).where(
            models.WorkflowVersion.workflow_id == workflow_id,
            models.WorkflowVersion.version == version_number,
        )
    )
    if version is None:
        raise VersionNotFoundError(f"workflow has no version {version_number}")
    workflow.active_version_id = version.id
    session.flush()
    return workflow


def get_workflow(session: Session, workflow_id: uuid.UUID) -> models.Workflow:
    workflow = session.get(models.Workflow, workflow_id)
    if workflow is None or workflow.deleted_at is not None:
        raise WorkflowNotFoundError(f"workflow {workflow_id} not found")
    return workflow


def get_version(
    session: Session, workflow_id: uuid.UUID, version_number: int
) -> models.WorkflowVersion:
    get_workflow(session, workflow_id)  # 404 if the workflow is missing
    version = session.scalar(
        select(models.WorkflowVersion).where(
            models.WorkflowVersion.workflow_id == workflow_id,
            models.WorkflowVersion.version == version_number,
        )
    )
    if version is None:
        raise VersionNotFoundError(f"workflow has no version {version_number}")
    return version


def delete_workflow(session: Session, workflow_id: uuid.UUID) -> models.Workflow:
    workflow = get_workflow(session, workflow_id)
    workflow.deleted_at = datetime.now(timezone.utc)
    session.flush()
    return workflow


def active_definition(session: Session, workflow_id: uuid.UUID) -> dict[str, object]:
    workflow = get_workflow(session, workflow_id)
    if workflow.active_version_id is None:
        raise VersionNotFoundError("workflow has no active version")
    version = session.get(models.WorkflowVersion, workflow.active_version_id)
    if version is None:  # pragma: no cover
        raise VersionNotFoundError("active version missing")
    return dict(version.definition)


def set_enabled(session: Session, workflow_id: uuid.UUID, enabled: bool) -> models.Workflow:
    workflow = get_workflow(session, workflow_id)
    workflow.is_enabled = enabled
    session.flush()
    return workflow


def list_workflows(session: Session, tenant_id: uuid.UUID) -> list[models.Workflow]:
    return list(
        session.scalars(
            select(models.Workflow)
            .where(
                models.Workflow.tenant_id == tenant_id,
                models.Workflow.deleted_at.is_(None),
            )
            .order_by(models.Workflow.created_at)
        )
    )
