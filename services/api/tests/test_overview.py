import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.services.overview import get_overview


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _exec(tenant, wf, ver, status, key):
    return models.Execution(
        tenant_id=tenant.id,
        workflow_id=wf.id,
        workflow_version_id=ver.id,
        temporal_workflow_id=key,
        status=status,
    )


def test_overview_aggregates_health_schedules_and_failures(session):
    tenant = models.Tenant(name="T", slug="default")
    session.add(tenant)
    session.flush()

    cron_wf = models.Workflow(
        tenant_id=tenant.id,
        name="nightly",
        trigger_type="cron",
        trigger_config={"cron": "0 6 * * *", "timezone": "Europe/Madrid"},
        is_enabled=True,
    )
    manual_wf = models.Workflow(tenant_id=tenant.id, name="adhoc", trigger_type="manual")
    session.add_all([cron_wf, manual_wf])
    session.flush()
    ver = models.WorkflowVersion(
        tenant_id=tenant.id,
        workflow_id=cron_wf.id,
        version=1,
        definition={},
        definition_hash="x" * 64,
    )
    session.add(ver)
    session.flush()

    session.add_all(
        [
            _exec(tenant, cron_wf, ver, "success", "k1"),
            _exec(tenant, cron_wf, ver, "success", "k2"),
            _exec(tenant, cron_wf, ver, "failed", "k3"),
            _exec(tenant, cron_wf, ver, "running", "k4"),
        ]
    )
    session.flush()

    ov = get_overview(session, tenant.id)

    assert ov["workflows"] == 2
    assert ov["executions"]["total"] == 4
    assert ov["executions"]["by_status"] == {"success": 2, "failed": 1, "running": 1}
    assert ov["executions"]["success_rate"] == round(2 / 3, 3)  # success / (success+failed)
    assert len(ov["schedules"]) == 1
    assert ov["schedules"][0] == {
        "id": str(cron_wf.id),
        "name": "nightly",
        "cron": "0 6 * * *",
        "timezone": "Europe/Madrid",
        "enabled": True,
    }
    assert len(ov["recent_failures"]) == 1
    assert ov["recent_failures"][0]["workflow_name"] == "nightly"
