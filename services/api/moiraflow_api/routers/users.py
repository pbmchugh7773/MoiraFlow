"""User management endpoints (admin only)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import models
from ..deps import get_current_tenant, get_session, require_roles
from ..schemas.auth import CreateUserRequest, UserOut
from ..services import audit as audit_svc
from ..services import users as svc

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    _: models.User = Depends(require_roles()),
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in svc.list_users(session, tenant.id)]


@router.post("", status_code=201, response_model=UserOut)
def create_user(
    request: CreateUserRequest,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    actor: models.User = Depends(require_roles()),
) -> UserOut:
    user = svc.create_user(session, tenant.id, request.email, request.password, request.role)
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="user.create",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(user.id),
        metadata={"role": user.role},
    )
    return UserOut.model_validate(user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: uuid.UUID,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    actor: models.User = Depends(require_roles()),
) -> UserOut:
    user = svc.set_active(session, user_id, False)
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="user.deactivate",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(user_id),
    )
    return UserOut.model_validate(user)


@router.post("/{user_id}/activate", response_model=UserOut)
def activate_user(
    user_id: uuid.UUID,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    actor: models.User = Depends(require_roles()),
) -> UserOut:
    user = svc.set_active(session, user_id, True)
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="user.activate",
        actor_user_id=actor.id,
        target_type="user",
        target_id=str(user_id),
    )
    return UserOut.model_validate(user)
