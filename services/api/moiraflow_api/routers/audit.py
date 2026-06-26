"""Audit log endpoint (admin only)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from ..db import models
from ..deps import get_current_tenant, get_session, require_roles
from ..services import audit as svc

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    actor_user_id: uuid.UUID | None
    target_type: str | None
    target_id: str | None
    audit_metadata: dict[str, Any]
    ip_address: str | None
    created_at: datetime

    @field_validator("ip_address", mode="before")
    @classmethod
    def _coerce_ip(cls, v: object) -> str | None:
        # Postgres INET round-trips as an ipaddress object; coerce to str.
        return None if v is None else str(v)


@router.get("", response_model=list[AuditEntryOut])
def list_audit(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    _: models.User = Depends(require_roles()),  # admin only
) -> list[AuditEntryOut]:
    return [AuditEntryOut.model_validate(e) for e in svc.list_audit(session, tenant.id)]
