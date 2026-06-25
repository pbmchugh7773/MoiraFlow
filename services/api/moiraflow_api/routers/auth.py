"""Authentication endpoints: login (issue JWT) and current-user."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.exceptions import AuthError
from ..auth.security import create_access_token
from ..config import get_settings
from ..db import models
from ..deps import get_current_user, get_default_tenant, get_session
from ..schemas.auth import LoginRequest, TokenResponse, UserOut
from ..services import users as user_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_default_tenant),
) -> TokenResponse:
    user = user_svc.authenticate(session, tenant.id, request.email, request.password)
    if user is None:
        raise AuthError(401, "invalid_credentials", "invalid email or password")
    settings = get_settings()
    token = create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        secret=settings.jwt_secret,
        expires_in=settings.jwt_expires_seconds,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_seconds)


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
