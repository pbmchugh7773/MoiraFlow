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
    elif event_type in _TERMINAL_STATUS:
        execution.status = _TERMINAL_STATUS[event_type]
        execution.finished_at = now
        if event_type == "execution_failed":
            execution.error = event.get("payload", {})

    session.flush()
    return row


def list_events(session: Session, execution_id: uuid.UUID) -> list[models.ExecutionEvent]:
    return list(
        session.scalars(
            select(models.ExecutionEvent)
            .where(models.ExecutionEvent.execution_id == execution_id)
            .order_by(models.ExecutionEvent.id)
        )
    )
