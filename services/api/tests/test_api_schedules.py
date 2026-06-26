import pytest
from fastapi.testclient import TestClient

from moiraflow_api.deps import get_current_user, get_schedule_manager, get_session
from moiraflow_api.main import app
from tests._helpers import make_sqlite_factory, seed_user, session_override

WF_CRON = """
apiVersion: moiraflow/v1
kind: Workflow
metadata: { name: nightly }
spec:
  trigger: { type: cron, cron: "0 3 * * *", timezone: "Europe/Madrid" }
  jobs:
    - id: run
      type: command
      with: { command: "echo nightly" }
"""

WF_MANUAL = WF_CRON.replace(
    'trigger: { type: cron, cron: "0 3 * * *", timezone: "Europe/Madrid" }',
    "trigger: { type: manual }",
).replace("nightly", "manualwf")


class FakeSched:
    def __init__(self):
        self.upserts = []
        self.pauses = []

    def upsert(self, *, schedule_id, cron, timezone, definition, input_context, task_queue):
        self.upserts.append({"schedule_id": schedule_id, "cron": cron, "timezone": timezone})

    def pause(self, schedule_id):
        self.pauses.append(schedule_id)

    def delete(self, schedule_id):
        pass


@pytest.fixture
def sched():
    return FakeSched()


@pytest.fixture
def client(sched):
    factory = make_sqlite_factory()
    admin = seed_user(factory, role="admin")
    app.dependency_overrides[get_session] = session_override(factory)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_schedule_manager] = lambda: sched
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_creating_cron_workflow_upserts_schedule(client, sched):
    client.post("/api/v1/workflows", json={"content": WF_CRON})
    assert len(sched.upserts) == 1
    assert sched.upserts[0]["cron"] == "0 3 * * *"
    assert sched.upserts[0]["timezone"] == "Europe/Madrid"


def test_manual_workflow_does_not_touch_schedules(client, sched):
    client.post("/api/v1/workflows", json={"content": WF_MANUAL})
    assert sched.upserts == [] and sched.pauses == []


def test_disable_pauses_and_enable_reupserts(client, sched):
    wid = client.post("/api/v1/workflows", json={"content": WF_CRON}).json()["id"]
    client.post(f"/api/v1/workflows/{wid}/disable")
    assert len(sched.pauses) == 1
    client.post(f"/api/v1/workflows/{wid}/enable")
    assert len(sched.upserts) == 2  # initial create + re-enable
