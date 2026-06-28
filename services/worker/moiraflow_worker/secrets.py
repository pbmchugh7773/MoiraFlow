"""Late secret resolution + redaction for server-side jobs (docs 05 §4.3).

The server-side worker is trusted: it resolves `secret://<key>` by reading the
encrypted `secrets` row from the MoiraFlow DB and decrypting it in memory, only
during execution. The Fernet derivation MUST match moiraflow_api.services.secrets.
Resolved values never touch disk; logs/errors pass through `redact`.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import uuid
from typing import Any

from temporalio.exceptions import ApplicationError

SECRET_PREFIX = "secret://"
# mask `scheme://user:PASSWORD@host` -> `scheme://user:***@host`
_PASSWORD_RE = re.compile(r"(://[^:/@\s]+:)[^@/\s]+(@)")


def redact(text_value: str) -> str:
    return _PASSWORD_RE.sub(r"\1***\2", text_value)


def _fernet(master_key: str):  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest())
    return Fernet(key)


def decrypt(master_key: str, ciphertext: bytes) -> str:
    plaintext: str = _fernet(master_key).decrypt(bytes(ciphertext)).decode()
    return plaintext


_engine: Any | None = None


def _db() -> Any:
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine

        _engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    return _engine


def resolve_secret(tenant_id: str, key: str) -> str:
    from sqlalchemy import text

    with _db().connect() as conn:
        row = conn.execute(
            text("SELECT ciphertext FROM secrets WHERE tenant_id = :t AND key = :k"),
            {"t": uuid.UUID(tenant_id), "k": key},
        ).first()
    if row is None:
        # A missing secret won't appear by retrying — fail fast (non-retryable).
        raise ApplicationError(
            f"secret '{key}' not found", type="MissingSecret", non_retryable=True
        )
    master = os.environ.get("SECRETS_MASTER_KEY", "dev-insecure-master-key")
    return decrypt(master, row[0])


def resolve_reference(value: str, tenant_id: str | None) -> str:
    """Resolve a `secret://key` reference; pass other values through unchanged."""
    if not value.startswith(SECRET_PREFIX):
        return value
    if not tenant_id:
        raise ApplicationError(
            "cannot resolve secret:// without a tenant", type="MissingSecret", non_retryable=True
        )
    return resolve_secret(tenant_id, value[len(SECRET_PREFIX) :])
