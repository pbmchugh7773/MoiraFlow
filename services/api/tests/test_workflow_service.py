import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.services import workflows as svc


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


WF = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: daily_import, description: "import job" }
spec:
  trigger: { type: cron, cron: "0 6 * * *", timezone: "Europe/Madrid" }
  jobs:
    - id: fetch
      type: command
      with: { command: "echo hi" }
"""


def test_create_workflow_creates_v1_and_sets_active(session, tenant):
    wf = svc.create_workflow(session, tenant.id, WF, "yaml")
    assert wf.name == "daily_import"
    assert wf.description == "import job"
    assert wf.trigger_type == "cron"
    assert wf.trigger_config == {"cron": "0 6 * * *", "timezone": "Europe/Madrid"}
    assert wf.active_version_id is not None

    version = session.scalar(
        select(models.WorkflowVersion).where(models.WorkflowVersion.id == wf.active_version_id)
    )
    assert version.version == 1
    assert len(version.definition_hash) == 64


def test_create_invalid_workflow_raises_validation_error(session, tenant):
    bad = WF.replace("needs", "x").replace("echo hi", "{{ context.missing }}")
    with pytest.raises(svc.WorkflowValidationError) as exc:
        svc.create_workflow(session, tenant.id, bad, "yaml")
    assert any(e.code == "unknown_context_ref" for e in exc.value.errors)


def test_duplicate_name_raises(session, tenant):
    svc.create_workflow(session, tenant.id, WF, "yaml")
    with pytest.raises(svc.WorkflowExistsError):
        svc.create_workflow(session, tenant.id, WF, "yaml")


def test_add_version_increments_and_is_immutable(session, tenant):
    wf = svc.create_workflow(session, tenant.id, WF, "yaml")
    v2 = svc.add_version(session, wf.id, WF.replace("echo hi", "echo bye"), "yaml")
    assert v2.version == 2
    count = session.scalar(
        select(func.count())
        .select_from(models.WorkflowVersion)
        .where(models.WorkflowVersion.workflow_id == wf.id)
    )
    assert count == 2
    # active version unchanged until explicit activate
    assert wf.active_version_id != v2.id


def test_add_version_name_mismatch_raises(session, tenant):
    wf = svc.create_workflow(session, tenant.id, WF, "yaml")
    with pytest.raises(svc.NameMismatchError):
        svc.add_version(session, wf.id, WF.replace("daily_import", "other_name"), "yaml")


def test_activate_version_switches_pointer(session, tenant):
    wf = svc.create_workflow(session, tenant.id, WF, "yaml")
    v2 = svc.add_version(session, wf.id, WF.replace("echo hi", "echo bye"), "yaml")
    svc.activate_version(session, wf.id, 2)
    assert wf.active_version_id == v2.id


def test_activate_unknown_version_raises(session, tenant):
    wf = svc.create_workflow(session, tenant.id, WF, "yaml")
    with pytest.raises(svc.VersionNotFoundError):
        svc.activate_version(session, wf.id, 99)


def test_get_unknown_workflow_raises(session):
    with pytest.raises(svc.WorkflowNotFoundError):
        svc.get_workflow(session, uuid.uuid4())


def test_list_workflows_scoped_to_tenant(session, tenant):
    svc.create_workflow(session, tenant.id, WF, "yaml")
    other = models.Tenant(name="Other", slug="other")
    session.add(other)
    session.flush()
    assert len(svc.list_workflows(session, tenant.id)) == 1
    assert svc.list_workflows(session, other.id) == []
