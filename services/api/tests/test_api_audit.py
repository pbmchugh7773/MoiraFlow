import pytest
from fastapi.testclient import TestClient

from moiraflow_api.deps import get_session
from moiraflow_api.main import app
from tests._helpers import make_sqlite_factory, seed_user, session_override

WF = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: audited_wf }
spec:
  trigger: { type: manual }
  jobs:
    - id: j
      type: command
      with: { command: "echo hi" }
"""


@pytest.fixture
def factory():
    return make_sqlite_factory()


@pytest.fixture
def client(factory):
    app.dependency_overrides[get_session] = session_override(factory)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_and_workflow_create_are_audited(client, factory):
    seed_user(factory, role="admin")
    token = client.post(
        "/api/v1/auth/login", json={"email": "admin@x.io", "password": "pw"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/v1/workflows", json={"content": WF}, headers=headers)

    entries = client.get("/api/v1/audit", headers=headers).json()
    actions = {e["action"] for e in entries}
    assert "auth.login" in actions
    assert "workflow.create" in actions
    wf_entry = next(e for e in entries if e["action"] == "workflow.create")
    assert wf_entry["target_type"] == "workflow"
    assert wf_entry["actor_user_id"] is not None


def test_audit_requires_admin(client, factory):
    seed_user(factory, role="developer")
    token = client.post(
        "/api/v1/auth/login", json={"email": "developer@x.io", "password": "pw"}
    ).json()["access_token"]
    resp = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
