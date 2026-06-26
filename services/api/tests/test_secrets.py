import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.deps import get_current_user, get_session
from moiraflow_api.main import app
from moiraflow_api.services import secrets as svc
from tests._helpers import make_sqlite_factory, seed_user, session_override

MASTER = "test-master-key"


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant(session):
    t = models.Tenant(name="T", slug="default")
    session.add(t)
    session.flush()
    return t


def test_encrypt_decrypt_roundtrip():
    cipher = svc.encrypt_secret(MASTER, "pg://user:pw@host/db")
    assert cipher != b"pg://user:pw@host/db"
    assert svc.decrypt_secret(MASTER, cipher) == "pg://user:pw@host/db"


def test_put_get_and_overwrite(session, tenant):
    svc.put_secret(session, MASTER, tenant.id, "pg_main", "dsn-1")
    assert svc.get_value(session, MASTER, tenant.id, "pg_main") == "dsn-1"
    svc.put_secret(session, MASTER, tenant.id, "pg_main", "dsn-2")  # overwrite
    assert svc.get_value(session, MASTER, tenant.id, "pg_main") == "dsn-2"
    assert svc.list_keys(session, tenant.id) == ["pg_main"]


def test_get_unknown_raises(session, tenant):
    with pytest.raises(svc.SecretNotFoundError):
        svc.get_value(session, MASTER, tenant.id, "ghost")


def test_ciphertext_stored_not_plaintext(session, tenant):
    svc.put_secret(session, MASTER, tenant.id, "k", "supersecret")
    row = session.scalar(__import__("sqlalchemy").select(models.Secret))
    assert b"supersecret" not in bytes(row.ciphertext)


# --- endpoint RBAC ---


def _client(role):
    factory = make_sqlite_factory()
    user = seed_user(factory, role=role)
    app.dependency_overrides[get_session] = session_override(factory)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_admin_can_manage_secrets():
    client = _client("admin")
    try:
        assert client.put("/api/v1/secrets/pg_main", json={"value": "dsn"}).status_code == 204
        assert client.get("/api/v1/secrets").json() == {"keys": ["pg_main"]}
        assert client.delete("/api/v1/secrets/pg_main").status_code == 204
        assert client.get("/api/v1/secrets").json() == {"keys": []}
    finally:
        app.dependency_overrides.clear()


def test_non_admin_forbidden():
    client = _client("developer")
    try:
        assert client.get("/api/v1/secrets").status_code == 403
        assert client.put("/api/v1/secrets/x", json={"value": "y"}).status_code == 403
    finally:
        app.dependency_overrides.clear()
