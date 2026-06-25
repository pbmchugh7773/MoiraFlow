import pytest
from fastapi.testclient import TestClient

from moiraflow_api.deps import get_session
from moiraflow_api.main import app
from tests._helpers import make_sqlite_factory, seed_user, session_override

WF = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: daily_import }
spec:
  trigger: { type: manual }
  jobs:
    - id: fetch
      type: command
      with: { command: "echo hi" }
"""


@pytest.fixture
def factory():
    return make_sqlite_factory()


@pytest.fixture
def client(factory):
    """Client with a real DB but NO auth override — exercises the real auth flow."""
    app.dependency_overrides[get_session] = session_override(factory)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_returns_token_and_me_works(client, factory):
    seed_user(factory, role="developer")
    resp = client.post("/api/v1/auth/login", json={"email": "developer@x.io", "password": "pw"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "developer@x.io"
    assert me.json()["role"] == "developer"


def test_login_wrong_password_401(client, factory):
    seed_user(factory, role="developer")
    resp = client.post("/api/v1/auth/login", json={"email": "developer@x.io", "password": "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_unauthenticated_request_401(client, factory):
    seed_user(factory)
    assert client.get("/api/v1/workflows").status_code == 401


def test_invalid_token_401(client, factory):
    seed_user(factory)
    resp = client.get("/api/v1/workflows", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"


def _login(client, role):
    return client.post(
        "/api/v1/auth/login", json={"email": f"{role}@x.io", "password": "pw"}
    ).json()["access_token"]


def test_viewer_cannot_create_workflow_403(client, factory):
    seed_user(factory, role="viewer")
    token = _login(client, "viewer")
    resp = client.post(
        "/api/v1/workflows",
        json={"content": WF},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_developer_can_create_workflow(client, factory):
    seed_user(factory, role="developer")
    token = _login(client, "developer")
    resp = client.post(
        "/api/v1/workflows",
        json={"content": WF},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
