"""Aggregates for the operability dashboard: execution health, schedules, failures."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models

_ACTIVITY_DAYS = 7


def _duration_seconds(e: models.Execution) -> float | None:
    if e.started_at and e.finished_at:
        return round((e.finished_at - e.started_at).total_seconds(), 1)
    return None


def _activity(session: Session, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    """Per-day success/failed/total counts for the last `_ACTIVITY_DAYS` days
    (oldest first). Grouped by calendar date — portable across SQLite/Postgres."""
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(_ACTIVITY_DAYS - 1, -1, -1)]
    buckets = {
        d.isoformat(): {"date": d.isoformat(), "total": 0, "success": 0, "failed": 0} for d in days
    }
    rows = session.execute(
        select(
            func.date(models.Execution.created_at),
            models.Execution.status,
            func.count(),
        )
        .where(models.Execution.tenant_id == tenant_id)
        .group_by(func.date(models.Execution.created_at), models.Execution.status)
    ).all()
    for day, status, count in rows:
        bucket = buckets.get(str(day)[:10])
        if bucket is None:
            continue
        bucket["total"] += count
        if status in ("success", "failed"):
            bucket[status] += count
    return list(buckets.values())


def get_overview(session: Session, tenant_id: uuid.UUID) -> dict[str, Any]:
    workflows = list(
        session.scalars(
            select(models.Workflow).where(
                models.Workflow.tenant_id == tenant_id,
                models.Workflow.deleted_at.is_(None),
            )
        )
    )
    schedules = [
        {
            "id": str(w.id),
            "name": w.name,
            "cron": (w.trigger_config or {}).get("cron"),
            "timezone": (w.trigger_config or {}).get("timezone"),
            "enabled": w.is_enabled,
        }
        for w in workflows
        if w.trigger_type == "cron"
    ]

    status_rows = session.execute(
        select(models.Execution.status, func.count())
        .where(models.Execution.tenant_id == tenant_id)
        .group_by(models.Execution.status)
    ).all()
    by_status = {status: count for status, count in status_rows}
    succeeded = by_status.get("success", 0)
    failed = by_status.get("failed", 0)
    finished = succeeded + failed

    recent_failures = list(
        session.scalars(
            select(models.Execution)
            .where(
                models.Execution.tenant_id == tenant_id,
                models.Execution.status == "failed",
            )
            .order_by(models.Execution.created_at.desc())
            .limit(8)
        )
    )
    recent = list(
        session.scalars(
            select(models.Execution)
            .where(models.Execution.tenant_id == tenant_id)
            .order_by(models.Execution.created_at.desc())
            .limit(8)
        )
    )

    return {
        "workflows": len(workflows),
        "executions": {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "success_rate": round(succeeded / finished, 3) if finished else None,
        },
        "schedules": schedules,
        "activity": _activity(session, tenant_id),
        "recent_executions": [
            {
                "id": str(e.id),
                "workflow_name": e.workflow_name,
                "status": e.status,
                "created_at": e.created_at.isoformat(),
                "duration_seconds": _duration_seconds(e),
            }
            for e in recent
        ],
        "recent_failures": [
            {
                "id": str(e.id),
                "workflow_name": e.workflow_name,
                "created_at": e.created_at.isoformat(),
            }
            for e in recent_failures
        ],
    }
