"""Password hashing (argon2id) and JWT access tokens.

Pure utilities — no DB, no FastAPI. `now` is injectable so token expiry is
testable without sleeping.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()  # argon2id by default
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


class TokenError(Exception):
    """Raised when a token is missing, malformed, or expired."""


def create_access_token(
    *,
    subject: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    secret: str,
    expires_in: int = 3600,
    now: datetime | None = None,
) -> str:
    issued = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=expires_in)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
