import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.services import executions as ex
from moiraflow_api.services import workflows as wf_svc

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
        self.cancelled = []
        self.describe_result = None
        self.described = []

    def start(self, *, temporal_workflow_id, definition, input_context, task_queue, meta=None):
        self.calls.append(
            {
                "id": temporal_workflow_id,
                "definition": definition,
                "input": input_context,
                "meta": meta,
            }
        )
        return f"run-{len(self.calls)}"

    def cancel(self, *, temporal_workflow_id):
        self.cancelled.append(temporal_workflow_id)

    def describe_status(self, *, temporal_workflow_id):
        self.described.append(temporal_workflow_id)
        return self.describe_result


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant(session):
    t = models.Tenant(name="Default", slug="default")
    session.add(t)
    session.flush()
    return t


@pytest.fixture
def workflow(session, tenant):
    return wf_svc.create_workflow(session, tenant.id, WF, "yaml")


def test_create_execution_starts_and_projects_row(session, tenant, workflow):
    starter = FakeStarter()
    execution = ex.create_execution(
        session, tenant.id, workflow.id, starter, input_context={"a": 1}
    )
    assert execution.status == "running"
    assert execution.workflow_version_id == workflow.active_version_id
    assert execution.temporal_run_id == "run-1"
    assert len(starter.calls) == 1
    assert starter.calls[0]["input"] == {"a": 1}
    # the started definition is the immutable stored version
    assert starter.calls[0]["definition"]["metadata"]["name"] == "daily_import"


def test_idempotency_key_does_not_start_twice(session, tenant, workflow):
    starter = FakeStarter()
    first = ex.create_execution(session, tenant.id, workflow.id, starter, idempotency_key="abc")
    second = ex.create_execution(session, tenant.id, workflow.id, starter, idempotency_key="abc")
    assert first.id == second.id
    assert len(starter.calls) == 1  # second call returned the existing projection


def test_same_inputs_are_idempotent_without_key(session, tenant, workflow):
    starter = FakeStarter()
    a = ex.create_execution(session, tenant.id, workflow.id, starter, input_context={"x": 1})
    b = ex.create_execution(session, tenant.id, workflow.id, starter, input_context={"x": 1})
    assert a.id == b.id
    assert len(starter.calls) == 1


def test_different_inputs_start_separate_executions(session, tenant, workflow):
    starter = FakeStarter()
    a = ex.create_execution(session, tenant.id, workflow.id, starter, input_context={"x": 1})
    b = ex.create_execution(session, tenant.id, workflow.id, starter, input_context={"x": 2})
    assert a.id != b.id
    assert len(starter.calls) == 2


def test_explicit_unknown_version_raises(session, tenant, workflow):
    with pytest.raises(wf_svc.VersionNotFoundError):
        ex.create_execution(session, tenant.id, workflow.id, FakeStarter(), version=99)


def _stale_running(session, tenant, workflow, starter):
    """A running execution old enough to be eligible for reconciliation."""
    execution = ex.create_execution(session, tenant.id, workflow.id, starter)
    execution.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.flush()
    return execution


def test_reconcile_heals_stale_running_from_temporal(session, tenant, workflow):
    starter = FakeStarter()
    execution = _stale_running(session, tenant, workflow, starter)
    starter.describe_result = "success"  # Temporal says it finished (events were lost)

    ex.reconcile_status(session, execution, starter)

    assert execution.status == "success"
    assert execution.finished_at is not None
    assert starter.described == [execution.temporal_workflow_id]


def test_reconcile_skips_fresh_running(session, tenant, workflow):
    # A just-launched run is left alone — its events will arrive normally.
    starter = FakeStarter()
    starter.describe_result = "success"
    execution = ex.create_execution(session, tenant.id, workflow.id, starter)

    ex.reconcile_status(session, execution, starter)

    assert execution.status == "running"
    assert starter.described == []  # Temporal not consulted for a fresh run


def test_reconcile_noop_when_temporal_still_running(session, tenant, workflow):
    starter = FakeStarter()
    execution = _stale_running(session, tenant, workflow, starter)
    starter.describe_result = None  # still running / unknown

    ex.reconcile_status(session, execution, starter)

    assert execution.status == "running"


def test_reconcile_ignores_terminal_executions(session, tenant, workflow):
    starter = FakeStarter()
    execution = _stale_running(session, tenant, workflow, starter)
    execution.status = "success"
    starter.describe_result = "failed"  # must be ignored

    ex.reconcile_status(session, execution, starter)

    assert execution.status == "success"
    assert starter.described == []


def test_workflow_without_active_version_raises(session, tenant):
    wf = models.Workflow(tenant_id=tenant.id, name="empty", trigger_type="manual")
    session.add(wf)
    session.flush()
    with pytest.raises(ex.WorkflowNotReadyError):
        ex.create_execution(session, tenant.id, wf.id, FakeStarter())


def test_replay_creates_new_execution_linked_to_original(session, tenant, workflow):
    starter = FakeStarter()
    original = ex.create_execution(session, tenant.id, workflow.id, starter, input_context={"x": 1})
    replay = ex.replay_execution(session, tenant.id, original.id, starter)
    assert replay.id != original.id
    assert replay.replay_of_execution_id == original.id
    assert replay.trigger_source == "replay"
    assert replay.input_context == {"x": 1}
    assert replay.temporal_workflow_id.startswith(f"{original.temporal_workflow_id}-replay-")
    assert len(starter.calls) == 2


def test_each_replay_gets_a_unique_fresh_id(session, tenant, workflow):
    # Replays never collide: each is an explicit re-run with its own durable id.
    starter = FakeStarter()
    original = ex.create_execution(session, tenant.id, workflow.id, starter)
    first = ex.replay_execution(session, tenant.id, original.id, starter)
    second = ex.replay_execution(session, tenant.id, original.id, starter)
    assert first.temporal_workflow_id != second.temporal_workflow_id
    assert len(starter.calls) == 3  # original + two distinct replays


def test_cancel_running_execution(session, tenant, workflow):
    starter = FakeStarter()
    ex_row = ex.create_execution(session, tenant.id, workflow.id, starter)
    cancelled = ex.cancel_execution(session, ex_row.id, starter)
    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    assert starter.cancelled == [ex_row.temporal_workflow_id]


def test_cancel_terminal_execution_is_noop(session, tenant, workflow):
    starter = FakeStarter()
    ex_row = ex.create_execution(session, tenant.id, workflow.id, starter)
    ex_row.status = "success"
    session.flush()
    ex.cancel_execution(session, ex_row.id, starter)
    assert starter.cancelled == []  # already finished


def test_get_unknown_execution_raises(session):
    with pytest.raises(ex.ExecutionNotFoundError):
        ex.get_execution(session, uuid.uuid4())


def test_list_executions_filtered_by_workflow(session, tenant, workflow):
    starter = FakeStarter()
    ex.create_execution(session, tenant.id, workflow.id, starter, input_context={"x": 1})
    ex.create_execution(session, tenant.id, workflow.id, starter, input_context={"x": 2})
    assert len(ex.list_executions(session, tenant.id, workflow.id)) == 2
    assert ex.list_executions(session, tenant.id, uuid.uuid4()) == []
