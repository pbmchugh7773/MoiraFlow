"""FastAPI dependencies: per-request DB session and the default tenant.

The session dependency commits on success and rolls back on error, so endpoints
just do their work. Tests override `get_session` to point at an in-memory sqlite
database (see tests/test_api_workflows.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .auth.exceptions import AuthError
from .auth.security import TokenError, decode_access_token
from .config import get_settings
from .db import models
from .db.session import make_engine, make_session_factory
from .services import users as user_svc
from .services.agents import AgentTokenStore
from .services.executions import WorkflowStarter
from .services.schedules import ScheduleManager

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def session_factory() -> sessionmaker[Session]:
    return make_session_factory(make_engine(get_settings().database_url))


def get_session() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_default_tenant(session: Session = Depends(get_session)) -> models.Tenant:
    """MVP runs a single operational tenant; ensure it exists."""
    tenant = session.scalar(select(models.Tenant).where(models.Tenant.slug == "default"))
    if tenant is None:
        tenant = models.Tenant(name="Default", slug="default")
        session.add(tenant)
        session.flush()
    return tenant


def get_workflow_starter() -> WorkflowStarter:
    """The production Temporal starter. Tests override this with a fake."""
    from .temporal import TemporalWorkflowStarter

    settings = get_settings()
    return TemporalWorkflowStarter(
        settings.temporal_host, settings.temporal_namespace, settings.secrets_master_key
    )


def get_schedule_manager() -> ScheduleManager:
    """The production Temporal schedule manager. Tests override this with a fake."""
    from .temporal import TemporalScheduleManager

    settings = get_settings()
    return TemporalScheduleManager(
        settings.temporal_host, settings.temporal_namespace, settings.secrets_master_key
    )


def get_agent_token_store() -> AgentTokenStore:
    """The production (Redis-backed) enrollment token store. Tests override this."""
    from .services.agents import RedisAgentTokenStore

    return RedisAgentTokenStore(get_settings().redis_url)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> models.User:
    if credentials is None:
        raise AuthError(401, "unauthenticated", "missing bearer token")
    try:
        claims = decode_access_token(credentials.credentials, get_settings().jwt_secret)
        user_id = uuid.UUID(claims["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise AuthError(401, "invalid_token", f"invalid token: {exc}") from exc
    try:
        return user_svc.get_user(session, user_id)
    except user_svc.UserNotFoundError as exc:
        raise AuthError(401, "invalid_token", "token subject not found") from exc


def get_current_tenant(
    user: models.User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> models.Tenant:
    tenant = session.get(models.Tenant, user.tenant_id)
    if tenant is None:  # pragma: no cover - tenant FK guards this
        raise AuthError(401, "invalid_token", "tenant not found")
    return tenant


def require_roles(*allowed: str) -> Callable[[models.User], models.User]:
    """RBAC guard. `admin` is always permitted (docs 04 §A.8)."""
    permitted = set(allowed) | {"admin"}

    def dependency(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in permitted:
            raise AuthError(403, "forbidden", f"role '{user.role}' may not perform this action")
        return user

    return dependency
