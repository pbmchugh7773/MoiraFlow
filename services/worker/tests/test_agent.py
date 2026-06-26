from moiraflow_worker.interpreter import JobRequest
from moiraflow_worker.workflow import _agent_task_queue


def test_default_agent_queue_is_local():
    req = JobRequest(job_id="j", type="command", inputs={}, run_on="agent")
    assert _agent_task_queue(req) == "agent-local"


def test_agent_selector_overrides_queue():
    req = JobRequest(
        job_id="j",
        type="command",
        inputs={},
        run_on="agent",
        agent_selector={"agent_id": "eu-prod-1"},
    )
    assert _agent_task_queue(req) == "agent-eu-prod-1"
