"""Launch executions on Temporal with an idempotent, deterministic workflow id.

Per ADR-0014 the `executions` row is an idempotent **projection**: the
`temporal_workflow_id` is derived deterministically from the idempotency key (or
the version + inputs), so a duplicate POST returns the same row and does not start
a second workflow. The Temporal interaction is behind the `WorkflowStarter`
protocol so the service is unit-testable without a Temporal server.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models
from . import workflows as wf_svc


class WorkflowStarter(Protocol):
    def start(
        self,
        *,
        temporal_workflow_id: str,
        definition: dict[str, Any],
        input_context: dict[str, Any],
        task_queue: str,
    ) -> str:
        """Start the interpreter workflow and return its Temporal run id."""
        ...


class ExecutionServiceError(Exception):
    pass


class ExecutionNotFoundError(ExecutionServiceError):
    pass


class WorkflowNotReadyError(ExecutionServiceError):
    """The workflow has no version to run (no active version / unknown version)."""


def _deterministic_workflow_id(
    version_id: uuid.UUID, input_context: dict[str, Any], idempotency_key: str | None
) -> str:
    if idempotency_key:
        return f"wf-{version_id}-{idempotency_key}"
    digest = hashlib.sha256(
        json.dumps(input_context, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return f"wf-{version_id}-{digest}"


def _resolve_version(
    session: Session, workflow: models.Workflow, version: int | None
) -> models.WorkflowVersion:
    if version is not None:
        found = session.scalar(
            select(models.WorkflowVersion).where(
                models.WorkflowVersion.workflow_id == workflow.id,
                models.WorkflowVersion.version == version,
            )
        )
        if found is None:
            raise wf_svc.VersionNotFoundError(f"workflow has no version {version}")
        return found
    if workflow.active_version_id is None:
        raise WorkflowNotReadyError("workflow has no active version to run")
    active = session.get(models.WorkflowVersion, workflow.active_version_id)
    if active is None:  # pragma: no cover - referential integrity guards this
        raise WorkflowNotReadyError("active version is missing")
    return active


def create_execution(
    session: Session,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    starter: WorkflowStarter,
    *,
    input_context: dict[str, Any] | None = None,
    version: int | None = None,
    idempotency_key: str | None = None,
    triggered_by: uuid.UUID | None = None,
    task_queue: str = "moiraflow-server",
) -> models.Execution:
    input_context = input_context or {}
    workflow = wf_svc.get_workflow(session, workflow_id)
    workflow_version = _resolve_version(session, workflow, version)

    temporal_workflow_id = _deterministic_workflow_id(
        workflow_version.id, input_context, idempotency_key
    )

    # Idempotent projection: a matching row means it was already launched.
    existing = session.scalar(
        select(models.Execution).where(
            models.Execution.temporal_workflow_id == temporal_workflow_id
        )
    )
    if existing is not None:
        return existing

    run_id = starter.start(
        temporal_workflow_id=temporal_workflow_id,
        definition=workflow_version.definition,
        input_context=input_context,
        task_queue=task_queue,
    )

    execution = models.Execution(
        tenant_id=tenant_id,
        workflow_id=workflow.id,
        workflow_version_id=workflow_version.id,
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id=run_id,
        trigger_source="manual",
        triggered_by=triggered_by,
        status="running",
        input_context=input_context,
    )
    session.add(execution)
    session.flush()
    return execution


def replay_execution(
    session: Session,
    tenant_id: uuid.UUID,
    execution_id: uuid.UUID,
    starter: WorkflowStarter,
    *,
    triggered_by: uuid.UUID | None = None,
    task_queue: str = "moiraflow-server",
) -> models.Execution:
    """Re-run a past execution: same version + inputs, a fresh durable workflow.

    A replay never reuses mutated history — it starts a new interpreter workflow
    with the same versioned definition + inputs (ADR-0001/0014).
    """
    original = get_execution(session, execution_id)
    version = session.get(models.WorkflowVersion, original.workflow_version_id)
    if version is None:  # pragma: no cover - FK guards this
        raise ExecutionNotFoundError("original version missing")

    replay_count = (
        session.scalar(
            select(func.count())
            .select_from(models.Execution)
            .where(models.Execution.replay_of_execution_id == original.id)
        )
        or 0
    )
    temporal_workflow_id = f"{original.temporal_workflow_id}-replay-{replay_count + 1}"
    existing = session.scalar(
        select(models.Execution).where(
            models.Execution.temporal_workflow_id == temporal_workflow_id
        )
    )
    if existing is not None:
        return existing

    run_id = starter.start(
        temporal_workflow_id=temporal_workflow_id,
        definition=version.definition,
        input_context=original.input_context,
        task_queue=task_queue,
    )
    execution = models.Execution(
        tenant_id=tenant_id,
        workflow_id=original.workflow_id,
        workflow_version_id=original.workflow_version_id,
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id=run_id,
        trigger_source="replay",
        triggered_by=triggered_by,
        status="running",
        input_context=original.input_context,
        replay_of_execution_id=original.id,
    )
    session.add(execution)
    session.flush()
    return execution


def get_execution(session: Session, execution_id: uuid.UUID) -> models.Execution:
    execution = session.get(models.Execution, execution_id)
    if execution is None:
        raise ExecutionNotFoundError(f"execution {execution_id} not found")
    return execution


def get_definition(session: Session, execution_id: uuid.UUID) -> dict[str, Any]:
    """The workflow definition this execution is running (for the live DAG view)."""
    execution = get_execution(session, execution_id)
    version = session.get(models.WorkflowVersion, execution.workflow_version_id)
    if version is None:  # pragma: no cover - FK guards this
        raise ExecutionNotFoundError("execution version missing")
    return dict(version.definition)


def list_executions(
    session: Session, tenant_id: uuid.UUID, workflow_id: uuid.UUID | None = None
) -> list[models.Execution]:
    query = select(models.Execution).where(models.Execution.tenant_id == tenant_id)
    if workflow_id is not None:
        query = query.where(models.Execution.workflow_id == workflow_id)
    return list(session.scalars(query.order_by(models.Execution.created_at.desc())))
