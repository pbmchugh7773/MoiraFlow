import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.services import secrets as secrets_svc
from moiraflow_api.services import simulation as sim

WF = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: sim }
spec:
  trigger: { type: manual }
  jobs:
    - id: a
      type: command
      run_on: agent
      with: { command: "echo hi" }
      outputs: { ok: "1" }
    - id: b
      type: sql
      needs: [a]
      with: { connection: "secret://pg_main", statement: "SELECT 1" }
"""


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant(session):
    t = models.Tenant(name="T", slug="default")
    session.add(t)
    session.flush()
    return t


def test_simulate_returns_ordered_plan_with_routing(session, tenant):
    result = sim.simulate(session, tenant.id, WF, "yaml")
    assert result.valid
    assert [s.job_id for s in result.plan] == ["a", "b"]  # topological order
    assert result.plan[0].task_queue == "agent-local"  # run_on: agent (default agent)
    assert result.plan[1].task_queue == "server"


def test_simulate_warns_about_missing_secret(session, tenant):
    result = sim.simulate(session, tenant.id, WF, "yaml")
    assert any("pg_main" in w for w in result.warnings)


def test_simulate_no_warning_when_secret_defined(session, tenant):
    secrets_svc.put_secret(session, "mk", tenant.id, "pg_main", "dsn")
    result = sim.simulate(session, tenant.id, WF, "yaml")
    assert result.warnings == []


def test_simulate_invalid_workflow_reports_errors(session, tenant):
    bad = WF.replace("needs: [a]", "needs: [ghost]")
    result = sim.simulate(session, tenant.id, bad, "yaml")
    assert not result.valid
    assert any(e.code == "unknown_dependency" for e in result.errors)
    assert result.plan == []
