"""Append-only governance log (docs 03 §3.12) — distinct from execution_events.

Records who did what: login, workflow create/activate/enable, execution
launch/cancel, secret changes, etc. Never updated or deleted.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models


def record(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> models.AuditLog:
    entry = models.AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        audit_metadata=metadata or {},
        ip_address=ip_address,
    )
    session.add(entry)
    session.flush()
    return entry


def list_audit(session: Session, tenant_id: uuid.UUID, limit: int = 100) -> list[models.AuditLog]:
    return list(
        session.scalars(
            select(models.AuditLog)
            .where(models.AuditLog.tenant_id == tenant_id)
            .order_by(models.AuditLog.id.desc())
            .limit(limit)
        )
    )
