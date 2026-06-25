import uuid

import pytest
from fastapi.testclient import TestClient

from moiraflow_api.db import models
from moiraflow_api.deps import get_current_user
from moiraflow_api.main import app


@pytest.fixture
def client():
    # validate is stateless (no DB); just satisfy authentication with a transient user.
    app.dependency_overrides[get_current_user] = lambda: models.User(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), email="t@x.io", password_hash="", role="developer"
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


GOOD_YAML = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: daily_import }
spec:
  trigger: { type: manual }
  context: { url: "https://x" }
  jobs:
    - id: fetch
      type: command
      with: { command: "curl {{ context.url }}" }
      outputs: { path: /tmp/data }
    - id: load
      type: command
      needs: [fetch]
      with: { command: "cat {{ jobs.fetch.outputs.path }}" }
"""


def test_validate_good_workflow_returns_valid(client):
    resp = client.post("/api/v1/workflows/validate", json={"content": GOOD_YAML, "format": "yaml"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_validate_reports_semantic_errors(client):
    bad = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: n }
spec:
  trigger: { type: manual }
  jobs:
    - id: a
      type: command
      needs: [ghost]
      with: { command: "echo {{ context.missing }}" }
"""
    resp = client.post("/api/v1/workflows/validate", json={"content": bad, "format": "yaml"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    codes = {e["code"] for e in body["errors"]}
    assert "unknown_dependency" in codes
    assert "unknown_context_ref" in codes


def test_validate_reports_parse_error(client):
    resp = client.post(
        "/api/v1/workflows/validate", json={"content": "metadata: [unclosed", "format": "yaml"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "parse_error"


def test_validate_accepts_json_format(client):
    import json

    definition = json.dumps(
        {
            "apiVersion": "moiraflow/v1",
            "kind": "Workflow",
            "metadata": {"name": "n"},
            "spec": {
                "trigger": {"type": "manual"},
                "jobs": [{"id": "j", "type": "command", "with": {"command": "ls"}}],
            },
        }
    )
    resp = client.post("/api/v1/workflows/validate", json={"content": definition, "format": "json"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
