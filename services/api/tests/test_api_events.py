import pytest
from fastapi.testclient import TestClient

from moiraflow_api.db import models
from moiraflow_api.deps import get_current_user, get_session
from moiraflow_api.main import app
from moiraflow_api.services import events as events_svc
from tests._helpers import make_sqlite_factory, seed_user, session_override


@pytest.fixture
def setup():
    factory = make_sqlite_factory()
    admin = seed_user(factory, role="admin")
    with factory() as s:
        wf = models.Workflow(tenant_id=admin.tenant_id, name="wf", trigger_type="manual")
        s.add(wf)
        s.flush()
        ver = models.WorkflowVersion(
            tenant_id=admin.tenant_id,
            workflow_id=wf.id,
            version=1,
            definition={},
            definition_hash="x" * 64,
        )
        s.add(ver)
        s.flush()
        ex = models.Execution(
            tenant_id=admin.tenant_id,
            workflow_id=wf.id,
            workflow_version_id=ver.id,
            temporal_workflow_id="wf-abc",
            status="pending",
        )
        s.add(ex)
        s.flush()
        events_svc.handle_event(
            s,
            {
                "temporal_workflow_id": "wf-abc",
                "type": "execution_started",
                "payload": {"job_count": 1},
            },
        )
        events_svc.handle_event(
            s,
            {
                "temporal_workflow_id": "wf-abc",
                "type": "execution_finished",
                "payload": {"status": "success"},
            },
        )
        s.commit()
        execution_id = str(ex.id)

    app.dependency_overrides[get_session] = session_override(factory)
    app.dependency_overrides[get_current_user] = lambda: admin
    yield TestClient(app), execution_id
    app.dependency_overrides.clear()


def test_events_endpoint_returns_persisted_events(setup):
    client, execution_id = setup
    resp = client.get(f"/api/v1/executions/{execution_id}/events")
    assert resp.status_code == 200
    types = [e["event_type"] for e in resp.json()]
    assert types == ["execution_started", "execution_finished"]


def test_execution_status_reflects_events(setup):
    client, execution_id = setup
    detail = client.get(f"/api/v1/executions/{execution_id}")
    assert detail.json()["status"] == "success"


def test_events_for_unknown_execution_404(setup):
    client, _ = setup
    resp = client.get("/api/v1/executions/00000000-0000-0000-0000-000000000000/events")
    assert resp.status_code == 404
