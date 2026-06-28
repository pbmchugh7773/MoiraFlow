"""Authentication endpoints: login (issue JWT) and current-user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..auth.exceptions import AuthError
from ..auth.security import create_access_token
from ..config import get_settings
from ..db import models
from ..deps import get_current_user, get_default_tenant, get_session
from ..schemas.auth import LoginRequest, TokenResponse, UserOut
from ..services import audit as audit_svc
from ..services import users as user_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    http_request: Request,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_default_tenant),
) -> TokenResponse:
    user = user_svc.authenticate(session, tenant.id, request.email, request.password)
    if user is None:
        raise AuthError(401, "invalid_credentials", "invalid email or password")
    audit_svc.record(
        session,
        tenant_id=tenant.id,
        action="auth.login",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        ip_address=http_request.client.host if http_request.client else None,
    )
    settings = get_settings()
    token = create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        secret=settings.jwt_secret,
        expires_in=settings.jwt_expires_seconds,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_seconds)


@router.post("/refresh", response_model=TokenResponse)
def refresh(user: models.User = Depends(get_current_user)) -> TokenResponse:
    """Sliding session: exchange a still-valid token for a fresh one."""
    settings = get_settings()
    token = create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        secret=settings.jwt_secret,
        expires_in=settings.jwt_expires_seconds,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_seconds)


@router.post("/logout", status_code=204)
def logout(_: models.User = Depends(get_current_user)) -> Response:
    """Stateless JWTs can't be server-revoked in the MVP; the client discards the
    token. Endpoint exists so the UI has a single sign-out contract (and audit hook)."""
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
