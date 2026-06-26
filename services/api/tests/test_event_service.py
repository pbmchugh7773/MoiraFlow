import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.services import events as svc


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def execution(session):
    tenant = models.Tenant(name="Default", slug="default")
    session.add(tenant)
    session.flush()
    wf = models.Workflow(tenant_id=tenant.id, name="wf", trigger_type="manual")
    session.add(wf)
    session.flush()
    ver = models.WorkflowVersion(
        tenant_id=tenant.id, workflow_id=wf.id, version=1, definition={}, definition_hash="x" * 64
    )
    session.add(ver)
    session.flush()
    ex = models.Execution(
        tenant_id=tenant.id,
        workflow_id=wf.id,
        workflow_version_id=ver.id,
        temporal_workflow_id="wf-abc",
        status="pending",
    )
    session.add(ex)
    session.flush()
    return ex


def _ev(type_, payload=None):
    return {"temporal_workflow_id": "wf-abc", "type": type_, "payload": payload or {}}


def test_started_event_sets_running(session, execution):
    svc.handle_event(session, _ev("execution_started", {"job_count": 2}))
    assert execution.status == "running"
    assert execution.started_at is not None
    assert len(svc.list_events(session, execution.id)) == 1


def test_finished_event_sets_success(session, execution):
    svc.handle_event(session, _ev("execution_finished", {"status": "success"}))
    assert execution.status == "success"
    assert execution.finished_at is not None


def test_failed_event_sets_failed_and_records_error(session, execution):
    svc.handle_event(session, _ev("execution_failed", {"error": "boom"}))
    assert execution.status == "failed"
    assert execution.error == {"error": "boom"}


def test_job_events_are_stored_in_order(session, execution):
    for t in ("execution_started", "job_started", "job_succeeded", "execution_finished"):
        svc.handle_event(session, _ev(t))
    rows = svc.list_events(session, execution.id)
    assert [r.event_type for r in rows] == [
        "execution_started",
        "job_started",
        "job_succeeded",
        "execution_finished",
    ]


def test_unknown_execution_is_ignored(session):
    assert svc.handle_event(session, _ev("execution_started")) is None


def test_event_without_workflow_id_is_ignored(session):
    assert svc.handle_event(session, {"type": "execution_started", "payload": {}}) is None
