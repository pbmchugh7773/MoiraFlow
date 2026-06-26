"""Worker construction — shared by the real entrypoint and the integration tests."""

from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import SERVER_ACTIVITIES, run_command_job
from .workflow import FlowInterpreter

SERVER_TASK_QUEUE = "moiraflow-server"
AGENT_TASK_QUEUE = "agent-local"


def build_worker(
    client: Client,
    task_queue: str = SERVER_TASK_QUEUE,
    *,
    activity_executor: object | None = None,
) -> Worker:
    """Build a worker registering the interpreter workflow + server activities.

    `activity_executor` must be a ThreadPoolExecutor when the registered
    activities are synchronous (our `command` activity is); Temporal runs sync
    activities on it.
    """
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[FlowInterpreter],
        activities=SERVER_ACTIVITIES,
        activity_executor=activity_executor,  # type: ignore[arg-type]
    )


def build_agent_worker(
    client: Client,
    task_queue: str = AGENT_TASK_QUEUE,
    *,
    activity_executor: object | None = None,
) -> Worker:
    """An agent worker: activities-only, runs ONLY `command` jobs on its dedicated
    queue (ADR-0017). The interpreter workflow runs on the server worker; jobs with
    `run_on: agent` are routed here. The agent never holds DB/secret access."""
    return Worker(
        client,
        task_queue=task_queue,
        activities=[run_command_job],
        activity_executor=activity_executor,  # type: ignore[arg-type]
    )
