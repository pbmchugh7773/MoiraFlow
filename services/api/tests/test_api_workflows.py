import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from moiraflow_api.db.base import Base
from moiraflow_api.deps import get_session
from moiraflow_api.main import app

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
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def override() -> object:
        session: Session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_workflow_returns_201_and_active_version(client):
    resp = client.post("/api/v1/workflows", json={"content": WF, "format": "yaml"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "daily_import"
    assert body["trigger_type"] == "manual"
    assert body["active_version_id"] is not None


def test_create_invalid_returns_422_with_errors(client):
    bad = WF.replace("echo hi", "{{ context.missing }}")
    resp = client.post("/api/v1/workflows", json={"content": bad, "format": "yaml"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert any(d["code"] == "unknown_context_ref" for d in err["details"])


def test_duplicate_name_returns_409(client):
    client.post("/api/v1/workflows", json={"content": WF})
    resp = client.post("/api/v1/workflows", json={"content": WF})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "workflow_exists"


def test_list_and_get_workflow(client):
    created = client.post("/api/v1/workflows", json={"content": WF}).json()
    listing = client.get("/api/v1/workflows").json()
    assert len(listing) == 1
    detail = client.get(f"/api/v1/workflows/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]


def test_get_unknown_workflow_returns_404(client):
    resp = client.get("/api/v1/workflows/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_add_version_and_activate(client):
    wf = client.post("/api/v1/workflows", json={"content": WF}).json()
    wid = wf["id"]
    v2 = client.post(
        f"/api/v1/workflows/{wid}/versions",
        json={"content": WF.replace("echo hi", "echo bye")},
    )
    assert v2.status_code == 201
    assert v2.json()["version"] == 2

    versions = client.get(f"/api/v1/workflows/{wid}/versions").json()
    assert [v["version"] for v in versions] == [1, 2]

    activated = client.post(f"/api/v1/workflows/{wid}/activate/2")
    assert activated.status_code == 200
    assert activated.json()["active_version_id"] == v2.json()["id"]


def test_add_version_name_mismatch_returns_409(client):
    wf = client.post("/api/v1/workflows", json={"content": WF}).json()
    resp = client.post(
        f"/api/v1/workflows/{wf['id']}/versions",
        json={"content": WF.replace("daily_import", "other")},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "name_mismatch"
