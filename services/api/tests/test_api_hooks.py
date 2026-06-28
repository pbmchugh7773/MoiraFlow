import pytest
from fastapi.testclient import TestClient

from moiraflow_api.deps import (
    get_current_user,
    get_session,
    get_schedule_manager,
    get_workflow_starter,
)
from moiraflow_api.main import app
from tests._helpers import make_sqlite_factory, seed_user, session_override

WEBHOOK_WF = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: hooked }
spec:
  trigger: { type: webhook }
  jobs:
    - id: run
      type: command
      with: { command: "echo hi" }
"""

MANUAL_WF = WEBHOOK_WF.replace("name: hooked", "name: manual_one").replace(
    "trigger: { type: webhook }", "trigger: { type: manual }"
)


class FakeStarter:
    def __init__(self):
        self.calls = []

    def start(self, *, temporal_workflow_id, definition, input_context, task_queue, meta=None):
        self.calls.append(temporal_workflow_id)
        return f"run-{len(self.calls)}"

    def cancel(self, *, temporal_workflow_id):
        pass


class FakeSchedules:
    def upsert(self, **kwargs):
        pass

    def pause(self, schedule_id):
        pass


@pytest.fixture
def client():
    factory = make_sqlite_factory()
    admin = seed_user(factory, role="admin")
    app.dependency_overrides[get_session] = session_override(factory)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_workflow_starter] = lambda: FakeStarter()
    app.dependency_overrides[get_schedule_manager] = lambda: FakeSchedules()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_webhook_workflow_gets_token_and_fires(client):
    wf = client.post("/api/v1/workflows", json={"content": WEBHOOK_WF}).json()
    token = wf["trigger_config"]["webhook_token"]
    assert token  # server-issued

    fired = client.post(f"/api/v1/hooks/{wf['id']}?token={token}", json={"source": "github"})
    assert fired.status_code == 200
    assert fired.json()["execution_id"]


def test_wrong_token_rejected(client):
    wf = client.post("/api/v1/workflows", json={"content": WEBHOOK_WF}).json()
    resp = client.post(f"/api/v1/hooks/{wf['id']}?token=nope")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_webhook"


def test_non_webhook_workflow_cannot_be_fired(client):
    wf = client.post("/api/v1/workflows", json={"content": MANUAL_WF}).json()
    resp = client.post(f"/api/v1/hooks/{wf['id']}?token=anything")
    assert resp.status_code == 401
