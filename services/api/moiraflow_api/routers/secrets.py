"""Secret management endpoints (admin only). Values are never returned."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import models
from ..deps import get_current_tenant, get_session, require_roles
from ..schemas.secrets import PutSecretRequest, SecretKeysOut
from ..services import secrets as svc

router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.get("", response_model=SecretKeysOut)
def list_secrets(
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    _: models.User = Depends(require_roles()),  # admin only
) -> SecretKeysOut:
    return SecretKeysOut(keys=svc.list_keys(session, tenant.id))


@router.put("/{key}", status_code=204)
def put_secret(
    key: str,
    request: PutSecretRequest,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    actor: models.User = Depends(require_roles()),
) -> Response:
    svc.put_secret(
        session, get_settings().secrets_master_key, tenant.id, key, request.value, actor.id
    )
    return Response(status_code=204)


@router.delete("/{key}", status_code=204)
def delete_secret(
    key: str,
    session: Session = Depends(get_session),
    tenant: models.Tenant = Depends(get_current_tenant),
    _: models.User = Depends(require_roles()),
) -> Response:
    svc.delete_secret(session, tenant.id, key)
    return Response(status_code=204)
