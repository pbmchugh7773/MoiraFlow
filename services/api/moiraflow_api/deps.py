"""FastAPI dependencies: per-request DB session and the default tenant.

The session dependency commits on success and rolls back on error, so endpoints
just do their work. Tests override `get_session` to point at an in-memory sqlite
database (see tests/test_api_workflows.py).
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .db import models
from .db.session import make_engine, make_session_factory


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return make_session_factory(make_engine(get_settings().database_url))


def get_session() -> Iterator[Session]:
    session = _session_factory()()
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
