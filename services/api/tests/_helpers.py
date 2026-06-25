"""Shared test helpers: in-memory sqlite factory + seeded users."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from moiraflow_api.auth.security import hash_password
from moiraflow_api.db import models
from moiraflow_api.db.base import Base


def make_sqlite_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def seed_user(factory: sessionmaker[Session], role: str = "admin") -> models.User:
    """Create the default tenant + a user with the given role; return the user."""
    with factory() as session:
        tenant = models.Tenant(name="Default", slug="default")
        session.add(tenant)
        session.flush()
        user = models.User(
            tenant_id=tenant.id,
            email=f"{role}@x.io",
            password_hash=hash_password("pw"),
            role=role,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def session_override(factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    def _override():  # type: ignore[no-untyped-def]
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _override
