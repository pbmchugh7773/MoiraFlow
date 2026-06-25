"""User management + authentication (argon2id-hashed passwords)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.security import hash_password, verify_password
from ..db import models


class UserServiceError(Exception):
    pass


class UserNotFoundError(UserServiceError):
    pass


class UserExistsError(UserServiceError):
    pass


def get_user_by_email(session: Session, tenant_id: uuid.UUID, email: str) -> models.User | None:
    return session.scalar(
        select(models.User).where(models.User.tenant_id == tenant_id, models.User.email == email)
    )


def create_user(
    session: Session,
    tenant_id: uuid.UUID,
    email: str,
    password: str,
    role: str = "viewer",
) -> models.User:
    if get_user_by_email(session, tenant_id, email) is not None:
        raise UserExistsError(email)
    user = models.User(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def authenticate(
    session: Session, tenant_id: uuid.UUID, email: str, password: str
) -> models.User | None:
    user = get_user_by_email(session, tenant_id, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user


def get_user(session: Session, user_id: uuid.UUID) -> models.User:
    user = session.get(models.User, user_id)
    if user is None:
        raise UserNotFoundError(f"user {user_id} not found")
    return user
