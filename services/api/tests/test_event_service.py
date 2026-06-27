import pytest
from sqlalchemy import create_engine, select
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


def test_scheduled_run_is_auto_registered_from_meta(session):
    # a fresh tenant/workflow/version, but NO execution row (as if started by a schedule)
    tenant = models.Tenant(name="T", slug="t")
    session.add(tenant)
    session.flush()
    wf = models.Workflow(tenant_id=tenant.id, name="cronwf", trigger_type="cron")
    session.add(wf)
    session.flush()
    ver = models.WorkflowVersion(
        tenant_id=tenant.id, workflow_id=wf.id, version=1, definition={}, definition_hash="x" * 64
    )
    session.add(ver)
    session.flush()

    event = {
        "temporal_workflow_id": "sched-run-1",
        "type": "execution_started",
        "payload": {
            "job_count": 1,
            "meta": {
                "tenant_id": str(tenant.id),
                "workflow_id": str(wf.id),
                "workflow_version_id": str(ver.id),
            },
        },
    }
    row = svc.handle_event(session, event)
    assert row is not None
    created = session.scalar(
        select(models.Execution).where(models.Execution.temporal_workflow_id == "sched-run-1")
    )
    assert created is not None
    assert created.workflow_id == wf.id
    assert created.trigger_source == "cron"
    assert created.status == "running"


def test_unknown_run_without_meta_still_ignored(session):
    # job_started for an unknown run (no meta) must not create anything
    assert svc.handle_event(session, _ev("job_started")) is None


def _job_ev(type_, job_id, payload=None):
    return {
        "temporal_workflow_id": "wf-abc",
        "type": type_,
        "job_id": job_id,
        "payload": payload or {},
    }


def test_job_executions_projected_from_events(session, execution):
    svc.handle_event(session, _job_ev("job_started", "a", {"type": "command"}))
    svc.handle_event(session, _job_ev("job_succeeded", "a", {"outputs": {"k": "v"}}))
    svc.handle_event(session, _job_ev("job_started", "b", {"type": "rest"}))
    svc.handle_event(session, _job_ev("job_failed", "b", {"error": "boom"}))

    jobs = svc.list_job_executions(session, execution.id)
    by_id = {j.job_id: j for j in jobs}
    assert by_id["a"].status == "success"
    assert by_id["a"].job_type == "command"
    assert by_id["a"].output == {"k": "v"}
    assert by_id["b"].status == "failed"
    assert by_id["b"].error == {"error": "boom"}
    assert by_id["a"].finished_at is not None


def test_artifacts_persisted_from_job_succeeded(session, execution):
    svc.handle_event(session, _job_ev("job_started", "a", {"type": "command"}))
    svc.handle_event(
        session,
        _job_ev(
            "job_succeeded",
            "a",
            {
                "outputs": {},
                "artifacts": [
                    {
                        "name": "out.csv",
                        "bucket": "arts",
                        "object_key": "a/out.csv",
                        "size_bytes": 42,
                        "content_type": "text/csv",
                    }
                ],
            },
        ),
    )
    arts = svc.list_artifacts(session, execution.id)
    assert len(arts) == 1
    assert arts[0].name == "out.csv"
    assert arts[0].object_key == "a/out.csv"
    assert arts[0].job_execution_id is not None


def test_event_without_workflow_id_is_ignored(session):
    assert svc.handle_event(session, {"type": "execution_started", "payload": {}}) is None
