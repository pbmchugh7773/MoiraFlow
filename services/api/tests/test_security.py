import uuid
from datetime import datetime, timedelta, timezone

import pytest

from moiraflow_api.auth.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "test-secret-at-least-32-bytes-long-xx"


def test_hash_and_verify_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert h.startswith("$argon2id$")
    assert verify_password(h, "s3cret") is True


def test_verify_rejects_wrong_password():
    h = hash_password("s3cret")
    assert verify_password(h, "wrong") is False


def test_token_roundtrip_carries_claims():
    uid, tid = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(subject=uid, tenant_id=tid, role="admin", secret=SECRET)
    claims = decode_access_token(token, SECRET)
    assert claims["sub"] == str(uid)
    assert claims["tenant_id"] == str(tid)
    assert claims["role"] == "admin"


def test_expired_token_raises():
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    token = create_access_token(
        subject=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="viewer",
        secret=SECRET,
        expires_in=60,
        now=past,
    )
    with pytest.raises(TokenError):
        decode_access_token(token, SECRET)


def test_wrong_secret_raises():
    token = create_access_token(
        subject=uuid.uuid4(), tenant_id=uuid.uuid4(), role="viewer", secret=SECRET
    )
    with pytest.raises(TokenError):
        decode_access_token(token, "a-different-secret-also-32-bytes-long")
