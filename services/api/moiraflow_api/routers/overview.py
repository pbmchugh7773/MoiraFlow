"""Operability dashboard aggregates."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import models
from ..deps import get_current_tenant, get_session
from ..services import overview as svc

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
def get_overview(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    return svc.get_overview(session, tenant.id)
