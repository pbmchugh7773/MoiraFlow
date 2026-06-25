from fastapi.testclient import TestClient

from moiraflow_api.main import app

client = TestClient(app)

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


def test_validate_good_workflow_returns_valid():
    resp = client.post("/api/v1/workflows/validate", json={"content": GOOD_YAML, "format": "yaml"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_validate_reports_semantic_errors():
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


def test_validate_reports_parse_error():
    resp = client.post(
        "/api/v1/workflows/validate", json={"content": "metadata: [unclosed", "format": "yaml"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "parse_error"


def test_validate_accepts_json_format():
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
