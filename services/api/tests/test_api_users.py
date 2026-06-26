import pytest
from fastapi.testclient import TestClient

from moiraflow_api.deps import get_current_user, get_session
from moiraflow_api.main import app
from tests._helpers import make_sqlite_factory, seed_user, session_override


def _client(role):
    factory = make_sqlite_factory()
    user = seed_user(factory, role=role)
    app.dependency_overrides[get_session] = session_override(factory)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def admin_client():
    client = _client("admin")
    yield client
    app.dependency_overrides.clear()


def test_admin_creates_lists_and_deactivates_users(admin_client):
    created = admin_client.post(
        "/api/v1/users", json={"email": "dev@x.io", "password": "pw", "role": "developer"}
    )
    assert created.status_code == 201
    assert created.json()["role"] == "developer"
    uid = created.json()["id"]

    listing = admin_client.get("/api/v1/users").json()
    assert {u["email"] for u in listing} >= {"admin@x.io", "dev@x.io"}

    deact = admin_client.post(f"/api/v1/users/{uid}/deactivate")
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False


def test_duplicate_email_returns_409(admin_client):
    admin_client.post("/api/v1/users", json={"email": "d@x.io", "password": "pw"})
    resp = admin_client.post("/api/v1/users", json={"email": "d@x.io", "password": "pw"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "user_exists"


def test_non_admin_forbidden():
    client = _client("developer")
    try:
        assert client.get("/api/v1/users").status_code == 403
        assert (
            client.post("/api/v1/users", json={"email": "x@x.io", "password": "p"}).status_code
            == 403
        )
    finally:
        app.dependency_overrides.clear()
