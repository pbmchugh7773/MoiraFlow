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
