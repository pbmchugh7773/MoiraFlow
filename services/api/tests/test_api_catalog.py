from fastapi.testclient import TestClient

from moiraflow_api.main import app

client = TestClient(app)


def test_workflow_schema_endpoint_returns_json_schema():
    resp = client.get("/api/v1/catalog/workflow-schema")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["title"] == "WorkflowDefinition"
    assert "properties" in schema


def test_openapi_is_served():
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "MoiraFlow API"


def test_job_types_catalog():
    resp = client.get("/api/v1/catalog/job-types")
    assert resp.status_code == 200
    types = {t["type"] for t in resp.json()}
    assert types == {"command", "rest", "sql"}
    command = next(t for t in resp.json() if t["type"] == "command")
    assert "command" in command["input_schema"]["properties"]
