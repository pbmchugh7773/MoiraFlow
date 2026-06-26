import pytest
from fastapi.testclient import TestClient

from moiraflow_api.deps import get_current_user, get_session, get_workflow_starter
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


class FakeStarter:
    def __init__(self):
        self.calls = []

    def start(self, *, temporal_workflow_id, definition, input_context, task_queue):
        self.calls.append(temporal_workflow_id)
        return f"run-{len(self.calls)}"


@pytest.fixture
def starter():
    return FakeStarter()


@pytest.fixture
def client(starter):
    factory = make_sqlite_factory()
    admin = seed_user(factory, role="admin")
    app.dependency_overrides[get_session] = session_override(factory)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_workflow_starter] = lambda: starter
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_workflow(client) -> str:
    return client.post("/api/v1/workflows", json={"content": WF}).json()["id"]


def test_launch_execution_returns_201(client, starter):
    wid = _make_workflow(client)
    resp = client.post("/api/v1/executions", json={"workflow_id": wid, "input_context": {"a": 1}})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["temporal_run_id"] == "run-1"
    assert len(starter.calls) == 1


def test_launch_is_idempotent_with_key(client, starter):
    wid = _make_workflow(client)
    a = client.post("/api/v1/executions", json={"workflow_id": wid, "idempotency_key": "k1"}).json()
    b = client.post("/api/v1/executions", json={"workflow_id": wid, "idempotency_key": "k1"}).json()
    assert a["id"] == b["id"]
    assert len(starter.calls) == 1


def test_get_and_list_executions(client):
    wid = _make_workflow(client)
    created = client.post(
        "/api/v1/executions", json={"workflow_id": wid, "input_context": {"a": 1}}
    ).json()
    detail = client.get(f"/api/v1/executions/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    listing = client.get(f"/api/v1/executions?workflow_id={wid}").json()
    assert len(listing) == 1


def test_execution_definition_returns_jobs(client):
    wid = _make_workflow(client)
    ex = client.post("/api/v1/executions", json={"workflow_id": wid}).json()
    resp = client.get(f"/api/v1/executions/{ex['id']}/definition")
    assert resp.status_code == 200
    assert resp.json()["spec"]["jobs"][0]["id"] == "fetch"


def test_launch_unknown_workflow_404(client):
    resp = client.post(
        "/api/v1/executions",
        json={"workflow_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_replay_creates_linked_execution(client, starter):
    wid = _make_workflow(client)
    original = client.post("/api/v1/executions", json={"workflow_id": wid}).json()
    resp = client.post(f"/api/v1/executions/{original['id']}/replay")
    assert resp.status_code == 201, resp.text
    replay = resp.json()
    assert replay["id"] != original["id"]
    assert replay["status"] == "running"
    assert len(starter.calls) == 2


def test_get_unknown_execution_404(client):
    resp = client.get("/api/v1/executions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
