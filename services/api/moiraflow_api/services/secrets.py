"""Secret storage encrypted at rest (provisional MVP — ADR-0007).

Symmetric authenticated encryption (Fernet) keyed by a SHA-256 digest of the
master key, so any env string works as `SECRETS_MASTER_KEY`. The worker uses the
SAME derivation to decrypt server-side at execution time (late resolution).
Values are never returned by the list/CRUD API — only keys.
"""

from __future__ import annotations

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models


class SecretNotFoundError(Exception):
    pass


def _fernet(master_key: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(master_key: str, plaintext: str) -> bytes:
    return _fernet(master_key).encrypt(plaintext.encode())


def decrypt_secret(master_key: str, ciphertext: bytes) -> str:
    return _fernet(master_key).decrypt(bytes(ciphertext)).decode()


def _get(session: Session, tenant_id: uuid.UUID, key: str) -> models.Secret | None:
    return session.scalar(
        select(models.Secret).where(models.Secret.tenant_id == tenant_id, models.Secret.key == key)
    )


def put_secret(
    session: Session,
    master_key: str,
    tenant_id: uuid.UUID,
    key: str,
    value: str,
    created_by: uuid.UUID | None = None,
) -> models.Secret:
    ciphertext = encrypt_secret(master_key, value)
    secret = _get(session, tenant_id, key)
    if secret is not None:
        secret.ciphertext = ciphertext
    else:
        secret = models.Secret(
            tenant_id=tenant_id, key=key, ciphertext=ciphertext, created_by=created_by
        )
        session.add(secret)
    session.flush()
    return secret


def list_keys(session: Session, tenant_id: uuid.UUID) -> list[str]:
    return list(
        session.scalars(
            select(models.Secret.key)
            .where(models.Secret.tenant_id == tenant_id)
            .order_by(models.Secret.key)
        )
    )


def get_value(session: Session, master_key: str, tenant_id: uuid.UUID, key: str) -> str:
    secret = _get(session, tenant_id, key)
    if secret is None:
        raise SecretNotFoundError(f"secret '{key}' not found")
    return decrypt_secret(master_key, secret.ciphertext)


def delete_secret(session: Session, tenant_id: uuid.UUID, key: str) -> None:
    secret = _get(session, tenant_id, key)
    if secret is None:
        raise SecretNotFoundError(f"secret '{key}' not found")
    session.delete(secret)
    session.flush()
