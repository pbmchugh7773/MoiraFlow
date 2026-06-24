import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowops_api.db import models
from flowops_api.db.base import Base


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _tenant(session, slug="default"):
    t = models.Tenant(name="Default", slug=slug, status="active")
    session.add(t)
    session.flush()
    return t


def test_full_schema_creates_on_sqlite():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    tables = set(Base.metadata.tables)
    # spot-check the immutable/audit tables and the agent envelope-encryption column
    assert {
        "tenants",
        "workflows",
        "workflow_versions",
        "executions",
        "job_executions",
        "execution_events",
        "agents",
        "audit_log",
    } <= tables
    assert "public_key" in models.Agent.__table__.columns


def test_workflow_version_chain_persists(session):
    t = _tenant(session)
    wf = models.Workflow(tenant_id=t.id, name="daily_import", trigger_type="manual")
    session.add(wf)
    session.flush()
    version = models.WorkflowVersion(
        tenant_id=t.id,
        workflow_id=wf.id,
        version=1,
        definition={"apiVersion": "flowops/v1"},
        definition_hash="a" * 64,
        source_format="yaml",
    )
    session.add(version)
    session.commit()

    got = session.scalar(
        select(models.WorkflowVersion).where(models.WorkflowVersion.workflow_id == wf.id)
    )
    assert got is not None
    assert got.definition == {"apiVersion": "flowops/v1"}
    assert got.version == 1


def test_workflow_name_unique_per_tenant(session):
    t = _tenant(session)
    session.add(models.Workflow(tenant_id=t.id, name="dup", trigger_type="manual"))
    session.commit()
    session.add(models.Workflow(tenant_id=t.id, name="dup", trigger_type="manual"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_workflow_version_unique_per_workflow(session):
    t = _tenant(session)
    wf = models.Workflow(tenant_id=t.id, name="wf", trigger_type="manual")
    session.add(wf)
    session.flush()
    common = dict(
        tenant_id=t.id, workflow_id=wf.id, version=1, definition={}, definition_hash="x" * 64
    )
    session.add(models.WorkflowVersion(**common))
    session.commit()
    session.add(models.WorkflowVersion(**common))
    with pytest.raises(IntegrityError):
        session.commit()


def test_execution_temporal_id_unique(session):
    t = _tenant(session)
    wf = models.Workflow(tenant_id=t.id, name="wf", trigger_type="manual")
    session.add(wf)
    session.flush()
    ver = models.WorkflowVersion(
        tenant_id=t.id, workflow_id=wf.id, version=1, definition={}, definition_hash="x" * 64
    )
    session.add(ver)
    session.flush()
    common = dict(
        tenant_id=t.id,
        workflow_id=wf.id,
        workflow_version_id=ver.id,
        temporal_workflow_id="wf-123",
    )
    session.add(models.Execution(**common))
    session.commit()
    # idempotency relies on this uniqueness (ADR-0014)
    session.add(models.Execution(**common))
    with pytest.raises(IntegrityError):
        session.commit()
