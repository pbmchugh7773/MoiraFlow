"""Persist execution lifecycle events and project execution status.

The worker publishes events to Redis (keyed by temporal_workflow_id); the API's
subscriber calls `handle_event` to append an immutable `execution_events` row and
advance `executions.status` (the projection — ADR-0014). Unknown executions are
ignored (events are best-effort and may arrive for foreign/stale workflows).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models

_TERMINAL_STATUS = {"execution_finished": "success", "execution_failed": "failed"}


def _auto_register(
    session: Session, temporal_workflow_id: str, event: dict[str, Any]
) -> models.Execution | None:
    """Create a projection row for a run that started outside POST /executions
    (e.g. a cron schedule). The interpreter rides tenant/workflow/version ids on
    `execution_started` so the row can be reconstructed."""
    if event.get("type") != "execution_started":
        return None
    meta = (event.get("payload") or {}).get("meta") or {}
    try:
        execution = models.Execution(
            tenant_id=uuid.UUID(meta["tenant_id"]),
            workflow_id=uuid.UUID(meta["workflow_id"]),
            workflow_version_id=uuid.UUID(meta["workflow_version_id"]),
            temporal_workflow_id=temporal_workflow_id,
            trigger_source="cron",
            status="running",
        )
    except (KeyError, ValueError, TypeError):
        return None
    session.add(execution)
    session.flush()
    return execution


def handle_event(session: Session, event: dict[str, Any]) -> models.ExecutionEvent | None:
    temporal_workflow_id = event.get("temporal_workflow_id")
    if not temporal_workflow_id:
        return None
    execution = session.scalar(
        select(models.Execution).where(
            models.Execution.temporal_workflow_id == temporal_workflow_id
        )
    )
    if execution is None:
        execution = _auto_register(session, temporal_workflow_id, event)
        if execution is None:
            return None

    event_type = event["type"]
    payload = dict(event.get("payload") or {})
    if event.get("job_id"):  # keep which job the event belongs to
        payload["job_id"] = event["job_id"]
    row = models.ExecutionEvent(
        tenant_id=execution.tenant_id,
        execution_id=execution.id,
        event_type=event_type,
        payload=payload,
    )
    session.add(row)

    now = datetime.now(timezone.utc)
    if event_type == "execution_started":
        execution.status = "running"
        execution.started_at = now
    elif event_type in _TERMINAL_STATUS and execution.status != "cancelled":
        # a user cancel is terminal; don't let a late failed/finished event override it
        execution.status = _TERMINAL_STATUS[event_type]
        execution.finished_at = now
        if event_type == "execution_failed":
            execution.error = event.get("payload", {})

    _project_job(session, execution, event, now)
    session.flush()
    return row


def _project_job(
    session: Session, execution: models.Execution, event: dict[str, Any], now: datetime
) -> None:
    """Maintain a job_executions row per job from job_* events (attempt=1; retries
    happen inside the activity, so per-attempt rows are a later refinement)."""
    job_id = event.get("job_id")
    if not job_id or not event["type"].startswith("job_"):
        return
    if event["type"] == "job_started":
        session.add(
            models.JobExecution(
                tenant_id=execution.tenant_id,
                execution_id=execution.id,
                job_id=job_id,
                job_type=str((event.get("payload") or {}).get("type", "")),
                status="running",
                started_at=now,
            )
        )
        return
    if event["type"] == "job_skipped":
        # A condition was false (or an upstream job was skipped): record the job as
        # skipped without a started/succeeded lifecycle.
        session.add(
            models.JobExecution(
                tenant_id=execution.tenant_id,
                execution_id=execution.id,
                job_id=job_id,
                job_type="",
                status="skipped",
                started_at=now,
                finished_at=now,
            )
        )
        return
    job = session.scalar(
        select(models.JobExecution).where(
            models.JobExecution.execution_id == execution.id,
            models.JobExecution.job_id == job_id,
        )
    )
    if job is None:
        return
    payload = event.get("payload") or {}
    if event["type"] == "job_succeeded":
        job.status = "success"
        job.output = payload.get("outputs", {})
        job.attempt = int(payload.get("attempt", 1))
        for ref in payload.get("artifacts") or []:
            session.add(
                models.Artifact(
                    tenant_id=execution.tenant_id,
                    execution_id=execution.id,
                    job_execution_id=job.id,
                    name=ref["name"],
                    bucket=ref["bucket"],
                    object_key=ref["object_key"],
                    size_bytes=ref.get("size_bytes", 0),
                    content_type=ref.get("content_type"),
                )
            )
    elif event["type"] == "job_failed":
        job.status = "failed"
        job.error = payload
    job.finished_at = now


def list_artifacts(session: Session, execution_id: uuid.UUID) -> list[models.Artifact]:
    return list(
        session.scalars(
            select(models.Artifact)
            .where(models.Artifact.execution_id == execution_id)
            .order_by(models.Artifact.created_at)
        )
    )


def list_job_executions(session: Session, execution_id: uuid.UUID) -> list[models.JobExecution]:
    return list(
        session.scalars(
            select(models.JobExecution)
            .where(models.JobExecution.execution_id == execution_id)
            .order_by(models.JobExecution.created_at)
        )
    )


def list_events(session: Session, execution_id: uuid.UUID) -> list[models.ExecutionEvent]:
    return list(
        session.scalars(
            select(models.ExecutionEvent)
            .where(models.ExecutionEvent.execution_id == execution_id)
            .order_by(models.ExecutionEvent.id)
        )
    )
