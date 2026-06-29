"""Aggregates for the operability dashboard: execution health, schedules, failures."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models


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

    return {
        "workflows": len(workflows),
        "executions": {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "success_rate": round(succeeded / finished, 3) if finished else None,
        },
        "schedules": schedules,
        "recent_failures": [
            {
                "id": str(e.id),
                "workflow_name": e.workflow_name,
                "created_at": e.created_at.isoformat(),
            }
            for e in recent_failures
        ],
    }
