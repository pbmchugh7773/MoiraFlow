"""Worker construction — shared by the real entrypoint and the integration tests."""

from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import SERVER_ACTIVITIES
from .workflow import FlowInterpreter

SERVER_TASK_QUEUE = "moiraflow-server"


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
